# my-claude-skills

Les skills Claude Code que j'utilise vraiment, offertes ici : une skill par tâche, rangées en deux
packs. Chaque pack s'installe seul ou avec l'autre, et chaque pack a son README.

| Pack | Pour quoi | Les skills | Guide |
|---|---|---|---|
| [`skills/short-video/`](skills/short-video/) | la vidéo courte face caméra : TikTok, Instagram Reels, YouTube Shorts. Auditer ton compte, trouver ce qui explose dans ta niche, écrire le script, monter le rush, découper une longue en shorts, publier. | `short-video`, `set-up-video-tools`, `audit-my-account`, `find-outliers-in-my-niche`, `write-my-script`, `edit-my-video`, `cut-long-video-into-shorts`, `publish-my-video` | [README du pack vidéo courte](skills/short-video/README.md) |
| [`skills/seo/`](skills/seo/) | le SEO de ton site, sans outil payant : l'audit technique, les concurrents, quoi écrire ensuite, le maillage, et ce que dit vraiment ta Search Console. | `audit-my-site-seo`, `analyze-my-competitors`, `find-keywords-to-write`, `improve-my-internal-links`, `read-my-search-console` | [README du pack SEO](skills/seo/README.md) |

Pas d'application, pas de serveur, pas d'abonnement. Une skill, c'est un dossier avec un
`SKILL.md` qui dit à Claude comment travailler, des scripts qui calculent (deux lancements donnent
le même résultat) et des références. Les scripts tournent sur ton ordinateur. Ce qui part
ailleurs est toujours dit, et rien ne se publie sans ton « oui ». Je les utilise pour mes propres
vidéos et mes propres sites avant de les mettre ici ; une nouvelle arrive chaque mardi avec
[ma newsletter](https://vincentventalon.com/newsletter).

## Le pack vidéo courte : `skills/short-video/`

Pour TikTok, Instagram Reels et YouTube Shorts. Tu tournes face caméra, Claude fait le reste : il mesure ce qui marche déjà sur ton compte et ce
qui explose dans ta niche, écrit le script, monte ton rush en vidéo à publier (coupes, titre,
cartons, sous-titres mot à mot, 9:16), découpe une longue en shorts, et programme le post sur les trois plateformes. Huit
skills, une par étape, qui se passent le relais par des fichiers posés dans ton dossier.

```text
/set-up-video-tools → /audit-my-account → /find-outliers-in-my-niche → /write-my-script
                   → tu tournes → /edit-my-video → /cut-long-video-into-shorts → /publish-my-video
/short-video <ce que tu veux> : à n'importe quelle étape, elle choisit et reprend la vidéo en cours
```

Tout tourne sur ta machine : ffmpeg pour couper et rendre, whisper.cpp pour le texte (gratuit),
Remotion pour animer les titres si tu as Node ; yt-dlp lit les comptes sans connexion. En option,
une clé ElevenLabs pour une transcription plus fidèle, et le connecteur Claude de
[Nadia](https://usenadia.com) pour programmer tes posts.

→ **[Le README du pack vidéo courte](skills/short-video/README.md)** : les huit skills, le parcours,
ce que `edit-my-video` rend par défaut, puis l'installation et ce qu'il faut sur ta machine.

## Le pack SEO : `skills/seo/`

Le référencement de ton site sans outil payant et sans scraper Google : est-ce que Google lit tes
pages, qui tient la première page sur ta requête, quoi écrire ensuite d'après ta propre Search
Console, le maillage dans le texte, et ce qui a vraiment bougé cette semaine. Cinq skills, une par
tâche, qui partagent un dossier `./seo/<site>/` et un journal des changements : ce qu'une skill met
en ligne, `read-my-search-console` le mesure trois semaines après.

```text
/audit-my-site-seo → /analyze-my-competitors → /find-keywords-to-write
                   → tu écris la page → /improve-my-internal-links → /read-my-search-console chaque semaine
```

Les scripts mesurent (robots.txt, le sitemap, chaque page, l'API Search Console), Claude lit les
chiffres et juge. Rien n'est modifié sur ton site sans ton « oui », et jamais dans ta Search
Console. Il faut Python 3, et un accès Google branché une fois.

→ **[Le README du pack SEO](skills/seo/README.md)** : les cinq skills, le parcours, le journal
partagé, mesuré contre jugé, puis l'installation et l'accès Google.

## Installer

Trois façons, pour un pack ou pour tout. Dans les trois, une skill s'installe sous son nom
(`edit-my-video`, `find-keywords-to-write`…), sans le dossier de catégorie, et tu n'es pas obligé de taper son nom :
dis à Claude ce que tu veux, il reconnaît la tâche.

### Avec `npx skills` (Claude Code, et les autres agents)

Dans le dossier de ton projet :

```sh
npx skills add vincentventalon/my-claude-skills -a claude-code
```

Il te montre la liste et tu coches ce que tu veux : la vidéo seule, le SEO seul, ou tout. Ajoute
`-g` pour les installer pour tous tes projets, `--skill set-up-video-tools edit-my-video` pour les nommer sans passer
par la liste (`set-up-video-tools` et `edit-my-video` vont ensemble). Pour mettre à jour : `npx skills update`.

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
le nom du plugin (`/short-video:edit-my-video`).

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
  ce qui marche, le motion design : c'est avec ça que je monte mes vidéos, dans
  [Pif Paf Cut Pro](https://pifpafcut.com/pro).
- Plus de hooks que les 22 formules de `write-my-script`, et la programmation des posts : le connecteur
  Claude de [Nadia](https://usenadia.com).

## Le dépôt

```text
skills/
  short-video/   le pack vidéo courte : README.md, puis un dossier par skill
  seo/           le pack SEO : README.md, puis un dossier par skill
.claude-plugin/  le marketplace Claude Code (les trois plugins)
dev/             les tests et les outils du dépôt, rien n'en est installé
```

Chaque skill porte le nom de ce qu'elle fait pour toi, en mots (`edit-my-video`,
`find-outliers-in-my-niche`), jamais un nom seul ; `dev/check_skills.py` le vérifie. Chaque skill
est un dossier `skills/<pack>/<nom>/` : `SKILL.md` (ce que Claude lit), `scripts/`
(ce qui calcule), `references/` (les règles et les mesures), parfois un `README.md` à elle quand
elle demande une installation ou un accès (`edit-my-video`, `write-my-script`, `read-my-search-console`).

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
and publish talking-head videos for TikTok, Instagram Reels and YouTube Shorts, cut a long video into shorts, audit
your own account) and [SEO](skills/seo/README.md) (technical audit, competitors, keywords,
internal links, Search Console), one skill per job. Install with
`npx skills add vincentventalon/my-claude-skills -a claude-code`. `short-video`, `edit-my-video`, `cut-long-video-into-shorts`,
`audit-my-account`, `find-outliers-in-my-niche` and `publish-my-video` work in English as well as in French (their guides are in
French); `set-up-video-tools`, `write-my-script` and the five SEO skills are written in French.

## Licence

MIT, voir [LICENSE](LICENSE).
