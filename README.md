# quant-pea-pipeline

Pipeline quantitatif quotidien (PEA) — migration cloud pour tourner indépendamment du PC.

## Architecture

Tout tourne dans **GitHub Actions** (`.github/workflows/daily_report.yml`, cron quotidien
en semaine — le sandbox cloud Cowork a un accès réseau restreint et ne peut ni atteindre
Boursorama ni lire/écrire ce dépôt directement) :

1. Récupération des cours EOD Boursorama (`scripts/fetch_boursorama.py`).
2. Fusion incrémentale dans `data/*.csv` (`scripts/update_dataset.py`).
3. Recalibration bornée et validée walk-forward des poids du modèle
   (`scripts/calibrate_weights.py`).
4. Détermination de la date de séance du jour (déduite des données, jamais de l'horloge
   système).
5. Score news par ticker + narratif (bilan prédiction/réalisé, avis par position, contexte
   macro) via une recherche web réelle par l'API Claude (`scripts/generate_narrative.py`).
6. Calcul des features et prédictions du jour, couche news incluse
   (`scripts/compute_features.py`).
7. Génération du rapport HTML complet (`scripts/make_report.py`).
8. Commit des données/rapport mis à jour dans le dépôt.
9. Envoi du rapport par e-mail à Michael (pièce jointe HTML, SMTP Gmail).

La **tâche planifiée Cowork** (session cloud Claude, peu après l'horaire GitHub Actions)
relit cet e-mail via Gmail et notifie Michael sur son téléphone, prête à discuter du
rapport à la demande — PC éteint.

## Secrets GitHub requis (Settings → Secrets and variables → Actions)

- `MAIL_USERNAME` — adresse Gmail d'envoi.
- `MAIL_PASSWORD` — mot de passe d'application Gmail (Compte Google → Sécurité → Mots de
  passe des applications ; nécessite la validation en 2 étapes activée).
- `MAIL_TO` — adresse de réception (peut être la même).
- `ANTHROPIC_API_KEY` — clé API Anthropic (console.anthropic.com, compte de facturation
  séparé de l'abonnement Claude.ai). Utilisée uniquement pour la recherche web et la
  rédaction de la couche news — facturée à l'usage (~10 $/1000 recherches + tokens
  standard, de l'ordre de quelques dizaines de centimes par jour pour cet usage).

Aucun autre secret n'est nécessaire : le workflow utilise le `GITHUB_TOKEN` intégré
(permissions `contents: write`) pour ses commits automatiques.

## Scripts

- `scripts/fetch_boursorama.py` — récupération des cours (GitHub Actions uniquement, non
  testable depuis le sandbox Cowork — réseau bloqué côté Cowork).
- `scripts/update_dataset.py` — fusion incrémentale dans `data/{TICKER}.csv`.
- `scripts/calibrate_weights.py` — recalibration bornée et validée walk-forward.
- `scripts/generate_narrative.py` — score news (recherche web API Claude) + narratif ;
  toute l'arithmétique (bilan prédiction/réalisé, statistiques) est calculée en Python,
  déterministe — le modèle ne fait que juger la news et rédiger la prose autour de
  chiffres déjà calculés.
- `scripts/compute_features.py` — features + prédiction quant déterministe + couche news.
- `scripts/make_report.py` — génération du rapport HTML final.

## Statut de conformité PAD

Voir `shortlist_instruments.md` et `config/universe.json` (champ `groupe`) : les lignes
`sectoriel` sont en scope PAD et ne sont pas investissables par Michael sans autorisation —
suivi de marché uniquement. `generate_narrative.py` reçoit cette contrainte explicitement
dans son prompt et ne doit jamais formuler d'avis d'investissement sur ces lignes ;
`make_report.py` affiche en plus un rappel systématique, indépendant du modèle.
