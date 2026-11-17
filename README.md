# my-claude-skills

Les skills Claude Code que j'utilise vraiment, offertes ici : une skill par tâche, rangées en deux
packs. Chaque pack s'installe seul ou avec l'autre, et chaque pack a son README.

| Pack | Pour quoi | Les skills | Guide |
|---|---|---|---|
| [`skills/short-video/`](skills/short-video/) | la vidéo courte face caméra : TikTok, Instagram Reels. Auditer ton compte, trouver ce qui explose dans ta niche, écrire le script, monter le rush, découper une longue en shorts, publier. | `video`, `setup`, `audit`, `outliers`, `script`, `edit`, `clips`, `publish` | [README du pack vidéo courte](skills/short-video/README.md) |
| [`skills/seo/`](skills/seo/) | le SEO de ton site, sans outil payant : l'audit technique, les concurrents, quoi écrire ensuite, le maillage, et ce que dit vraiment ta Search Console. | `seo-audit`, `competitors`, `keywords`, `internal-links`, `search-console` | [README du pack SEO](skills/seo/README.md) |

Pas d'application, pas de serveur, pas d'abonnement. Une skill, c'est un dossier avec un
`SKILL.md` qui dit à Claude comment travailler, des scripts qui calculent (deux lancements donnent
le même résultat) et des références. Les scripts tournent sur ton ordinateur. Ce qui part
ailleurs est toujours dit, et rien ne se publie sans ton « oui ». Je les utilise pour mes propres
vidéos et mes propres sites avant de les mettre ici ; une nouvelle arrive chaque mardi avec
[ma newsletter](https://vincentventalon.com/newsletter).

## Le pack vidéo courte : `skills/short-video/`

Pour TikTok et Instagram Reels. Tu tournes face caméra, Claude fait le reste : il mesure ce qui marche déjà sur ton compte et ce
qui explose dans ta niche, écrit le script, monte ton rush en vidéo à publier (coupes, titre,
cartons, sous-titres mot à mot, 9:16), découpe une longue en shorts, et programme le post sur les deux plateformes. Huit
skills, une par étape, qui se passent le relais par des fichiers posés dans ton dossier.

```text
/setup → /audit → /outliers → /script
                   → tu tournes → /edit → /clips → /publish
/video <ce que tu veux> : à n'importe quelle étape, elle choisit et reprend la vidéo en cours
```

Tout tourne sur ta machine : ffmpeg pour couper et rendre, whisper.cpp pour le texte (gratuit),
Remotion pour animer les titres si tu as Node ; yt-dlp lit les comptes sans connexion. En option,
une clé ElevenLabs pour une transcription plus fidèle, et le connecteur Claude de
[Nadia](https://usenadia.com) pour programmer tes posts.

→ **[Le README du pack vidéo courte](skills/short-video/README.md)** : les huit skills, le parcours,
ce que `edit` rend par défaut, puis l'installation et ce qu'il faut sur ta machine.

## Le pack SEO : `skills/seo/`

Le référencement de ton site sans outil payant et sans scraper Google : est-ce que Google lit tes
pages, qui tient la première page sur ta requête, quoi écrire ensuite d'après ta propre Search
Console, le maillage dans le texte, et ce qui a vraiment bougé cette semaine. Cinq skills, une par
tâche, qui partagent un dossier `./seo/<site>/` et un journal des changements : ce qu'une skill met
en ligne, `search-console` le mesure trois semaines après.

```text
/seo-audit → /competitors → /keywords
                   → tu écris la page → /internal-links → /search-console chaque semaine
```

Les scripts mesurent (robots.txt, le sitemap, chaque page, l'API Search Console), Claude lit les
chiffres et juge. Rien n'est modifié sur ton site sans ton « oui », et jamais dans ta Search
Console. Il faut Python 3, et un accès Google branché une fois.

→ **[Le README du pack SEO](skills/seo/README.md)** : les cinq skills, le parcours, le journal
partagé, mesuré contre jugé, puis l'installation et l'accès Google.

## Installer

### D'abord, Claude Code

Les skills tournent dans Claude Code, qui demande un abonnement Claude payant (Pro ou plus : le
plan gratuit n'a pas Claude Code). Deux façons de l'avoir, Mac ou Windows :

- **L'app Claude**, sans terminal : télécharge-la sur [claude.com/download](https://claude.com/download),
  connecte-toi, passe sur l'onglet **Code**, puis choisis ton dossier (« Open folder… »). Claude Code
  est dedans, rien d'autre à installer.
- **Le terminal** : macOS et Linux, `curl -fsSL https://claude.ai/install.sh | bash` ; Windows
  (PowerShell), `irm https://claude.ai/install.ps1 | iex`. Ouvre un nouveau terminal, va dans ton
  dossier et tape `claude`.

### En une phrase (le pack vidéo courte)

Dans Claude Code ouvert dans ton dossier, l'app ou le terminal, colle cette phrase :

```text
Installe le pack short-video de https://github.com/vincentventalon/my-claude-skills dans ce dossier, pour Claude Code
```

Claude récupère le dépôt, copie les huit skills dans le dossier `.claude/skills/` de ton dossier
et te dit ce qu'il a fait (il te demande ton accord avant chaque commande, sauf si tu l'as
désactivé). Ouvre ensuite **une nouvelle session** : les skills sont là sous leur nom, `/setup`,
`/edit`… Commence par `/setup`. Pour mettre à jour, recolle la même phrase.

Ce que Claude fait avec cette phrase, pour que tu le saches (et pour qu'il le lise) :

1. Il récupère le dépôt dans un dossier temporaire : `git clone --depth 1
   https://github.com/vincentventalon/my-claude-skills.git`, ou, sans git, l'archive
   `https://github.com/vincentventalon/my-claude-skills/archive/refs/heads/main.zip` dézippée
   (le dossier s'appelle alors `my-claude-skills-main`).
2. Il copie chaque dossier de `skills/short-video/` (le dossier lui-même, pas seulement son
   contenu) dans `.claude/skills/` du dossier ouvert : `video`, `setup`, `audit`, `outliers`,
   `script`, `edit`, `clips`, `publish`, chacun avec son `SKILL.md`. Pas dans `~/.claude/skills/`,
   sauf si tu le demandes.
3. Il supprime le dossier temporaire et n'installe rien d'autre : ffmpeg, whisper et le reste,
   c'est `/setup` qui les installe, après t'avoir montré les commandes.

Les autres façons ci-dessous installent aussi le pack SEO, ou les deux. Dans toutes, une skill
s'installe sous son nom (`edit`, `keywords`…), sans le dossier de catégorie, et tu n'es pas
obligé de taper son nom : dis à Claude ce que tu veux, il reconnaît la tâche.

### Avec `npx skills` (Claude Code, Codex, et les autres agents)

Dans le dossier de ton projet :

```sh
npx skills add vincentventalon/my-claude-skills -a claude-code
```

Il te montre la liste et tu coches ce que tu veux : la vidéo seule, le SEO seul, ou tout. Ajoute
`-g` pour les installer pour tous tes projets, `--skill setup edit` pour les nommer sans passer
par la liste (`setup` et `edit` vont ensemble). Pour mettre à jour : `npx skills update`.

**Dans Codex**, la même ligne avec `-a codex` :

```sh
npx skills add vincentventalon/my-claude-skills -a codex
```

Puis tu lui parles pareil : « installe la skill vidéo », « monte ma vidéo ». Deux différences,
à cause de son bac à sable : whisper y tourne sur le processeur (la skill bascule toute seule,
mais la transcription est bien plus lente : si c'est trop long, « prends le modèle small », ou
ElevenLabs), et Remotion ne peut pas s'installer dans le dossier de la skill, alors ffmpeg
dessine le titre et le carton de fin. La vidéo sort quand même, sous-titrée.

### Avec le plugin Claude Code

Trois plugins dans le même dépôt : `short-video` (le pack vidéo courte), `seo` (le pack SEO), `vincent-skills`
(tout). Dans Claude Code :

```
/plugin marketplace add vincentventalon/my-claude-skills
/plugin install short-video@my-claude-skills
```

Pour le SEO seul, `/plugin install seo@my-claude-skills` ; pour tout,
`/plugin install vincent-skills@my-claude-skills`. Depuis Claude Code 2.1.275, en une ligne :
`/plugin install short-video --marketplace vincentventalon/my-claude-skills` (de même pour `seo`).
Depuis un terminal, les mêmes commandes s'écrivent `claude plugin marketplace add …` et
`claude plugin install …`. Relance Claude Code après l'installation. Les skills apparaissent sous
le nom du plugin (`/short-video:edit`).

Ces commandes `/plugin` sont celles de Claude Code **dans le terminal**. Dans l'app Claude (onglet
Code), prends plutôt la phrase plus haut : d'après la documentation d'Anthropic, l'app n'a pas la
commande `/plugin` mais son propre gestionnaire de plugins (le bouton **+** à côté de la zone de
texte), et je n'ai pas encore essayé d'y ajouter ce dépôt.

### À la main

macOS et Linux :

```sh
git clone https://github.com/vincentventalon/my-claude-skills.git
mkdir -p .claude/skills
cp -R my-claude-skills/skills/*/* .claude/skills/
```

Windows (PowerShell) :

```powershell
git clone https://github.com/vincentventalon/my-claude-skills.git
New-Item -ItemType Directory -Force .claude\skills | Out-Null
Copy-Item -Recurse -Force my-claude-skills\skills\*\* .claude\skills\
```

`~/.claude/skills/` au lieu de `.claude/skills/` pour tous tes projets. Garde les skills d'un pack
côte à côte : elles se renvoient l'une à l'autre. Pour mettre à jour : `git -C my-claude-skills pull`,
puis copie à nouveau.

### Mettre à jour

`npx skills update`, ou pour le plugin :

```sh
claude plugin marketplace update my-claude-skills
claude plugin update short-video@my-claude-skills
```

(`seo@my-claude-skills` ou `vincent-skills@my-claude-skills` selon ce que tu as installé), puis
relance Claude Code. Tes réglages (`~/.config/video-editing/`, `./seo/`) vivent en dehors des
skills : une mise à jour n'y touche pas.

## Ce qu'il n'y a pas ici

- La relecture dans le navigateur, le split réglé sur ton propre cadrage, les scènes mesurées sur
  ce qui marche, le motion design, choisir son style (sept looks ou le sien, réglé sur sa propre
  prise) : c'est avec ça que je monte mes vidéos, dans
  [Pif Paf Cut Pro](https://pifpafcut.com/skill).
- Plus de hooks que les 22 formules de `script`, et la programmation des posts : le connecteur
  Claude de [Nadia](https://usenadia.com).

## Le dépôt

```text
skills/
  short-video/   le pack vidéo courte : README.md, puis un dossier par skill
  seo/           le pack SEO : README.md, puis un dossier par skill
.claude-plugin/  le marketplace Claude Code (les trois plugins)
dev/             les tests et les outils du dépôt, rien n'en est installé
```

Chaque skill porte un nom court, un ou deux mots qui disent ce qu'elle fait (`edit`,
`outliers`, `seo-audit`), sans préfixe : le plugin en met déjà un (`/short-video:edit`) ;
`dev/check_skills.py` le vérifie. Chaque skill
est un dossier `skills/<pack>/<nom>/` : `SKILL.md` (ce que Claude lit), `scripts/`
(ce qui calcule), `references/` (les règles et les mesures), parfois un `README.md` à elle quand
elle demande une installation ou un accès (`edit`, `script`, `search-console`).

## Signaler un problème, contribuer

Une panne, un message d'erreur qui n'est pas dans le guide d'une skill, une idée : ouvre une
[issue](https://github.com/vincentventalon/my-claude-skills/issues) avec le nom de la skill, ton
système (macOS, Windows, Linux) et le message exact. Une correction est la bienvenue en pull
request ; avant de l'envoyer, vérifie que le plugin et les skills restent valides :

```sh
python3 dev/check_skills.py
claude plugin validate . --strict
```

(`git config core.hooksPath .githooks` les lance à chaque commit.)

## In English

Free Claude Code skills in two packs: [short video](skills/short-video/README.md) (script, edit
and publish talking-head videos for TikTok and Instagram Reels, cut a long video into shorts, audit
your own account) and [SEO](skills/seo/README.md) (technical audit, competitors, keywords,
internal links, Search Console), one skill per job. Install with
`npx skills add vincentventalon/my-claude-skills -a claude-code`, or paste this sentence into
Claude Code (the Claude app's Code tab or the terminal), in your folder: `Install the short-video
pack from https://github.com/vincentventalon/my-claude-skills in this folder, for Claude Code`. `video`, `edit`, `clips`,
`audit`, `outliers` and `publish` work in English as well as in French (their guides are in
French); `setup`, `script` and the five SEO skills are written in French.

## Licence

MIT, voir [LICENSE](LICENSE).
