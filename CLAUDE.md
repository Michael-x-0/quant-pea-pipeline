# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A daily quantitative pipeline for Michael's PEA (French tax-advantaged brokerage account),
running entirely on GitHub Actions (`.github/workflows/daily_report.yml`, weekday cron)
since the local PC and the Cowork cloud sandbox can't reach Boursorama or push to this repo
directly. Each weekday run: fetches EOD prices, merges them into the dataset, recalibrates
model weights, scores news via the Claude API (with real web search), computes deterministic
predictions, renders an HTML report, commits everything back to the repo, and emails the
report to Michael.

The repo language is French throughout — code comments, docstrings, config `_comment` keys,
JSON output, and the report itself. Match this when editing.

## Running the pipeline

There's no test suite, build step, or linter configured. Each script is a standalone CLI run
with `python scripts/<name>.py`; run them from the repo root (they resolve paths from
`Path(__file__).resolve().parent.parent`, not the cwd).

Full sequence, in order (mirrors `.github/workflows/daily_report.yml`):

```bash
python scripts/fetch_boursorama.py            # network — GitHub Actions only, not runnable from this sandbox
python scripts/update_dataset.py
python scripts/calibrate_weights.py            # add --dry-run to preview without writing weights.json
python scripts/generate_narrative.py --date YYYY-MM-DD   # needs ANTHROPIC_API_KEY; web search via Claude API
python scripts/compute_features.py --news predictions/news_YYYY-MM-DD.json --out predictions/quant_YYYY-MM-DD.json
python scripts/make_report.py --date YYYY-MM-DD
```

`fetch_boursorama.py` cannot be tested from this sandbox — outbound network to boursorama.com
is blocked here (confirmed 2026-08-20). Everything downstream of `data/incoming.json` can be
exercised locally against the existing `data/*.csv` history. `generate_narrative.py` needs
`ANTHROPIC_API_KEY` set and the `anthropic` pip package installed, and performs real (billed)
web searches — avoid running it speculatively.

The run date is never taken from the system clock; it's derived from the max date present in
`data/*.csv` (see step 4 of the workflow, or `latest_data_date()` in `generate_narrative.py`).

## Architecture: strict separation of deterministic and judgment-based code

This is the load-bearing design decision in the repo, and it explains why the scripts are
split the way they are:

- **Everything numeric is plain, deterministic Python**: price merging, technical features,
  the prediction model, backtesting/calibration, and the prediction-vs-realized comparison in
  the daily report. Same prices in ⇒ same numbers out, always.
- **The only place an LLM makes a judgment call is `generate_narrative.py`**: attributing a
  bounded `news_score` per ticker (via a real Claude web search) and writing prose around
  numbers that were already computed in Python. It never recalculates anything — it receives
  pre-computed `bilan_data` and must reuse those figures verbatim if it references them.

When editing, preserve this boundary: don't let the model compute a number, and don't
hand-write a number in Python that could drift from the dataset.

### Data flow between scripts

```
config/universe.json  ──────────────────────┐  (single source of truth for the instrument list;
                                              │   fetch_boursorama, update_dataset, compute_features,
                                              │   calibrate_weights, generate_narrative all read it)
fetch_boursorama.py → data/incoming.json
        → update_dataset.py → data/{TICKER}.csv        (date;close;volume, deduped/sorted)
                → calibrate_weights.py → config/weights.json, config/weights_history.json,
                                          config/calibration_log.json
                → generate_narrative.py → predictions/news_{date}.json,
                                           predictions/narratif_{date}.json
                        → compute_features.py (--news predictions/news_{date}.json)
                                → predictions/quant_{date}.json
                                        → make_report.py → rapports/rapport_{date}.html
```

`compute_features.py` doubles as a library: `calibrate_weights.py` imports it directly
(`import compute_features as CF`) and calls `CF.core_signals()` / `CF.predict_from_signals()`
— the exact production functions — to replay history walk-forward. This is deliberate: it's
what guarantees calibration and production can never diverge. If you change the model math in
`compute_features.py`, the backtest in `calibrate_weights.py` picks it up automatically; don't
duplicate the formulas there.

### The prediction model (`compute_features.py`)

Deterministic, closed-form, no ML. Given technical signals (20/60-day momentum, 20-day
z-score, 20-day realized vol, Wilder RSI-14) and weights from `config/weights.json`, it
produces clipped point predictions for J+1, J+5, and end-of-year. The news layer is applied
strictly afterward and additively: `pred_finale_h = pred_quant_h + news_score * k_h`, with the
score in `[-5, 5]` and `k_h` chosen so the news layer's maximum influence is capped (±0.20pt
J+1, ±0.50pt J+5, ±1.50pt EOY — see `config/news_scale.md` for the full grading rubric).

### Bounded self-calibration (`calibrate_weights.py`)

Walk-forward backtests the current model, then does bounded coordinate-descent search for
better weights, gated by several guardrails read from `config/weights.json` →
`calibration`: minimum evaluable sessions per ticker, ±5% max step per run, ±30% hard bound
around the frozen `ancrage_v1` values (never around current values — this prevents cumulative
drift), and validation against a held-out 30% test split (in-sample-only gains are rejected).
It also checks the live hit ratio of previously published predictions and can roll back to the
prior weight set if live performance degraded. `W_EOY_BASE` and the `CLIP_*` guardrails are
frozen and never calibrated. Every run overwrites `config/calibration_log.json` (consumed by
`make_report.py` for the report's "model changes" section) and, if a change is applied, appends
to `config/weights_history.json` (the rollback trail).

### PAD compliance boundary

`config/universe.json`'s `groupe` field is `core` (PEA-eligible, outside PAD scope,
investable by Michael) or `sectoriel` (PAD scope — tracked for observation only, not
investable by Michael without separate authorization; see `README.md` and
`shortlist_instruments.md`). This constraint is enforced in two independent places: the prompt
in `generate_narrative.py` explicitly forbids investment opinions on sectoriel lines, and
`make_report.py` renders a hardcoded reminder banner regardless of what the model produced.
When adding tickers or touching either script, preserve this dual enforcement — don't rely on
the LLM alone to respect the boundary. Note: `make_report.py`'s reserve banner text currently
lists tickers by name (including `HLT`, replaced by `GOAI` in `universe.json` on 2026-08-18) —
treat `universe.json` as the source of truth if the two disagree.

### Config files

- `config/universe.json` — instrument list, Boursorama symbols, PAD group. Single source of
  truth; scripts derive their ticker list from here, not from `data/*.csv` contents.
- `config/weights.json` — live model weights (`poids`), frozen anchor values (`ancrage_v1`),
  calibration guardrails, and news-layer coefficients. Only `calibrate_weights.py` should
  write `poids`/`version`/`date_maj`.
- `config/news_scale.md` — the news-scoring rubric given verbatim to Claude in
  `generate_narrative.py`'s prompt. Keep the coefficient table here and in `weights.json` →
  `news` in sync if the scale ever changes.
- `position.txt` — Michael-maintained open positions (`TICKER;QUANTITE;PRU_EUR;DATE_ACHAT`),
  read by `generate_narrative.py` to ground the per-position commentary.

## GitHub Actions secrets

`MAIL_USERNAME`, `MAIL_PASSWORD` (Gmail app password), `MAIL_TO`, `ANTHROPIC_API_KEY`. The
workflow's auto-commit uses the built-in `GITHUB_TOKEN`, no separate secret needed.
