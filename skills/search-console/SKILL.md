---
name: search-console
description: >
  Compte rendu SEO d'un site à partir de Google Search Console. Récupère les données par l'API,
  calcule ce qui est du signal et ce qui est du bruit (seuils calculés par script, jamais à l'œil),
  rend un tableau de bord HTML autonome, suit l'effet de chaque changement mis en ligne et finit par
  un calendrier de relecture. À utiliser quand on dit « fais-moi un compte rendu SEO de monsite.com »,
  « rafraîchis le dashboard », « est-ce que mon changement de titre a marché ? », « pourquoi mes clics
  ont baissé ? », « qu'est-ce qui a bougé cette semaine ? », « mes pages sont-elles indexées ? »,
  « analyse mes données Search Console », « branche-moi Search Console ».
---

# Search Console : le signal et le bruit

Tu lis les chiffres Search Console d'un site et tu dis ce qui a vraiment bougé. L'erreur à éviter :
expliquer avec assurance un changement qui n'a pas eu lieu. La plupart des écarts d'une semaine à
l'autre sont du hasard. Le seuil se calcule avant de regarder l'écart, et ce sont les scripts qui le
calculent, pas toi.

Les scripts sont dans `scripts/` à côté de ce fichier (`<skill>` ci-dessous : le dossier de base de la skill ; appelle-les par ce chemin, quel que soit le
dossier courant). Python 3 seul, aucune dépendance. Tout ce qui appartient au lecteur va dans
`./seo/` du dossier courant : `config.json`, puis un dossier par site avec `journal.csv`,
`groupes.csv`, `donnees/` et `tableau-de-bord.html`. Jamais dans le dossier de la skill. Seule
exception : `~/.config/search-console/dossiers.txt` retient le dernier `./seo/` utilisé, pour
rafraîchir depuis n'importe où (l'effacer suffit pour l'oublier).

## Déroulé

1. **Lance le script.** Premier passage : `python3 <skill>/scripts/rapport.py monsite.com`.
   Rafraîchir (« rafraîchis le dashboard ») : `python3 <skill>/scripts/rapport.py` sans site, il
   reprend tous les sites de `./seo/`, ou du dernier `./seo/` utilisé si on est ailleurs. Rafraîchir,
   c'est tout ce déroulé : le script remet un résumé générique, réécris-le à l'étape 4. Compte une
   minute. S'il répond `ERREUR` parce que l'accès Google n'est pas branché, guide l'utilisateur pas à
   pas avec `references/installation.md` : lance toi-même ce qui se lance sans lui (activer l'API,
   le projet de quota), et pour la connexion, qui ouvre son navigateur, dis-lui quoi valider. Une
   étape à la fois, puis relance le script. L'id du projet Google Cloud se pose dans
   `./seo/config.json` : `{"projet_google_cloud": "mon-projet"}`.
2. **Lis le bloc imprimé** (FENÊTRE, VOLUME, SEUIL, COUVERTURE, CHANGEMENTS, puis les verdicts).
   Chaque chiffre y porte déjà son seuil et son verdict. Tu ne refais aucun calcul de tête.
3. **Vérifie l'historique avant d'expliquer.** Lis `journal.csv`. Si le code du site est dans le
   dossier courant, lance `git log --since=<début de la fenêtre d'avant>` ; sinon, demande
   directement. Demande ce qui a changé et que le journal ne dit pas (titres, URL, redirections, contenu, déploiements). Propose de
   l'ajouter au journal, puis relance.
4. **Écris le résumé** en deux ou trois phrases : ce qui dépasse le seuil, et « non détectable »
   pour le reste. Pose-le en tête de page sans rappeler l'API :
   `python3 <skill>/scripts/rapport.py monsite.com --resume "…"` (il ne réimprime que la ligne
   TABLEAU, c'est normal).
5. **Donne la page.** Si tu as l'outil Artifact, publie `./seo/<site>/tableau-de-bord.html` en
   Artifact. Sinon, donne son chemin absolu : elle s'ouvre hors ligne, aussi sur téléphone.
6. **Finis par le calendrier** : recopie le bloc CALENDRIER (quoi relire, quand, et pourquoi pas
   avant), puis rappelle que « rafraîchis le dashboard » suffit la semaine prochaine.

## Le journal, c'est ta mémoire

`journal.csv` est ce qui reste d'un passage à l'autre (format : `references/fichiers.md`).
- Ajoute une ligne dès qu'un changement est en ligne : celui que l'utilisateur te décrit, et celui
  que tu fais toi-même dans le code du site pendant la session (un titre, une URL, une page, une
  redirection). Dis-lui que tu l'as noté et quand tu le reliras.
- Quand une ligne arrive à sa date de relecture, écris le verdict du script dans `constat` et la
  date du jour dans `constat_le` (entre guillemets si le texte a une virgule). La ligne sort du
  calendrier, et au passage suivant tu sais ce que ce changement a donné.
- Avant de proposer un nouveau changement sur une page, relis ses lignes : ce qui a déjà été
  essayé, et ce que ça a donné.

Pour lire un cluster ou un type de page à part, remplis `groupes.csv`.

## Le régime du site (le script le choisit sur les clics des 28 derniers jours)

- **Établi** (200 clics ou plus) : écart réel s'il dépasse 1,96 × √(avant + après).
- **Petit** (30 à 199) : seuil élargi, 1,96 × √(2,5 × (avant + après)), car un petit site varie
  plus que le hasard pur. Aucun verdict à la semaine sur les clics.
- **Neuf** (moins de 30) : dis-le franchement, les comparaisons ne sont pas lisibles à ce volume.
  Passe à l'indexation : pages indexées, « explorée, non indexée », « détectée, non explorée »,
  requêtes qui apparaissent. Ce sont des faits oui ou non, lisibles tout de suite. Des
  impressions parties de presque zéro sont « pas comparables » : le site n'apparaissait pas
  avant, ce n'est pas une hausse mesurée.

## Règles de lecture

1. Seuil d'abord, écart ensuite. Sous le seuil, le verdict est « non détectable ». Ce n'est pas une
   version prudente de « ça monte » : c'est le verdict.
2. Deux périodes de même durée, données finales seulement (Search Console a 2 à 3 jours de retard),
   semaines complètes du lundi au dimanche.
3. Une semaine hors du seuil n'est pas une tendance. Relis la suivante avant d'agir.
4. Beaucoup de pages testées d'un coup : quelques dépassements sortent par hasard. Une page ne
   compte qu'à |z| au-delà de 3.
5. La position moyenne bouge dès que le mélange de requêtes change. Elle ne se compare que sur un
   panier fixe de requêtes. Le CTR ne se lit jamais à la semaine sur un petit site.
6. Une ligne à moins de 10 impressions, c'est du bruit. « Position 1 sur 8 impressions » ne dit pas
   ce que la page tiendrait sur 500.
7. La dimension requête ne montre qu'une partie des impressions (le script donne la part). Toute
   lecture par requête porte sur cette part, biaisée vers les grosses requêtes. Dis-le.
8. Demande ou classement : sur les mêmes requêtes, des impressions qui baissent à position stable,
   c'est la demande qui baisse (saison, pays), pas le classement. Regarde aussi par pays et sur
   mobile seul.
9. Sépare le stock des pages neuves : la montée des neuves peut cacher une baisse du stock.
10. Impressions ordinateur qui s'effondrent ou explosent sans que les clics suivent : trafic sans
    humain ou changement côté Google. Ne cite alors ni CTR ni position du site, lis clics et mobile.
11. Pays et appareil se lisent au niveau du site : croisés avec une page, l'API les tronque.
12. Zéro impression ne veut pas dire zéro demande : Search Console ne voit que là où le site est déjà.

## Après un changement

13. Une ligne de journal par changement, datée du jour de la mise en ligne réelle (le déploiement,
    pas le commit), avec la requête ou la page visée et ce qu'on attend.
14. Suis la cible, pas le total : un total qui monte peut cacher la requête visée qui s'effondre.
15. Verdict au plus tôt 3 semaines après la mise en ligne, 4 pour l'accueil ou une page hub. À
    une semaine, c'est un test de fumée. Quatre issues seulement : amélioration détectable, pas de
    régression détectable, régression détectable (reviens en arrière), indécidable.
16. Si le plus petit écart visible dépasse ce que le changement peut produire, annonce d'avance
    que seul « pas de régression » est mesurable.
17. Un changement à la fois par page. Deux changements groupés ne s'attribuent pas ; revenir en
    arrière est le seul test de cause.
18. Une URL renommée coupe son historique : l'ancienne garde ses impressions 2 à 4 semaines. Ne
    juge pas un groupe dont les URL ont changé dans la fenêtre, et n'empile rien sur une 301
    fraîche. Pas de date dans une URL, pour ne jamais avoir à la renommer.

## Clusters et cannibalisation

19. Une requête servie par plusieurs pages est un constat de structure, prouvable. Qu'elle coûte
    des clics se prouve rarement. Écris les deux verdicts séparément ; corrige sur le premier sans
    le présenter comme le second.
20. Une page outil et un article sur la même intention : Google en garde un, il ne partage pas.
21. Avant de parler de cannibalisation, teste-la : si les deux pages baissent ensemble, ou si l'une
    disparaît sans que l'autre remonte, rien n'était volé.

Le détail, les chiffres de calibration et les règles de stratégie (hub et satellites, quand
découper, pages à portée) : `references/regles.md`.

## Ce que tu rends

Le bloc d'en-tête tel que le script l'imprime, puis chaque affirmation avec son chiffre, son seuil
et son verdict ; le lien ou le chemin du tableau de bord ; le calendrier. Rien qui ne dépasse le
seuil n'est présenté comme une tendance, et aucune cause n'est donnée à un écart sous le seuil.
