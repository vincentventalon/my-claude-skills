# edit : monter ses vidéos face caméra avec Claude Code

*La skill comprend aussi l'anglais : parle-lui dans ta langue (« edit my video »).
This guide is in French; the skill works just as well in English.*

## Ce que ça fait

Tu tournes face caméra, tu donnes tes rushs à Claude, il te rend la vidéo à publier.

- Les blancs, les faux départs et les reprises coupés : il garde ta **dernière** prise et ne coupe jamais un mot en deux.
- Le texte de la vidéo, mot par mot : avec **whisper**, sur ton ordinateur (gratuit), ou **ElevenLabs** (payant, plus précis).
- Les sous-titres incrustés, un titre sur les premières secondes, un carton de fin, la voix au volume des plateformes.
- Deux vues qui alternent entre deux phrases : plein cadre pour le hook, puis un split (un haut en aplat, toi dans
  une carte aux coins arrondis en bas, les sous-titres sur la couture), avec ton titre et tes cartons en haut.
- Des cartons sur le mot qui les dit : un chiffre, une liste, une phrase. Dis « mets des cartons », Claude les
  propose à partir de ce que tu dis.
- En 9:16 pour TikTok, Reels et Shorts ; aussi en 16:9 pour YouTube quand tu as filmé à l'horizontale.
- Claude relit ensuite les prises comme un monteur. Ce qui reste à couper, tu le lui dis avec tes mots.
- Avant de monter, la skill `audit-my-account` mesure ce qui marche déjà sur ton compte TikTok.

```
toi     monte ma vidéo, les rushs sont dans Téléchargements, titre « Mon *gros* conseil »
claude  Un rush de 9 min. Les blancs et 22 reprises coupés : il reste 1 min 58.
        Une phrase recommencée avec d'autres mots, que le script ne voit pas : je la coupe aussi.
        → ~/Videos/edited/IMG_4127.mp4 (9:16, plein cadre et split, sous-titres, titre, carton de fin)
toi     mets des cartons
claude  Six cartons : « 15 min » sur « quinze minutes », la liste des trois étapes… Je rends ?
toi     oui, et garde la pause après la blague
claude  Remise. Nouveau rendu, sans retranscrire.
```

## Installer

Dans un terminal, dans le dossier de ton projet :

```sh
npx skills add vincentventalon/my-claude-skills -a claude-code
```

(ou le plugin Claude Code : [le README du dépôt](../../../README.md#installer)), puis, dans Claude Code,
dis **« installe la skill vidéo »** (ou `/set-up-video-tools`).

Claude regarde ce qui est installé sur ta machine, te pose sept questions (whisper ou ElevenLabs,
la langue de tes vidéos, où ranger les vidéos montées, les sous-titres, Remotion, la police, la
couleur du mot dit), installe ce qui manque une fois que tu as vu les commandes, et écrit ta
configuration dans `~/.config/video-editing/config.json` (la police et la couleur dans `style.json`).
Un réglage à changer plus tard : « passe à ElevenLabs », « change le dossier de sortie », « change ma
police ».

Les skills `set-up-video-tools` et `edit-my-video` doivent rester côte à côte (elles se renvoient l'une à l'autre) :
les deux installations les posent ainsi.

## Prérequis

Tu n'as rien à installer à la main : l'étape 3 vérifie tout et donne la commande de ton
système ; sur Mac, elle lance les installations Homebrew avec ton accord. Ce tableau sert à
savoir à l'avance ce qui va arriver sur ta machine.

| Quoi | Pourquoi | macOS | Windows | Linux | Taille |
|---|---|---|---|---|---|
| Python 3.10 ou plus | les scripts du montage | `brew install python` | `winget install Python.Python.3.12` | `sudo apt install python3` | — |
| ffmpeg et ffprobe, avec libass | couper, assembler, rendre ; libass incruste les sous-titres | `brew install ffmpeg-full` | `winget install Gyan.FFmpeg` | `sudo apt install ffmpeg` | ~270 Mo avec ses dépendances (mesuré sur un Mac) |
| whisper.cpp *(si whisper)* | la transcription sur ton ordinateur | `brew install whisper-cpp` | la skill `set-up-video-tools` télécharge le zip officiel (GitHub) dans `%LOCALAPPDATA%\whisper.cpp`, sans toucher au PATH ; il lui faut le Visual C++ Redistributable de Microsoft, que `set-up-video-tools` vérifie | à compiler, la skill donne la commande | ~8 Mo (Mac), ~23 Mo (Windows) |
| le modèle `large-v3-turbo` *(si whisper)* | ce avec quoi whisper entend | se télécharge tout seul au premier montage | pareil | pareil | 1,6 Go |
| une clé ElevenLabs *(si ElevenLabs)* | la transcription chez ElevenLabs | — | — | — | — |
| Node 18 ou plus *(facultatif)* | Remotion anime le titre, les cartons et le carton de fin ; sans Node, ffmpeg les dessine et la vidéo sort quand même | `brew install node` | `winget install OpenJS.NodeJS.LTS` | `sudo apt install nodejs npm` (vérifie `node -v`) | Remotion : ~400 Mo, installé tout seul au premier rendu, plus ~200 Mo pour le navigateur qu'il télécharge pour rendre (mesuré sur un Mac) |
| yt-dlp *(pour les skills `audit-my-account` et `find-outliers-in-my-niche`)* | lire les comptes sans connexion ; `set-up-video-tools` l'installe avec le reste | `brew install yt-dlp` | `winget install yt-dlp.yt-dlp` | `pipx install yt-dlp` | — |

- **Mac** : la formule `ffmpeg` de Homebrew est compilée sans libass. Avec elle, la vidéo sort sans
  sous-titres incrustés. `ffmpeg-full` s'installe à côté, sans rien remplacer, et le montage le
  trouve tout seul.
- **Mac** : le Python livré par Apple est en 3.9. `brew install python` en installe un plus récent.
- **Windows** : après l'installation de Python ou de Node, ferme et rouvre le terminal et Claude
  Code, sinon le nouvel outil n'est pas trouvé (ffmpeg et whisper.cpp, eux, sont trouvés tout de
  suite). Les commandes Python s'y tapent avec `py`.

## Choisir son moteur de transcription

Le montage a besoin du texte de ta vidéo, mot par mot, pour savoir où couper et pour les
sous-titres. Deux moteurs, au choix, et tu peux changer quand tu veux (« passe à ElevenLabs »,
« reviens à whisper ») :

| | **whisper** (par défaut) | **ElevenLabs Scribe** |
|---|---|---|
| Prix | gratuit | payant à l'usage, selon la durée du son ([tarifs](https://elevenlabs.io/pricing)) |
| Où ça tourne | sur ton ordinateur, rien ne sort | le son de ta vidéo est envoyé à ElevenLabs |
| À installer | whisper.cpp et un modèle de 1,6 Go | rien : une clé d'API |
| Ce qu'il entend | bien ; un peu moins précis sur les reprises (une phrase redite juste après l'autre peut être avalée) et sur les noms propres | le meilleur verbatim : les reprises, les noms, les chiffres |
| Remonter la même vidéo | rien à retranscrire | la réponse est gardée sur ton ordinateur : tu ne paies pas deux fois |

Pour commencer sans compte ni carte : whisper. ElevenLabs quand whisper laisse passer des
reprises que tu entends, toi.

**Poser la clé ElevenLabs.** Crée une clé d'API sur elevenlabs.io (si on te propose de limiter
ses droits, « Speech to Text » suffit). Copie-la, **ne la colle pas dans la conversation**, et
dis à Claude « c'est copié » : il la lit dans ton presse-papier
(`pbpaste | python3 …/setup.py --cle-elevenlabs-stdin`) et l'écrit dans
`~/.config/video-editing/env`, lisible par toi seul. Elle n'apparaît jamais à l'écran ni dans
`config.json`. Si tu préfères, une variable d'environnement `ELEVENLABS_API_KEY` marche aussi.

**Ordinateur modeste ?** Avec whisper, le modèle par défaut est le meilleur, mais il pèse.

| ton ordinateur | dis à Claude | téléchargement |
|---|---|---|
| Mac M1 ou plus récent, PC avec carte graphique | rien, c'est le défaut (`large-v3-turbo`) | 1,6 Go |
| peu de place, 8 Go de mémoire | « prends le modèle large-v3-turbo-q5_0 » | 0,57 Go, presque aussi bon |
| PC sans carte graphique, ou c'est trop lent | « prends le modèle small » | 0,49 Go, plusieurs fois plus rapide, rate un peu plus de reprises |

`medium` ne vaut pas le coup : aussi lourd que le défaut, et plus lent.

## Première vidéo

1. **Tourne comme tu parles.** Une phrase ratée ? Redis-la jusqu'à ce qu'elle soit juste, et
   enchaîne : la dernière prise gagne.
2. **Dis à Claude** : « monte ma vidéo, les rushs sont dans Téléchargements ». Donne le titre si
   tu l'as : « titre : Mon *gros* conseil » (les `*` mettent un mot en couleur).
3. **Ce qu'il te demande** : où sont tes rushs (et leur ordre, si ce n'est pas celui des noms), ta
   langue si ta configuration ne la donne pas, et si tu veux un titre : le tien, ou il t'en propose
   un d'après ce que tu dis. Le reste a un défaut : le carton de fin dit « Abonne-toi pour la
   suite ». La version YouTube, c'est toi qui la demandes, si tu as filmé à l'horizontale. Si tu as
   fait l'audit de ton compte (plus bas), il s'en sert pour te proposer le titre et la durée à viser.
4. **Ce que tu obtiens**, dans ton dossier de sortie (`~/Videos/edited` par défaut), au nom de
   ton premier rush :

| Fichier | Ce que c'est |
|---|---|
| `<nom>.mp4` | la vidéo à publier, 1080×1920 : plein cadre et split, sous-titres, titre, cartons, carton de fin, voix à -14 LUFS |
| `<nom>.youtube.mp4` | la version 16:9 pour YouTube, quand tu l'as demandée et que tu as filmé à l'horizontale |
| `<nom>.cut.mp4` | le montage seul, cadré comme tu as filmé, sans texte |
| `<nom>.txt` · `<nom>.srt` | le texte de la vidéo, et les sous-titres avec leurs temps (CapCut, Premiere, YouTube) |
| `<nom>.ass` | les sous-titres tels qu'incrustés, en texte (avec le titre et le carton quand c'est ffmpeg qui les dessine, pas Remotion) |
| `<nom>.takes.tsv` | chaque morceau de ton rush, gardé ou coupé, avec ce que tu y dis |
| `<nom>.timeline.json` | les passages gardés et les mots, avec leurs temps dans la vidéo montée ; les vues et les cartons |
| `<nom>.state.json` | où en est la vidéo : les rushs, la dernière commande, les étapes faites (montage, publication). « reprends ma vidéo » repart de là |

5. **Il reste quelque chose ?** « coupe la phrase sur le prix », « garde la pause après la
   blague », « change le titre », « mets des cartons », « que du plein cadre », « dans les
   sous-titres, c'est cloud, pas clown ». Claude retrouve le moment et rend à nouveau, sans
   retranscrire.

### Les deux vues et les cartons

- **Plein cadre** : tu remplis l'écran. Le hook (les 3 à 5 premières secondes) est toujours en
  plein cadre, ton titre posé dessus dans un cadre blanc.
- **Split** : un haut en aplat (anthracite par défaut), toi en bas dans une carte aux coins
  arrondis (58 % de la hauteur), les sous-titres sur la couture. Ton titre et tes cartons sont
  en haut. Filmé à la verticale, la carte montre ta tête (la tranche qui commence à 7 % du haut
  de l'image) ; filmé à l'horizontale, ton image entière, sans recadrage.
- **L'alternance** : une phrase avec un carton passe en split, une phrase sans rien à montrer en
  plein cadre, jamais beaucoup plus de 8 secondes sans changer, et toujours entre deux phrases.
  Sans carton, les deux vues alternent toutes les 4 à 8 secondes, ton titre en haut du split.
  Sans titre ni carton : plein cadre seulement.
- « que du plein cadre » ou « que du split » : une seule vue pour toute la vidéo.
- **Les cartons** : trois formes, un chiffre (« 15 min », qui défile jusqu'à sa valeur), une
  liste numérotée, une phrase. Ils tombent sur le mot qui les dit. Claude te les propose à partir
  du texte de ta vidéo ; un vrai exemple : [examples/boards.json](examples/boards.json), pour la
  vidéo dont le texte est [examples/jen-ai-marre.txt](examples/jen-ai-marre.txt).
- **Le style** : Inter ExtraBold, le mot dit en vert menthe. Tout se change dans
  `~/.config/video-editing/style.json` (seulement les clés qui changent) : « mets mes sous-titres
  en jaune », « un haut gris clair ». La géométrie du split, elle, est fixe.

### Comment il coupe

- **Le son décide où couper.** L'audio est découpé en îlots de son, ce qu'il y a entre deux
  silences. Une coupe ne tombe que dans un silence, jamais au milieu d'un mot.
- **La transcription dit quoi.** Avec whisper, chaque îlot est transcrit seul : d'un seul
  tenant, whisper colle deux prises en une phrase et n'écrit la redite qu'une fois.
- **La dernière prise gagne.** Un îlot qui est le début de ce que tu dis juste après était un
  faux départ : il part, la dernière prise reste.
- **Claude relit les prises comme un monteur.** Une phrase abandonnée puis redite *avec d'autres
  mots*, seul un lecteur la voit : il la coupe d'une commande de plus, sans retranscrire. Dans le
  doute, il garde.

## Auditer ton compte avant de monter

La skill `audit-my-account` mesure ce qui marche déjà sur ton compte TikTok (TikTok seulement), sur tes propres
vidéos, sans connexion, et écrit `AUDIT.md` avec un bloc « Pour le montage ». Au montage suivant,
Claude relit ce bloc pour te proposer le titre et la durée à viser. Dis « audite mon compte
TikTok » ou colle le lien de ton profil ; le détail est dans [sa SKILL.md](../audit-my-account/SKILL.md).

## Ce que ça ne fait pas, et où c'est

Pas de page pour relire et couper à la souris (tu dis à Claude ce qu'il faut couper), pas de
split réglé sur ton propre cadrage ni d'autres scènes, pas de motion design, pas de choix du style :
un seul style de base, dont tu choisis la police et la couleur à l'installation. Choisir son style
(sept looks ou le sien, réglé sur sa propre prise), c'est dans Pif Paf Cut, avec le reste :
[pifpafcut.com/skill](https://pifpafcut.com/skill).

## Publier

La skill `publish-my-video` prend la vidéo finie : avec le connecteur Claude de [Nadia](https://usenadia.com),
elle la programme sur TikTok et Instagram après ton « oui » ; sans Nadia, elle te prépare un kit
prêt à poster (`post.md` : titre, descriptions, hashtags, couverture, où cliquer).

## Problèmes fréquents

| Ce que tu vois | Quoi faire |
|---|---|
| `command not found` juste après une installation | ferme et rouvre le terminal et Claude Code |
| Mac : la vidéo sort sans sous-titres incrustés | la formule `ffmpeg` de Homebrew n'a pas libass : `brew install ffmpeg-full` (ou dis « installe la skill vidéo », il le voit) |
| Mac : `brew` introuvable juste après l'avoir installé | lance les deux lignes « Next steps » que l'installeur de Homebrew a affichées, puis rouvre le terminal |
| le premier montage est long | le modèle whisper (1,6 Go) se télécharge, une seule fois |
| le téléchargement du modèle s'est arrêté | « relance le téléchargement du modèle whisper » |
| rien n'est coupé, il y a du bruit de fond (rue, ventilateur) | « coupe plus fort, il y a du bruit » (le seuil de silence, `--noise 25`) |
| une vidéo de 0 s ou une erreur `concat` | tes rushs n'ont pas le même format (taille, images par seconde) : monte-les un par un |
| ElevenLabs refuse la clé | clé mal copiée ou supprimée : « change ma clé ElevenLabs » |
| c'est lent, sur un PC sans carte graphique | « prends le modèle small » |
| savoir quels réglages il utilise | « montre-moi la configuration du montage » (`edit_video.py --config`) |
| le split coupe ma tête (cadrage très serré ou très large) | « que du plein cadre » (`--scene full`) ; régler le split sur ton cadrage, c'est la version payante |
| un carton n'apparaît pas | ses mots ne sont pas dits tels quels dans `<nom>.txt` : Claude reprend les mots exacts, ou un instant (`at`) |

## Mettre à jour

Installé avec `npx skills` : `npx skills update`. Avec le plugin Claude Code : les commandes du
[README du dépôt](../../../README.md#mettre-à-jour), puis relance Claude Code. Ta configuration (`~/.config/video-editing/`) vit en dehors des skills : une mise à jour n'y
touche pas. Après une mise à jour, « vérifie l'installation du montage » refait le diagnostic.

## Pour qui maintient ce dépôt

`dev/edit/`, à la racine du dépôt, ne fait pas partie de la skill (rien n'en est installé).
`dev/edit/check_edit.py` mesure un montage (durée, décalage image et son, mots coupés aux
jointures, redites restées). `dev/edit/sync_from_private.py` reporte ici les améliorations de
coupe de ma chaîne privée et les teste sur un vrai rush ; lis son en-tête, il ne commite ni ne
pousse rien. `dev/edit/test_stt.py` teste le chemin ElevenLabs sans réseau. Le banc de
l'installation : `python3 skills/short-video/set-up-video-tools/banc/test_setup.py` (des machines simulées, rien n'est
installé).

## Licence

MIT — Vincent Ventalon.
