# -*- coding: utf-8 -*-
"""
make_report.py — Génère le rapport HTML quotidien.  (v2, 2026-08-11)

Usage :
  python make_report.py --date 2026-08-11 [--out ../rapports/rapport_2026-08-11.html]

Entrées :
  predictions/quant_{date}.json      produit par compute_features.py (--news déjà appliqué)
  predictions/narratif_{date}.json   parties rédigées : bilan, contexte news
  config/calibration_log.json        produit par calibrate_weights.py — section « modifications du modèle »

Les tableaux de cours, de prédictions et la section calibration sont générés
automatiquement : aucun chiffre n'est recopié à la main, donc le rapport ne peut pas
diverger du dataset.
"""
import json
import argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

CSS = """
  body { font-family: -apple-system, Segoe UI, Arial, sans-serif; max-width: 1060px; margin: 30px auto; padding: 0 20px; color: #1a1a1a; line-height: 1.5; }
  h1 { font-size: 1.5em; border-bottom: 3px solid #1a4d8f; padding-bottom: 10px; }
  h2 { font-size: 1.15em; color: #1a4d8f; margin-top: 34px; border-bottom: 1px solid #ddd; padding-bottom: 6px; }
  h3 { font-size: 1.0em; color: #333; margin-top: 22px; }
  table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 0.92em; }
  th, td { border: 1px solid #ddd; padding: 6px 9px; text-align: right; }
  th { background: #1a4d8f; color: #fff; text-align: center; }
  td:first-child, th:first-child { text-align: left; font-weight: 600; }
  tr:nth-child(even) { background: #f6f8fb; }
  .pos { color: #0a7a2f; font-weight: 600; }
  .neg { color: #b3221e; font-weight: 600; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.85em; font-weight: 600; }
  .ok { background: #dff3e3; color: #0a7a2f; }
  .nok { background: #fbe0df; color: #b3221e; }
  .note { background: #fff8e1; border-left: 4px solid #f0ad4e; padding: 10px 14px; margin: 14px 0; font-size: 0.93em; }
  .reserve { background: #fdeceb; border-left: 4px solid #b3221e; padding: 10px 14px; margin: 14px 0; font-size: 0.93em; }
  .calib { background: #eef4fb; border-left: 4px solid #1a4d8f; padding: 10px 14px; margin: 14px 0; font-size: 0.93em; }
  .sect th { background: #6b4d8f; }
  footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #ddd; font-size: 0.85em; color: #555; }
  .small { font-size: 0.85em; color: #555; }
  td.just { text-align: left; font-weight: 400; font-size: 0.9em; }
"""


def fr(x, nd=2, sign=True):
    if x is None:
        return "n/a"
    s = f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"
    return s.replace(".", ",")


def pct(x, nd=2):
    if x is None:
        return '<td>n/a</td>'
    cls = "pos" if x >= 0 else "neg"
    return f'<td class="{cls}">{fr(100*x, nd)}%</td>'


def pp(x, nd=2):
    if x is None:
        return '<td>n/a</td>'
    cls = "pos" if x >= 0 else "neg"
    return f'<td class="{cls}">{fr(x, nd)}%</td>'


def table_cours(rows, sect=False):
    cls = ' class="sect"' if sect else ''
    h = (f'<table{cls}>\n<tr><th>Ticker</th><th>Close</th><th>Var 1J</th><th>Var 5J</th>'
         f'<th>YTD</th><th>Var 1 an</th><th>RSI14</th><th>Z20</th><th>Vol. 20j ann.</th></tr>\n')
    for t, r in rows:
        h += (f'<tr><td>{t}</td><td>{fr(r["close"], 3, False)}</td>{pct(r["ret_1d"])}{pct(r["ret_5d"])}'
              f'{pct(r["ytd"])}{pct(r["ret_252d"])}<td>{fr(r["rsi14"],1,False)}</td>'
              f'<td>{fr(r["z20"],2,False)}</td><td>{fr(100*r["vol20_ann"],1,False)}%</td></tr>\n')
    return h + "</table>\n"


def table_pred(rows, nw, sect=False):
    cls = ' class="sect"' if sect else ''
    h = (f'<table{cls}>\n<tr><th>Ticker</th><th>Quant J+1</th><th>News</th><th>Préd. J+1</th>'
         f'<th>Quant J+5</th><th>Préd. J+5</th><th>Quant EOY</th><th>Préd. EOY</th>'
         f'<th>Justification du score news</th></tr>\n')
    for t, r in rows:
        p = r["pred"]
        s = r.get("news_score", 0)
        h += (f'<tr><td>{t}</td>{pp(p.get("pred_1d_pct"))}<td>{s:+d}</td>'
              f'{pp(p.get("final_1d_pct", p.get("pred_1d_pct")))}'
              f'{pp(p.get("pred_5d_pct"))}{pp(p.get("final_5d_pct", p.get("pred_5d_pct")))}'
              f'{pp(p.get("pred_eoy_pct"))}{pp(p.get("final_eoy_pct", p.get("pred_eoy_pct")))}'
              f'<td class="just">{r.get("news_justif","")}</td></tr>\n')
    return h + "</table>\n"


def section_calibration(clog):
    if not clog:
        return '<p class="small">Aucun journal de calibration disponible pour cette exécution.</p>'
    dec = clog.get("decision", "?")
    badge = {"APPLIQUE": "ok", "ROLLBACK": "nok", "REJETE_VALIDATION": "ok",
             "AUCUNE_MODIFICATION": "ok"}.get(dec.split()[0], "ok")
    h = f'<p><span class="badge {badge}">{dec}</span></p>\n'
    h += f'<div class="calib">{clog.get("resume_rapport","")}</div>\n'

    tr = clog.get("train", {}).get("avant", {})
    te = clog.get("test", {})
    if tr:
        h += ('<table>\n<tr><th>Métrique</th><th>Apprentissage (70 % anciens)</th>'
              '<th>Validation (30 % récents)</th></tr>\n')
        h += (f'<tr><td>Hit ratio J+1</td><td>{fr(100*tr.get("hit_1d",0),1,False)}%</td>'
              f'<td>{fr(100*te.get("avant",{}).get("hit_1d",0),1,False)}%</td></tr>\n')
        h += (f'<tr><td>Hit ratio J+5</td><td>{fr(100*tr.get("hit_5d",0),1,False)}%</td>'
              f'<td>{fr(100*te.get("avant",{}).get("hit_5d",0),1,False)}%</td></tr>\n')
        h += (f'<tr><td>Observations J+1</td><td>{tr.get("n_obs_1d",0)}</td>'
              f'<td>{te.get("avant",{}).get("n_obs_1d",0)}</td></tr>\n')
        h += "</table>\n"
    live = clog.get("live", {})
    if live.get("hit_ratio_1d") is not None:
        h += (f'<p class="small">Hit ratio des prédictions <em>réellement publiées</em> sur les '
              f'{live.get("n_observations",0)} dernières observations : '
              f'<strong>{fr(100*live["hit_ratio_1d"],1,False)} %</strong>. '
              'Cet indicateur pilote le mécanisme de rollback.</p>\n')
    ex = clog.get("tickers_exclus_faute_historique") or {}
    if ex:
        liste = ", ".join(f"{k} ({v} séances)" for k, v in ex.items())
        h += ('<p class="small">Exclus de la calibration faute d\'historique suffisant : '
              + liste + ".</p>\n")
    gf = clog.get("garde_fous", {})
    if gf:
        h += (f'<p class="small">Garde-fous actifs : seuil de {gf.get("min_seances_evaluees_par_ticker")} '
              f'séances évaluées par ticker · pas maximal de '
              f'{fr(100*gf.get("pas_max_relatif_par_run",0),0,False)} % par exécution · borne dure de '
              f'±{fr(100*gf.get("borne_relative_vs_ancrage",0),0,False)} % autour des poids v1 · '
              f'validation walk-forward obligatoire · rollback si le hit ratio live perd plus de '
              f'{fr(100*gf.get("rollback_seuil_degradation_hit",0),0,False)} pt sur '
              f'{gf.get("rollback_fenetre_seances")} séances.</p>\n')
    return h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    d = args.date

    q = json.loads((BASE / "predictions" / f"quant_{d}.json").read_text(encoding="utf-8"))
    npath = BASE / "predictions" / f"narratif_{d}.json"
    narr = json.loads(npath.read_text(encoding="utf-8")) if npath.exists() else {}
    cpath = BASE / "config" / "calibration_log.json"
    clog = json.loads(cpath.read_text(encoding="utf-8")) if cpath.exists() else {}

    tk = q["tickers"]
    core = [(t, r) for t, r in tk.items() if r["groupe"] == "core"]
    sect = [(t, r) for t, r in tk.items() if r["groupe"] == "sectoriel"]
    nw = q["news_coeffs"]

    H = [f'<!DOCTYPE html>\n<html lang="fr">\n<head>\n<meta charset="UTF-8">\n'
         f'<title>Rapport PEA — {d}</title>\n<style>{CSS}</style>\n</head>\n<body>\n',
         f'<h1>📊 Rapport PEA — {d}</h1>\n',
         f'<p class="small">Analyste quotidien automatisé — modèle <strong>{q["model"]}</strong>. '
         f'Univers : {len(core)} ETF socle (éligibles PEA, hors scope PAD) + {len(sect)} ETF sectoriels '
         f'<strong>en suivi seul</strong>. Données Boursorama EOD, clôture Euronext définitive.</p>\n']

    H.append('<div class="reserve"><strong>Statut PAD des lignes sectorielles.</strong> Les cinq ETF '
             'sectoriels (EXA1, STEC, DEFS, SMH, HLT) sont des fonds sectoriels au sens des critères PAD : '
             'ils sont <strong>en scope</strong> et ne sont pas investissables par Michael sans autorisation '
             'préalable. Ils figurent ici à titre de suivi de marché uniquement — aucun avis '
             'd\'investissement personnel n\'est formulé sur ces lignes.</div>\n')

    H.append("<h2>1. Cours et variations exactes (source : dataset local)</h2>\n")
    H.append("<h3>Socle — investissable</h3>\n" + table_cours(core))
    H.append("<h3>Sectoriels — suivi seul</h3>\n" + table_cours(sect, sect=True))
    if narr.get("note_donnees"):
        H.append(f'<div class="note">{narr["note_donnees"]}</div>\n')

    if narr.get("bilan_html"):
        H.append("<h2>2. Bilan des prédictions passées (auto-évaluation)</h2>\n" + narr["bilan_html"])

    H.append("<h2>3. Prédictions — J+1 / J+5 / fin d'année</h2>\n")
    H.append(f'<p class="small">Valeur unique = signal quant déterministe + overlay news borné. '
             f'Échelle news <strong>[-5, +5]</strong> (élargie le 11/08/2026) · '
             f'J+1 : quant + score×{fr(nw["k_1d"],2,False)} · J+5 : quant + score×{fr(nw["k_5d"],2,False)} · '
             f'EOY : quant + score×{fr(nw["k_eoy"],2,False)}. Influence maximale des news : '
             f'±{fr(5*nw["k_1d"],2,False)} pt (J+1), ±{fr(5*nw["k_5d"],2,False)} pt (J+5), '
             f'±{fr(5*nw["k_eoy"],2,False)} pt (EOY) — identique à la v1 malgré l\'échelle élargie. '
             f'Barème : config/news_scale.md</p>\n')
    H.append("<h3>Socle</h3>\n" + table_pred(core, nw))
    H.append("<h3>Sectoriels — suivi seul</h3>\n" + table_pred(sect, nw, sect=True))

    H.append("<h2>4. Modifications du modèle appliquées à cette exécution</h2>\n")
    H.append(section_calibration(clog))

    if narr.get("contexte_html"):
        H.append("<h2>5. Résumé de l'actualité du jour</h2>\n" + narr["contexte_html"])

    H.append(f'<footer>Rapport généré par make_report.py · modèle {q["model"]} · '
             'composante quant strictement déterministe et reproductible (mêmes cours ⇒ mêmes valeurs) ; '
             "seule l'attribution du score news comporte une part de jugement, bornée. "
             "Ce document est un outil de suivi personnel et ne constitue pas un conseil en investissement."
             '</footer>\n</body>\n</html>\n')

    out = Path(args.out) if args.out else BASE / "rapports" / f"rapport_{d}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(H), encoding="utf-8")
    print(f"Rapport écrit : {out}")


if __name__ == "__main__":
    main()
