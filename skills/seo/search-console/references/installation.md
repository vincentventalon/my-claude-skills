# Accès à l'API et pannes courantes

## Ce qu'il faut, une fois

1. **Une propriété Search Console de type Domaine** (`sc-domain:monsite.com`), vérifiée par un
   enregistrement DNS. Une propriété « préfixe d'URL » marche aussi (le script la trouve seul), mais
   elle ne voit que ce préfixe : ni `www`, ni `http`, ni les sous-domaines.
2. **Le Google Cloud CLI** (`gcloud`) : https://cloud.google.com/sdk/docs/install
3. **Un projet Google Cloud** avec l'API activée :
   ```
   gcloud projects create mon-projet-seo        # ou un projet existant : gcloud projects list
   gcloud services enable searchconsole.googleapis.com --project mon-projet-seo
   ```
4. **La connexion**, avec le compte Google qui voit la propriété dans Search Console :
   ```
   gcloud auth application-default login --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/webmasters.readonly
   ```
5. **Le projet de quota.** Chaque appel doit porter l'en-tête `X-Goog-User-Project: <id du projet>`,
   sinon Google répond 403 « requires a quota project ». Le script le lit, dans cet ordre :
   - la variable `GSC_QUOTA_PROJECT` ;
   - `./seo/config.json` du dossier courant : `{"projet_google_cloud": "mon-projet-seo"}` ;
   - le projet de quota de gcloud : `gcloud auth application-default set-quota-project mon-projet-seo`.

Le scope `webmasters.readonly` suffit : la skill ne modifie rien dans Search Console.

## Les messages d'erreur et quoi faire

| message du script | cause | remède |
|---|---|---|
| `gcloud introuvable` | CLI pas installé, ou pas dans le PATH | installer, rouvrir le terminal |
| `Pas de jeton d'accès Google` | jamais connecté, ou session expirée | relancer la commande de connexion (étape 4) |
| `Pas de projet Google Cloud pour le quota` | aucune des trois sources de l'étape 5 | écrire `./seo/config.json` |
| `Le projet … n'existe pas` | id faux (on a donné le nom du projet) | `gcloud projects list`, prendre la colonne PROJECT_ID |
| `l'API Google Search Console n'est pas activée` | API coupée sur ce projet | `gcloud services enable searchconsole.googleapis.com --project …`, attendre deux minutes |
| `scope manquant` | connexion faite sans `webmasters.readonly` | relancer la connexion avec les deux scopes |
| `n'a pas le droit d'utiliser le projet … comme projet de quota` | le compte n'a pas de rôle sur ce projet | rôle « Service Usage Consumer », ou un projet dont on est propriétaire |
| `Propriété introuvable` | le compte ne voit pas ce site | le script liste les propriétés visibles : vérifier le compte, ou créer la propriété Domaine |
| `ne renvoie aucune donnée` | propriété créée il y a moins de 2 à 3 jours | attendre |
| `429` ou `5xx` | quota ou panne passagère chez Google | le script réessaie seul ; sinon relancer plus tard |
| `inspection(s) en échec` | quota d'inspection (2 000 par jour) | relancer avec `--sans-inspection` |

Le rapport Liens (backlinks) n'a pas d'API : la skill ne le lit pas.
