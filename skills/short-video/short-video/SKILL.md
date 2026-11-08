---
name: short-video
description: The front door of the short-video pack. The user says what they want ("monte ma vidéo", "la suite", "publie-la", "edit my video", "what's next") and this skill does two things - it finds the video already in progress (from the <name>.state.json file that `edit-my-video` leaves next to every video) so nothing starts over, and it hands the request to the one skill that does the job (set-up-video-tools, edit-my-video, cut-long-video-into-shorts, audit-my-account, find-outliers-in-my-niche, write-my-script, publish-my-video). It never edits, writes or publishes on its own. Use when the user types /short-video, says "monte ma vidéo", "reprends ma vidéo", "où j'en suis", "la suite", "audite mon compte", "écris-moi un script", "publie-la", "edit my video", "pick up my video", "what's next", "publish it", or is not sure which skill of the pack to use.
argument-hint: "[what you want] [clip | video | path]"
---

# Video: the front door

This skill is a dispatcher. The short-video pack has seven skills that do the
work (`set-up-video-tools`, `edit-my-video`, `cut-long-video-into-shorts`, `audit-my-account`, `find-outliers-in-my-niche`, `write-my-script`, `publish-my-video`);
this one only decides **which video** the user is talking about and **which
skill** does what they ask, then hands over. It has no method of its own:
never edit, write or publish here. Talk in the user's language.

Three jobs, in this order:

1. Find the video in progress (so the user never starts over).
2. If they ask for "the next step", work out what it is from the video's state.
3. Pick the skill and hand over.

## 1. Find the video in progress

Most requests are the next step of a video already under way. Look before
choosing:

1. **This conversation** already works on a video (a clip just edited, a
   script just written, boards just proposed): that is the one. Apply the
   change with the skill already in use, running its step again with the
   same files.
2. **The state files.** `edit-my-video` writes `<name>.state.json` next to every video
   it makes. List the newest ones in the output folder (`output_dir` in
   `~/.config/video-editing/config.json`, else `~/Videos/edited`) and in the
   current folder:

   ```sh
   ls -t "<output_dir>"/*.state.json ./*.state.json 2>/dev/null | head -5
   ```

   - The request names a video (its name, a clip, a word of its title): that one.
   - It says "my video", "it", "the last one", "la suite": the newest.
   - Two or more fit and nothing tells them apart: ask one question, listing
     them (name, title, date of `steps.edit.done`).
3. **Nothing found**: a new video.

Tell the user in one line which video you pick up and where it is
("I pick up IMG_4127, edited today at 18:02, not published yet").

### What a state file holds

`<name>.state.json`, one per video, next to it. `edit-my-video` writes it at each run;
the other skills only add their own step under `steps` and never remove
anything.

| key | what |
|---|---|
| `short-video` | the name (`<name>.mp4` is the video to post) |
| `cut-long-video-into-shorts` | the raw clips, absolute paths, in order |
| `command` | the exact command of the last edit: run it again, plus the new option, for any change |
| `final` | the 9:16 to post |
| `duration`, `lang`, `title`, `boards` | the edited length, the language, the title on screen, the boards file |
| `steps.edit` | `done` (date), `rough` (only the cut) |
| `steps.publish` | written by `publish-my-video`: `kit` (path of `post.md`) or `nadia` (the posts: platform, date, id), and `status` (`kit`, `scheduled`, `posted`) |

## 2. "What's next?"

When the user asks for "the next step", "la suite", "what's next" about a
video found in step 1, the state answers:

| the state says | next |
|---|---|
| no `~/.config/video-editing/config.json` | `set-up-video-tools` first (at least its diagnostic), then the edit |
| `steps.edit` missing, or `rough: true` | `edit-my-video` |
| edited, a title but no `boards` | offer boards (`edit-my-video`, "mets des cartons"), or go on to publishing; the user chooses |
| edited, no `steps.publish` | `publish-my-video` |
| `steps.publish.status` is `scheduled` | say when it goes out, platform by platform; nothing to do |
| `steps.publish.status` is `kit` | ask whether it is posted; yes = `publish-my-video` records it |

## 3. Which skill does the job

| the user wants | skill |
|---|---|
| to install, tools, whisper or ElevenLabs, a missing ffmpeg or yt-dlp, "les sous-titres ne s'incrustent pas", a setting (language, output folder) | `set-up-video-tools` |
| clips edited, "monte", "coupe", subtitles, title, boards, "plein cadre", "split", a change on a video already edited ("garde la pause", "c'est cloud pas clown") | `edit-my-video` (asked before any setup: `set-up-video-tools` first) |
| a long video cut into shorts: a YouTube link, a podcast, "découpe ma vidéo en shorts", "repurpose", "clips from my video" | `cut-long-video-into-shorts` (it edits each clip with `edit-my-video`) |
| to know what works on their own TikTok, their profile link (TikTok only: an Instagram account is told so) | `audit-my-account` |
| to know what blew up on other accounts, "ideas to remake", an @account to dig | `find-outliers-in-my-niche` |
| a script, a hook, a topic or an anecdote to turn into a video | `write-my-script` |
| to post or schedule, "publie-la", "mets-la en ligne", a caption, hashtags | `publish-my-video` |
| still unclear | ask one question, no more |

The whole chain, for reference: `set-up-video-tools` (once) → `audit-my-account` (your account) →
`find-outliers-in-my-niche` (your niche) → `write-my-script` (`script.md`, with a "Pour le montage"
block: title, end card, length) → record → `edit-my-video` (`<name>.mp4`) →
`publish-my-video`. A `script.md` in the current folder gives `edit-my-video` its title
(`titre`) and end card: pass them along.

Google Search Console is not a video job: that is the `read-my-search-console` skill
of the SEO pack.

## 4. Hand over

Invoke the target skill with the Skill tool (its name; installed as a plugin,
the name may carry the plugin's prefix, `short-video:edit-my-video`). If that is not
possible, read `../<skill>/SKILL.md` (the skills are installed next to this
one) and follow it exactly as if the user had asked it directly. Pass on the
user's words and the video found in step 1 (its clips, its `command`).

Say in one line which skill you picked and for which video, then hand over.
From there, the target skill's rules apply, and its end state is yours.
