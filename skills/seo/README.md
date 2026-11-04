# Le pack SEO : le référencement de ton site avec Claude Code

Cinq skills, une par tâche, sans outil payant et sans scraper Google : est-ce que Google lit tes
pages, qui tient la première page sur ta requête, quoi écrire ensuite, le maillage dans le texte,
et ce qui a vraiment bougé dans ta Search Console. Les scripts mesurent (robots.txt, sitemap,
chaque page, l'API Search Console), Claude lit les chiffres et juge. Rien n'est modifié sur ton
site sans ton « oui », et jamais dans ta Search Console.

*Les cinq skills sont écrites en français ; elles comprennent les demandes en anglais (« SEO audit
of my site », « what should I write next? »). This guide is in French.*

## Les skills

| Skill | Ce qu'elle fait |
|---|---|
| [`/seo-audit`](seo-audit/SKILL.md) | L'audit technique de ton site : est-ce que Google arrive à lire tes pages. Le script lit robots.txt, le sitemap et chaque page (redirections, titles, descriptions, H1, canonical, noindex, hreflang, JSON-LD, images, dates), compte les liens dans le texte à part des liens de menu, trouve les pages orphelines et les liens cassés, demande à Google l'état de chaque adresse (inspection d'URL) et passe Lighthouse si tu as Node. `AUDIT.md` classé par priorité, avec la preuve de chaque constat. Il ne modifie rien. |
| [`/competitors`](competitors/SKILL.md) | Qui tient la première page sur ta requête : Claude la cherche, le script mesure chaque page contre la tienne (mots, sections, tableaux, FAQ, dates, schema, auteur, liens), puis lit le sitemap d'un concurrent et dit ce qu'il couvre que tu ne couvres pas, et à quel rythme il publie. |
| [`/keywords`](keywords/SKILL.md) | Quoi écrire ensuite, d'après ta propre Search Console, la seule source qui dit où Google te place : les requêtes où tu sors déjà sans page dédiée, celles en page 2 à renforcer, les gros gisements lointains, deux pages qui se battent sur la même requête, les requêtes neuves, les questions pour une FAQ, et les suggestions Google. Un verdict par candidat (nouvelle page, ou renforcer une page qui existe) ; sous 10 impressions, pas de page. |
| [`/internal-links`](internal-links/SKILL.md) | Le maillage dans le texte : les liens entre tes pages que le menu et le footer ne font pas, les pages orphelines ou trop peu liées, les ancres vides ou ambiguës, les liens cassés, redirigés ou vers une page noindex, la profondeur depuis l'accueil, et des propositions phrase par phrase (quelle page, quelle phrase, quelle ancre, vers quelle page) que Claude pose dans ton code quand tu dis oui. |
| [`/search-console`](search-console/SKILL.md) · [guide](search-console/README.md) | Ton compte rendu SEO depuis Google Search Console : ce qui bouge vraiment et ce qui n'est que du hasard (les seuils calculés par script, jamais à l'œil), si une baisse vient de la demande ou de ton classement, l'effet de chaque changement mis en ligne, l'indexation page par page, et un tableau de bord HTML autonome qui se rafraîchit d'une phrase. |

Tu n'es pas obligé de taper le nom d'une skill : dis à Claude ce que tu veux, il reconnaît la tâche.

## Le parcours

```text
/seo-audit        une fois, puis une semaine après : Google lit-il tes pages → seo/<site>/seo-audit/AUDIT.md
/competitors      qui tient la page 1 sur ta requête              → seo/<site>/competitors/
/keywords         quoi écrire ensuite, d'après ta Search Console   → seo/<site>/keywords/MOTS-CLES.md
                  tu écris la page
/internal-links   le maillage, le jour où la page sort            → seo/<site>/internal-links/MAILLAGE.md
/search-console   chaque semaine : ce qui a vraiment bougé         → seo/<site>/tableau-de-bord.html
```

Les cinq partagent un dossier `./seo/<site>/` dans le dossier où tu lances Claude, et un journal
des changements : un titre réécrit par `seo-audit`, une page nouvelle décidée par `keywords`, des
liens posés par `internal-links`, tout y est noté, y compris quand c'est Claude qui fait le
changement. `search-console` reprend chaque changement à chaque rafraîchissement et dit, trois
semaines après, s'il a marché, s'il n'a rien cassé, ou s'il faut revenir en arrière. Tu n'as rien
à retenir.

## Ce qui est mesuré, ce qui est jugé

- **Les scripts mesurent.** Longueur d'une page, nombre de liens dans le texte, écart de clics et
  son seuil, position moyenne : deux lancements donnent le même résultat. Rien n'est laissé à
  l'œil du modèle.
- **Claude juge.** Il lit les chiffres, trois pages concurrentes, ton site, et écrit ce qu'il faut
  faire : l'angle qui manque, la page à écrire, la phrase où poser le lien.
- **Le bruit est dit bruit.** Sous 10 impressions, `keywords` ne propose pas de page ;
  `search-console` écrit « non détectable » quand l'écart tient dans le hasard, plutôt qu'une
  explication.

## Ce que le pack ne fait pas

Pas de volume de recherche acheté à un outil tiers, pas de suivi de position par scraping de
Google, pas de netlinking. Ce que Google te dit lui-même (Search Console, ses suggestions,
l'inspection d'URL) et ce que tes pages et celles des concurrents contiennent suffisent pour
décider quoi écrire et quoi corriger.

## Installer

Le pack s'installe seul ou avec le pack vidéo courte, de trois façons (npx skills, le plugin Claude
Code `seo`, à la main) : [le README du dépôt](../../README.md#installer). Il faut Python 3, rien
d'autre côté Python. Node est facultatif : avec lui, `seo-audit` passe Lighthouse. Puis :

1. **Branche ton accès Google**, une fois, dix minutes : une propriété Search Console de type
   Domaine, le Google Cloud CLI, une connexion avec ton compte. Pas à pas dans
   [le guide de `search-console`](search-console/README.md#brancher-ton-accès-google-une-fois-dix-minutes).
   Les quatre autres skills s'en servent aussi, et marchent sans en disant ce qu'elles n'ont pas
   pu lire.
2. Dis à Claude **« fais-moi un audit SEO de monsite.com »** : la première chose à savoir sur un
   site, surtout un site neuf, c'est si Google arrive à le lire.

## Mettre à jour, signaler un problème

Les commandes de mise à jour : [le README
du dépôt](../../README.md#mettre-à-jour). Une panne d'accès Google : la table du
[guide de `search-console`](search-console/README.md#pannes-courantes), sinon une
[issue](https://github.com/vincentventalon/my-claude-skills/issues) avec le nom de la skill, ton
système et le message exact.
