# Sans terminal : depuis l'export du rapport Performances

## Ce que le lecteur fait dans Search Console

1. Rapport **Performances** > **Résultats de recherche**.
2. Filtre de date > onglet **Comparer** > « 28 derniers jours par rapport à la période précédente ».
   Sans comparaison, pages, requêtes et pays ne se comparent pas.
3. Coche Clics, Impressions, CTR et Position.
4. **Exporter** > **Télécharger le fichier CSV** : un zip avec Graphique.csv (ou Chart.csv),
   Requêtes, Pages, Pays, Appareils, Filtres.
5. Dépose le zip dans la conversation.

Pour la courbe par semaine et la saison, un second export sans comparaison sur 16 mois donne les
totaux par jour.

## Ce que tu fais

- **Si tu peux exécuter du Python** (outil d'analyse de claude.ai, ou terminal) :
  `python3 <skill>/scripts/rapport.py --export <zip ou dossier> --site monsite.com`. Le tableau de
  bord sort comme en mode API, avec une section « ce qui manque ».
- **Sinon**, à la main, avec les mêmes formules :
  - totaux : somme des 28 derniers jours contre les 28 d'avant dans Graphique.csv ; seuil
    1,96 × √(avant + après), ou 1,96 × √(2,5 × (avant + après)) sous 200 clics par 28 jours ;
  - pages qui bougent : z = (après − avant) / √(avant + après), ne retiens que |z| > 3 ;
  - demande ou classement : requêtes présentes sur les deux périodes avec au moins 10 impressions
    avant ; rapport d'impressions et écart de position moyen. Sans intervalle calculé, ne parle que
    d'un écart net (plus de 20 % sur des centaines de requêtes) et dis que le test est approximatif.

## Ce qui manque, à dire au lecteur

- l'**indexation** : pas d'inspection d'URL. Regarde à la main le rapport Pages (Indexation) ;
- les **requêtes servies par plusieurs pages** : l'export ne croise pas requête et page ;
- le **suivi d'un changement** jour par jour sur une page ou une requête : il faut filtrer le rapport
  sur cette page ou cette requête et exporter à part ;
- **1 000 lignes** au plus par tableau : la longue traîne est coupée ;
- la **saison**, si l'export couvre moins de 13 mois ;
- le **rafraîchissement d'une commande** : il faut refaire l'export chaque semaine.
