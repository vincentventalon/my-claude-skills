# video-editing : monter ses vidéos face caméra avec Claude Code

*La skill comprend aussi l'anglais : parle-lui dans ta langue (« edit my video »).
This guide is in French; the skill works just as well in English.*

## Ce que ça fait

Tu tournes face caméra, tu donnes tes rushs à Claude, il te rend la vidéo à publier.

- Les blancs, les faux départs et les reprises coupés : il garde ta **dernière** prise et ne coupe jamais un mot en deux.
- Le texte de la vidéo, mot par mot : avec **whisper**, sur ton ordinateur (gratuit), ou **ElevenLabs** (payant, plus précis).
- Les sous-titres incrustés, un titre sur les premières secondes, un carton de fin, la voix au volume des plateformes.
- En 9:16 pour TikTok, Reels et Shorts ; aussi en 16:9 pour YouTube quand tu as filmé à l'horizontale.
- Claude relit ensuite les prises comme un monteur. Ce qui reste à couper, tu le lui dis avec tes mots.

```
toi     monte ma vidéo, les rushs sont dans Téléchargements, titre « Mon *gros* conseil »
claude  Un rush de 9 min. Les blancs et 22 reprises coupés : il reste 1 min 58.
        Une phrase recommencée avec d'autres mots, que le script ne voit pas : je la coupe aussi.
        → ~/Videos/edited/IMG_4127.mp4 (9:16, sous-titres, titre, carton de fin)
toi     garde la pause après la blague
claude  Remise. Nouveau rendu, sans retranscrire.
```

## Installer en 3 étapes

1. Dans Claude Code, ajoute le catalogue de skills (une fois) :

   ```
   /plugin marketplace add vincentventalon/my-claude-skills
   ```

2. Installe le plugin, puis relance Claude Code :

   ```
   /plugin install video-editing@my-claude-skills
   ```

3. Dis **« installe la skill vidéo »**.

   Claude regarde ce qui est installé sur ta machine, te pose cinq questions (whisper ou
   ElevenLabs, la langue de tes vidéos, où ranger les vidéos montées, les sous-titres, Remotion),
   installe ce qui manque une fois que tu as vu les commandes, et écrit ta configuration dans
   `~/.config/video-editing/config.json`. Un réglage à changer plus tard : « passe à ElevenLabs »,
   « change le dossier de sortie ».

**Installée avant le 20 octobre 2026 avec `git clone` ?** Ce dépôt est devenu une collection de
skills : le dossier `~/.claude/skills/video-editing` que tu as cloné n'a plus la skill à sa
racine. Supprime-le, puis installe avec les étapes ci-dessus.

**Sans le système de plugins** : copie les deux dossiers `video-editing/skills/video-editing` et
`video-editing/skills/setup` de ce dépôt dans tes skills (macOS et Linux : `~/.claude/skills/`,
Windows : `C:\Users\<toi>\.claude\skills\`). Ils doivent rester côte à côte.

```sh
git clone https://github.com/vincentventalon/my-claude-skills /tmp/my-claude-skills
cp -R /tmp/my-claude-skills/video-editing/skills/video-editing /tmp/my-claude-skills/video-editing/skills/setup ~/.claude/skills/
```

## Prérequis

Tu n'as rien à installer à la main : l'étape 3 vérifie tout et donne la commande de ton
système ; sur Mac, elle lance les installations Homebrew avec ton accord. Ce tableau sert à
savoir à l'avance ce qui va arriver sur ta machine.

| Quoi | Pourquoi | macOS | Windows | Linux | Taille |
|---|---|---|---|---|---|
| Python 3.10 ou plus | les scripts du montage | `brew install python` | `winget install Python.Python.3.12` | `sudo apt install python3` | — |
| ffmpeg et ffprobe, avec libass | couper, assembler, rendre ; libass incruste les sous-titres | `brew install ffmpeg-full` | `winget install Gyan.FFmpeg` | `sudo apt install ffmpeg` | ~270 Mo avec ses dépendances (mesuré sur un Mac) |
| whisper.cpp *(si whisper)* | la transcription sur ton ordinateur | `brew install whisper-cpp` | `whisper-bin-x64.zip` des [releases](https://github.com/ggml-org/whisper.cpp/releases), à mettre dans le PATH | à compiler, la skill donne la commande | ~8 Mo (Mac) |
| le modèle `large-v3-turbo` *(si whisper)* | ce avec quoi whisper entend | se télécharge tout seul au premier montage | pareil | pareil | 1,6 Go |
| une clé ElevenLabs *(si ElevenLabs)* | la transcription chez ElevenLabs | — | — | — | — |
| Node 18 ou plus *(facultatif)* | Remotion anime le titre et le carton de fin ; sans Node, ffmpeg les dessine et la vidéo sort quand même | `brew install node` | `winget install OpenJS.NodeJS.LTS` | `sudo apt install nodejs npm` (vérifie `node -v`) | Remotion : ~250 Mo, installé tout seul au premier rendu, plus le navigateur qu'il télécharge pour rendre (à vérifier) |

- **Mac** : la formule `ffmpeg` de Homebrew est compilée sans libass. Avec elle, la vidéo sort sans
  sous-titres incrustés. `ffmpeg-full` s'installe à côté, sans rien remplacer, et le montage le
  trouve tout seul.
- **Mac** : le Python livré par Apple est en 3.9. `brew install python` en installe un plus récent.
- **Windows** : après un `winget install`, ferme et rouvre le terminal et Claude Code, sinon le
  nouvel outil n'est pas trouvé.

## Choisir son moteur de transcription

Le montage a besoin du texte de ta vidéo, mot par mot, pour savoir où couper et pour les
sous-titres. Deux moteurs, au choix, et tu peux changer quand tu veux (« passe à ElevenLabs »,
« reviens à whisper ») :

| | **whisper** (par défaut) | **ElevenLabs Scribe** |
|---|---|---|
| Prix | gratuit | payant à l'usage, à la minute de son ([tarifs](https://elevenlabs.io/pricing)) |
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
3. **Ce qu'il te demande** : ce qu'il ne peut pas deviner, le titre s'il n'en a pas, la version
   YouTube si tu as filmé à l'horizontale (à vérifier).
4. **Ce que tu obtiens**, dans ton dossier de sortie (`~/Videos/edited` par défaut), au nom de
   ton premier rush :

| Fichier | Ce que c'est |
|---|---|
| `<nom>.mp4` | la vidéo à publier, 1080×1920 : sous-titres, titre, carton de fin, voix à -14 LUFS |
| `<nom>.youtube.mp4` | la version 16:9 pour YouTube, quand tu l'as demandée et que tu as filmé à l'horizontale |
| `<nom>.cut.mp4` | le montage seul, cadré comme tu as filmé, sans texte |
| `<nom>.txt` · `<nom>.srt` | le texte de la vidéo, et les sous-titres avec leurs temps (CapCut, Premiere, YouTube) |
| `<nom>.ass` | les sous-titres, le titre et le carton tels qu'incrustés : du texte, un mot s'y corrige à la main |
| `<nom>.takes.tsv` | chaque morceau de ton rush, gardé ou coupé, avec ce que tu y dis |
| `<nom>.timeline.json` | les passages gardés et les mots, avec leurs temps dans la vidéo montée |

5. **Il reste quelque chose ?** « coupe la phrase sur le prix », « garde la pause après la
   blague », « change le titre », « dans les sous-titres, c'est cloud, pas clown ». Claude
   retrouve le moment et rend à nouveau, sans retranscrire.

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

## Ce que ça ne fait pas, et où c'est

Pas de page pour relire et couper à la souris (tu dis à Claude ce qu'il faut couper), pas de
scènes (ta tête en petit, une capture en grand), pas de motion design. Ça existe dans Pif Paf
Cut : [pifpafcut.com/pro](https://pifpafcut.com/pro).

## Publier

Le plugin s'arrête à la vidéo. Pour la programmer sur tes réseaux depuis Claude :
[Nadia](https://usenadia.com).

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

## Mettre à jour

Dans Claude Code, le menu `/plugin` ; ou dans un terminal :

```sh
claude plugin marketplace update my-claude-skills
claude plugin update video-editing@my-claude-skills
```

puis relance Claude Code. Ta configuration (`~/.config/video-editing/`) vit en dehors du plugin :
une mise à jour n'y touche pas. Après une mise à jour, « vérifie l'installation du montage » refait
le diagnostic.

## Pour qui maintient ce dépôt

`dev/` ne fait pas partie de la skill. `dev/check_edit.py` mesure un montage (durée, décalage
image et son, mots coupés aux jointures, redites restées). `dev/sync_from_private.py` reporte ici
les améliorations de coupe de ma chaîne privée et les teste sur un vrai rush ; lis son en-tête,
il ne commite ni ne pousse rien. Le banc de l'installation :
`python3 skills/setup/banc/test_setup.py` (des machines simulées, rien n'est installé).

## Licence

MIT — Vincent Ventalon.
