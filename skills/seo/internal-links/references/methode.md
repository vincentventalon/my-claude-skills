# Comment maillage.py lit un site

## La lecture d'une page

Le HTML servi est lu tel quel (bibliothèque standard, `html.parser`) : ce qu'un script ajoute dans le
navigateur n'y est pas. Sont mis de côté : `script`, `style`, `pre`, `code`, les formulaires et
boutons.

Un élément est de la **navigation** quand :

- c'est un `<nav>`, `<header>` ou `<footer>`, ou son rôle est `navigation`, `banner`, `contentinfo`,
  `menu`, `search`, `dialog` ;
- sa classe, son id, son `aria-label` ou un attribut `data-` contient un mot de navigation : nav,
  menu, breadcrumb, ariane, sidebar, widget, related, toc, sommaire, pagination, share, social,
  cookie, newsletter, author, auteur, comments, footer… ;
- c'est un `<aside>` hors du contenu principal, ou un `<aside>` dont plus de la moitié du texte est
  en liens (un encadré « conseil » dans l'article reste du contenu) ;
- il est hors de `<main>` quand la page en a un ;
- c'est la section qu'ouvre un titre « À lire aussi », « Les autres articles », « Related posts »,
  « Keep reading »… ;
- ou le même lien (même cible, même ancre) revient, hors menu, sur la moitié des pages au moins
  (4 pages au minimum) : c'est le gabarit du site. De même, un paragraphe répété sur la moitié des
  pages (une bio d'auteur) ne sert pas aux propositions.

Dans le contenu, un lien est **dans le texte** quand son paragraphe, son élément de liste ou sa
cellule a au moins 3 mots hors des liens ; sinon il est **en bloc**, comme un lien qui contient une
image, un titre ou un paragraphe (une carte), ou un lien dans un titre.

## Le graphe

- Liens comptés par pages sources différentes (deux liens de la même page vers la même cible = 1).
- Une cible redirigée compte pour sa page finale ; une cible dont la canonique pointe ailleurs
  compte pour la canonique ; les deux sont signalées à corriger.
- Pages à mailler : celles du sitemap, indexables (pas de noindex, canonique sur elle-même), hors
  accueil et pages de service (légal, confidentialité, contact, compte, panier).
- Profondeur : nombre de clics depuis l'accueil, avec tous les liens, puis avec les seuls liens du
  contenu (texte et blocs).
- Hub : une page (hors accueil) qui lie au moins 8 pages depuis son contenu, et au moins le double
  de la médiane. Un satellite sans retour est une page liée par le hub qui ne le lie pas dans son
  contenu ; celles rangées sous l'URL du hub passent en premier.
- Puits : une page qui reçoit au moins le seuil de liens dans le texte et n'en donne aucun.

## Les propositions

| réglage | valeur |
|---|---|
| mot seul : fréquence sur la cible / fréquence sur le site | 4 fois au moins, 3 occurrences sur la cible |
| expression : un de ses mots | 3 fois au moins |
| terme partagé par | 2 titres au plus (mot seul), 3 (expression) |
| mot de slug courant | seulement entre pages de proximité 0,10 ou plus |
| phrase | 5 mots au moins, pas dans un titre ni dans un lien |
| par cible | 5 propositions au plus ; une phrase ne sert qu'une cible (la mieux notée) |

Score : +2 pour une expression (−1,5 pour un mot courant), + log2 du rapport de fréquence (3 au
plus), +2 si la section porte sur le sujet, +2 si la mention est dans le premier quart de la page
(+1 dans la première moitié), + 10 × proximité (3 au plus), + log10 des impressions de la source sur
28 jours (2 au plus), −1 si l'ancre mène déjà ailleurs. La proximité est le cosinus des
vocabulaires des deux pages (tf-idf), de 0 à 1.

## pages.csv

`url, dans_sitemap, indexable, type, entrants_texte, entrants_blocs, entrants_nav,
liens_texte_entrants, sortants_texte, sortants_blocs, sortants_nav, profondeur, profondeur_contenu,
mots, title, h1, impressions_28j, couverture, canonique`. Les colonnes `entrants_*` et `sortants_*`
ont les mêmes noms que dans `seo-audit/pages.csv`. `entrants_blocs` et `entrants_nav` ne comptent
que les pages qui ne la lient pas déjà dans le texte.

## graphe.csv

`source, cible, cible_demandee, type, raison, ancre, problemes, nofollow`. `type` : texte, bloc ou
navigation ; `raison` : pourquoi (menu, pied de page, répété sur N pages, carte ou image…) ;
`problemes` : paramètres, redirigé, cassé (404), noindex, non canonique, non vérifié (au-delà de
`--max`).
