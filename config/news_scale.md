# Grille d'attribution du `news_score` — échelle [-5, +5]

*Introduite le 2026-08-11, remplace l'échelle [-2, +2].*

## Pourquoi élargir l'échelle

L'échelle à 5 crans ne distinguait pas un communiqué de routine d'un choc macro. En pratique,
presque toutes les séances recevaient -1, 0 ou +1 : la couche news ne servait quasiment qu'à
indiquer un signe, pas une intensité. L'échelle à 11 crans permet de dire « nouvelle légèrement
favorable » (+1) sans la confondre avec « choc majeur » (+5).

## Le plafond d'influence reste celui de la v1

Les coefficients ont été divisés par 2,5 en même temps que l'échelle était multipliée par 2,5.
L'influence maximale des news est donc **strictement identique** à avant :

| Horizon | k (v1, échelle ±2) | k (v2, échelle ±5) | Influence max |
|---------|--------------------|--------------------|---------------|
| J+1 | 0,10 | **0,04** | ±0,20 pt |
| J+5 | 0,25 | **0,10** | ±0,50 pt |
| Fin d'année | 0,75 | **0,30** | ±1,50 pt |

`pred_finale_h = pred_quant_h + news_score × k_h`

Autrement dit : plus de granularité, pas plus de pouvoir. Le quant reste dominant, et une
erreur de jugement de ma part sur une news reste plafonnée au même niveau qu'auparavant.

## Barème

| Score | Intensité | Critères |
|-------|-----------|----------|
| **±5** | Choc systémique | Événement qui redéfinit le régime de marché : krach ou rallye >4 % sur l'indice de référence, défaut souverain ou bancaire majeur, choc géopolitique de premier ordre (fermeture d'un détroit stratégique, conflit entre grandes puissances), décision de banque centrale hors anticipation totale. Attendu quelques fois par an au plus. |
| **±4** | Catalyseur majeur | Surprise macro nette sur une publication de premier plan (CPI, NFP, décision Fed/BCE) qui décale les anticipations de taux ; résultats ou guidance d'une valeur pesant >15 % de l'indice qui surprennent fortement. |
| **±3** | Catalyseur significatif | Publication macro modérément décalée par rapport au consensus ; annonce sectorielle structurante (plan d'investissement public, réglementation) ; mouvement de change marqué et durable sur une ligne à forte exposition devise. |
| **±2** | Nouvelle notable | Résultats d'entreprise importants mais dans la fourchette anticipée ; rotation sectorielle identifiable ; tension géopolitique ou sur les matières premières sans rupture. |
| **±1** | Biais léger | Ton général du marché, commentaires de banquiers centraux sans annonce, flux d'actualité orienté sans catalyseur isolable. |
| **0** | Neutre | Pas de catalyseur identifiable, ou catalyseurs contraires qui s'équilibrent. **Doit rester le score le plus fréquent.** |

## Règles d'attribution

1. **Le score porte sur la nouvelle, pas sur la prédiction.** Il ne faut jamais choisir un score
   pour « corriger » un résultat quant qui semble faux : c'est le rôle de la calibration.
2. **Spécificité au ticker.** Une news sur le yen concerne PTPXE, pas PE500. Une news sur TSMC
   concerne PAEEM, SMH et STEC à des degrés différents — le score doit refléter l'exposition réelle.
3. **Un risque à venir n'est pas un score directionnel.** Un CPI publié demain avec un risque
   symétrique des deux côtés se traduit par 0, mentionné en justification, pas par un score signé.
4. **Justification obligatoire** en une phrase factuelle, avec les chiffres, dans le rapport.
5. **Ancrage par la fréquence.** Sur un mois de séances ordinaires, la distribution attendue est
   à peu près : 0 dans la moitié des cas, ±1/±2 dans la plupart des autres, ±3 occasionnel,
   ±4/±5 rare. Si les ±4 deviennent courants, c'est que l'échelle a dérivé.

## Format d'entrée

`predictions/news_YYYY-MM-DD.json` :

```json
{
  "WPEA":  {"score": 0,  "justif": "Marché mondial quasi stable, pas de catalyseur net."},
  "PAEEM": {"score": 3,  "justif": "TSMC : CA juillet +45 % a/a et capex 2026 relevé à 60-64 Mds$."}
}
```

Puis : `python compute_features.py --news predictions/news_2026-08-12.json`
