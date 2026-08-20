# -*- coding: utf-8 -*-
"""
compute_features.py — Features quantitatives + prédiction ponctuelle DÉTERMINISTE.  (v2)

Usage :
  python compute_features.py [--data-dir data] [--out predictions/quant_YYYY-MM-DD.json]
                             [--news predictions/news_YYYY-MM-DD.json] [--groupe core|sectoriel|tous]

NOUVEAUTÉS v2 (2026-08-11)
  1. Univers lu depuis config/universe.json (7 ETF « core » + 5 ETF sectoriels de suivi).
  2. Nouvelle feature ret_252d = variation sur 1 an glissant (252 séances), affichée
     à côté du YTD. Calculée exactement depuis les cours, comme tout le reste.
  3. Poids du modèle lus depuis config/weights.json (plus de constantes en dur) :
     ils peuvent être ajustés par scripts/calibrate_weights.py dans des bornes strictes.
  4. Échelle news élargie de {-2..+2} à {-5..+5}, avec k divisés par 2,5 pour que le
     plafond d'influence des news reste identique à la v1.

RENDEMENTS EXACTS (calculés depuis les cours, jamais estimés) :
  ret_1d   = close_t / close_{t-1} - 1
  ret_5d, ret_20d, ret_60d, ret_120d             (idem, en séances)
  ret_252d = close_t / close_{t-252} - 1         ← variation 1 an glissant (NOUVEAU)
  ytd      = close_t / dernier close de l'année précédente - 1

FEATURES :
  ma5..ma200, px_vs_maX, trend_20d (pente régression log 20 s.), z20 (z-score vs ma20),
  rsi14 (Wilder), vol20_d et vol20_ann, dist_52wk_high, vol_ratio (vol 5 s. / vol 60 s.)

MODÈLE DE PRÉDICTION (déterministe — même entrée => même sortie) :
  mom   = W_MOM20*(ret_20d/20) + W_MOM60*(ret_60d/60)
  mr    = W_MR  * z20 * vol20_d
  rsi_a = W_RSI * ((rsi14 - 50)/50) * vol20_d
  pred_1d  = clip(mom + mr + rsi_a,              ± CLIP_1D*vol20_d)
  pred_5d  = clip(5*mom + sqrt(5)*(mr + rsi_a),  ± CLIP_5D*vol20_d*sqrt(5))
  pred_eoy = clip(h*(W_EOY_MOM*mom + W_EOY_BASE*BASE) + sqrt(h)*W_EOY_MR*(mr + rsi_a),
                  ± CLIP_EOY*vol20_d*sqrt(h))
    h = séances restantes jusqu'au 31/12 ; BASE = 0.07/252 (prior actions ~7 %/an)

COUCHE NEWS (appliquée en aval, seule part de jugement du système) :
  pred_finale_h = pred_quant_h + news_score * k_h
  news_score entier dans [-5, +5] ; k_1d=0.04, k_5d=0.10, k_eoy=0.30 (points de %)
  => plafond d'influence : ±0.20 pt (J+1), ±0.50 pt (J+5), ±1.50 pt (fin d'année).
  Grille d'attribution des scores : voir config/news_scale.md
"""
import json
import math
import argparse
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BASE_DAILY = 0.07 / 252  # prior long terme actions


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def load_universe(groupe="tous"):
    with open(BASE_DIR / "config" / "universe.json", encoding="utf-8") as f:
        u = json.load(f)
    inst = u["instruments"]
    if groupe != "tous":
        inst = [i for i in inst if i["groupe"] == groupe]
    return inst


def load_weights():
    with open(BASE_DIR / "config" / "weights.json", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# I/O prix
# --------------------------------------------------------------------------- #
def load(path):
    dates, closes, vols = [], [], []
    with open(path, encoding="utf-8") as f:
        f.readline()
        for line in f:
            line = line.strip()
            if not line:
                continue
            d, c, v = line.split(";")
            dates.append(d)
            closes.append(float(c))
            vols.append(float(v))
    return dates, closes, vols


# --------------------------------------------------------------------------- #
# Primitives statistiques
# --------------------------------------------------------------------------- #
def sma(x, n):
    return sum(x[-n:]) / n if len(x) >= n else None


def std(x):
    if len(x) < 2:
        return None
    m = sum(x) / len(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def rsi_wilder(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for a, b in zip(closes, closes[1:]):
        ch = b - a
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def lin_slope_log(closes, n=20):
    if len(closes) < n:
        return None
    y = [math.log(c) for c in closes[-n:]]
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(y) / n
    num = sum((x - mx) * (yy - my) for x, yy in zip(xs, y))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den


def trading_days_to_eoy(today: date) -> int:
    d, n = today, 0
    end = date(today.year, 12, 31)
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return max(n, 1)


def ret(closes, k):
    return closes[-1] / closes[-1 - k] - 1 if len(closes) > k else None


def clip(x, lim):
    return max(-lim, min(lim, x))


# --------------------------------------------------------------------------- #
# Cœur du modèle — utilisable aussi par calibrate_weights.py (walk-forward)
# --------------------------------------------------------------------------- #
def predict_from_signals(r20, r60, z20, vol20_d, rsi, h, W):
    """Retourne (pred_1d, pred_5d, pred_eoy) en fraction (pas en %).
    Fonction pure : c'est elle qui définit le modèle. Le backtest de calibration
    appelle EXACTEMENT cette fonction, donc calibration et production ne peuvent
    pas diverger."""
    if None in (r20, r60, z20, vol20_d, rsi):
        return None, None, None
    mom = W["W_MOM20"] * (r20 / 20) + W["W_MOM60"] * (r60 / 60)
    mr = W["W_MR"] * z20 * vol20_d
    rsi_a = W["W_RSI"] * ((rsi - 50) / 50) * vol20_d
    p1 = clip(mom + mr + rsi_a, W["CLIP_1D"] * vol20_d)
    p5 = clip(5 * mom + math.sqrt(5) * (mr + rsi_a),
              W["CLIP_5D"] * vol20_d * math.sqrt(5))
    peoy = clip(h * (W["W_EOY_MOM"] * mom + W["W_EOY_BASE"] * BASE_DAILY)
                + math.sqrt(h) * W["W_EOY_MR"] * (mr + rsi_a),
                W["CLIP_EOY"] * vol20_d * math.sqrt(h))
    return p1, p5, peoy


def core_signals(closes):
    """Signaux minimaux nécessaires à la prédiction, calculés sur la fenêtre fournie.
    Utilisé en production ET en backtest walk-forward (closes tronqué à la date t)."""
    if len(closes) < 61:
        return None
    c = closes[-1]
    rets_d = [b / a - 1 for a, b in zip(closes, closes[1:])]
    vol20_d = std(rets_d[-20:])
    m20 = sma(closes, 20)
    s20 = std(closes[-20:])
    if m20 is None or s20 is None or vol20_d is None:
        return None
    z20 = (c - m20) / s20 if s20 > 0 else 0.0
    return {
        "r20": ret(closes, 20),
        "r60": ret(closes, 60),
        "z20": z20,
        "vol20_d": vol20_d,
        "rsi": rsi_wilder(closes, 14),
    }


# --------------------------------------------------------------------------- #
# Analyse complète (production)
# --------------------------------------------------------------------------- #
def analyze(dates, closes, vols, W):
    last_date = date.fromisoformat(dates[-1])
    c = closes[-1]

    prev_year = last_date.year - 1
    prev_year_closes = [cl for d, cl in zip(dates, closes) if d[:4] == str(prev_year)]
    ytd = (c / prev_year_closes[-1] - 1) if prev_year_closes else None

    rets_d = [b / a - 1 for a, b in zip(closes, closes[1:])]
    vol20_d = std(rets_d[-20:]) if len(rets_d) >= 20 else None
    m20 = sma(closes, 20)
    z20 = None
    if m20 and len(closes) >= 20:
        s20 = std(closes[-20:])
        z20 = (c - m20) / s20 if s20 and s20 > 0 else 0.0

    feats = {
        "date": dates[-1],
        "close": c,
        "n_seances": len(closes),
        "ret_1d": ret(closes, 1),
        "ret_5d": ret(closes, 5),
        "ret_20d": ret(closes, 20),
        "ret_60d": ret(closes, 60),
        "ret_120d": ret(closes, 120),
        "ret_252d": ret(closes, 252),          # ← NOUVEAU : variation 1 an glissant
        "ytd": ytd,
        "ma5": sma(closes, 5), "ma10": sma(closes, 10), "ma20": m20,
        "ma50": sma(closes, 50), "ma100": sma(closes, 100), "ma200": sma(closes, 200),
        "trend_20d": lin_slope_log(closes, 20),
        "z20": z20,
        "rsi14": rsi_wilder(closes, 14),
        "vol20_d": vol20_d,
        "vol20_ann": vol20_d * math.sqrt(252) if vol20_d else None,
        "dist_52wk_high": c / max(closes[-252:]) - 1 if len(closes) >= 2 else None,
        "vol_ratio": (sum(vols[-5:]) / 5) / (sum(vols[-60:]) / 60) if len(vols) >= 60 else None,
    }
    for n in (5, 10, 20, 50, 100, 200):
        ma = feats[f"ma{n}"]
        feats[f"px_vs_ma{n}"] = (c / ma - 1) if ma else None

    preds = {}
    sig = core_signals(closes)
    if sig:
        h = trading_days_to_eoy(last_date)
        p1, p5, peoy = predict_from_signals(sig["r20"], sig["r60"], sig["z20"],
                                            sig["vol20_d"], sig["rsi"], h, W)
        if p1 is not None:
            preds = {
                "pred_1d_pct": round(100 * p1, 3),
                "pred_5d_pct": round(100 * p5, 3),
                "pred_eoy_pct": round(100 * peoy, 2),
                "h_seances_eoy": h,
            }
    feats["pred"] = preds
    return feats


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(BASE_DIR / "data"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--news", default=None,
                    help="JSON {ticker: {score:int, justif:str}} — scores news dans [-5,+5]")
    ap.add_argument("--groupe", default="tous", choices=["core", "sectoriel", "tous"])
    args = ap.parse_args()
    data_dir = Path(args.data_dir)

    cfg = load_weights()
    W = cfg["poids"]
    NW = cfg["news"]
    universe = load_universe(args.groupe)

    news = {}
    if args.news and Path(args.news).exists():
        with open(args.news, encoding="utf-8") as f:
            news = json.load(f)

    results = {}
    for inst in universe:
        t = inst["ticker"]
        p = data_dir / f"{t}.csv"
        if not p.exists():
            print(f"{t}: fichier manquant ({p})")
            continue
        dates, closes, vols = load(p)
        r = analyze(dates, closes, vols, W)
        r["groupe"] = inst["groupe"]
        r["nom"] = inst["nom"]

        # ---- couche news -----------------------------------------------------
        entry = news.get(t)
        if entry is not None and r["pred"]:
            s = entry["score"] if isinstance(entry, dict) else int(entry)
            lo, hi = NW["echelle_min"], NW["echelle_max"]
            if not (lo <= s <= hi) or int(s) != s:
                raise SystemExit(f"{t}: news_score={s} invalide (entier attendu dans [{lo},{hi}])")
            r["news_score"] = int(s)
            r["news_justif"] = entry.get("justif", "") if isinstance(entry, dict) else ""
            r["pred"]["final_1d_pct"] = round(r["pred"]["pred_1d_pct"] + s * NW["k_1d"], 3)
            r["pred"]["final_5d_pct"] = round(r["pred"]["pred_5d_pct"] + s * NW["k_5d"], 3)
            r["pred"]["final_eoy_pct"] = round(r["pred"]["pred_eoy_pct"] + s * NW["k_eoy"], 2)
        results[t] = r

    if not results:
        raise SystemExit("Aucun ticker traité.")

    run_date = max(r["date"] for r in results.values())
    out_path = Path(args.out) if args.out else BASE_DIR / "predictions" / f"quant_{run_date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_date": run_date,
            "model": cfg["version"],
            "poids": W,
            "news_coeffs": NW,
            "tickers": results,
        }, f, ensure_ascii=False, indent=1)

    def pc(x, nd=2):
        return f"{100*x:+.{nd}f}%" if x is not None else "n/a"

    for grp, label in (("core", "SOCLE — investissable (hors scope PAD)"),
                       ("sectoriel", "SECTORIEL — SUIVI SEUL (en scope PAD, non investissable par Michael)")):
        rows = [(t, r) for t, r in results.items() if r["groupe"] == grp]
        if not rows:
            continue
        print(f"\n=== {label} — {run_date} (modèle {cfg['version']}) ===")
        print(f"{'TICKER':7}{'CLOSE':>10}{'1J':>8}{'5J':>8}{'YTD':>9}{'1AN':>9}{'RSI14':>7}"
              f"{'Z20':>6}{'VOL.ANN':>8} | {'P_1J':>7}{'P_5J':>7}{'P_EOY':>8}")
        for t, r in rows:
            pr = r["pred"]
            an = pc(r["ret_252d"]) if r["ret_252d"] is not None else "n/a"
            print(f"{t:7}{r['close']:>10.3f}{pc(r['ret_1d']):>8}{pc(r['ret_5d']):>8}"
                  f"{pc(r['ytd']):>9}{an:>9}{r['rsi14']:>7.1f}{r['z20']:>6.2f}"
                  f"{pc(r['vol20_ann'],0):>8} | "
                  f"{pr.get('pred_1d_pct',0):>+6.2f}%{pr.get('pred_5d_pct',0):>+6.2f}%"
                  f"{pr.get('pred_eoy_pct',0):>+7.2f}%")

    print(f"\nJSON: {out_path}")


if __name__ == "__main__":
    main()
