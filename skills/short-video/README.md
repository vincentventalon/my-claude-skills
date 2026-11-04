# Le pack vidéo courte : tes TikTok, Reels et Shorts avec Claude Code

Huit skills, une par tâche, pour la vidéo courte face caméra sur TikTok, Instagram Reels et
YouTube Shorts : savoir ce qui marche déjà sur ton compte, ce qui explose dans ta niche, écrire le
script, tourner, monter le rush en vidéo à publier, découper une longue en shorts, publier sur les
trois plateformes. Pas d'application : les scripts tournent sur ton ordinateur (ffmpeg, whisper.cpp,
Remotion si tu as Node), et tu parles à Claude.

*Les skills `video`, `edit`, `clips`, `audit`, `outliers` et `publish` comprennent aussi l'anglais ;
`setup` et `script` sont écrites en français. This guide is in French.*

## Les skills

| Skill | Ce qu'elle fait |
|---|---|
| [`/video`](video/SKILL.md) | La porte d'entrée. Elle ne monte rien elle-même : tu dis ce que tu veux (« monte ma vidéo », « la suite », « publie-la »), elle retrouve la vidéo en cours (l'état est noté à côté de chaque vidéo : ses rushs, la dernière commande, les étapes faites) et passe la main à la skill qui fait le travail. |
| [`/setup`](setup/SKILL.md) | À lancer en premier, la seule skill qui installe. Regarde ce qui est installé (Python, ffmpeg avec libass pour les sous-titres, whisper.cpp et son modèle, Node, yt-dlp pour `audit`, `outliers` et `clips`), te fait choisir le moteur de transcription (whisper, gratuit et sur ton ordinateur, ou ElevenLabs Scribe, payant à l'usage, la clé jamais collée dans la conversation), pose tes réglages et installe ce qui manque une fois que tu as vu les commandes. macOS, Windows, Linux. |
| [`/audit`](audit/SKILL.md) | Ton propre compte TikTok ou Instagram : tes 30 dernières vidéos lues sans connexion, chacune comparée à la médiane de ton compte, ce que tu dis dans les 5 premières secondes transcrit sur ton ordinateur, et `AUDIT.md` : ce qui marche déjà chez toi, chiffres à l'appui, 3 tests à faire et un bloc que `edit` relit pour ton titre et ta durée. Gratuit. Instagram refuse presque toujours la lecture sans connexion : tu donnes alors tes chiffres. |
| [`/outliers`](outliers/SKILL.md) | Ce qui a explosé chez les comptes TikTok que tu suis : les 30 dernières vidéos de chaque compte lues sans connexion, chacune contre la médiane de son propre compte (×3 ou plus), les vidéos trop récentes et sponsorisées à part, les succès qui se répètent, le hook des 5 premières secondes transcrit sur ton ordinateur, une liste de comptes qui grandit avec toi, et 5 idées à refaire avec ta voix dans `OUTLIERS.md`, comme des tests. Gratuit ; Instagram à la main. |
| [`/script`](script/SKILL.md) · [guide](script/README.md) | Le script de ta prochaine vidéo courte : 3 hooks tirés de 22 formules nommées (un hook se récupère, il ne s'invente pas), 3 hooks texte pour l'écran, le script en beats « mais / donc » avec double payoff et appels à l'action aux coutures, les notes pour le montage, une passe anti-slop et le timing à ton débit, dans `script.md`. Part de ton audit et de tes outliers s'ils sont dans le dossier. |
| [`/edit`](edit/SKILL.md) · [guide](edit/README.md) | Ton rush en vidéo à publier, en une commande : rushs joints, blancs, faux départs et reprises coupés (ta dernière prise gagne), texte mot à mot par whisper ou ElevenLabs, plein cadre et split qui alternent entre deux phrases, ton titre, des cartons (un chiffre, une liste, une phrase) sur le mot qui les dit, sous-titres mot à mot, carton de fin, voix à -14 LUFS, en 9:16 (16:9 pour YouTube), plus le `.srt` pour CapCut ou Premiere. Ce qui reste à couper, tu le lui dis avec tes mots. |
| [`/clips`](clips/SKILL.md) | Une longue (un lien YouTube, un podcast, un live, un fichier) en shorts finis : le transcript lu dans les sous-titres YouTube avec yt-dlp (ou transcrit sur ton ordinateur par `edit`), les moments qui tiennent seuls (une idée, 20 à 60 s) trouvés et notés sur 10, le plan dans `clips/<source>.md`, puis chaque clip que tu choisis coupé en rush et monté par `edit` (coupes, titre, cartons, sous-titres, 9:16). Les idées trop étalées pour être coupées deviennent des scripts à tourner, écrits par `script`. |
| [`/publish`](publish/SKILL.md) | La vidéo finie en ligne sur TikTok et Instagram (YouTube Shorts si tu le demandes) : les descriptions de TikTok et d'Instagram tirées de ce que tu dis (la recherche en première ligne, une phrase par ligne, le mot à commenter quand tu envoies une ressource, 4 à 6 hashtags), le plan montré, puis, après ton « oui », programmée avec le connecteur Claude de [Nadia](https://usenadia.com) : jamais tout de suite, un seul post par plateforme, TikTok et Instagram à la même heure. Sans Nadia, un kit prêt à poster (`post.md`, la couverture, où cliquer). |

Tu n'es pas obligé de taper le nom d'une skill : dis à Claude ce que tu veux, il reconnaît la tâche.
Tu ne sais pas laquelle prendre ? **`/video <ce que tu veux>`** la choisit pour toi et reprend
la vidéo en cours au lieu de repartir de zéro.

## Le parcours

```text
/setup            une fois : les outils, le moteur de transcription, tes réglages
/audit            ce qui marche sur ton compte              → AUDIT.md
/outliers         ce qui a explosé dans ta niche            → OUTLIERS.md, 5 idées à refaire
/script           le script de la prochaine vidéo           → script.md
                  tu tournes
/edit             ton rush → la vidéo à publier             → ~/Videos/edited/<nom>.mp4
/clips            une longue → des shorts finis, par edit    → clips/<source>.md, ~/Videos/edited/<slug>.mp4
/publish          TikTok, Instagram Reels, YouTube Shorts    → Nadia, ou post.md
```

`/video <ce que tu veux>` à n'importe quelle étape : elle sait où tu en es.

Les skills se passent le relais par des fichiers posés dans ton dossier : `script` lit
`AUDIT.md` et `OUTLIERS.md` s'ils sont là, `edit` relit le bloc « Pour le montage » de l'audit et
du script pour te proposer le titre et la durée, `publish` et `video` repartent de l'état que
`edit` laisse à côté de chaque vidéo (`<nom>.state.json`).

## Ce que `edit` rend par défaut

- **Les coupes** : les blancs, les faux départs et les reprises partent, ta dernière prise reste,
  et une coupe ne tombe jamais au milieu d'un mot.
- **Deux vues qui alternent** : le hook en plein cadre, ton titre posé dessus ; puis un split,
  un haut en aplat anthracite et toi dans une carte aux coins arrondis en bas. Elles changent
  toujours entre deux phrases, en visant 4 à 8 secondes par vue.
- **Des cartons sur le mot qui les dit** : un chiffre qui défile jusqu'à sa valeur, une liste
  numérotée, une phrase. Dis « mets des cartons » : Claude les propose à partir de ce que tu dis.
- **Les sous-titres** mot à mot, le mot dit en vert, sur la couture du split.
- **Un carton de fin** (« Abonne-toi pour la suite » dans ta langue), la voix à -14 LUFS, le
  volume des plateformes.
- **En 9:16** pour TikTok, Instagram Reels et YouTube Shorts ; en 16:9 pour YouTube si tu as
  filmé à l'horizontale.

Le style (police, couleurs, taille des sous-titres, couleur du haut) se change dans
`~/.config/video-editing/style.json` : « mets mes sous-titres en jaune », « un haut gris clair ».
Ce qu'une vidéo produit, sur un vrai exemple : [edit/examples/](edit/examples/). Le détail du
montage (les prérequis par système, whisper ou ElevenLabs, les fichiers rendus, les pannes
courantes) : [le guide de `edit`](edit/README.md).

## Ce que le pack ne fait pas, et où c'est

- La relecture dans le navigateur, le split réglé sur ton propre cadrage, les scènes mesurées sur
  ce qui marche, le motion design : [Pif Paf Cut Pro](https://pifpafcut.com/pro), c'est avec ça
  que je monte mes vidéos.
- Plus de hooks que les 22 formules de `script` (la recherche parmi des milliers de vrais hooks
  qui ont marché) et la programmation des posts : le connecteur Claude de
  [Nadia](https://usenadia.com).

## Installer

Le pack s'installe seul ou avec le pack SEO, de trois façons (npx skills, le plugin Claude Code
`short-video`, à la main) : [le README du dépôt](../../README.md#installer). Puis, trois étapes jusqu'à
ta première vidéo montée :

1. **Ouvre Claude Code** dans le dossier de ton projet.
2. **`/setup`** (ou « installe la skill vidéo ») : Claude regarde ce qui est installé sur ta
   machine, te fait choisir whisper ou ElevenLabs, pose ta langue et ton dossier de sortie, et
   installe ce qui manque une fois que tu as vu les commandes. Une fois.
3. Tourne une prise (téléphone, webcam, caméra), puis **`/edit`** : « monte ma vidéo, le rush est
   dans Téléchargements, titre : J'en ai *marre* ». Tu obtiens `~/Videos/edited/<nom>.mp4`, plus le
   texte, les sous-titres en `.srt` et l'état de la vidéo.

### Ce qu'il faut sur ta machine

`/setup` vérifie tout et donne la commande de ton système. En clair : Python 3.10 ou plus, ffmpeg
avec libass (sur Mac, `ffmpeg-full` de Homebrew, la formule `ffmpeg` sort sans sous-titres),
whisper.cpp et son modèle (1,6 Go, téléchargé une fois) ou une clé ElevenLabs, Node pour que
Remotion anime le titre et les cartons (sans Node, ffmpeg les dessine et la vidéo sort quand
même), yt-dlp pour `audit`, `outliers` et `clips`. Le tableau par système, avec les tailles :
[le guide de `edit`](edit/README.md#prérequis).

Ce qui part de ta machine, et seulement si tu le choisis : le son de ta vidéo vers ElevenLabs, ta
vidéo et ses textes vers Nadia quand tu publies avec elle. Rien ne se publie sans ton « oui ».

## Mettre à jour, signaler un problème

Les commandes de mise à jour : [le README
du dépôt](../../README.md#mettre-à-jour). Une panne : la table des pannes courantes du
[guide de `edit`](edit/README.md#problèmes-fréquents), sinon une
[issue](https://github.com/vincentventalon/my-claude-skills/issues) avec le nom de la skill, ton
système et le message exact.
