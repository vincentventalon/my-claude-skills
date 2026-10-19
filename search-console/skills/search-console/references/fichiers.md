# Les fichiers du lecteur et ce que calculent les scripts

## Où vivent les choses

```
./seo/
  config.json                 {"projet_google_cloud": "mon-projet"}   (facultatif, voir installation.md)
  monsite.com/
    journal.csv               les changements suivis (à remplir)
    groupes.csv               les groupes de pages (facultatif)
    resume.txt                le résumé en tête de page (écrit par --resume)
    tableau-de-bord.html      la page à ouvrir ou publier
    analyse.json              tous les chiffres calculés
    donnees/                  ce que l'API a renvoyé (CSV), réécrit à chaque rafraîchissement
```

`~/.config/search-console/dossiers.txt` retient les dossiers `./seo/` déjà utilisés : un
rafraîchissement lancé d'un autre dossier reprend le dernier.

## journal.csv

Une ligne par changement mis en ligne. Mets entre guillemets un champ qui contient une virgule.

| colonne | contenu |
|---|---|
| `en_ligne` | date de mise en ligne réelle, `2026-10-14` ou `2026-10-14T12:37:00Z` |
| `ajustement` | ce qui a changé, en clair |
| `url` | page(s) visée(s), séparées par des espaces ; `https://monsite.com/blog/*` pour un préfixe |
| `attendu_index` | `indexée` ou `hors index` si le but est l'indexation, sinon vide |
| `requete` | la requête exacte à suivre, sinon vide |
| `attendu` | ce qu'on attend, en une phrase |
| `relire_le` | date de relecture ; vide = mise en ligne + 21 jours |
| `statut` | vide, ou un état posé à la main qui remplace le calcul |
| `constat` | ce qu'on a vu à la relecture, écrit à la main |
| `constat_le` | date du constat ; une relecture faite sort du calendrier |

Exemple :

```
en_ligne,ajustement,url,attendu_index,requete,attendu,relire_le,statut,constat,constat_le
2026-10-14,Nouveau title de la page tarifs,https://monsite.com/tarifs,,prix logiciel facture,Plus de clics sur la requête,2026-11-04,,,
2026-10-14,Liens internes vers /guide,https://monsite.com/guide,indexée,,Sort de « explorée non indexée »,,,,
```

Ce que le script calcule pour chaque ligne : la requête (filtre exact, jour par jour) et les pages
visées, sur N jours avant et N jours après la mise en ligne (N = jours écoulés, 28 au plus), en clics
si la cible en a au moins 20 sur les deux fenêtres, sinon en impressions, au seuil élargi. Puis :

- moins de 7 jours : « trop tôt » ;
- 7 à 20 jours : « en cours », sauf si une baisse est déjà détectable ;
- 21 jours et plus : amélioration détectable (z ≥ 1,96), régression détectable (z ≤ −1,96),
  pas de régression détectable (le seuil fait moins de 30 % de l'avant), sinon indécidable ;
- avec `attendu_index` : tenu, attend un recrawl (dernier crawl avant la mise en ligne), pas tenu ;
- deux lignes sur la même cible à moins de 28 jours : signalées comme empilées.

## groupes.csv

Une règle par ligne, la première qui correspond gagne. Le motif porte sur le chemin de l'URL
(`/blog/*`, `*prix*`) ou sur l'URL entière s'il commence par `http`. Sans `*`, c'est un préfixe.

```
motif,groupe
/blog/*,articles
/outils/*,outils
*,autres pages
```

Sans groupes.csv, les pages se rangent en « stock » et « pages neuves » (vues pour la première fois
depuis le début de la fenêtre d'avant). Les pages neuves restent à part dans tous les cas.

## Ce que fait chaque script

| script | rôle |
|---|---|
| `rapport.py` | enchaîne les trois ; sans site, rafraîchit tout ce qui est suivi ; `--resume` refait la page seule |
| `collecte.py` | appels API : totaux par jour sur 16 mois, page par jour sur 17 semaines, requêtes, requête × page, requête × pays, requête × appareil, pays, appareils sur les deux fenêtres, requêtes du journal jour par jour, sitemaps, inspection d'URL |
| `analyse.py` | régime, seuils, verdicts, test demande ou classement (bootstrap sur les requêtes, 600 tirages), chevauchements, suivi du journal, calendrier ; écrit `analyse.json` et imprime le résumé |
| `tableau.py` | la page HTML (SVG inline, aucun appel réseau, clair et sombre, lisible sur téléphone) |
| `gsc_api.py` | jeton gcloud, en-tête de projet, reprises sur 429 et 5xx, messages d'erreur lisibles |

Fenêtres : les 28 derniers jours finaux contre les 28 d'avant. Inspection d'URL : toutes les pages
du sitemap sous 200 clics par 28 jours ; au-delà, celles du journal et celles du sitemap sans
aucune impression (150 au plus, quota Google : 2 000 par jour et par propriété).

## Seuils dans analyse.py

`SEUIL_ETABLI = 200`, `SEUIL_NEUF = 30` (clics sur 28 jours), `SURDISPERSION = 2.5`, `Z_PAGES = 3`,
`DELAI_VERDICT = 21`. Pages testées : 10 clics ou plus sur l'une des deux fenêtres. Test demande :
requêtes à 10 impressions ou plus avant (3 sur un petit site), 20 requêtes au moins. Chevauchement :
requête à 30 impressions ou plus (10 sur un petit site), au moins deux pages à 20 % chacune.
