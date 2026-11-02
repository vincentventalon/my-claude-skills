# my-claude-skills

Les skills Claude Code que j'utilise vraiment, sur mes sites et pour mes vidéos.

Je suis Vincent Ventalon. Je publie une vidéo par jour pendant 100 jours sur TikTok
([@vincentleserpent_](https://www.tiktok.com/@vincentleserpent_)), et chaque mardi
[ma newsletter](https://vincentventalon.com/newsletter) raconte un sujet de ma semaine, mon process,
et la skill qui m'a servi. La skill arrive ici le même jour. Mes vidéos, je les monte avec
[Pif Paf Cut](https://pifpafcut.com), mon logiciel de montage pour agents IA.

## Les plugins

| Plugin | Ce qu'il fait | Skills |
|---|---|---|
| [**video-editing**](video-editing/) | Monter une vidéo face caméra avec Claude, du rush brut à la vidéo à publier : coupe, sous-titres, titre, carton de fin, en 9:16 et en 16:9. Avec l'installation guidée et l'audit de ton compte TikTok ou Instagram. | `setup`, `video-editing`, `insta-audit` |
| [**search-console**](search-console/) | Un compte rendu SEO de ton site à partir de Google Search Console : ce qui bouge vraiment, ce qui n'est que du hasard, et un tableau de bord qui se rafraîchit d'une phrase. | `search-console` |

Tu n'appelles pas une skill par son nom : tu dis à Claude ce que tu veux, il reconnaît la tâche et
suit la bonne skill. Les phrases ci-dessous sont des exemples qui la déclenchent.

### video-editing

| Skill | Ce qu'elle fait | Ce que tu dis à Claude |
|---|---|---|
| `setup` | Regarde ce qui est installé sur ta machine, te fait choisir le moteur de transcription (whisper, gratuit et sur ton ordinateur, ou ElevenLabs Scribe, payant à l'usage), pose les réglages (langue, dossier de sortie, sous-titres, Remotion) et installe ce qui manque une fois que tu as vu les commandes. À lancer en premier. | « installe la skill vidéo », « configure le montage », « je veux utiliser ElevenLabs », « passe à whisper » |
| `video-editing` | Le montage : joint tes rushs, coupe les blancs, les faux départs et les reprises (ta dernière prise est gardée, aucun mot coupé en deux), transcrit, incruste les sous-titres, un titre et un carton de fin, et rend la vidéo en 9:16, et en 16:9 pour YouTube quand tu as filmé à l'horizontale. Ce qui reste à couper, tu le lui dis avec tes mots. | « monte ma vidéo, les rushs sont dans Téléchargements », « enlève mes reprises », « garde la pause après la blague » |
| `insta-audit` | Lit tes dernières vidéos sans connexion (30 par défaut), compare chacune à la médiane de ton compte, transcrit sur ton ordinateur ce que tu dis dans les 5 premières secondes, et écrit `AUDIT.md` : ce qui marche déjà chez toi, trois tests à faire, un bloc pour le prochain montage. Gratuit. Instagram refuse presque toujours la lecture sans connexion : tu donnes alors tes chiffres (un export, ou collés). | « audite mon compte Instagram », « analyse mon TikTok », « qu'est-ce qui marche sur mon compte », ou le lien de ton profil |

Prérequis, réglages et pannes courantes : [video-editing/README.md](video-editing/README.md).

### search-console

| Skill | Ce qu'elle fait | Ce que tu dis à Claude |
|---|---|---|
| `search-console` | Récupère tes données Search Console, calcule ce qui est du signal et ce qui est du bruit, suit l'effet de chaque changement que tu mets en ligne et rend un tableau de bord HTML avec un calendrier de relecture. | « fais-moi un compte rendu SEO de monsite.com », « rafraîchis le dashboard », « est-ce que mon changement de titre a marché ? » |

Brancher ton accès Google, ce que tu obtiens, pannes courantes : [search-console/README.md](search-console/README.md).

## Installer

### Skill, plugin, marketplace

Une **skill**, c'est un dossier que Claude Code lit quand tu lui demandes un travail précis : des
instructions (le fichier `SKILL.md`), et souvent des scripts qu'il lance pour toi.

Un **plugin**, c'est l'emballage qui installe une ou plusieurs skills en une commande et les met à
jour. Ce dépôt est un **marketplace**, un catalogue de plugins : tu l'ajoutes une fois à Claude
Code, puis tu installes les plugins qui t'intéressent, un par un.

### Avec le marketplace

Dans Claude Code, ajoute le dépôt une fois :

```
/plugin marketplace add vincentventalon/my-claude-skills
```

puis installe le plugin que tu veux :

```
/plugin install video-editing@my-claude-skills
/plugin install search-console@my-claude-skills
```

C'est pareil sur macOS, Windows et Linux. Depuis un terminal, les mêmes commandes s'écrivent
`claude plugin marketplace add vincentventalon/my-claude-skills` puis
`claude plugin install video-editing@my-claude-skills`. Relance Claude Code après l'installation.

### À la main

Copie les skills d'un plugin dans le dossier des skills de Claude Code (ici `video-editing` ;
remplace par `search-console` pour l'autre).

macOS et Linux :

```sh
git clone https://github.com/vincentventalon/my-claude-skills.git
mkdir -p ~/.claude/skills
cp -R my-claude-skills/video-editing/skills/* ~/.claude/skills/
```

Windows (PowerShell) :

```powershell
git clone https://github.com/vincentventalon/my-claude-skills.git
New-Item -ItemType Directory -Force $HOME\.claude\skills | Out-Null
Copy-Item -Recurse -Force my-claude-skills\video-editing\skills\* $HOME\.claude\skills\
```

Pour un seul projet, copie dans `.claude/skills/` à la racine du projet au lieu de `~/.claude/skills/`.
Garde ensemble les skills d'un même plugin : elles renvoient l'une à l'autre. Installées à la main,
elles ne se mettent pas à jour toutes seules.

### Mettre à jour

Avec le marketplace, depuis un terminal :

```sh
claude plugin marketplace update my-claude-skills
claude plugin update video-editing@my-claude-skills
```

(ou le menu `/plugin` dans Claude Code), puis relance Claude Code.

À la main : `git -C my-claude-skills pull`, puis copie à nouveau.

## Ce que tu trouveras ici

- Des skills testées sur mes propres sites et mes propres vidéos avant d'arriver ici.
- Le calcul est dans des scripts, pas laissé au modèle : deux lancements donnent le même résultat.
- Pour chaque plugin, les prérequis et les pannes courantes, avec le message d'erreur que tu verras.
- Les scripts tournent sur ton ordinateur. Ce qui part ailleurs est dit : le son de ta vidéo si
  tu choisis ElevenLabs pour la transcription, les appels à l'API Google pour Search Console.

## Ce que tu ne trouveras pas ici

- La relecture dans le navigateur, les scènes (ta tête en petit, une capture en grand) et la
  motion : ce sont les outils avec lesquels je monte mes propres vidéos, ils sont dans
  [Pif Paf Cut Pro](https://pifpafcut.com/pro).
- La publication : les plugins s'arrêtent à la vidéo. Je programme les miennes avec
  [Nadia](https://usenadia.com).

## Signaler un problème, contribuer

Une panne, un message d'erreur qui n'est pas dans le README du plugin, une idée : ouvre une
[issue](https://github.com/vincentventalon/my-claude-skills/issues) avec le nom de la skill, ton
système (macOS, Windows, Linux) et le message exact. Une correction est la bienvenue en pull
request ; avant de l'envoyer, vérifie que le catalogue et les plugins restent valides :

```sh
claude plugin validate . --strict
claude plugin validate video-editing --strict
claude plugin validate search-console --strict
```

## In English

Claude Code skills I actually use on my own sites and videos, one new skill every Tuesday with my
newsletter. The video-editing plugin works in English as well as in French (its guide is in
French); search-console is written in French. Install with the commands above.

## Licence

MIT, voir [LICENSE](LICENSE).
