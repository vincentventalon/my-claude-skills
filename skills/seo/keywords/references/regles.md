# Seuils, regroupements et fichiers

## Les seuils (en tête de `scripts/keywords.py`)

| constante | valeur | rôle |
|---|---|---|
| `PLANCHER` | 10 | impressions sur 28 jours sous lesquelles une requête ou un groupe est du bruit |
| `PAGE2_MIN` | 20 | impressions minimales d'une requête en position 11 à 20 |
| `LOIN_MIN` | 50 | impressions minimales d'un gros gisement lointain (position 20 à 60), par groupe |
| `PART_CANNIBALE` | 20 % | part des impressions d'une requête à partir de laquelle une page compte |
| `CANNIBALE_MIN` | 30 / 10 | impressions minimales d'une requête testée (site établi / petit site) |
| `SEUIL_ETABLI`, `SEUIL_NEUF` | 200, 30 | clics sur 28 jours : établi, petit, neuf (les mêmes que `search-console`) |
| `UBIQUITE` | 25 % | un mot présent dans un quart des requêtes (le nom de la ville d'un site local) ne sert ni à grouper ni à juger un title |
| `SUGGEST_MAX`, `SUGGEST_DELAI` | 60, 2 s | appels Google Suggest au plus, pause entre deux |
| `FRAIS_HEURES` | 48 | âge au-delà duquel les données reprises sont rappelées |

Fenêtres : les 28 derniers jours finaux (`dataState final`, dernier jour complet) contre les 28
d'avant, les mêmes que `search-console`. Le contrôle `--verifier` prend les 28 derniers jours
jusqu'à aujourd'hui, données provisoires comprises.

## Comment le script compare une requête à une page

Les mots de la requête, sans mots vides (français et anglais), sans chiffres, au singulier grossier
(`beaches` et `beach` donnent `beach`), sont cherchés dans l'URL et le `<title>` de la page. Un mot
de 4 lettres ou plus compte aussi s'il apparaît collé dans l'URL (`monsite-voyage` porte `voyage`). La
couverture est la part des mots trouvés. Heuristique : les synonymes et les conjugaisons
(`live`, `living`) ne sont pas reconnus.

## Les regroupements

- **Mots qui manquent** (gisement 1) : d'abord par paire (un mot absent et un voisin de la
  requête, 50 impressions ou plus), puis par mot absent seul ; deux requêtes au moins par groupe ;
  chaque requête dans un seul groupe, le plus lourd.
- **Gisements lointains** (gisement 3) : par paire de mots (50 impressions ou plus), puis par mot
  seul, puis la requête seule si elle fait 10 impressions ou plus. Les mots de pure forme (best,
  guide, gratuit, month, 2026…) ne fondent pas un groupe. Deux groupes servis par la même page et
  qui partagent un mot sont fondus (« corporate tax / company tax »).
- **Marque et autres sites** : les requêtes qui contiennent ton domaine ou `--marque`, celles qui
  nomment un autre site (`autresite.com`, `autresite com`, ou son nom seul quand il vient surtout
  avec son domaine) et les opérateurs (`site:`) sont mises à part.

## candidats.csv

`gisement` (deja_classe, mots_absents, page_2, lointain, lointain_petit, cannibalisation, neuve,
question, sous_le_bruit), `requete_ou_groupe`, `requetes`, `impressions_28j`,
`impressions_28j_avant`, `clics_28j`, `position`, `position_avant`, `page_qui_sert`, `title`,
`couverture` (0 à 1), `mots_absents_ou_requetes`, `page_qui_vise` (la page du site qui porte déjà
tous les mots), `verdict`.

## suggestions.csv

`suggestion`, `graine`, `servie` (oui : la même requête, mots dans n'importe quel ordre, a des
impressions), `impressions_28j`, `position`, `page`.
