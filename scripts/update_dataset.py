# -*- coding: utf-8 -*-
"""
update_dataset.py — Mise à jour incrémentale du dataset de prix.

Usage : python update_dataset.py [--incoming data/incoming.json] [--data-dir data]

Entrée : data/incoming.json, produit par l'agent à partir de l'API Boursorama
GetTicksEOD (https://www.boursorama.com/bourse/action/graph/ws/GetTicksEOD
?symbol={SYMBOLE}&length=30&period=1&guid= , header X-Requested-With:
XMLHttpRequest, appelé depuis une page boursorama.com dans le navigateur).

Le symbole Boursorama de chaque ticker est dans config/universe.json (champ "bourso") :
préfixe 1rT pour Euronext Paris, 1rA pour Euronext Amsterdam (EXA1, STEC).
Ex. : 1rTWPEA, 1rTDEFS, 1rTSMH, 1rTHLT, 1rAEXA1, 1rASTEC.

Format accepté (deux variantes, par ticker) :
  {"WPEA": [{"d": 20670, "c": 7.032, "v": 1458234}, ...], ...}   # brut API (d = jours depuis 1970-01-01 UTC)
  {"WPEA": [["2026-08-05", 7.032, 1458234], ...], ...}           # déjà converti

Comportement :
- Fusionne dans data/{TICKER}.csv (colonnes date;close;volume), déduplique par
  date (la nouvelle valeur remplace l'ancienne — utile si le close du jour
  était provisoire), trie par date.
- Affiche pour chaque ticker : ancienne date max, nouvelle date max, lignes
  ajoutées/mises à jour.
- Signale un GAP si des séances semblent manquer (trou > 4 jours calendaires
  entre deux dates consécutives, hors week-end prolongé).
- Code retour 1 si un ticker n'a pas pu être mis à jour jusqu'à la dernière
  séance disponible dans incoming.json.
"""
import json
import sys
import argparse
from datetime import date, timedelta
from pathlib import Path

EPOCH = date(1970, 1, 1)


def load_tickers():
    """Univers lu depuis config/universe.json (source unique de vérité, partagée
    avec compute_features.py et calibrate_weights.py)."""
    cfg = Path(__file__).resolve().parent.parent / "config" / "universe.json"
    with open(cfg, encoding="utf-8") as f:
        return [i["ticker"] for i in json.load(f)["instruments"]]


TICKERS = load_tickers()


def load_csv(path: Path):
    rows = {}
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as f:
        header = f.readline()
        for line in f:
            line = line.strip()
            if not line:
                continue
            d, c, v = line.split(";")
            rows[d] = (float(c), int(float(v)))
    return rows


def save_csv(path: Path, rows: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("date;close;volume\n")
        for d in sorted(rows):
            c, v = rows[d]
            c_str = f"{c:.6f}".rstrip("0").rstrip(".")
            f.write(f"{d};{c_str};{v}\n")


def normalize(entries):
    """Convertit les deux formats acceptés en liste [(iso_date, close, volume)]."""
    out = []
    for e in entries:
        if isinstance(e, dict):
            iso = (EPOCH + timedelta(days=int(e["d"]))).isoformat()
            out.append((iso, float(e["c"]), int(float(e.get("v", 0)))))
        else:
            out.append((str(e[0]), float(e[1]), int(float(e[2])) if len(e) > 2 else 0))
    return out


def find_gaps(dates_sorted):
    gaps = []
    for a, b in zip(dates_sorted, dates_sorted[1:]):
        da = date.fromisoformat(a)
        db = date.fromisoformat(b)
        if (db - da).days > 5:  # >5 j : tolère week-ends prolongés et jours fériés Euronext
            gaps.append((a, b))
    return gaps


def main():
    ap = argparse.ArgumentParser()
    base = Path(__file__).resolve().parent.parent
    ap.add_argument("--incoming", default=str(base / "data" / "incoming.json"))
    ap.add_argument("--data-dir", default=str(base / "data"))
    args = ap.parse_args()

    incoming_path = Path(args.incoming)
    data_dir = Path(args.data_dir)

    if not incoming_path.exists():
        print(f"ERREUR: {incoming_path} introuvable. Rien à fusionner.")
        sys.exit(1)

    with open(incoming_path, encoding="utf-8") as f:
        incoming = json.load(f)

    exit_code = 0
    for ticker in TICKERS:
        csv_path = data_dir / f"{ticker}.csv"
        rows = load_csv(csv_path)
        old_max = max(rows) if rows else None

        entries = incoming.get(ticker)
        if not entries:
            print(f"{ticker}: AUCUNE donnée dans incoming.json — non mis à jour (date max: {old_max})")
            exit_code = 1
            continue

        new_rows = normalize(entries)
        added = updated = 0
        for d, c, v in new_rows:
            if d in rows:
                if rows[d] != (c, v):
                    updated += 1
                rows[d] = (c, v)
            else:
                rows[d] = (c, v)
                added += 1

        save_csv(csv_path, rows)
        new_max = max(rows)
        incoming_max = max(d for d, _, _ in new_rows)
        status = "OK" if new_max >= incoming_max else "INCOMPLET"
        if status != "OK":
            exit_code = 1
        gap_msg = ""
        gaps = find_gaps(sorted(rows))
        if gaps:
            gap_msg = " | GAPS: " + ", ".join(f"{a}->{b}" for a, b in gaps[-3:])
        print(f"{ticker}: {status} | {old_max} -> {new_max} | +{added} lignes, {updated} maj | total {len(rows)}{gap_msg}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
