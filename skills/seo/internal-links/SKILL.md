---
name: internal-links
description: >
  Le maillage interne d'un site : mesure les liens posés dans le texte entre ses pages (pas ceux du
  menu ni du pied de page), trouve les pages orphelines ou trop peu liées, les ancres génériques ou
  ambiguës, les liens cassés, redirigés ou vers une page noindex, la profondeur depuis l'accueil, puis
  propose des liens précis (quelle page, quelle phrase, quelle ancre, vers quelle page) et les pose
  dans le code du site si son dépôt est là. À utiliser quand on dit « fais-moi le maillage interne de
  monsite.com », « quelles pages sont orphelines ? », « où mettre des liens internes ? », « propose-moi
  des liens internes vers ma page X », « ma page n'est pas indexée, comment la pousser ? », « vérifie
  mes ancres », « mes liens internes sont-ils cassés ? », « pose les liens dans mes articles »,
  « audit my internal links », « find orphan pages », « internal linking suggestions ».
---

# Le maillage interne : les liens dans le texte

Tu mesures les liens qu'un site se fait à lui-même, puis tu en ajoutes là où ils manquent. Le script
`scripts/maillage.py` lit le site et pose tous les chiffres ; toi, tu juges les propositions avec
l'utilisateur, tu poses les liens retenus et tu écris les parties de `MAILLAGE.md` marquées
`<!-- CLAUDE:`.

## Pourquoi le texte, et pas le menu

Google lit un lien posé dans une phrase comme un vote, avec un contexte : la phrase autour dit de
quoi parle la page liée, et l'ancre (le texte cliquable) le résume. Un lien de menu ou de pied de
page est le même sur toutes les pages : 40 liens de footer ne disent rien de plus sur aucune d'elles.
Le script range donc chaque lien interne en trois sortes :

- **dans le texte** : au milieu d'une phrase du contenu (au moins 3 mots autour). C'est celui qu'on compte ;
- **en bloc** : une carte, une liste de liens nus, un bouton, un titre cliquable. Le robot passe,
  sans phrase pour dire pourquoi ;
- **de navigation** : menu, en-tête, pied de page, barre latérale, fil d'Ariane, sommaire,
  « à lire aussi », ou un même lien répété sur la moitié des pages au moins.

Une page **orpheline**, ici, c'est une page qui ne reçoit aucun lien depuis une phrase, même si le
menu la montre partout.

Les scripts sont dans `scripts/` à côté de ce fichier (`<skill>` ci-dessous : le dossier de la
skill). Python 3.10 ou plus, rien à installer (`python` au lieu de `python3` sur Windows). Tout ce qui
appartient à l'utilisateur va dans `./seo/<site>/internal-links/` du dossier courant, jamais dans le
dossier de la skill.

## Déroulé

1. **Lance le script.**
   `python3 <skill>/scripts/maillage.py monsite.com`
   Il lit le sitemap (déclaré dans robots.txt, sinon `/sitemap.xml`, index et `.gz` compris), puis
   chaque page, cinq à la fois avec une pause, en respectant robots.txt, 300 pages au plus
   (`--max`). Compte 15 secondes pour 100 pages. Options : `--min-entrants 3` (le seuil de liens
   dans le texte par page), `--dossier ./seo`. S'il écrit « Plafond atteint », relance avec le
   `--max` qu'il propose.
2. **Lis le bloc imprimé** (PAGES, ORPHELINES, À CORRIGER, STRUCTURE, PROPOSÉS) puis `MAILLAGE.md`.
   Chaque chiffre y est déjà calculé : tu n'en refais aucun de tête, tu cites ceux du rapport.
3. **Écris les marqueurs** `<!-- CLAUDE: … -->` : le constat en deux ou trois phrases (avec ses
   chiffres : combien d'orphelines sur combien de pages, la page qui y perd le plus d'impressions),
   puis « ce qu'on fait maintenant ». Vérifie à la fin : `grep -c "<!-- CLAUDE:" MAILLAGE.md` donne 0.
4. **Choisis les propositions avec l'utilisateur.** Montre-les par page cible, les mieux notées
   d'abord. Pour chacune, demande-toi : le lien aide-t-il le lecteur à cet endroit de la phrase ?
   Écarte les faux amis (le mot est là, mais ne parle pas du sujet de la page cible : « Google »
   dans « Google Cloud » ne mène pas à une page sur le référencement) et les propositions marquées
   « mot courant, à vérifier » qui ne tiennent pas. Ajuste l'ancre si elle sonne mal. Note le choix
   dans la colonne `statut` de `propositions.csv` : `à poser` ou `écarté` (un `écarté` reste écarté
   au passage suivant).
5. **Pose les liens dans le code**, si le dépôt du site est dans le dossier courant (voir plus bas).
   Sinon, rends la liste à faire à la main dans l'éditeur du site : page, phrase, ancre, adresse.
6. **Après la mise en ligne** (le déploiement, pas le commit), relance le script : un lien posé et
   vu en ligne passe en `posé (vu en ligne le …)` dans `propositions.csv`, et les compteurs
   bougent. Puis note chaque page cible dans le journal :
   `python3 <skill>/scripts/maillage.py monsite.com --noter /ma-page /autre-page --en-ligne 2026-11-03`
   Une ligne par page cible dans `./seo/<site>/journal.csv` (« Liens internes vers /ma-page depuis
   … », attendu : sort de « explorée, non indexée », ou plus d'impressions), pour que la skill
   `search-console` en mesure l'effet trois semaines après. Dis à l'utilisateur ce que tu as noté et
   quand ce sera relu.

## Poser les liens dans le code

Le rapport donne pour chaque proposition la phrase telle qu'elle s'affiche, et `propositions.csv`
une colonne `extrait` (l'ancre et trois mots de chaque côté) faite pour la recherche.

1. **Retrouve la phrase dans les sources** :
   `grep -rnF "trois mots avant ancre trois mots" --include='*.md' --include='*.mdx' --include='*.astro' --include='*.html' --include='*.vue' --include='*.jsx' --include='*.tsx' .`
   Pas trouvée : la mise en forme coupe souvent la phrase (`**gras**`, retour à la ligne, `&nbsp;`).
   Cherche l'ancre seule avec un mot voisin, puis lis le fichier. Plusieurs fichiers : celui de la
   page source (son chemin d'URL ressemble au chemin du fichier). Une phrase qui vient d'une base de
   données ou d'un CMS ne se pose pas dans le code : rends-la dans la liste à la main.
2. **Pose le lien sur la première mention utile**, au format du fichier : `[ancre](/chemin)` en
   Markdown, `<a href="/chemin">ancre</a>` en HTML, le composant de lien du site s'il en a un
   (regarde comment les autres liens internes du même fichier sont écrits, et fais pareil).
3. Une seule fois par page cible et par page source. Jamais dans un titre (`#`, `<h2>`), jamais à
   l'intérieur d'un lien existant. L'ancre est un groupe de mots naturel de la phrase, jamais l'URL
   nue ni « ici ». L'adresse est le chemin final de la page cible : sans paramètre (`?utm_`, `?src=`),
   sans redirection, avec la même barre finale que le site.
4. Montre le diff à l'utilisateur, puis laisse-le commiter et déployer (ou fais-le s'il te le
   demande, par la voie habituelle de son site).

## Les règles

1. Chaque page à mailler reçoit au moins 3 liens dans le texte, de 3 pages différentes. L'accueil,
   les pages légales, contact et compte n'entrent pas dans ce compte.
2. Une page neuve reçoit ses liens le jour de sa publication : depuis 2 ou 3 pages qui parlent déjà
   du sujet, et elle-même en donne vers 2 ou 3 pages. Lance le script le jour même.
3. Hub et satellites dans les deux sens : la page principale d'un sujet lie ses pages de détail
   dans des phrases, et chaque page de détail renvoie vers elle dans une phrase. Le fil d'Ariane ne
   compte pas.
4. Pas d'ancre générique (« ici », « cliquez », « lire la suite », « en savoir plus ») : l'ancre dit
   ce qu'on trouve de l'autre côté.
5. Une même ancre mène toujours à la même page. Deux pages qui reçoivent la même ancre se disputent
   le sujet : c'est un constat de structure, à trancher (une page garde l'ancre), pas une
   cannibalisation prouvée.
6. Pas de lien interne vers une URL à paramètres, redirigée, non canonique ou noindex : on vise
   l'URL finale, celle du sitemap. Un lien de menu vers une page noindex sur toutes les pages se
   retire ou se corrige en premier : il compte sur chaque page.
7. Pas plus d'un lien vers la même page dans une même page, et pas de liens empilés dans une
   phrase : un lien utile vaut mieux que trois.
8. Une page qui ne reçoit aucune proposition n'est mentionnée nulle part : il faut écrire la phrase
   qui amène le lien dans une page proche, ou se demander si la page a sa place sur le site.
9. Pas de conclusion sans chiffre. Poser des liens est une hypothèse : l'effet se lit dans
   `search-console` trois semaines après, avec son seuil, et sous le seuil c'est « non détectable ».
   Un changement à la fois par page : ne pose pas de liens vers une page dont le title vient de
   changer, les deux effets ne se sépareraient pas.

## Comment le script choisit les propositions

Pour chaque page sous le seuil (orphelines d'abord), il cherche dans les autres pages la première
mention, dans une phrase, hors lien et hors titre, d'un terme qui désigne la page cible :

- une **expression** de 2 à 4 mots de son title ou de son H1 (« coût de la vie », « vidéo par jour »),
  ou de son slug ;
- un **mot seul** seulement s'il est le slug entier (`/docker`) ou un nom propre écrit avec une
  majuscule dans la page cible ; un mot de slug courant (`/outils` → « outil ») ne compte qu'entre
  deux pages qui parlent des mêmes choses, et il est marqué « à vérifier » ;
- toujours un terme nettement plus fréquent sur la page cible que sur le reste du site, et partagé
  par 3 titres au plus.

Le score monte quand la mention est dans une section dont le titre porte sur le sujet, tôt dans la
page, quand c'est une expression, quand les deux pages ont un vocabulaire proche, et quand la page
source a des impressions Search Console. Cinq propositions au plus par page cible, une seule par
couple source → cible, jamais depuis une page qui la lie déjà dans son contenu. Le détail de la
lecture des pages et des fichiers : `references/methode.md`.

## Search Console

Si la skill `search-console` a déjà tourné dans ce dossier (`./seo/<site>/donnees/`), le rapport
montre les impressions de chaque page sur 28 jours et son état d'indexation, et le score en tient
compte. Sinon le script le dit (« Search Console non branchée ») et marche quand même : installe
la skill `search-console` et lance-la une fois pour l'ajouter. Si la skill `seo-audit` a lu le site
il y a moins de 2 jours, son `pages.csv` sert pour les statuts des URL que le script ne relit pas.

## Ce que tu rends

Le constat en une ligne avec ses chiffres (pages lues, orphelines sur pages à mailler, médiane de
liens reçus dans le texte), les trois actions dans l'ordre (les liens à poser, les liens à corriger,
les hubs et satellites à relier), les propositions retenues sous la forme « Dans `/source`, phrase
« … », ancre « … » → `/cible` », le diff si tu les as posés, le chemin de `MAILLAGE.md`, et la date de
relecture dans le journal. Pour l'état général du site (titles, indexation, vitesse), renvoie vers
`seo-audit` ; pour savoir quelle page créer quand un sujet n'a pas de page, vers `keywords`.

## Les fichiers

`./seo/<site>/internal-links/` :

| fichier | contenu |
|---|---|
| `MAILLAGE.md` | le rapport : chiffres posés par le script, lecture par toi aux marqueurs ; une version où tu avais écrit est gardée à côté (`MAILLAGE-<date>.md`) |
| `propositions.csv` | une ligne par lien à poser : source, cible, phrase, ancre, score, statut, terme, section, extrait, raison |
| `pages.csv` | une ligne par page : liens reçus et donnés (texte, blocs, navigation), profondeur, mots, title, H1, impressions, indexation |
| `graphe.csv` | un lien interne par ligne : source, cible, type, raison du type, ancre, problèmes (cassé, redirigé, paramètres, noindex) |

## Quand ça coince

- **« Aucune page HTML lisible »** : le site refuse les robots, ou il affiche son texte en
  JavaScript. Le rapport le signale aussi quand la moitié des pages ont moins de 50 mots : le
  script ne voit que le HTML servi, comme un robot pressé.
- **« Plafond atteint »** : relance avec le `--max` proposé. Les URL hors sitemap les plus liées
  sont lues d'abord.
- **Des liens de menu comptés dans le texte** (un menu sans `<nav>` ni classe parlante) : dis-le à
  l'utilisateur, et lis `graphe.csv` (colonne `raison`) pour voir où ils sont classés.

Inspirée de `internal-links` (kostja94/marketing-skills, MIT) et de `site-architecture`
(coreyhaines31/marketingskills, MIT).
