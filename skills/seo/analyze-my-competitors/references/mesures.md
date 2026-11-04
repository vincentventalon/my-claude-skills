# Comment les scripts mesurent

## pages.py, pour chaque page

| mesure | comment |
|---|---|
| texte principal | `<main>` s'il porte au moins 25 % des mots de la page, sinon le plus gros `<article>` (30 %), sinon `<body>` ; puis le plus petit élément qui porte 85 % du texte en paragraphes. Hors texte : `nav`, `aside`, `footer`, `header` (au niveau de la page), rôles ARIA de navigation, éléments cachés, blocs dont la classe dit cookie, sidebar, related, share, comment, newsletter, menu, toc. Un élément qui contient le H1 n'est jamais écarté sur sa classe. La ligne « mots comptés dans » dit où. |
| mots | suites de lettres ou de chiffres du texte principal (« l'eau » = 2) |
| H2, H3 | ceux du texte principal ; les titres de décor (« Related posts », « Partager », « Sommaire ») sont écartés |
| FAQ | oui si schema FAQPage, ou un titre FAQ / questions fréquentes, ou 3 titres (h2 à h5, summary, dt) finissant par « ? » |
| dates | publiée : JSON-LD `datePublished`, puis `article:published_time`, microdata, `<time>` ; modifiée : `dateModified`, `article:modified_time`, `og:updated_time`, microdata |
| auteur | JSON-LD `author`, puis meta author, `rel=author`, `itemprop=author`, classe author ou byline |
| liens | `<a href>` http(s) du texte principal, cibles uniques ; interne = même domaine ou sous-domaine |
| requête | ses mots (sans mots vides, au singulier) présents dans le title, le H1, les 100 premiers mots |
| temps de réponse | du début de la requête à la fin du téléchargement, une mesure |
| Search Console | 28 jours finaux, requêtes qui contiennent tous les mots de la requête, par page (sans `#ancre`) et par requête |

Les mots comparés : minuscules, sans accents, sans mots vides fr/en, sans mots génériques (guide,
best, conseils, complet…), réduits à une racine grossière (loyers = loyer, taxes = taxe). Les mots
de la requête et la marque de chaque site (og:site_name, fin du title) sont ignorés. Un mot entre
dans « ce qu'ils titrent et pas toi » s'il est dans un H2 ou H3 d'au moins 2 concurrents (un tiers
au-delà de 6) et dans aucun de tes titres H1 à H4.

## site.py, pour chaque site

| mesure | comment |
|---|---|
| sitemap | lignes `Sitemap:` de robots.txt, sinon `/sitemap.xml`, `/sitemap_index.xml`, `/sitemap-index.xml`, `/wp-sitemap.xml` ; index et `.gz` suivis ; pour ton site, les sitemaps déclarés dans Search Console en dernier recours. Limites : 150 sitemaps, 50 000 URL, 60 s par site ; les séries numérotées (`annonces/12.xml`) sont lues en dernier |
| section | premier dossier de l'URL ; « (racine) » pour une page posée à la racine |
| taxonomie | `/tag/`, `/category/`, `/author/`, `/page/2/`… : comptées dans l'inventaire, hors de l'écart |
| langue | un site traduit (/fr/, /de/… sur 10 URL ou plus) : seule ta langue compte, sinon les URL sans préfixe |
| mots du slug | la fin de l'URL, mêmes règles que plus haut ; un mot présent dans plus de 25 % des slugs d'un site (« malta ») est retiré partout |
| sujet | groupe glouton : la paire de mots qui réunit le plus de pages pas encore prises, puis la suivante, 2 pages au moins |
| absent chez toi | aucune de tes URL n'a les deux mots ; une page seule : aucune de tes URL ne partage deux de ses mots (ou son seul mot) |
| hub | un mot dans 10 URL ou plus chez lui et au moins trois fois plus que chez toi |
| cadence | URL par mois de `lastmod` sur 12 mois ; « non fiable » si plus de la moitié des URL datées ont la même date |
