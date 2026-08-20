# -*- coding: utf-8 -*-
"""
generate_narrative.py — Couche « actualités » : score news par ticker (recherche web via
l'API Claude) + rédaction du narratif quotidien (bilan prédiction/réalisé — socle ET
sectoriel —, avis par position, contexte macro).

Tourne sur GitHub Actions, après update_dataset.py et calibrate_weights.py, et AVANT
compute_features.py (qui consomme predictions/news_{date}.json) et make_report.py (qui
consomme predictions/narratif_{date}.json).

Principe (identique à l'esprit du reste du pipeline) : toute l'arithmétique — comparaison
prédiction/réalisé, statistiques — est calculée ici en Python, déterministe, à partir des
fichiers de données. Claude n'intervient que pour (a) attribuer un score news borné et
justifié par ticker en s'appuyant sur une recherche web réelle, et (b) rédiger la prose
(contexte macro, avis par position) autour de chiffres déjà calculés — jamais l'inverse.

Nécessite : la variable d'environnement ANTHROPIC_API_KEY et le paquet `anthropic`
(pip install anthropic).

Usage :
  python generate_narrative.py [--date 2026-08-20]   # déduit de data/*.csv si omis
"""
import argparse
import json
import re
import sys
from pathlib import Path

import anthropic

BASE = Path(__file__).resolve().parent.parent
# IDs de modèles disponibles : voir docs.claude.com/en/docs/about-claude/models
MODEL = "claude-haiku-4-5"


def load_json(p):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load_csv_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        next(f)
        for line in f:
            line = line.strip()
            if not line:
                continue
            d, c, v = line.split(";")
            rows.append((d, float(c), int(float(v))))
    return rows


def latest_data_date():
    dates = []
    for p in (BASE / "data").glob("*.csv"):
        rows = load_csv_rows(p)
        if rows:
            dates.append(rows[-1][0])
    if not dates:
        raise SystemExit("Aucune donnée dans data/ — lancez update_dataset.py d'abord.")
    return max(dates)


def previous_quant_file(today_iso):
    files = sorted((BASE / "predictions").glob("quant_*.json"))
    files = [f for f in files if f.stem.replace("quant_", "") < today_iso]
    return files[-1] if files else None


def fr(x, nd=2, sign=True):
    if x is None:
        return "n/a"
    s = f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"
    return s.replace(".", ",")


def build_bilan(today_iso, universe):
    """Compare, en Python pur, les prédictions J+1 de la veille au réalisé exact du
    dataset — pour TOUS les tickers (socle ET sectoriel). Renvoie le HTML de la section
    et les données chiffrées (transmises à Claude comme contexte, jamais recalculées
    par le modèle)."""
    prev_file = previous_quant_file(today_iso)
    if not prev_file:
        return ('<p class="small">Aucune prédiction antérieure disponible pour un bilan '
                '(premier run du pipeline automatisé).</p>'), {}

    prev = load_json(prev_file)
    rows, errs, per_ticker = [], [], {}
    hits = n = 0
    for inst in universe:
        t = inst["ticker"]
        p = prev["tickers"].get(t)
        csv_path = BASE / "data" / f"{t}.csv"
        if not p or not p.get("pred") or not csv_path.exists():
            continue
        pr = p["pred"]
        pred_pct = pr.get("final_1d_pct", pr.get("pred_1d_pct"))
        if pred_pct is None:
            continue
        closes = load_csv_rows(csv_path)
        if len(closes) < 2:
            continue
        realise_pct = 100 * (closes[-1][1] / closes[-2][1] - 1)
        err = realise_pct - pred_pct
        ok = (pred_pct >= 0) == (realise_pct >= 0)
        hits += int(ok)
        n += 1
        errs.append(err)
        per_ticker[t] = {"groupe": inst["groupe"], "pred": round(pred_pct, 3),
                          "realise": round(realise_pct, 3), "ok": ok}
        rows.append(
            f'<tr><td>{t}</td><td>{fr(pred_pct)}</td><td>{fr(realise_pct)}</td>'
            f'<td>{fr(err)}</td><td><span class="badge {"ok" if ok else "nok"}">'
            f'{"OUI" if ok else "NON"}</span></td></tr>'
        )

    if n == 0:
        return "<p class=\"small\">Aucune ligne évaluable pour le bilan aujourd'hui.</p>", {}

    mean_err = sum(errs) / n
    mean_abs = sum(abs(e) for e in errs) / n
    html = (
        f'<p class="small">Comparaison des prédictions J+1 faites le {prev["run_date"]} '
        f'vs réalisé exact du dataset. Univers évalué : {n} tickers (socle + sectoriel).</p>\n'
        f'<table>\n<tr><th>Ticker</th><th>Prédit %</th><th>Réalisé %</th>'
        f'<th>Erreur (pts)</th><th>Direction</th></tr>\n' + "\n".join(rows) + "\n</table>\n"
        f'<p><strong>{hits}/{n} directions correctes</strong> &middot; erreur moyenne signée '
        f'<strong>{fr(mean_err)} pt</strong> &middot; erreur absolue moyenne '
        f'<strong>{fr(mean_abs, sign=False)} pt</strong>.</p>'
    )
    return html, per_ticker


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="Déduite de data/*.csv si omise.")
    args = ap.parse_args()
    today_iso = args.date or latest_data_date()

    universe = load_json(BASE / "config" / "universe.json")["instruments"]
    news_scale = (BASE / "config" / "news_scale.md").read_text(encoding="utf-8")
    position_path = BASE / "position.txt"
    position_txt = position_path.read_text(encoding="utf-8") if position_path.exists() else "(vide)"

    bilan_html, bilan_data = build_bilan(today_iso, universe)

    tickers_desc = "\n".join(
        f'- {i["ticker"]} ({i["nom"]}) — groupe {i["groupe"]}'
        + (f', secteur {i["secteur"]}' if i.get("secteur") else '')
        for i in universe
    )
    tickers_attendus = {i["ticker"] for i in universe}

    prompt = f"""Tu es l'analyste quantitatif quotidien du pipeline PEA de Michael. Voici la
grille officielle d'attribution du score news, à respecter strictement :

{news_scale}

Univers suivi aujourd'hui ({today_iso}) :
{tickers_desc}

position.txt (positions ouvertes de Michael, format TICKER;QUANTITE;PRU_EUR;DATE_ACHAT) :
{position_txt}

Rappel de conformité PAD, impératif : les lignes du groupe "sectoriel" sont en scope PAD
et ne sont PAS investissables par Michael. Ne formule JAMAIS d'avis d'investissement
dessus (achat/vente/renforcement/DCA) — uniquement des points d'observation factuels. Les
lignes du groupe "core" sont hors scope PAD, seules celles où Michael peut investir.

Bilan chiffré déjà calculé (ne recalcule rien, réutilise ces chiffres tels quels si tu les
commentes) :
{json.dumps(bilan_data, ensure_ascii=False, indent=1)}

Fais une recherche web pour t'informer de l'actualité financière et macro du jour,
pertinente pour ces tickers (indices sous-jacents, secteurs, devises concernées,
macro US/Europe/Asie).

Réponds UNIQUEMENT avec un objet JSON valide (rien avant, rien après), au format exact :
{{
  "news": {{
    "TICKER": {{"score": <entier -5..5>, "justif": "<une phrase factuelle en français, avec chiffres>"}},
    ... (un par ticker de l'univers ci-dessus, aucun de plus, aucun de moins)
  }},
  "contexte_html": "<quelques paragraphes HTML (balises <p>, <strong>) résumant l'actualité macro et sectorielle du jour, style note d'analyste>",
  "avis_html": "<HTML : avis factuel par position ouverte sur le socle uniquement (jamais sur le sectoriel), plus tout point de vigilance ; termine par un rappel explicite que les lignes sectorielles ne sont pas investissables par Michael>"
}}"""

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 20}],
        messages=[{"role": "user", "content": prompt}],
    )

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        print("ERREUR : pas de JSON trouvé dans la réponse Claude.", file=sys.stderr)
        print(text, file=sys.stderr)
        sys.exit(1)
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        print(f"ERREUR : JSON invalide ({e}).", file=sys.stderr)
        print(text, file=sys.stderr)
        sys.exit(1)

    news = payload.get("news", {})
    for t, entry in news.items():
        s = entry.get("score") if isinstance(entry, dict) else None
        if t not in tickers_attendus or not isinstance(s, int) or not (-5 <= s <= 5):
            print(f"ERREUR : entrée news invalide pour {t} : {entry}", file=sys.stderr)
            sys.exit(1)
    manquants = tickers_attendus - set(news.keys())
    if manquants:
        print(f"ERREUR : tickers sans score news : {manquants}", file=sys.stderr)
        sys.exit(1)

    news_path = BASE / "predictions" / f"news_{today_iso}.json"
    news_path.parent.mkdir(parents=True, exist_ok=True)
    news_path.write_text(json.dumps(news, ensure_ascii=False, indent=1), encoding="utf-8")

    narratif = {
        "bilan_html": bilan_html,
        "avis_html": payload.get("avis_html", ""),
        "contexte_html": payload.get("contexte_html", ""),
    }
    narr_path = BASE / "predictions" / f"narratif_{today_iso}.json"
    narr_path.write_text(json.dumps(narratif, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Écrit : {news_path}")
    print(f"Écrit : {narr_path}")


if __name__ == "__main__":
    main()
