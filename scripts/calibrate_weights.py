# -*- coding: utf-8 -*-
"""
calibrate_weights.py — Auto-calibration bornée des poids du modèle quant.  (v2, 2026-08-11)

Usage :
  python calibrate_weights.py [--data-dir data] [--dry-run] [--force]

PRINCIPE
--------
Le modèle quant est déterministe : à une date t, la prédiction ne dépend que des cours
jusqu'à t. On peut donc le REJOUER sur tout l'historique de prix (walk-forward strict,
aucun look-ahead) et obtenir plusieurs milliers d'observations prédiction/réalisé, au
lieu des seules quelques séances de prédictions live. C'est ce qui rend la calibration
statistiquement défendable : optimiser sur 5 jours de live reviendrait à apprendre du bruit.

Le backtest appelle compute_features.core_signals() et compute_features.predict_from_signals(),
c'est-à-dire EXACTEMENT le code de production : calibration et production ne peuvent pas diverger.

GARDE-FOUS (config/weights.json → "calibration", choix « prudent et borné » du 2026-08-11)
------------------------------------------------------------------------------------------
  1. min_seances_evaluees_par_ticker : un ticker avec moins de 20 séances évaluables est
     exclu de l'objectif (il ne pèse pas sur la calibration tant qu'il n'a pas d'historique).
     Si AUCUN ticker n'atteint le seuil, aucune modification n'est écrite.
  2. pas_max_relatif_par_run = 5 % : chaque poids ne peut bouger que de ±5 % par exécution.
  3. borne_relative_vs_ancrage = 30 % : bornes dures calculées vs les valeurs v1 FIGÉES
     (ancrage_v1), jamais vs les valeurs courantes — sinon 30 pas de +5 % quadrupleraient
     un poids par dérive cumulative.
  4. Validation walk-forward : le candidat est optimisé sur les 70 % les plus anciens
     (train) et n'est ACCEPTÉ que s'il améliore aussi les 30 % les plus récents (test).
     Un gain purement in-sample est rejeté.
  5. Rollback : si le hit ratio LIVE (fichiers predictions/quant_*.json confrontés aux
     cours réalisés) s'est dégradé de plus de 5 points sur les 10 dernières séances
     depuis le dernier changement de poids, on restaure le jeu de poids précédent
     au lieu d'en proposer un nouveau.
  6. Poids gelés : W_EOY_BASE (prior 7 %/an, hypothèse économique et non paramètre
     statistique) et les CLIP_* (garde-fous de sécurité, pas des paramètres de prévision).

OBJECTIF OPTIMISÉ
-----------------
  obj = 0.6 * hit_ratio(J+1) + 0.4 * hit_ratio(J+5) - 0.10 * (MAE_relatif)
  où MAE_relatif = MAE(J+1) du candidat / MAE(J+1) des poids courants.
  La direction prime (c'est ce qui pilote les décisions), l'amplitude n'intervient
  qu'en départage.

SORTIES
-------
  config/weights.json          (mis à jour si un candidat est accepté)
  config/weights_history.json  (journal versionné, permet le rollback)
  config/calibration_log.json  (dernier run : métriques, deltas, décision, résumé FR
                                prêt à être collé dans le rapport quotidien)
"""
import json
import argparse
import statistics
from datetime import date
from pathlib import Path

import compute_features as CF

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

W_HIT1, W_HIT5, LAMBDA_MAE = 0.6, 0.4, 0.10
TRAIN_FRACTION = 0.70
MIN_WARMUP = 61          # séances nécessaires avant la 1re prédiction (ret_60d)


# --------------------------------------------------------------------------- #
# Panel de signaux (indépendant des poids → calculé une seule fois)
# --------------------------------------------------------------------------- #
def build_panel(data_dir: Path, universe):
    """Rejoue l'historique en walk-forward et retourne, par ticker, la liste des
    observations {date, signaux, réalisé J+1, réalisé J+5}.
    À l'indice t on n'utilise QUE closes[:t+1] — aucun look-ahead possible."""
    panel = {}
    for inst in universe:
        t = inst["ticker"]
        p = data_dir / f"{t}.csv"
        if not p.exists():
            continue
        dates, closes, _ = CF.load(p)
        obs = []
        for i in range(MIN_WARMUP, len(closes) - 1):
            sig = CF.core_signals(closes[:i + 1])
            if not sig or sig["rsi"] is None:
                continue
            real_1d = closes[i + 1] / closes[i] - 1
            real_5d = (closes[i + 5] / closes[i] - 1) if i + 5 < len(closes) else None
            obs.append({"date": dates[i], "sig": sig, "r1": real_1d, "r5": real_5d})
        if obs:
            panel[t] = obs
    return panel


def score_panel(panel, W, min_obs, mae_baseline=None):
    """Évalue un jeu de poids sur un panel. Retourne (objectif, métriques détaillées)."""
    hits1 = hits5 = n1 = n5 = 0
    abs_err1, per_ticker = [], {}
    for t, obs in panel.items():
        if len(obs) < min_obs:
            continue
        th1 = tn1 = th5 = tn5 = 0
        for o in obs:
            s = o["sig"]
            # h fixé à 100 : n'intervient que dans pred_eoy, non évaluée ici.
            p1, p5, _ = CF.predict_from_signals(s["r20"], s["r60"], s["z20"],
                                                s["vol20_d"], s["rsi"], 100, W)
            if p1 is None:
                continue
            n1 += 1; tn1 += 1
            abs_err1.append(abs(p1 - o["r1"]))
            if (p1 >= 0) == (o["r1"] >= 0):
                hits1 += 1; th1 += 1
            if o["r5"] is not None:
                n5 += 1; tn5 += 1
                if (p5 >= 0) == (o["r5"] >= 0):
                    hits5 += 1; th5 += 1
        if tn1:
            per_ticker[t] = {"n": tn1, "hit_1d": round(th1 / tn1, 4),
                             "hit_5d": round(th5 / tn5, 4) if tn5 else None}
    if not n1:
        return None, {}
    hit1, hit5 = hits1 / n1, (hits5 / n5 if n5 else 0.0)
    mae1 = statistics.fmean(abs_err1)
    penalty = LAMBDA_MAE * (mae1 / mae_baseline) if mae_baseline else 0.0
    obj = W_HIT1 * hit1 + W_HIT5 * hit5 - penalty
    return obj, {"hit_1d": round(hit1, 4), "hit_5d": round(hit5, 4),
                 "mae_1d": mae1, "n_obs_1d": n1, "n_obs_5d": n5,
                 "par_ticker": per_ticker}


def split_panel(panel, frac):
    train, test = {}, {}
    for t, obs in panel.items():
        k = int(len(obs) * frac)
        train[t], test[t] = obs[:k], obs[k:]
    return train, test


# --------------------------------------------------------------------------- #
# Génération des candidats (grille bornée)
# --------------------------------------------------------------------------- #
def candidate_values(name, current, anchor, step, bound):
    lo = anchor - abs(anchor) * bound
    hi = anchor + abs(anchor) * bound
    if lo > hi:
        lo, hi = hi, lo
    vals = []
    for mult in (1 - step, 1.0, 1 + step):
        v = current * mult
        v = max(lo, min(hi, v))
        vals.append(round(v, 6))
    return sorted(set(vals))


def coordinate_descent(panel_train, W0, cal, min_obs, mae_baseline, max_passes=3):
    """Descente par coordonnées : bien plus rapide qu'une grille complète (3^6=729),
    et suffisante ici car chaque poids ne peut bouger que d'un cran de ±5 %."""
    W = dict(W0)
    best_obj, _ = score_panel(panel_train, W, min_obs, mae_baseline)
    improved = True
    passes = 0
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for name in cal["poids_calibrables"]:
            for v in candidate_values(name, W0[name], cal["_anchor"][name],
                                      cal["pas_max_relatif_par_run"],
                                      cal["borne_relative_vs_ancrage"]):
                if v == W[name]:
                    continue
                trial = dict(W); trial[name] = v
                obj, _ = score_panel(panel_train, trial, min_obs, mae_baseline)
                if obj is not None and obj > best_obj + 1e-9:
                    best_obj, W, improved = obj, trial, True
    return W, best_obj


# --------------------------------------------------------------------------- #
# Suivi live (pour le rollback)
# --------------------------------------------------------------------------- #
def live_hit_ratio(data_dir: Path, n_last=10):
    """Hit ratio directionnel J+1 des prédictions réellement publiées
    (predictions/quant_*.json) confrontées aux cours réalisés."""
    pred_dir = BASE_DIR / "predictions"
    files = sorted(pred_dir.glob("quant_*.json"))[-n_last:]
    closes_cache = {}
    hits = tot = 0
    detail = []
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        for t, r in data.get("tickers", {}).items():
            p1 = r.get("pred", {}).get("pred_1d_pct")
            if p1 is None:
                continue
            if t not in closes_cache:
                cp = data_dir / f"{t}.csv"
                if not cp.exists():
                    continue
                d, c, _ = CF.load(cp)
                closes_cache[t] = dict(zip(d, c)), d
            m, order = closes_cache[t]
            if r["date"] not in order:
                continue
            i = order.index(r["date"])
            if i + 1 >= len(order):
                continue
            real = m[order[i + 1]] / m[order[i]] - 1
            tot += 1
            ok = (p1 >= 0) == (real >= 0)
            hits += ok
            detail.append({"date": r["date"], "ticker": t, "pred_pct": p1,
                           "real_pct": round(100 * real, 3), "ok": ok})
    return (hits / tot if tot else None), tot, detail


# --------------------------------------------------------------------------- #
def fr(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(BASE_DIR / "data"))
    ap.add_argument("--dry-run", action="store_true", help="calcule et journalise sans écrire weights.json")
    ap.add_argument("--force", action="store_true", help="ignore le gate min_seances")
    args = ap.parse_args()
    data_dir = Path(args.data_dir)

    cfg = CF.load_weights()
    cal = dict(cfg["calibration"])
    cal["_anchor"] = cfg["ancrage_v1"]
    W0 = cfg["poids"]
    min_obs = 0 if args.force else cal["min_seances_evaluees_par_ticker"]

    if not cal.get("actif", True):
        print("Calibration désactivée (config/weights.json → calibration.actif = false).")
        return

    universe = CF.load_universe("tous")
    panel = build_panel(data_dir, universe)
    eligibles = [t for t, o in panel.items() if len(o) >= min_obs]
    exclus = {t: len(o) for t, o in panel.items() if len(o) < min_obs}

    log = {
        "run_date": date.today().isoformat(),
        "version_avant": cfg["version"],
        "tickers_eligibles": eligibles,
        "tickers_exclus_faute_historique": exclus,
        "garde_fous": {k: v for k, v in cal.items() if not k.startswith("_")},
    }

    if not eligibles:
        log["decision"] = "AUCUNE_MODIFICATION"
        log["motif"] = (f"Aucun ticker n'atteint {min_obs} séances évaluables. "
                        "Calibration gelée — le modèle tourne avec les poids courants.")
        log["resume_rapport"] = ("Auto-calibration : aucune modification. Historique insuffisant "
                                 f"(seuil de {min_obs} séances évaluables par ticker non atteint).")
        write_log(log)
        print(log["motif"])
        return

    # --- rollback ? ----------------------------------------------------------
    hist_path = CONFIG_DIR / "weights_history.json"
    history = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else []
    live_hit, live_n, _ = live_hit_ratio(data_dir, cal["rollback_fenetre_seances"])
    log["live"] = {"hit_ratio_1d": live_hit, "n_observations": live_n}

    if history and live_hit is not None and len(history) >= 2:
        ref = history[-1].get("live_hit_ratio_au_moment_du_changement")
        if ref is not None and live_hit < ref - cal["rollback_seuil_degradation_hit"]:
            prev = history[-2]["poids"]
            cfg["poids"] = prev
            cfg["date_maj"] = date.today().isoformat()
            cfg["origine"] = f"ROLLBACK vers {history[-2]['version']} (dégradation du hit ratio live)."
            (CONFIG_DIR / "weights.json").write_text(
                json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
            log["decision"] = "ROLLBACK"
            log["resume_rapport"] = (
                f"Auto-calibration : ROLLBACK. Le hit ratio live est tombé à {fr(100*live_hit)} % "
                f"contre {fr(100*ref)} % au moment du dernier changement de poids "
                f"(seuil de tolérance : {fr(100*cal['rollback_seuil_degradation_hit'])} pt). "
                f"Les poids de la version {history[-2]['version']} ont été restaurés.")
            write_log(log)
            print(log["resume_rapport"])
            return

    # --- optimisation --------------------------------------------------------
    train, test = split_panel(panel, TRAIN_FRACTION)
    _, base_all = score_panel(panel, W0, min_obs)
    mae_base = base_all["mae_1d"]

    obj_tr_0, m_tr_0 = score_panel(train, W0, min_obs, mae_base)
    obj_te_0, m_te_0 = score_panel(test, W0, min_obs, mae_base)

    Wc, obj_tr_c = coordinate_descent(train, W0, cal, min_obs, mae_base)
    obj_te_c, m_te_c = score_panel(test, Wc, min_obs, mae_base)

    deltas = {k: round(Wc[k] - W0[k], 6) for k in W0 if abs(Wc[k] - W0[k]) > 1e-9}
    log["train"] = {"avant": m_tr_0, "objectif_avant": round(obj_tr_0, 5),
                    "objectif_apres": round(obj_tr_c, 5)}
    log["test"] = {"avant": m_te_0, "apres": m_te_c,
                   "objectif_avant": round(obj_te_0, 5), "objectif_apres": round(obj_te_c, 5)}
    log["poids_avant"] = W0
    log["poids_candidat"] = Wc
    log["deltas"] = deltas

    if not deltas:
        log["decision"] = "AUCUNE_MODIFICATION"
        log["motif"] = "Les poids courants sont déjà optimaux dans le pas autorisé de ±5 %."
        log["resume_rapport"] = (
            f"Auto-calibration : aucune modification. Sur {base_all['n_obs_1d']} observations "
            f"walk-forward ({len(eligibles)} tickers), les poids courants restent optimaux dans le "
            f"pas autorisé de ±5 %. Hit ratio backtest J+1 : {fr(100*base_all['hit_1d'])} %, "
            f"J+5 : {fr(100*base_all['hit_5d'])} %.")
    elif obj_te_c <= obj_te_0 + cal.get("gain_min_validation", 0.003):
        log["decision"] = "REJETE_VALIDATION"
        log["resume_rapport"] = (
            f"Auto-calibration : candidat REJETÉ. L'ajustement proposé ({fmt_deltas(deltas)}) "
            f"améliorait l'échantillon d'apprentissage mais le gain sur l'échantillon de "
            f"validation ({fr(100*m_te_0['hit_1d'])} % → {fr(100*m_te_c['hit_1d'])} % de hit "
            f"ratio J+1) reste sous le seuil de significativité de "
            f"{fr(100*cal.get('gain_min_validation', 0.003), 1)} pt : indiscernable du bruit. "
            "Poids inchangés.")
    else:
        new_version = bump(cfg["version"])
        history.append({
            "version": cfg["version"], "poids": dict(W0),
            "date": cfg.get("date_maj"),
            "live_hit_ratio_au_moment_du_changement": live_hit,
        })
        cfg["poids"] = Wc
        cfg["version"] = new_version
        cfg["date_maj"] = date.today().isoformat()
        cfg["origine"] = f"Auto-calibration walk-forward du {date.today().isoformat()}."
        if not args.dry_run:
            (CONFIG_DIR / "weights.json").write_text(
                json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
            hist_path.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
        log["decision"] = "APPLIQUE" + (" (dry-run)" if args.dry_run else "")
        log["version_apres"] = new_version
        log["resume_rapport"] = (
            f"Auto-calibration : poids ajustés ({cfg['version']}). {fmt_deltas(deltas)}. "
            f"Validé en walk-forward : hit ratio J+1 sur l'échantillon de validation "
            f"{fr(100*m_te_0['hit_1d'])} % → {fr(100*m_te_c['hit_1d'])} %, "
            f"J+5 {fr(100*m_te_0['hit_5d'])} % → {fr(100*m_te_c['hit_5d'])} %. "
            f"Base : {base_all['n_obs_1d']} observations sur {len(eligibles)} tickers. "
            f"Chaque poids est resté dans le pas de ±5 % par run et la borne de ±30 % vs v1.")

    write_log(log)
    print(log["resume_rapport"])


def fmt_deltas(d):
    lab = {"W_MOM20": "momentum 20 s.", "W_MOM60": "momentum 60 s.",
           "W_MR": "retour à la moyenne", "W_RSI": "correction RSI",
           "W_EOY_MOM": "momentum fin d'année", "W_EOY_MR": "retour à la moyenne fin d'année"}
    return " ; ".join(f"{lab.get(k,k)} {v:+.4f}".replace(".", ",") for k, v in d.items())


def bump(v):
    try:
        maj, mino = v.lstrip("v").split(".")
        return f"v{maj}.{int(mino)+1}"
    except Exception:
        return v + "+1"


def write_log(log):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "calibration_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
