---
name: setup
description: Installe et configure le plugin video-editing (le montage de vidéos face caméra) - diagnostic de la machine (Python, ffmpeg avec libass pour les sous-titres, whisper.cpp et son modèle, clé ElevenLabs, Node pour Remotion, dossier de sortie), questionnaire (whisper ou ElevenLabs, langue, dossier de sortie, sous-titres, Remotion), installation de ce qui manque, puis ~/.config/video-editing/config.json. Use when the user says "installe la skill vidéo", "configure le montage", "set up video editing", "install the video editing skill", "je veux utiliser ElevenLabs", "change de moteur de transcription", "passe à whisper", "ma clé ElevenLabs", "il manque ffmpeg", "les sous-titres ne s'incrustent pas", or when the video-editing skill stops on a missing tool, model, key or setting.
---

# Installer le montage vidéo

Cette skill prépare l'ordinateur pour la skill de montage du même plugin (`video-editing`) :
elle regarde ce qui est installé, pose cinq questions, installe ce qui manque et écrit
`~/.config/video-editing/config.json`. Une fois au premier usage ; ensuite, seulement quand un
réglage change ou que le montage s'arrête sur un manque.

- Parle la langue de l'utilisateur. Le script écrit en français : traduis ce que tu en dis.
- `<setup>` = le dossier de ce fichier. Le script : `<setup>/scripts/setup.py`, bibliothèque
  standard seulement. `python3` sur macOS et Linux, `python` sur Windows.
- Une question par message, sauf les questions 2 à 5 (section 2), qui vont ensemble.
- Rien de payant, rien d'installé sans que l'utilisateur ait vu la commande.

## 1. Le diagnostic

```sh
python3 <setup>/scripts/setup.py --json
```

N'écrit rien. Chaque point de `constats` a un `etat` :

| etat | sens |
|---|---|
| `ok` | là et bon |
| `manque` | le montage ne peut pas tourner (`bloque: true`) |
| `a_faire` | setup ou le premier montage s'en charge (le modèle, le dossier de sortie, la config) |
| `option` | pas besoin avec les choix faits (whisper-cli quand on a choisi ElevenLabs) |
| `attention` | marche, mais à savoir (pas de Node : le titre est dessiné par ffmpeg) |

`corrige` donne les commandes exactes pour ce système ; une ligne `# ...` est une explication,
pas une commande. `pret` dit si le montage peut tourner tel quel.

Dis à l'utilisateur, en trois à six lignes, ce qui est là et ce qui manque. Pas le JSON, pas
les chemins sauf s'il les demande.

- **Première installation** (`config_etat` vaut `absente`) : tout le questionnaire (section 2).
- **Une seule chose à changer** (« passe à ElevenLabs », « coupe les sous-titres ») : seulement
  la question concernée, puis section 5. Les autres réglages restent tels quels.
- **Envoyée par le montage** : voir « Quand c'est le montage qui t'envoie » plus bas.

## 2. Le questionnaire

Pose la question 1 seule : c'est la seule qui demande une explication. Puis les questions 2 à 5
dans un même message, chacune avec son défaut ; « ok » garde tous les défauts. Si l'outil de
questions à choix (AskUserQuestion) est disponible, sers-t'en. N'invente aucune réponse : une
réponse floue prend le défaut, et tu le dis.

### Question 1 : le moteur de transcription

Le montage a besoin du texte de la vidéo, mot par mot, pour savoir où couper et pour les
sous-titres. Présente le choix tel quel, sans pousser l'un ou l'autre :

| | **whisper** (défaut) | **ElevenLabs Scribe** |
|---|---|---|
| Prix | gratuit | payant à l'usage, selon la durée du son (tarifs sur elevenlabs.io) |
| Où ça tourne | sur ton ordinateur, rien ne sort | le son de ta vidéo est envoyé à ElevenLabs |
| À installer | whisper.cpp et un modèle de 1,6 Go | rien : une clé d'API |
| Ce qu'il entend | bien ; un peu moins précis sur les reprises (une phrase redite juste après l'autre peut être avalée) et les noms propres | le meilleur verbatim : les reprises, les noms, les chiffres |

Ce qu'il faut savoir en plus :

- Avec ElevenLabs, la réponse est gardée sur l'ordinateur : remonter la même vidéo avec d'autres
  réglages ne repaie rien.
- On peut changer d'avis à tout moment : « passe à ElevenLabs », « reviens à whisper ».
- Pour commencer sans compte ni carte, whisper. ElevenLabs quand whisper laisse passer des
  reprises que tu entends.

Ordinateur modeste avec whisper (un PC sans carte graphique, 8 Go de mémoire, peu de place) :
propose un modèle plus léger, passé ensuite par `--modele` à `--ecris` :

| modèle | téléchargement | quand |
|---|---|---|
| `large-v3-turbo` (défaut) | 1,6 Go | Mac M1 ou plus récent, PC avec carte graphique |
| `large-v3-turbo-q5_0` | 0,57 Go | peu de place ou 8 Go de mémoire ; presque aussi bon |
| `small` | 0,49 Go | PC sans carte graphique, ou trop lent : plus rapide, rate un peu plus de reprises |

### Questions 2 à 5, ensemble

2. **La langue parlée dans tes vidéos ?** Défaut : la langue dans laquelle l'utilisateur
   t'écrit. Un code : `fr`, `en`, `es`, `de`...
3. **Où ranger les vidéos montées ?** Défaut : `~/Videos/edited`. Sur Mac, le dossier Vidéos
   du Finder est `~/Movies` : propose `~/Movies/edited` s'il veut les y retrouver.
4. **Sous-titres incrustés dans la vidéo ?** (quelques mots à la fois, le mot dit qui
   s'allume) Défaut : oui. Il faut un ffmpeg avec libass ; sur Mac, c'est `ffmpeg-full`.
5. **Titre et carton de fin animés avec Remotion ?** Défaut : oui si Node 18 ou plus est là
   (le diagnostic le dit), non sinon. Sans Remotion, ffmpeg dessine le titre et le carton,
   sans les animations, et la vidéo sort quand même. Avec, il faut Node ; le premier rendu
   installe Remotion tout seul (environ une minute, une fois).

## 3. La clé ElevenLabs (seulement si ElevenLabs)

La clé ne passe jamais par la conversation, ni par config.json, ni par une ligne de commande.
Dis à l'utilisateur :

1. Crée un compte sur elevenlabs.io, puis une clé d'API (dans les réglages développeur, « API
   Keys »). Si on te propose de limiter ses droits, garde seulement « Speech to Text ».
2. Copie la clé. **Ne la colle pas ici.**
3. Dis-moi « c'est copié ».

Puis lance, selon le système :

```sh
pbpaste | python3 <setup>/scripts/setup.py --cle-elevenlabs-stdin                      # macOS
Get-Clipboard | python <setup>/scripts/setup.py --cle-elevenlabs-stdin                  # Windows (PowerShell)
xclip -selection clipboard -o | python3 <setup>/scripts/setup.py --cle-elevenlabs-stdin # Linux (wl-paste sous Wayland)
```

Le script lit la clé sur son entrée, l'écrit dans `~/.config/video-editing/env` (mode 600) et ne
l'affiche jamais. « rien reçu » ou « pas la forme d'une clé » : le presse-papier contenait
autre chose, fais recopier. L'utilisateur peut aussi le faire seul, dans un terminal :
`python3 <setup>/scripts/setup.py --cle-elevenlabs-stdin` demande la clé sans l'afficher.

Si l'utilisateur colle quand même sa clé dans la conversation : ne la répète pas, ne l'écris
nulle part toi-même. Dis-lui qu'elle est maintenant dans l'historique de la conversation, qu'il
vaut mieux la supprimer sur ElevenLabs et en créer une autre, puis refais les étapes 2 et 3.

## 4. Installer ce qui manque

**macOS** : les installations passent par Homebrew.

```sh
python3 <setup>/scripts/setup.py --installe --a-blanc     # la liste, rien n'est lancé
```

Montre la liste à l'utilisateur ; sur son accord :

```sh
python3 <setup>/scripts/setup.py --installe
```

`ffmpeg-full` tire beaucoup de dépendances : plusieurs minutes, c'est normal. Il s'installe à
côté du `ffmpeg` de Homebrew sans le remplacer, et le montage le trouve tout seul.

Homebrew absent : la commande d'installation est dans le diagnostic. Elle demande le mot de
passe de l'ordinateur, c'est donc l'utilisateur qui la lance, dans son terminal. À la fin,
l'installeur affiche deux lignes « Next steps » à copier (elles mettent `brew` dans le PATH) :
qu'il les lance aussi, puis qu'il rouvre Claude Code.

**Windows** : les commandes `winget` du diagnostic. Lance-les si l'utilisateur est d'accord ;
ensuite il doit fermer et rouvrir le terminal et Claude Code, sinon les nouveaux outils ne sont
pas trouvés. whisper.cpp n'a pas de paquet winget : le diagnostic dit quoi télécharger.

**Linux** : les commandes `sudo` demandent un mot de passe, l'utilisateur les tape dans son
terminal. Donne-les telles que le diagnostic les écrit.

**Le modèle whisper** : demande « maintenant (1,6 Go) ou au premier montage ? ». Maintenant :

```sh
python3 <setup>/scripts/setup.py --modele
```

(en tâche de fond si tu peux, c'est long ; relancé après une coupure, il recommence). Au premier
montage : rien à faire, il se télécharge tout seul.

**Remotion** : rien à faire, le premier rendu l'installe.

## 5. Écrire la configuration

Avec les réponses, en ne passant que ce que l'utilisateur a choisi (le reste de config.json est
gardé) :

```sh
python3 <setup>/scripts/setup.py --ecris --moteur whisper --langue fr --sortie "~/Videos/edited" \
  --sous-titres oui --remotion oui --json
```

`--moteur whisper|elevenlabs`, `--langue <code>`, `--sortie <dossier>`, `--sous-titres oui|non`,
`--remotion oui|non`, `--modele <nom>`. La clé ElevenLabs peut venir dans le même appel
(`--cle-elevenlabs-stdin`, le presse-papier en entrée). `--ecris` crée aussi le dossier de
sortie, et retire de config.json une ligne `ffmpeg` qui pointe un ffmpeg disparu ou sans libass
quand le montage en trouve un meilleur tout seul.

La sortie contient le diagnostic refait. `pret: true` : dis-le, en une phrase, avec ce qu'il
faut dire pour la première vidéo : **« monte ma vidéo, les rushs sont dans Téléchargements »**.
Sinon, ce qui bloque encore, et retour à la section 4.

## Quand c'est le montage qui t'envoie

La skill de montage peut citer cette phrase :

> Il manque un outil, le modèle whisper, la clé ElevenLabs ou un réglage ? Suis la skill `setup`
> de ce plugin (`../setup/SKILL.md`, son diagnostic : `python3 ../setup/scripts/setup.py --json`),
> puis reprends le montage là où il s'est arrêté.

Dans ce cas, pas de questionnaire complet :

1. Le diagnostic (section 1).
2. Répare seulement ce qui a `bloque: true` (section 4). Pour la clé, la section 3.
3. Ne pose que les questions dont la réponse manque et sans laquelle le montage ne peut pas
   tourner (par exemple : ElevenLabs choisi, pas de clé → « tu as une clé, ou on passe à
   whisper ? »). Puis `--ecris` avec ces réponses seulement.
4. Rends la main au montage : relance la commande qui s'était arrêtée.

## Le contrat avec la skill de montage

`~/.config/video-editing/config.json`, toutes les clés facultatives ; sans clé, le montage prend
son défaut :

| clé | valeurs | sans la clé, le montage prend |
|---|---|---|
| `stt` | `"whisper"` ou `"elevenlabs"` | `whisper` |
| `whisper_model` | un nom (`large-v3-turbo`, `small`...) ou le chemin d'un `ggml-*.bin` | `large-v3-turbo`, cherché dans `~/.cache/whisper-cpp/` puis `~/.local/share/whisper-cpp/models/` |
| `ffmpeg` | le chemin d'un ffmpeg | le premier qui a libass (`ffmpeg-full` de Homebrew d'abord), sinon celui du PATH |
| `lang` | `"fr"`, `"en"`... | `en` |
| `output_dir` | un dossier, `~` accepté | `~/Videos/edited` |
| `subtitles` | `true` / `false` | `true` |
| `remotion` | `true` / `false` | `true` (sans Node, ffmpeg dessine le titre) |

La clé ElevenLabs : seulement dans la variable d'environnement `ELEVENLABS_API_KEY`, ou dans
`~/.config/video-editing/env` (mode 600, une ligne `ELEVENLABS_API_KEY=...`). Jamais dans
config.json. La variable d'environnement passe avant le fichier.

Ce que le montage en lit vraiment, et d'où vient chaque valeur :
`python3 <setup>/../video-editing/scripts/edit_video.py --config`.

## Pannes fréquentes

| ce qu'on voit | quoi faire |
|---|---|
| `command not found` juste après une installation | fermer et rouvrir le terminal et Claude Code |
| Mac : les sous-titres ne s'incrustent pas | la formule `ffmpeg` de Homebrew n'a pas libass : `brew install ffmpeg-full` |
| Mac : `brew` introuvable alors qu'il est installé | lancer les deux lignes « Next steps » de l'installeur Homebrew, rouvrir le terminal |
| Mac : Python 3.9 | c'est celui d'Apple : `brew install python` |
| le téléchargement du modèle s'est arrêté | `setup.py --modele` le recommence |
| ElevenLabs refuse la clé (401) | clé mal copiée ou supprimée : section 3 |
| ElevenLabs : quota épuisé | recharger le compte ElevenLabs, ou repasser à whisper (`--ecris --moteur whisper`) |

## Le banc

```sh
python3 <setup>/banc/test_setup.py                                   # tout, sans rien installer
python3 <setup>/scripts/setup.py --simule <setup>/banc/machines/mac-vide.json
```

Des machines simulées (`banc/machines/*.json` : un Mac neuf, un Mac avec le ffmpeg sans libass,
Linux, Windows...) disent chacune ce que le diagnostic doit y trouver. Le banc vérifie aussi ce
que `--ecris` et `--cle-elevenlabs-stdin` écrivent, dans un dossier jetable, et que la clé
n'apparaît jamais à l'écran.
