# -*- coding: utf-8 -*-
"""
fetch_boursorama.py — Récupère les cours EOD Boursorama pour tout l'univers et écrit
data/incoming.json, au format attendu par update_dataset.py.

Conçu pour tourner sur un runner GitHub Actions (accès internet complet), PAS depuis le
sandbox cloud Cowork (dont le réseau sortant est restreint et ne peut pas atteindre
boursorama.com — vérifié le 2026-08-20).

Reproduit l'appel fait depuis un navigateur sur une page boursorama.com :
  GET https://www.boursorama.com/bourse/action/graph/ws/GetTicksEOD
      ?symbol={SYMBOLE}&length={N}&period=1&guid=
  Header requis : X-Requested-With: XMLHttpRequest

Ce point n'a pas pu être testé depuis le sandbox de développement (réseau bloqué) : le
premier run planifié sur GitHub Actions fait donc office de test réel. En cas de blocage
(anti-bot, changement d'API, code non-200), le script échoue bruyamment (exit 1) plutôt
que d'écrire des données silencieusement incomplètes — le run GitHub Actions apparaîtra en
échec et Michael peut activer les notifications d'échec de workflow dans les paramètres
GitHub pour en être averti.

Usage :
  python fetch_boursorama.py [--universe ../config/universe.json] [--out ../data/incoming.json]
                              [--length 30]
"""
import json
import sys
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = "https://www.boursorama.com/bourse/action/graph/ws/GetTicksEOD"

HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.boursorama.com/bourse/",
}


def fetch_ticker(symbol: str, length: int, retries: int = 3, backoff: float = 2.0):
    url = f"{BASE_URL}?symbol={symbol}&length={length}&period=1&guid="
    last_err = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                body = resp.read()
                data = json.loads(body)
                # Format attendu : {"d": {"QuoteTab": [{"d": ..., "c": ..., "v": ...}, ...]}}
                # ou une variante — on essaie plusieurs chemins connus de l'API Boursorama.
                ticks = None
                if isinstance(data, dict):
                    d = data.get("d", data)
                    if isinstance(d, dict):
                        ticks = d.get("QuoteTab") or d.get("quoteTab") or d.get("ticks")
                    elif isinstance(d, list):
                        ticks = d
                if ticks is None:
                    raise RuntimeError(f"format de réponse inattendu : {str(data)[:300]}")
                return ticks
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise RuntimeError(f"{symbol}: échec après {retries} tentatives — dernière erreur : {last_err}")


def main():
    ap = argparse.ArgumentParser()
    base = Path(__file__).resolve().parent.parent
    ap.add_argument("--universe", default=str(base / "config" / "universe.json"))
    ap.add_argument("--out", default=str(base / "data" / "incoming.json"))
    ap.add_argument("--length", type=int, default=30)
    args = ap.parse_args()

    with open(args.universe, encoding="utf-8") as f:
        instruments = json.load(f)["instruments"]

    result = {}
    failures = []
    for inst in instruments:
        ticker = inst["ticker"]
        symbol = inst["bourso"]
        try:
            ticks = fetch_ticker(symbol, args.length)
            result[ticker] = ticks
            print(f"{ticker} ({symbol}): OK — {len(ticks)} séances récupérées")
        except Exception as e:
            failures.append(ticker)
            print(f"{ticker} ({symbol}): ÉCHEC — {e}", file=sys.stderr)
        time.sleep(1)  # courtoisie envers l'API

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    print(f"Écrit : {out_path} ({len(result)}/{len(instruments)} tickers)")

    if failures:
        print(f"ERREUR : échec pour {failures}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
