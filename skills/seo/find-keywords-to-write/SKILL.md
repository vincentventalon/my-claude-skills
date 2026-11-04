---
name: find-keywords-to-write
description: >
  Quoi écrire ensuite sur ton site : la recherche de mots-clés à partir de ce que Google Search Console
  montre déjà (la seule source qui dit où Google te place), complétée par les suggestions Google, sans
  outil payant. Le script chiffre les gisements (requêtes déjà en page 1 sans page dédiée, page 2 à
  renforcer, gros groupes de requêtes lointaines, cannibalisation, requêtes neuves, questions pour une
  FAQ), met à part ce qui est sous le bruit, et pose un verdict par candidat : nouvelle page, ou renforcer
  une page qui existe. À utiliser quand on dit « quoi écrire ensuite ? », « fais-moi une recherche de
  mots-clés pour monsite.com », « trouve-moi des idées d'articles », « sur quels mots-clés je peux me
  positionner ? », « quelle page écrire cette semaine ? », « nouvelle page ou je renforce celle-ci ? »,
  « mes pages se cannibalisent ? », « des questions pour ma FAQ », « what should I write next? »,
  « keyword research for my site », « find content gaps in my Search Console ».
---

# Mots-clés : quoi écrire ensuite

Tu cherches la prochaine page à écrire, ou celle à renforcer, à partir de ce que Google montre déjà
du site. Search Console est la seule source qui dit où Google te place : les outils payants estiment
des volumes, elle mesure ta place. Les deux erreurs à éviter : écrire une page neuve sur un mot-clé
qu'une page du site vise déjà (elles se partagent alors le signal), et écrire sur une requête sous
le bruit (moins de 10 impressions sur 28 jours : des pages écrites sur 7 et 11 impressions ont été
déclassées en quelques semaines).

Le script est dans `scripts/` à côté de ce fichier (`<skill>` ci-dessous : le dossier de la skill ;
`python` au lieu de `python3` sur Windows). Python 3.10+, aucune dépendance. Il lit Search Console
par la skill `read-my-search-console`, installée à côté (même dossier `skills/`) : sans elle, il s'arrête et
le dit. Tout ce qu'il écrit va dans `./seo/<site>/keywords/` du dossier courant, le même `./seo/`
que `read-my-search-console`. Jamais dans le dossier de la skill.

## Déroulé

1. **Lance le script.**
   `python3 <skill>/scripts/keywords.py monsite.com --langue fr --pays fr`
   Compte deux à trois minutes : les suggestions Google partent une par une, 2 s entre deux. Sans
   elles (`--sans-suggestions`), quelques secondes. Un thème précis : `--theme "visa"` (ne lit que
   les requêtes qui le contiennent et s'en sert de graine). Ton nom ou celui de ta marque, s'il n'est
   pas dans le domaine : `--marque "prénom nom"`. Si `read-my-search-console` a collecté le site il y a
   moins de 2 jours, le script reprend ses fichiers sans rappeler l'API.
2. **S'il répond `ERREUR`** : Search Console n'est pas branchée. Installe la skill `read-my-search-console`
   à côté de celle-ci et suis son `references/installation.md`, une étape à la fois, puis relance.
3. **Lis le bloc imprimé, puis `MOTS-CLES.md`.** Chaque chiffre y est posé par le script, avec son
   seuil. Tu ne refais aucun calcul de tête. Commence par « En bref » : la part visible, le régime
   du site, le nombre de requêtes distinctes.
4. **Écarte ce qui n'est pas un sujet pour le site.** Le script met déjà à part ta marque et les
   requêtes qui nomment un autre site (`autresite.com`, `site:`). Reste à ta charge : une marque
   tierce sans son domaine, un mot isolé sans sens (« yes »), une requête où Google répond lui-même
   (l'heure, la météo : le bloc dit « 0 clic en position 2 »). Dis à l'utilisateur ce que tu écartes
   et pourquoi, en une ligne.
5. **Vérifie chaque candidat retenu avec une requête fraîche** avant d'en parler comme d'une page à
   écrire : `python3 <skill>/scripts/keywords.py monsite.com --verifier "salaire minimum"` (les 28
   derniers jours, données provisoires comprises, toutes les requêtes qui contiennent ces mots, page
   par page). Les gisements bougent : un groupe noté à 54 impressions est déjà retombé à 11 au
   contrôle suivant. Retombé sous 10 : trop tôt, passe au suivant.
6. **Passe les portes** (ci-dessous). Une porte fermée donne « attendre » ou « renforcer telle page »,
   jamais un silence.
7. **Trouve l'angle.** Pour chaque candidat qui passe, regarde les 3 premiers résultats Google de la
   requête avec ton outil de recherche web. Écris en une phrase ce que la page du site donnera et
   qu'aucun des trois ne donne (un chiffre à jour, un outil, une expérience vécue, une réponse plus
   directe). Pas de phrase, pas de page. Pour une lecture plus fouillée de ces concurrents, la skill
   `analyze-my-competitors`.
8. **Remplis les marqueurs** `<!-- CLAUDE: … -->` de `MOTS-CLES.md` : le résumé en tête, l'angle et le
   choix final de chaque candidat, le plan de la semaine. Vérifie :
   `grep -c "<!-- CLAUDE:" ./seo/monsite.com/keywords/MOTS-CLES.md` donne 0.
9. **Quand une page sort ou change**, ajoute la ligne du journal (plus bas) le jour de la mise en
   ligne, et dis quand `read-my-search-console` la relira.

## Les gisements

Le script les cherche dans cet ordre, du gain le moins cher au plus cher :

1. **Déjà classé sans page dédiée** : position 1 à 10, 10 impressions ou plus, mais la page que
   Google montre ne porte pas tous les mots de la requête dans son title ni dans son URL (le script
   lit le `<title>` des pages). Google te donne déjà raison. Les mots qui manquent sur plusieurs
   requêtes sont regroupés (« salaire minimum » : 22 requêtes, plus de 1 000 impressions, servies
   par un calculateur) : c'est souvent la meilleure page à écrire du rapport.
2. **Page 2** : position 11 à 20, 20 impressions ou plus. La page existe et Google hésite : on la
   renforce, on n'en écrit pas une deuxième.
3. **Gros gisements lointains** : position 20 à 60, requêtes regroupées par mots communs, 50
   impressions ou plus par groupe. Une page qui porte ces mots est trop faible ; aucune page ne les
   porte, c'est un sujet à écrire.
4. **Cannibalisation** : une requête servie par deux pages ou plus, chacune avec 20 % des
   impressions au moins. Rangée par paire de pages, avec les « bascules » (la page en tête a changé
   d'une fenêtre à l'autre).
5. **Requêtes neuves** : apparues sur les 28 derniers jours, absentes des 28 d'avant. Avec le nombre
   de requêtes distinctes d'une fenêtre à l'autre, le signal de croissance le plus robuste.
6. **Questions** : les requêtes qui commencent par comment, pourquoi, combien, quel, où, est-ce,
   how, why, what… La matière d'une FAQ ou d'un H2.
7. **Suggestions Google** : chaque graine (le thème, sinon les 15 requêtes les plus vues), puis
   « graine a », « graine c »… pour les premières, 60 appels au plus. Le script marque celles que le
   site sert déjà. Un refus de Google (403, 429) arrête les suggestions, pas le rapport.
8. **Sous le bruit** : moins de 10 impressions sur 28 jours, montré à part, à revoir le mois prochain.

Détail des seuils, des regroupements et des fichiers : `references/regles.md`.

## Le verdict par règle

| situation | verdict |
|---|---|
| moins de 10 impressions sur 28 jours | trop tôt |
| deux pages se partagent la requête (20 % chacune au moins) | trancher la cannibalisation |
| une autre page du site porte déjà tous les mots dans son title ou son URL | renforcer cette page |
| Google montre un fichier (PDF, GPX) | nouvelle page |
| position 1 à 10, la page porte la moitié des mots ou plus | renforcer la page (les mots manquants dans le title ou un H2) |
| position 1 à 10, la page porte moins de la moitié des mots | nouvelle page |
| position 11 à 20 | renforcer la page |
| position 20 à 60, la page porte la moitié des mots ou plus | renforcer la page |
| position 20 à 60, sinon | nouvelle page |

Le verdict est un point de départ calculé, pas une décision. Le choix final est le tien, après la
vérification fraîche, les portes et la lecture des trois premiers résultats.

## Les portes, avant toute page neuve

- **Le mot-clé est-il déjà visé ?** Le script cherche dans les URL et les titles qu'il connaît
  (Search Console, sitemap). Si le code du site est dans le dossier courant, cherche aussi dans les
  titres et le front matter. Déjà visé : réécris cette page, n'en crée pas une autre.
- **Données minces : une page forte vaut mieux que deux.** Une page neuve ne se justifie que si le
  mot-clé est vraiment distinct ET que la page qui sert aujourd'hui le traite en section secondaire.
  Dans le doute, renforce.
- **10 impressions ou plus sur 28 jours, revérifiées fraîches** (étape 5).
- **La cadence** : 3 pages neuves au plus par semaine sur un petit site (moins de 200 clics sur 28
  jours). Plus de 5 changements de fond dans la semaine : ralentis. Un seul changement à la fois par
  page, sinon `read-my-search-console` ne peut pas dire lequel a marché.
- **La saison** : un sujet saisonnier se publie 1 à 2 mois avant son pic, pas pendant.
- **Les liens** : 3 pages existantes au moins peuvent lier vers la nouvelle, et ces liens se posent
  le jour même (skill `improve-my-internal-links`). Un satellite et sa page mère se lient dans les deux sens.
- **Finis un groupe de pages avant d'en ouvrir un autre.**
- **Un atout dans la main** (tes photos, ton expérience, un outil du site, des chiffres à toi) bat un
  candidat égal : c'est ce que les trois premiers résultats n'ont pas.
- **Une page de résultats saturée** de contenus solides, sans aucune impression du site sur le
  sujet : passe au suivant et dis pourquoi.

## Lire sans se tromper

1. **La part visible.** La dimension requête ne montre qu'une partie des impressions (le script donne
   la part, souvent 30 à 40 %) : Google masque les requêtes rares. Toute lecture par requête porte
   sur cette part, biaisée vers les grosses requêtes. Dis-le une fois à l'utilisateur.
2. **Le plancher.** Sous 10 impressions, une position ne dit rien : « position 3 sur 6 impressions »
   ne dit pas ce que la page tiendrait sur 500.
3. **Une requête neuve n'est pas une hausse mesurée** : le site n'y apparaissait pas avant. Pour dire
   si quelque chose monte vraiment, c'est `read-my-search-console`, avec ses seuils.
4. **La position moyenne d'un groupe** est pondérée par les impressions. Elle ne se compare pas d'un
   mois à l'autre si le mélange de requêtes a changé.
5. **La cannibalisation est un constat de structure**, prouvable. Qu'elle coûte des clics se prouve
   rarement : si les deux pages baissent ensemble, ou si l'une disparaît sans que l'autre remonte,
   rien n'était volé. Un outil et un article sur la même intention : Google en garde un.
6. **Une suggestion prouve que des gens tapent la requête, pas combien.** Ce n'est pas un volume.
   Sers-t'en pour l'angle et les H2, et pour confirmer qu'un sujet existe hors de ton site.
7. **Zéro impression ne veut pas dire zéro demande** : Search Console ne voit que là où le site est
   déjà. Un sujet absent des données mais présent dans les suggestions est un pari, présente-le
   comme tel.
8. **L'heuristique title / URL est grossière** : pluriels approximatifs, synonymes non reconnus
   (« living » ne porte pas « live »). Avant de conclure « page absente », ouvre la page.
9. **Pas de conclusion sans chiffre.** Chaque phrase que tu écris porte son nombre et sa fenêtre.

## Le journal

Quand une page sort, ou qu'une page change (title réécrit, section ajoutée, redirection), ajoute
une ligne à `./seo/<site>/journal.csv`, datée du jour de la mise en ligne réelle. C'est le fichier
de `read-my-search-console` (format complet dans son `references/fichiers.md`) : il mesure la requête visée
trois semaines après. S'il n'existe pas, crée-le avec cet en-tête. Un champ qui contient une virgule
va entre guillemets.

```
en_ligne,ajustement,url,attendu_index,requete,attendu,relire_le,statut,constat,constat_le
2026-11-10,Nouvelle page salaire minimum,https://monsite.com/salaire-minimum/,indexée,salaire minimum,"Page 1 sur la requête, servie aujourd'hui en position 5,7 par le calculateur",,,,
```

Avant de proposer un changement sur une page, relis ses lignes du journal : ce qui a déjà été
essayé, et ce que ça a donné.

## Ce que tu rends

Dans la conversation, court : la part visible et le régime en une ligne ; les 3 à 5 candidats
retenus, chacun avec sa requête ou son groupe, ses impressions, sa position, la page actuelle, le
verdict, le contrôle frais et l'angle ; ce que tu écartes et pourquoi ; le plan de la semaine
(au plus 3 pages neuves sur un petit site) ; le chemin de `MOTS-CLES.md`. Puis : relance dans un
mois, ou trois semaines après une mise en ligne, en même temps que la relecture `read-my-search-console`.

## Fichiers

`./seo/<site>/keywords/` :

| fichier | contenu |
|---|---|
| `MOTS-CLES.md` | le rapport : les tableaux et les candidats, chiffrés par le script, lus par toi aux marqueurs |
| `candidats.csv` | une ligne par requête ou groupe de chaque gisement, avec sa page, son title, le verdict |
| `suggestions.csv` | chaque suggestion Google, sa graine, servie ou non, et ses chiffres si le site la sert |
| `donnees/` | le cache des appels (Search Console et suggestions), repris pendant 2 jours |

Un `MOTS-CLES.md` complété n'est jamais écrasé : un nouveau passage le garde à côté sous
`MOTS-CLES-avant-<date>.md`.

## Réglages

| option | défaut | quand |
|---|---|---|
| `--langue`, `--pays` | la langue de la page d'accueil, le pays qu'elle déclare | toujours pour un site hors de France : `--langue en --pays gb`, `--pays be`, `--pays ca` |
| `--theme "mot"` | aucun | un sujet précis ; répétable |
| `--marque "nom"` | le nom de domaine | ton nom, ton pseudo, ta marque ; répétable |
| `--sans-suggestions` | | pour aller vite, ou si Google refuse |
| `--rafraichir` | | rappeler l'API même si les données ont moins de 2 jours |
| `--verifier "mots"` | | le contrôle frais d'un candidat, puis sortie |
| `--dossier` | `./seo` | le même que `read-my-search-console` |

## Quand ça coince

- **`Search Console non branchée`** : la skill `read-my-search-console` manque à côté, ou son accès n'est
  pas posé. Son `references/installation.md` donne le pas à pas.
- **`aucune requête sur les 28 derniers jours`** : site trop neuf. Repars des suggestions
  (`--theme`) et de ce que tu sais du lecteur, et présente chaque idée comme un pari.
- **`Google a refusé (HTTP 429)`** : les suggestions s'arrêtent, le rapport est complet sans elles.
  Ne relance pas dans la foulée : le cache de 2 jours garde ce qui a été lu.
- **`Titles illisibles`** : le site refuse les robots sur certaines pages ; seule l'URL est comparée.
  Ouvre ces pages toi-même avant de conclure.

Inspirée de `keyword-research` et `content-strategy` de marketingskills (Corey Haines, MIT), de
`keyword-research` de marketing-skills (kostja94, MIT) et de `keyword-research` /
`content-gap-analysis` de seo-geo-claude-skills (Aaron He Zhu, Apache-2.0).
