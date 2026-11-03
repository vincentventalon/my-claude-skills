---
name: video
description: The entry point for every video job - say what you want, it picks the right skill (setup, edit, audit, outliers, script, publish) and picks up the video in progress instead of starting over, from the state the edit leaves next to the video (<name>.state.json - which clips, the last command, the steps done). Use when the user says /video, "monte ma vidéo", "reprends ma vidéo", "où j'en suis", "la suite", "audite mon compte", "écris-moi un script", "publie-la", "edit my video", "pick up my video", "what's next", "publish it", or is not sure which video skill to use.
argument-hint: "[what you want] [clip | video | path]"
---

# Video

Send the request to the one skill that does it, then do the work with that
skill. Never edit, write or publish with your own method: every rule lives in
the target skill. Talk in the user's language.

## 1. Continue before you start

The request is often the next step of a video already under way. Find it
before choosing:

1. **This conversation** already works on a video (a clip just edited, a
   script just written, boards just proposed): that is the one. Apply the
   change with the skill already in use, run its step again with the same
   files, never from scratch.
2. **The state files.** `edit` writes `<name>.state.json` next to every
   video it makes. Look in the output folder (`output_dir` of
   `~/.config/video-editing/config.json`, else `~/Videos/edited`) and in the
   current folder:

   ```sh
   ls -t "<output_dir>"/*.state.json ./*.state.json 2>/dev/null | head -5
   ```

   The request names a video (its name, a clip, a word of its title): that
   one. It says "my video", "it", "the last one", "la suite": the newest. Two
   or more could fit and nothing tells them apart: ask, one question, listing
   them (name, title, date of `steps.edit.done`).
3. Nothing found: a new video.

Say in one line which video you pick up and where it is ("I pick up
IMG_4127, edited today at 18:02, not published yet").

### The state file

`<name>.state.json`, one per video, next to it. `edit` writes it at each
run; other skills only add their step under `steps` and never remove
anything.

| key | what |
|---|---|
| `video` | the name (`<name>.mp4` is the video to post) |
| `clips` | the raw clips, absolute paths, in order |
| `command` | the exact command of the last edit: run it again, plus the new option, for any change |
| `final`, `youtube` | the 9:16 to post, the 16:9 when there is one (`null` otherwise) |
| `duration`, `lang`, `title`, `boards` | the edited length, the language, the title on screen, the boards file |
| `steps.edit` | `done` (date), `rough` (only the cut) |
| `steps.publish` | written by `publish`: `kit` (path of `post.md`) or `nadia` (the posts: platform, date, id), and `status` (`kit`, `scheduled`, `posted`) |

## 2. What comes next

For a video found in step 1, when the user asks for "the next step" or
"la suite" without saying which:

| the state says | next |
|---|---|
| no `~/.config/video-editing/config.json` | `setup` first (at least its diagnostic), then the edit |
| `steps.edit` missing, or `rough: true` | `edit` |
| edited, a title but no `boards` | offer boards (`edit`, "mets des cartons"), or go on to publishing; the user chooses |
| edited, no `steps.publish` | `publish` |
| `steps.publish.status` is `scheduled` | say when it goes out, platform by platform; nothing to do |
| `steps.publish.status` is `kit` | ask whether it is posted; yes = `publish` records it |

## 3. Which skill

| the request | skill |
|---|---|
| first time, "installe", tools, whisper or ElevenLabs, a missing ffmpeg, "les sous-titres ne s'incrustent pas", a setting (language, output folder) | `setup` |
| clips to edit, "monte", "coupe", subtitles, title, boards, "plein cadre", "split", a change on a video already edited ("garde la pause", "c'est cloud pas clown") | `edit` (an edit asked before any setup: `setup` first) |
| their own TikTok or Instagram, "what works on my account", their profile link | `audit` |
| other accounts, "what blew up in my niche", "ideas to remake", an @account to dig | `outliers` |
| a script, a hook, "écris-moi un script", a topic or an anecdote to turn into a video | `script` |
| post, schedule, "publie-la", "mets-la en ligne", a caption, hashtags | `publish` |
| still ambiguous | ask one question, no more |

The chain, for reference: `setup` (once) → `audit` (your account) →
`outliers` (your niche) → `script` (`script.md`, with a "Pour le montage"
block: title, end card, length) → record → `edit` (`<name>.mp4`) → `publish`.
A `script.md` in the current folder gives `edit` its title (`titre`) and end
card: pass them along.

Google Search Console is not a video job: that is the `search-console`
skill.

## 4. Hand over

Invoke the target with the Skill tool (its name; installed as a plugin, the
name may carry the plugin's prefix, `<plugin>:edit`), else read
`../<skill>/SKILL.md` (the skills are installed next to this one) and follow
it exactly as if the user had asked it directly. Pass on their words and the
video found in step 1 (its clips, its `command`).

Say in one line which skill you picked and for which video, then hand over.
Its end state is yours.
