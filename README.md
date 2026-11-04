# my-claude-skills

Les skills Claude Code que j'utilise vraiment, offertes ici : une skill par tâche, rangées en deux
packs.

| Pack | Pour quoi | Les skills | Guide |
|---|---|---|---|
| [`skills/short-video/`](skills/short-video/) | tes vidéos face caméra : TikTok, Reels, Shorts. Auditer ton compte, trouver ce qui explose dans ta niche, écrire le script, monter le rush, découper une longue en shorts, publier. | `video`, `setup`, `audit`, `outliers`, `script`, `edit`, `clips`, `publish` | [README du pack vidéo](skills/short-video/README.md) |
| [`skills/seo/`](skills/seo/) | le SEO de ton site, sans outil payant : l'audit technique, les concurrents, quoi écrire ensuite, le maillage, et ce que dit vraiment ta Search Console. | `seo-audit`, `competitors`, `keywords`, `internal-links`, `search-console` | [README du pack SEO](skills/seo/README.md) |

Pas d'application, pas de serveur, pas d'abonnement. Une skill, c'est un dossier avec un
`SKILL.md` qui dit à Claude comment travailler, des scripts qui calculent (deux lancements donnent
le même résultat) et des références. Les scripts tournent sur ton ordinateur : ffmpeg,
whisper.cpp, Remotion si tu as Node, l'API Google Search Console et tes propres pages. Ce qui part
ailleurs est toujours dit, et rien ne se publie sans ton « oui ».

Je les utilise pour mes propres vidéos et mes propres sites avant de les mettre ici. Une nouvelle
arrive chaque mardi avec [ma newsletter](https://vincentventalon.com/newsletter).

## Installer

Trois façons, pour un pack ou pour tout. Dans les trois, une skill s'installe sous son nom
(`edit`, `keywords`…), sans le dossier de catégorie, et tu n'es pas obligé de taper son nom :
dis à Claude ce que tu veux, il reconnaît la tâche.

### Avec `npx skills` (Claude Code, et les autres agents)

Dans le dossier de ton projet :

```sh
npx skills add vincentventalon/my-claude-skills -a claude-code
```

Il te montre la liste et tu coches ce que tu veux : la vidéo seule, le SEO seul, ou tout. Ajoute
`-g` pour les installer pour tous tes projets, `--skill setup edit` pour les nommer sans passer
par la liste (`setup` et `edit` vont ensemble). Pour mettre à jour : `npx skills update`.

### Avec le plugin Claude Code

Trois plugins dans le même dépôt : `video` (le pack vidéo), `seo` (le pack SEO), `vincent-skills`
(tout). Dans Claude Code :

```
/plugin marketplace add vincentventalon/my-claude-skills
/plugin install video@my-claude-skills
```

Pour le SEO seul, `/plugin install seo@my-claude-skills` ; pour tout,
`/plugin install vincent-skills@my-claude-skills`. Depuis Claude Code 2.1.275, en une ligne :
`/plugin install video --marketplace vincentventalon/my-claude-skills` (de même pour `seo`).
Depuis un terminal, les mêmes commandes s'écrivent `claude plugin marketplace add …` et
`claude plugin install …`. Relance Claude Code après l'installation. Les skills apparaissent sous
le nom du plugin (`/video:edit`).

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
claude plugin update video@my-claude-skills
```

(`seo@my-claude-skills` ou `vincent-skills@my-claude-skills` selon ce que tu as installé), puis
relance Claude Code. Tes réglages (`~/.config/video-editing/`, `./seo/`) vivent en dehors des
skills : une mise à jour n'y touche pas.

### Installé avant novembre 2026 ?

Le dépôt avait deux plugins, `video-editing` (avec les skills `video-editing`, `setup`,
`insta-audit`) et `search-console`. `video-editing` est remplacé par `video` :
`video-editing` s'appelle maintenant `edit`, `insta-audit` s'appelle `audit`. Retire l'ancien,
puis installe le nouveau :

```sh
claude plugin marketplace update my-claude-skills
claude plugin uninstall video-editing@my-claude-skills
claude plugin install video@my-claude-skills
```

(ou `/plugin uninstall video-editing@my-claude-skills` dans Claude Code). Installé le plugin
`search-console` ? Il reste installable, mais `seo` le contient avec quatre skills de plus :
`claude plugin uninstall search-console@my-claude-skills` puis
`claude plugin install seo@my-claude-skills` (les deux à la fois donneraient la skill en double ;
pour la garder seule quand même : `/plugin install search-console --marketplace vincentventalon/my-claude-skills`).
Tes données dans `./seo/` ne bougent pas. Installé `vincent-skills` début novembre ?
`claude plugin update vincent-skills@my-claude-skills` ajoute les skills SEO. Copiées à la main ?
Supprime `~/.claude/skills/video-editing` et `~/.claude/skills/insta-audit`, puis installe avec
`npx skills`. Ta configuration (`~/.config/video-editing/`) ne bouge pas : rien à refaire.

## Ce qu'il n'y a pas ici

- La relecture dans le navigateur, le split réglé sur ton propre cadrage, les scènes mesurées sur
  ce qui marche, le motion design : c'est avec ça que je monte mes vidéos, dans
  [Pif Paf Cut Pro](https://pifpafcut.com/pro).
- Plus de hooks que les 22 formules de `script`, et la programmation des posts : le connecteur
  Claude de [Nadia](https://usenadia.com).

## Le dépôt

```text
skills/
  short-video/   le pack vidéo : README.md, puis un dossier par skill
  seo/           le pack SEO : README.md, puis un dossier par skill
.claude-plugin/  le marketplace Claude Code (les trois plugins)
dev/             les tests et les outils du dépôt, rien n'en est installé
```

Chaque skill est un dossier `skills/<pack>/<nom>/` : `SKILL.md` (ce que Claude lit), `scripts/`
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
and publish talking-head videos for TikTok, Reels and Shorts, cut a long video into shorts, audit
your own account) and [SEO](skills/seo/README.md) (technical audit, competitors, keywords,
internal links, Search Console), one skill per job. Install with
`npx skills add vincentventalon/my-claude-skills -a claude-code`. `video`, `edit`, `clips`,
`audit`, `outliers` and `publish` work in English as well as in French (their guides are in
French); `setup`, `script` and the five SEO skills are written in French.

## Licence

MIT, voir [LICENSE](LICENSE).
