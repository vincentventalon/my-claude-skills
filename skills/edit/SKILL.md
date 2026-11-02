---
name: edit
description: Edits a talking-head video from the raw clips to the video you post, in one command - joins the clips, cuts the silences, the false starts and the retakes (the last take wins, never inside a word), transcribes word by word (whisper.cpp on the computer, or ElevenLabs Scribe with the user's key), burns in subtitles word by word, renders 9:16 for TikTok, Instagram Reels and Shorts in two views that take turns between sentences (full frame for the hook, then a split - a flat top zone over the camera in a rounded card - with the title and the boards on top and the subtitles on the seam), a title, boards on the words that say them (a figure, a list, a sentence), an end card, 16:9 for YouTube on request. macOS first, Windows, Linux. Use when the user says "edit my video", "cut the silences", "remove my retakes", "add subtitles", "add captions", "make it a TikTok / a Reel / a Short", "add boards", "split screen", "monte ma vidéo", "coupe les blancs", "enlève mes reprises", "ajoute des sous-titres", "mets un titre sur ma vidéo", "mets des cartons", "fais-en un TikTok / un Reel", or drops raw clips to edit.
---

# Edit a video

One command, one finished video:

```sh
python scripts/edit_video.py CLIP1.MOV CLIP2.MOV --lang fr --title "J'en ai *marre*"
```

(`scripts/` is in this skill's folder; `python3` on macOS / Linux if `python`
is missing.) It joins the clips in the order given, cuts what is not speech,
the false starts and the retakes, transcribes, and renders, next to `-o`
(default: `~/Videos/edited/<first clip name>.mp4`):

| file | what it is |
|---|---|
| `<name>.mp4` | **the video to post**: 1080x1920 for TikTok, Reels and Shorts, full frame and split taking turns (below), subtitles word by word, the title on top, the boards, the end card on the last seconds, the voice evened out to about -14 LUFS (the loudness the platforms play at) |
| `<name>.youtube.mp4` | with `--youtube`, 1920x1080, when the clips are horizontal |
| `<name>.cut.mp4` | the cut alone, as filmed, no text (for someone who finishes in their own editor) |
| `<name>.srt`, `<name>.txt` | the transcript of the video (the .srt can be uploaded as captions) |
| `<name>.ass` | the subtitles as burned in, plain text, with the title, the boards and the end card when ffmpeg draws them (not Remotion); `<name>.youtube.ass` for the 16:9 |
| `<name>.takes.tsv` | every island of sound, kept or cut and why, with its words |
| `<name>.timeline.json` | the kept passages and the words, with their times in the edited video; the views (`views`) and the boards placed (`boards`) |
| `<name>.state.json` | this video's state: the clips, the exact command of the last run (`command`), the steps done (`steps.edit`, then `steps.publish` written by the `publish` skill). The `video` skill reads it to pick the video up where it was left |

`*word*` in the title = highlighted, `" | "` = a new line. An iPhone clip
comes out upright, its HDR brought back to normal colours.

## The two views (the scene)

The 9:16 has two views, and by default (`--scene auto`) they take turns:

- **full frame**: the camera fills the screen (filmed sideways: in the middle
  on a blurred copy of itself; `--fit fill` crops it to fill). The title sits
  on top in a white box for its first seconds, the subtitles at the bottom of
  the middle third.
- **split**: a flat top zone (the style's background, anthracite by
  default) over the camera in a card with rounded corners, on the lower 58 %.
  The title and the boards are in the top zone, the subtitles on the seam.
  Filmed upright, the card shows the slice of the clip that starts 7 % down
  (the head of a selfie, chin included); filmed sideways, the whole clip at
  the card's width, not cropped. This geometry is fixed.

The rule of `auto`, the one the script applies (`plan_views` in
`scripts/finish.py`), and the one to explain when asked:

1. **The hook is full frame**: from 0 to the end of the first sentence that
   ends after 3 s (in practice 3 to 5 s).
2. **A sentence with a board on it is split**, the board in the top zone; a
   sentence with nothing to show is full frame.
3. **Never much more than 8 s without a change**: a full-frame run past 8 s
   turns split at the next sentence (the title at the top); after 8 s of
   split, the next board comes over the camera, in a box, in full frame.
4. **Without boards**, the two views take turns every 4 to 8 s, the split
   showing the title at the top. **With neither title nor boards**, full frame
   only (an empty top zone is not shown).
5. **Views only change between two sentences** (after a `.` `!` `?` or a
   pause; inside a sentence longer than 8 s, after a comma or where a pause
   was cut), never under a subtitle line, never once the end card is up, and
   a view lasts 2 s at least.

`--scene split` or `--scene full` keeps one view for the whole video (split:
the title stays at the top between the boards).

## Boards

A board is a card drawn on the word that says it, in the top zone of the
split (over the camera, in a box, in full frame). Three kinds, nothing more:

| kind | text | shows |
|---|---|---|
| `stat` | `"150 min \| = 3 h of work"` | the figure, big, in the accent colour (it counts up when it starts with a number), its caption under it |
| `list` | `"Cut \| Subtitles \| Publish"` | a numbered list, one item per part, the items coming in one by one |
| `text` | `"What I love: *teaching*"` | a sentence, `*word*` highlighted, `" \| "` = a new line |

They go in a JSON file passed with `--boards boards.json`:

```json
[
  {"say": "90 days", "text": "90 days | one video a day", "kind": "stat"},
  {"at": 21.7, "text": "Ten videos | 2.5 to 3 hours | Sunday, 5 pm", "kind": "list"}
]
```

`say` = the words that say it, as in `<name>.txt` (the board comes up on the
first of them, the first time they are said after the previous board); `at` =
the second in the edited video (`<name>.timeline.json`, `words`). A board
stays to the end of its sentence (2.5 s at least), never past the next one;
`"until": 30.5` holds it longer. `examples/boards.json` is a real one, for the
video whose transcript is `examples/jen-ai-marre.txt`.

**When the user says "add boards" / "mets des cartons"**, or when a first
render has a title but nothing else to show: read `<name>.txt` and propose
the boards before rendering, as a short list (the words that trigger each,
the kind, the text):

- a `stat` for every figure that matters (a duration, a price, a count), a
  `list` when they enumerate (steps, tools, reasons), a `text` for the one
  sentence they would want read; their words, shortened, never a fact they
  did not say;
- the first one on the first idea after the hook, then one every 5 to 10 s at
  most, 4 to 10 for a minute of video; a board that says the same as the
  subtitle under it is useless;
- `say` with 2 to 4 words copied from `<name>.txt` exactly (spelling
  included), so the board lands on the word.

Write the file next to the video (`<name>.boards.json`), run again with
`--boards`: it costs one render, not a new cut. The run lists the boards it
could not place (words not found).

## Ask the user — these three things, nothing else

1. **Where the clips are** (often the newest videos in `~/Downloads`; an
   AirDrop from an iPhone lands there), and their order if it is not the
   order of their names.
2. **The language they speak**, unless `--config` already shows `lang`.
3. **A title on top: yes or no.** Yes: their words, or offer one from what
   they say once the first run has written `<name>.txt` (a new title costs
   one render, not a new cut).

An audit of their account (`audit-*/AUDIT.md` in the current folder, or
one they give, written by the `audit` skill): read its "For the edit"
block ("Pour le montage") first, to offer a title shaped like `hook_style` /
`hook_example` (unless `title_on_screen` says no) and to give the edited
length next to `target_duration_s`. Nothing else changes.

The rest has a default: the end card says "Follow for more" in their
language ("Abonne-toi pour la suite" in French); change it only if they ask
(`--cta "..."`, `--no-cta`).

## First time

```sh
python scripts/edit_video.py --config
```

prints every setting, where it comes from (command line, then
`~/.config/video-editing/config.json`, then the default) and what is
installed. A tool missing (ffmpeg, libass, whisper-cli, the ElevenLabs key
with `stt` elevenlabs) or no config file yet (`(none: defaults)`): follow
this line, the one the `setup` skill (installed next to this one) waits for (it diagnoses,
shows the commands before installing anything, writes the settings):

> Il manque un outil, le modèle whisper, la clé ElevenLabs ou un réglage ? Suis la skill `setup`,
> installée à côté de celle-ci (`../setup/SKILL.md`, son diagnostic :
> `python3 ../setup/scripts/setup.py --json`), puis reprends le montage là où il s'est arrêté.

What setup installs, for reference:

| tool | for | macOS | Windows | Linux |
|---|---|---|---|---|
| Python 3.10+ | the scripts | `brew install python` | `winget install Python.Python.3.12` | already there |
| ffmpeg **with libass** | everything; libass burns the subtitles in | `brew install ffmpeg-full` (Homebrew's plain `ffmpeg` has no libass; the script finds `ffmpeg-full` by itself) | `winget install Gyan.FFmpeg` | `sudo apt install ffmpeg` |
| whisper-cli (whisper.cpp) | the local transcription | `brew install whisper-cpp` | `whisper-bin-x64.zip` from https://github.com/ggml-org/whisper.cpp/releases, unzipped, on the PATH | `sudo apt install whisper-cpp`, or build it |
| Node 18+ (optional) | Remotion draws the title, the boards and the end card, animated | `brew install node` | `winget install OpenJS.NodeJS.LTS` | `sudo apt install nodejs npm` |

The whisper model downloads itself on the first run into
`~/.cache/whisper-cpp/` (it is also found in
`~/.local/share/whisper-cpp/models/`):

| machine | `--model` | download | note |
|---|---|---|---|
| recent Mac (M1+) or PC with a GPU | nothing (`large-v3-turbo`) | 1.6 GB | the best |
| little disk space or RAM (8 GB) | `large-v3-turbo-q5_0` | 0.57 GB | almost as good |
| PC without a GPU, or too slow | `small` | 0.49 GB | several times faster on a CPU, catches a few less retakes |

When one is missing, the script says it and does what it can:

- no ffmpeg: it stops and says what to install;
- ffmpeg without libass: the video comes out without subtitles burned in
  (the .srt is written all the same), the title, the boards and the end card
  drawn by Remotion if Node is there, else none;
- no whisper-cli: silences only (no retake cut, no subtitles);
- no Node, or `remotion` off: ffmpeg draws the title, the boards and the
  end card (square boxes, a simple pop, no count-up); the video comes out all
  the same;
- `stt` = elevenlabs without a key: it stops before doing anything.

## The two transcription engines

Same output for both (words with their start and end), the cut and the
subtitles do not know which one spoke.

- **whisper** (default): whisper.cpp on this computer, free, nothing leaves
  it. Each island of sound is transcribed on its own, then the kept ones
  are heard again for the timing of each word (the subtitles light up the
  word being said).
- **elevenlabs**: ElevenLabs Scribe, paid on the user's ElevenLabs account,
  better on names and on the retakes whisper smooths over. One call for
  the whole video, kept in a cache (running again never pays twice).
  `--stt elevenlabs`, or `"stt": "elevenlabs"` in the config. The key is
  `ELEVENLABS_API_KEY`, in the environment or in
  `~/.config/video-editing/env` (a line `ELEVENLABS_API_KEY=...`, chmod
  600): the `setup` skill writes it, or the user does. **Never ask for the
  key in the chat, never print it, never put it in config.json.**

## What to do

1. Run the command. A 6 min rush takes about 2 to 3 minutes on a recent Mac.
2. Read what it prints: duration before / after, the retakes it cut (each
   quotes the words), and the `to check at 12.3s` lines (a repeat it saw
   but could not cut: no silence to cut in).
3. **Read the takes, like an editor.** Open `<name>.takes.tsv` and read the
   `kept` lines in order, as a script. The script only catches a retake
   that starts like the next one. Look for what it cannot see: a sentence
   abandoned and said again **in other words** just after ("let me show
   you the 5 steps" ... "in fact there are 5 ways, let me show you"), a
   lone fragment ("So..."). If you find one, run again with `--cut A:B`
   (the times of the abandoned lines, straight from the file) and the same
   `-o`. **In doubt, keep**: a repeat left costs a second pass, a sentence
   lost costs the video. Never cut something because it is off topic, a
   joke or an aside.
4. **Read `<name>.txt`** for misheard words (names, brands, jargon): run
   again with `--fix "heard=meant"` (`--fix "clode code=Claude Code"`); it
   fixes the subtitles, the .srt and the .txt.
5. **Look before handing it back**: stills of `<name>.mp4`
   (`ffmpeg -ss 1 -i <name>.mp4 -frames:v 1 a.png`), one in each view
   (`views` in `<name>.timeline.json`: the hook, a split, the last second),
   then read them: the title, a board, a subtitle on the seam, the end card,
   nothing over the face.
6. Hand back the path of the video, what you cut and why, the `to check`
   times if any, the views (how many turns), and the next step: boards if
   there are none yet ("mets des cartons"), then publishing with the
   `publish` skill (with Nadia, or a ready-to-post kit).

## What the user asks next

Run `edit_video.py` again with the **same clips and the same `-o`**, and
every option of the previous runs (`--cut`, `--protect`, `--fix`,
`--title`, `--cta`, `--noise`, `--boards`, `--scene`...: each run starts from
the clips). The last command is in `<name>.state.json` (`command`): start
from it, add the new option. It
re-transcribes nothing, and the cut is not rendered again when it did not
change.

| they say | you pass |
|---|---|
| "cut the part about the price" | `--cut A:B` (times from `<name>.takes.tsv`) |
| "keep the pause after the joke" | `--protect A:B` |
| "cut harder, there is background noise", nothing got cut | `--noise 25` (the islands change: the new ones are transcribed) |
| "in the subtitles it's cloud, not clown" | `--fix "clown=cloud"` |
| "another title", "no title" | `--title "..."`, `--title ""` |
| "another end card", "no end card" | `--cta "..."`, `--no-cta` |
| "add boards", "mets des cartons", "show the figures" | `--boards <name>.boards.json` (section Boards) |
| "full frame only", "no split", "only the split" | `--scene full`, `--scene split` |
| "a YouTube version" | `--youtube` (horizontal clips only; a vertical video goes on YouTube as a Short) |
| "no subtitles" | `--no-subtitles` |
| "just the cut, I finish it myself" | `--rough` (`-o` is then the cut) |
| "bigger subtitles", "another colour", "higher", "one word at a time", "another font" | the style (below) |

Say what you changed for each request; one you cannot place in the takes,
ask, do not guess.

## The look: style.json

`style.json` (next to `scripts/`) holds the defaults: Inter ExtraBold
(shipped, SIL OFL), white subtitles with the said word in mint green, an
anthracite top zone. To change the look,
write **only the keys that change** in `~/.config/video-editing/style.json`
(kept when the plugin updates), or in a file passed with `--style FILE`:

```json
{"captions": {"size": 130, "highlight": "#7CFF6B", "y": 0.62, "max_words": 1}}
```

| key | default | what |
|---|---|---|
| `font`, `font_file` | `Inter ExtraBold` (shipped; `Anton` too) | a font installed on the computer by its name, or `font_file` = the path of a .ttf / .otf and `font` = its family name |
| `captions.size` | 86 | px on the 1080x1920 frame |
| `captions.color`, `.highlight` | white, mint `#3DDC97` | the line, the word being said |
| `captions.outline`, `.outline_width`, `.shadow` | near black, 6, 2 | |
| `captions.max_words`, `.max_chars` | 3, 18 | words per line (1 = one word at a time) |
| `captions.uppercase`, `.punctuation`, `.pop` | false, false, true | |
| `captions.y` / `.y_wide` | 0.64 / 0.85 | full frame: height of the text centre, 0 = top, 1 = bottom (9:16 / 16:9); in the split they sit on the seam |
| `title.size`, `.color`, `.box`, `.highlight` | 92, near black on white, green `*word*` | full frame |
| `title.duration`, `.y` | 3.5 s, 0.17 | |
| `end_card.text` | "" = "Follow for more" in the language | |
| `end_card.size`, `.color`, `.box`, `.duration`, `.y` | 80, near black on mint, 3 s, 0.2 | |
| `split.background` | anthracite `#17181C` | the top zone and around the card |
| `split.text`, `.highlight`, `.title_size` | off-white, mint, 120 | the title and the boards on the top zone |
| `boards.size`, `.muted` | 104, grey | a board's size, the caption of a `stat` |
| `wide_scale` | 0.72 | sizes in 16:9 |
| `loudness` | -14 | LUFS aimed at, one even gain that never pushes a peak past -1.5 dBTP; `null` keeps the sound as recorded |

Keep the text away from the bottom fifth and the right edge of a 9:16:
TikTok and Instagram put their buttons and the caption there.

## Cut settings

| setting | default | when to touch it |
|---|---|---|
| `--min-sil` | 0.22 s | the edit feels breathless: 0.35; pauses left between sentences: 0.18 |
| `--noise` | 32 dB | background noise (street, fan) and nothing gets cut: 25 |
| `--pad` | 0.05 s | a word's ending sounds clipped: 0.08 |

`--keep-retakes` keeps every take (a deliberate repetition, a chorus),
`--keep-fillers` keeps the lone "um"s, `--no-transcript` skips the
transcription (silences only, no subtitles).

## When it fails

- A 0 s video or a `concat` error: the clips do not share the same format
  (an iPhone clip and another camera's): edit each clip alone.
- `nothing kept`: a very quiet recording, `--noise 40` (25 is for background noise).
- No subtitles on the video: `--config` says `NO libass` (install table above).
- `ElevenLabs refused the key` / `no credits left`: the key or the account;
  `--stt whisper` works meanwhile, free.

## Not in this skill

The review page in the browser with the audio check, the split fitted to
your own framing and the scenes measured on what works, the motion design:
the paid version, https://pifpafcut.com/pro.
