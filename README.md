# my-claude-skills

Les skills Claude Code que j'utilise vraiment, sur mes sites et pour mes vidéos.

Je suis Vincent. Je fais un challenge : une vidéo par jour pendant 100 jours sur [TikTok](https://www.tiktok.com/@vincentleserpent_), et une newsletter le mardi. Chaque mardi, un sujet que j'ai traité dans la semaine, mon process, et la skill qui m'a servi. Elle arrive ici le même jour.

## C'est quoi une skill, c'est quoi un plugin ?

Une **skill**, c'est un dossier que Claude Code lit quand tu lui demandes un travail précis : des
instructions (le fichier `SKILL.md`), et souvent des scripts qu'il lance pour toi. Tu n'as pas à
l'appeler par son nom : tu dis « fais-moi un compte rendu SEO de monsite.com », Claude reconnaît la
tâche et suit la skill.

Un **plugin**, c'est l'emballage qui permet d'installer une skill en une commande et de la mettre à
jour. Ce repo est un *marketplace*, un catalogue de plugins : tu l'ajoutes une fois à Claude Code,
puis tu installes les skills qui t'intéressent, une par une. Quand j'améliore une skill, le menu
`/plugin` (ou `claude plugin update <skill>@my-claude-skills`) te donne la nouvelle version.

## Les skills

| Skill | Ce qu'elle fait |
|---|---|
| [**search-console**](search-console/) | Un compte rendu SEO de ton site à partir de Google Search Console : ce qui bouge vraiment, ce qui n'est que du hasard, si une baisse vient de la demande ou de ton classement, et un tableau de bord qui se rafraîchit d'une phrase. |
| [**video-editing**](video-editing/) | Le dérushage d'une vidéo face caméra : silences et faux départs coupés, dernière prise gardée, transcription. En anglais. |

Chaque dossier a son README : ce que fait la skill, à quoi ça ressemble, ce qu'il faut installer avant.

## Installer

Dans Claude Code, ajoute le repo une fois, puis installe les skills que tu veux :

```
/plugin marketplace add vincentventalon/my-claude-skills
/plugin install search-console@my-claude-skills
/plugin install video-editing@my-claude-skills
```

Ou à la main : copie le dossier `<skill>/skills/<skill>` dans `~/.claude/skills/`.

## Ce que tu trouveras ici

- Des skills testées sur mes propres sites et mes propres vidéos avant d'arriver ici.
- Le calcul est dans des scripts, pas laissé au modèle : deux lancements donnent le même résultat.
- Pour chaque skill, les prérequis et les pannes courantes, avec le message d'erreur que tu verras.

## Pour suivre

La newsletter du mardi, où chaque nouvelle skill arrive en premier : [deviensdev.fr](https://deviensdev.fr).

## In English

Claude Code skills I actually use on my own sites and videos, one new skill every Tuesday with my newsletter. Most are written in French (search-console), the video editing one is in English. Install with the commands above.

## Licence

MIT
