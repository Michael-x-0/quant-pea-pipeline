# Shortlist — ETF éligibles PEA suivis quotidiennement

*Établie le 2026-08-04, mise à jour le 2026-08-04 au soir : ajout du volet dynamique (RS2K, PANX) et levée de la contrainte de détention 30 jours (confirmée par le Compliance Officer le 2026-08-04).*

## Socle (5 ETF hors scope PAD — zéro démarche)

| # | Ticker | Nom | ISIN | Indice | Émetteur | Frais |
|---|--------|-----|------|--------|----------|-------|
| 1 | **WPEA** | iShares MSCI World Swap PEA | IE0002XZSHO1 | MSCI World (~1 400 valeurs) | iShares / BlackRock | 0,20 % |
| 2 | **PE500** | Amundi PEA S&P 500 Screened Acc | FR0013412285 | S&P 500 Scored & Screened | Amundi | 0,25 % |
| 3 | **PCEU** | Amundi PEA MSCI Europe | FR0013412038 | MSCI Europe (~414 valeurs) | Amundi | 0,15 % |
| 4 | **PAEEM** | Amundi PEA MSCI Emerging Markets | FR0013412020 | MSCI Emerging Markets | Amundi | 0,30 % |
| 5 | **PTPXE** | Amundi PEA Japon (TOPIX) | FR0013411980 | TOPIX (~2 000 valeurs) | Amundi | 0,20 % |

## Volet dynamique (plus volatil, meilleur potentiel)

| # | Ticker | Nom | ISIN | Indice | Frais | Statut PAD |
|---|--------|-----|------|--------|-------|------------|
| 6 | **RS2K** | Amundi Russell 2000 | LU1681038672 | Russell 2000 (small caps US, ~2 000 valeurs) | 0,35 % | ✅ Hors scope — zéro démarche |
| 7 | **PUST** | Amundi PEA Nasdaq-100 UCITS ETF Acc | FR0011871110 | Nasdaq-100 (complet, multi-sectoriel, lignes plafonnées <20 %) | 0,30 % | ✅ Hors scope probable* |

*\*PUST (remplace PANX le 2026-08-04) : indice Nasdaq-100 complet, non sectoriel au sens des fournisseurs d'indices, diversifié, géré par Amundi → hors scope selon les critères PAD. Réserves : ~60 % de poids tech (Compliance pourrait l'assimiler à un ETF sectoriel — confirmation écrite ponctuelle recommandée) ; contrepartie de swap BNP Paribas (la société de gestion, seule déterminante pour le scope, reste Amundi). PANX (« US Tech Screened », FR0013412269) écarté car explicitement sectoriel tech → en scope.*

## Checklist PAD (Mode 1)

| Contrôle | Résultat | Détail |
|----------|----------|--------|
| Éligibilité PEA | ✅ (×7) | ETF UCITS synthétiques éligibles PEA, cotés Euronext Paris |
| Hors scope PAD | ✅ ×6 / ⚠️ PUST | PUST : hors scope probable (indice large non sectoriel) — confirmation Compliance recommandée vu le poids tech |
| Périmètre professionnel | ⚠️ | Périmètre non renseigné — à confirmer, surtout pour PUST (tech) |
| Diversification (ligne < 20 %) | ✅ | Indices larges ; 1ʳᵉ ligne < 20 % partout (Nasdaq-100 plafonné) |
| Société de gestion | ✅ | Amundi / iShares — aucun fonds BNPP |
| Détention 30 jours | ✅ N/A | Non applicable à Michael (confirmation Compliance 2026-08-04). Éviter néanmoins les rotations très fréquentes (spéculation excessive surveillée) |

## Logique du portefeuille

WPEA = socle mondial ; PE500, PCEU, PTPXE, PAEEM = curseurs régionaux ; RS2K et PUST = poches dynamiques à volatilité élevée (drawdowns potentiellement sévères — à dimensionner en conséquence). Stratégie compatible PAD : DCA à fréquence fixe, renforcements opportunistes sur forte baisse, pas de rotations excessives.

**Exclu** : BNP Paribas Easy Stoxx Europe 600 (ETZ) — géré par BNPP → en scope, jamais proposé. Produits à effet de levier — exclus (spéculation excessive).

## Volet sectoriel — suivi seul (en scope PAD, NON investissable par Michael)

*Ajouté le 2026-08-11 dans `config/universe.json`. Ces 5 ETF sont en scope PAD (contrairement au socle ci-dessus) : Michael ne peut pas les acheter sans démarche de conformité complète. Ils sont suivis quotidiennement (prix + signal quant + news) à titre indicatif uniquement — une éventuelle ligne dans `position.txt` correspondrait au compte d'un tiers, jamais à Michael. Toujours présentés dans une section à part du rapport quotidien, jamais mélangés au socle investissable ci-dessus.*

*Mise à jour le 2026-08-18 : HLT (Amundi STOXX Europe 600 Healthcare, LU1834986900) remplacé par GOAI (Amundi MSCI Robotics & AI, LU1861132840) à la demande de Michael, pour de meilleures performances historiques (justETF, 08/2026 : GOAI YTD +30,53 %, 1 an +38,58 %, 3 ans +88,71 %, 5 ans +80,76 %, contre HLT YTD +1,70 %, 1 an +9,45 % sur notre dataset). GOAI reste un ETF sectoriel thématique → statut PAD inchangé (en scope, suivi seul, non investissable). Limite technique : l'historique Boursorama pour GOAI n'est fiable que sur 1 an glissant (au-delà, l'API renvoie des données corrompues) — dataset disponible depuis 2025-08-18 au lieu de 2025-01-02 pour les autres tickers ; sans impact sur les features (YTD, RSI14, z20, vol20, momentum) qui nécessitent au plus ~252 séances.*

| # | Ticker | Nom | ISIN | Secteur | Place | Frais |
|---|--------|-----|------|---------|-------|-------|
| 8 | **EXA1** | iShares EURO STOXX Banks 30-15 (Acc) | DE000A2QP372 | Banques zone euro | Euronext Amsterdam | 0,52 % |
| 9 | **STEC** | iShares STOXX Europe 600 Technology (Acc) | DE000A2QP398 | Technologie Europe | Euronext Amsterdam | 0,39 % |
| 10 | **DEFS** | Amundi Stoxx Europe Defense | LU3038520774 | Défense Europe | Euronext Paris | 0,35 % |
| 11 | **SMH** | VanEck Semiconductor | IE00BMC38736 | Semi-conducteurs monde | Euronext Paris | 0,35 % |
| 12 | **GOAI** | Amundi MSCI Robotics & AI UCITS ETF Acc | LU1861132840 | IA / robotique monde | Euronext Paris | 0,40 % |

---
*Pré-filtre indicatif — seule la validation de Compliance Professional Ethics fait foi. Ceci n'est pas un conseil en investissement.*

Sources : [PUST (justETF)](https://www.justetf.com/en/etf-profile.html?isin=FR0011871110), [Comparatif PUST/PANX](https://finance-et-compagnies.com/bourse/etf/nasdaq-100-pea/), [RS2K (justETF)](https://www.justetf.com/en/etf-profile.html?isin=LU1681038672), [PE500 (justETF)](https://www.justetf.com/en/etf-profile.html?isin=FR0013412285), [PCEU (justETF)](https://www.justetf.com/en/etf-profile.html?isin=FR0013412038), [PAEEM (Amundi)](https://www.amundietf.fr/fr/professionnels/produits/equity/amundi-pea-asie-emergente-msci-emerging-asia-screened-ucits-etf-acc/fr0013412012), [PTPXE (Amundi)](https://www.amundietf.fr/fr/professionnels/produits/equity/amundi-pea-japon-topix-ucits-etf-eur-acc/fr0013411980)
