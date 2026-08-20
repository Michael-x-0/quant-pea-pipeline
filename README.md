# quant-pea-pipeline

Pipeline quantitatif quotidien (PEA) — migration cloud pour tourner indépendamment du PC.

## Architecture

Le sandbox cloud de Cowork a un accès réseau restreint (ne peut pas atteindre Boursorama)
et ne peut pas lire/écrire ce dépôt GitHub directement (proxy de sécurité de session). Tout
le calcul lourd tourne donc entièrement dans **GitHub Actions**
(`.github/workflows/daily_report.yml`, cron quotidien en semaine) :

1. Récupération des cours EOD Boursorama (`scripts/fetch_boursorama.py`).
2. Fusion incrémentale dans `data/*.csv` (`scripts/update_dataset.py`).
3. Recalibration bornée et validée walk-forward des poids du modèle
   (`scripts/calibrate_weights.py`).
4. Calcul des features et prédictions du jour (`scripts/compute_features.py`).
5. Génération du rapport HTML (`scripts/make_report.py`).
6. Commit des données/rapport mis à jour dans le dépôt.
7. Envoi du rapport par e-mail à Michael (SMTP Gmail).

La **tâche planifiée Cowork** (session cloud Claude, peu après l'horaire GitHub Actions) relit
cet e-mail via Gmail, notifie Michael sur son téléphone, et reste disponible pour discuter du
rapport ou relancer une analyse à la demande — PC éteint. La couche « actualités » (score news
qualitatif, actuellement absente du run automatisé) peut être ajoutée/affinée par Cowork à la
demande de Michael, qui régénère alors le rapport avec `--news`.

## Secrets GitHub requis (Settings → Secrets and variables → Actions)

- `MAIL_USERNAME` — adresse Gmail d'envoi.
- `MAIL_PASSWORD` — mot de passe d'application Gmail (Compte Google → Sécurité → Mots de
  passe des applications ; nécessite la validation en 2 étapes activée).
- `MAIL_TO` — adresse de réception (peut être la même).

Aucun autre secret n'est nécessaire : le workflow utilise le `GITHUB_TOKEN` intégré
(permissions `contents: write`) pour ses commits automatiques.

## Scripts

- `scripts/fetch_boursorama.py` — récupération des cours (GitHub Actions uniquement, non
  testable depuis le sandbox Cowork — réseau bloqué côté Cowork, voir ci-dessus).
- `scripts/update_dataset.py` — fusion incrémentale dans `data/{TICKER}.csv`.
- `scripts/compute_features.py` — features + prédiction quant déterministe.
- `scripts/calibrate_weights.py` — recalibration bornée et validée walk-forward.
- `scripts/make_report.py` — génération du rapport HTML final.

## Statut de conformité PAD

Voir `shortlist_instruments.md` et `config/universe.json` (champ `groupe`) : les lignes
`sectoriel` sont en scope PAD et ne sont pas investissables par Michael sans autorisation —
suivi de marché uniquement.
