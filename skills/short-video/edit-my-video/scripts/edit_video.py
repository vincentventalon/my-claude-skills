#!/usr/bin/env python3
"""edit_video.py — a talking-head video, from the raw clips to the video you post, in one command.

    python scripts/edit_video.py clip1.MOV [clip2.MOV ...] --lang fr --title "My *big* idea"

THE CUT. THE SOUND DECIDES WHERE, THE TRANSCRIPT SAYS WHAT, THE LAST TAKE WINS.

  1. joins the clips back to back without re-encoding (and drops the
     thumbnail stream some cameras, DJI for instance, hide in the file);
  2. splits the audio into ISLANDS of sound: whatever lies between two
     silences. A cut can only ever fall in a silence, never inside a word;
  3. transcribes each island, word by word, with one of two engines that
     give the same thing (stt.py): whisper.cpp on this computer (default,
     free; each island ON ITS OWN — transcribed in one go, whisper glues two
     takes into one sentence and swallows the repeat), or ElevenLabs Scribe
     (--stt elevenlabs, paid, one call). An island with no word in it (a
     breath, a click, a lone "um") goes;
  4. drops the retakes: an island (or a run of islands) that is the
     beginning of what comes right after is a false start — it goes, the
     LAST take stays. An island that repeats itself inside ("the the
     server") is re-split on finer silences, each piece transcribed alone
     and judged again; no silence to cut in = kept and reported, never cut
     at a guessed timestamp;
  5. renders the cut, <name>.cut.mp4 (the framing of the clips, no text),
     every segment a whole number of frames (picture and sound stay in
     sync), a 10 ms fade at each join (no click); an iPhone clip comes out
     upright, its HDR brought back to normal colours.

THE FINISH (finish.py).

  6. <name>.mp4, 1080x1920 for TikTok and Instagram, in two views that take
     turns between sentences (--scene auto; split or full for one only): full
     frame, and split (a flat top zone over the camera in a card); the
     subtitles word by word, a title on top for the first seconds (--title),
     the boards on their words (--boards), an end card on the last seconds,
     the voice evened out to about -14 LUFS;
  7. writes the transcript (<name>.txt, <name>.srt), the subtitles
     (<name>.ass), the list of every island with what happened to it
     (<name>.takes.tsv), the timeline (<name>.timeline.json: the views and
     the boards too) and the state (<name>.state.json: the clips and the
     options of this run, the steps done, for picking the video up later).

Running again with the same -o re-transcribes nothing (<name>.stt.json; the
ElevenLabs answer is cached too) and does not render the cut again when it
did not change: a new title costs one render.

Settings: the command line, else ~/.config/video-editing/config.json, else
the defaults (settings.py). `--config` prints them and where each comes from.
Needs Python 3.10+, ffmpeg + ffprobe (with libass for the subtitles) and,
for stt=whisper, whisper-cli (whisper.cpp; the model downloads itself the
first time). Optional: Node 18+, then Remotion draws the title and the end
card. Without whisper-cli the edit still comes out: silences only.
"""
import argparse, array, difflib, hashlib, json, math, os, re, shutil, subprocess, sys, tempfile, unicodedata, wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finish, settings, stt  # noqa: E402

for _s in (sys.stdout, sys.stderr):          # Windows writes cp1252 into a pipe: Claude would read "�"
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(encoding='utf-8', errors='replace')

ap = argparse.ArgumentParser(description='A talking-head video, from the raw clips to the video you post.')
ap.add_argument('rushes', nargs='*', help='video files, in order (whatever ffmpeg reads: mp4, mov, mkv...)')
ap.add_argument('-o', '--out', help='the finished video (default: <output_dir>/<first clip name>.mp4)')
ap.add_argument('--lang', help='spoken language: en, fr, es, de... (config: lang, default en)')
ap.add_argument('--title', default='', help='title on top for the first seconds; *word* = highlighted, " | " = new line')
ap.add_argument('--cta', help='end card text (default: end_card.text of the style, else "Follow for more" in the language)')
ap.add_argument('--no-cta', action='store_true', help='no end card')
ap.add_argument('--scene', choices=['auto', 'split', 'full'], default='auto',
                help='9:16 views: auto = full frame for the hook, then full frame and split take turns between '
                     'sentences; split = the camera in a card under a flat top zone; full = the camera fills it')
ap.add_argument('--boards', metavar='FILE',
                help='boards.json: [{"at": 12.4 or "say": "the words", "text": "150 min | = 3 h", '
                     '"kind": "text|stat|list"}], drawn in the top zone of the split')
ap.add_argument('--fit', choices=['auto', 'fill', 'frame'], default='auto',
                help='9:16 from horizontal clips: frame = in the middle on a blurred copy (auto), fill = cropped')
ap.add_argument('--rough', action='store_true', help='the cut only, as filmed: no subtitles, no title, no 9:16')
ap.add_argument('--stt', choices=['whisper', 'elevenlabs'], help='transcription engine (config: stt, default whisper)')
ap.add_argument('--model', help='whisper model: large-v3-turbo, large-v3-turbo-q5_0, small... downloaded '
                                 'automatically, or a ggml-*.bin path (config: whisper_model)')
ap.add_argument('--ffmpeg', help='the ffmpeg to use (config: ffmpeg; default: the first found with libass)')
ap.add_argument('--subtitles', action=argparse.BooleanOptionalAction, default=None,
                help='burn the subtitles in (config: subtitles, default yes)')
ap.add_argument('--remotion', action=argparse.BooleanOptionalAction, default=None,
                help='let Remotion draw the title and the end card when Node is there (config: remotion, default yes)')
ap.add_argument('--style', help='a JSON file with the style keys to change (see style.json)')
ap.add_argument('--fix', nargs='*', default=[], metavar='HEARD=MEANT',
                help='fix a misheard word in the subtitles and the transcript: --fix "clode=Claude"')
ap.add_argument('--config', action='store_true', help='print the settings, where each comes from, and stop')
ap.add_argument('--min-sil', type=float, default=0.22,
                help='a silence this long (s) separates two islands and is cut (0.22)')
ap.add_argument('--noise', type=float, default=32,
                help='silence threshold in dB below 0 (32; lower to 25 in a noisy room)')
ap.add_argument('--pad', type=float, default=0.05,
                help='air kept before each island, in s (0.05; after: pad + 0.02)')
ap.add_argument('--protect', nargs='*', default=[], metavar='A:B',
                help='A:B windows (s, joined footage) never to cut: a deliberate pause')
ap.add_argument('--cut', nargs='*', default=[], metavar='A:B',
                help='A:B windows (s, joined footage) to remove on top of the automatic cuts')
ap.add_argument('--keep-retakes', action='store_true', help='keep every take')
ap.add_argument('--keep-fillers', action='store_true', help='keep the islands that are only "um"')
ap.add_argument('--no-transcript', action='store_true', help='no transcription: silences only, no subtitles')
args = ap.parse_args()

KEY_ORIGIN = settings.load_env_file()
cfg, cfg_src = settings.resolve({'stt': args.stt, 'whisper_model': args.model, 'ffmpeg': args.ffmpeg,
                                 'lang': args.lang, 'output_dir': None, 'subtitles': args.subtitles,
                                 'remotion': args.remotion})
FF, FP = cfg['ffmpeg'], cfg['ffprobe']
WHISPER = settings.find_whisper()
if args.config:
    print(settings.describe(cfg, cfg_src, KEY_ORIGIN, WHISPER, stt.find_model(cfg['whisper_model']),
                            finish.REMOTION, bool(args.out)))
    sys.exit()
if not args.rushes:
    ap.error('give the video files to edit (or --config)')
args.lang, args.model, ENGINE = cfg['lang'], cfg['whisper_model'], cfg['stt']

# Filler words per language (an island that is only these goes), and the
# lead-in words that are not part of the sentence ("So, the server..." is
# the same take as "The server...").
FILLERS = {'fr': {'euh', 'heu', 'hum', 'hm', 'mh', 'mmh', 'bah', 'ben'},
           'en': {'um', 'uh', 'uhm', 'hm', 'hmm', 'mh', 'mm', 'erm', 'er'},
           'es': {'eh', 'em', 'este', 'mmm'}, 'de': {'äh', 'ähm', 'hm', 'öh'}}
LEADINS = {'fr': {'voila', 'euh', 'heu', 'bon', 'alors', 'ben', 'bah', 'hum'},
           'en': {'um', 'uh', 'so', 'well', 'okay', 'ok', 'right'}}
# Linking words a new take often adds in front ("and", "that"): set aside only
# when comparing two neighbouring islands.
LINKS_ = {'fr': {'et', 'que', 'qu', 'mais', 'donc', 'puis'},
          'en': {'and', 'but', 'so', 'then', 'that'}}
# What whisper writes on a silence or a noise, well known.
PHANTOMS = ['soustitrage', 'soustitres', 'amaraorg', 'merci davoir regarde',
            'thanks for watching', 'thank you for watching', 'subtitles by']


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', **kw)


def probe(path, entries, stream=None):
    cmd = [FP, '-v', 'error']
    if stream:
        cmd += ['-select_streams', stream]
    cmd += ['-show_entries', entries, '-of', 'csv=p=0', path]
    # an iPhone clip carries a rotation (side data): ffprobe then ends the line with a comma
    return run(cmd).stdout.strip().split('\n')[0].strip().rstrip(',')


def say(msg):
    print(msg, file=sys.stderr)


def windows(specs):
    return [tuple(map(float, p.split(':'))) for p in specs]


for r in args.rushes:
    if not os.path.isfile(r):
        sys.exit(f'not found: {r}')
    if not probe(r, 'stream=index', 'a:0'):
        sys.exit(f'{r}: no sound in this file (the edit follows the voice)')
use_stt = not args.no_transcript
if use_stt and ENGINE == 'whisper' and not WHISPER:
    say('whisper-cli not found: silences only, no retakes, no subtitles (see SKILL.md to install it)')
    use_stt = False
if use_stt and ENGINE == 'elevenlabs':
    stt.scribe_key()                     # no key: stop now, not after the join

work = tempfile.mkdtemp(prefix='monte-')
out = os.path.abspath(args.out) if args.out else os.path.join(
    cfg['output_dir'], os.path.splitext(os.path.basename(args.rushes[0]))[0] + '.mp4')
os.makedirs(os.path.dirname(out), exist_ok=True)
base = os.path.splitext(out)[0]
CUT = out if args.rough else f'{base}.cut.mp4'

# 1. lossless join ---------------------------------------------------------------
clean = []
for i, r in enumerate(args.rushes):
    c = f'{work}/clip{i}.mp4'
    # 0:v:0 / 0:a:0 = first video and first audio stream; everything else
    # (mjpeg thumbnail, data tracks) is dropped. A rotation (iPhone) travels along.
    run([FF, '-y', '-i', r, '-map', '0:v:0', '-map', '0:a:0', '-c', 'copy', c])
    clean.append(c)
merged = f'{work}/merged.mp4'
if len(clean) == 1:
    shutil.move(clean[0], merged)
else:
    lst = f'{work}/list.txt'
    # the clips by their bare name: concat reads them next to the list (no drive letter, no quote to escape)
    open(lst, 'w', encoding='utf-8').write(''.join(f"file '{os.path.basename(c)}'\n" for c in clean))
    run([FF, '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', merged])

dur = float(probe(merged, 'format=duration'))
for st in ('v:0', 'a:0'):          # the shorter stream sets the end: no tail of picture without sound
    try:
        dur = min(dur, float(probe(merged, 'stream=duration', st)))
    except ValueError:
        pass
num, den = (probe(merged, 'stream=r_frame_rate', 'v:0').split('/') + ['1'])[:2]
FRAME = float(den) / float(num)          # one frame's duration
say(f'joined footage: {dur:.1f}s, {len(args.rushes)} clip(s), {float(num)/float(den):.2f} fps')

# HDR (iPhone: HLG; some cameras: PQ) -> normal colours, else it plays grey and washed out
TONEMAP = ''
colour = dict(l.split('=', 1) for l in run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                             'stream=color_transfer,color_primaries,color_space', '-of',
                                             'default=nw=1', merged]).stdout.split() if '=' in l)
trc, prim, spc = (colour.get(k, '') for k in ('color_transfer', 'color_primaries', 'color_space'))
prim, spc = (x if x and x != 'unknown' else d for x, d in ((prim, 'bt2020'), (spc, 'bt2020nc')))
if trc in ('arib-std-b67', 'smpte2084'):
    if settings.has_filter(FF, 'zscale'):
        TONEMAP = (f',zscale=tin={trc}:pin={prim}:min={spc}:t=linear:npl=100,'
                   'format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,'
                   'zscale=t=bt709:m=bt709:r=tv,format=yuv420p')
        say('HDR clip: brought back to normal colours')
    else:
        say(f'HDR clip but this ffmpeg has no zscale: colours may look washed out (install {settings.INSTALL_LIBASS})')

WAV = f'{work}/full.wav'                 # 16 kHz mono: what the transcription and the detector read
run([FF, '-y', '-i', merged, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', WAV])


# 2. islands of sound ------------------------------------------------------------
def silences(noise, d, a=0.0, b=None):
    cmd = [FF, '-hide_banner']
    if b is not None:
        cmd += ['-ss', f'{a}', '-to', f'{b}']
    det = subprocess.run(cmd + ['-i', WAV, '-af', f'silencedetect=noise=-{noise}dB:d={d}',
                                '-f', 'null', '-'], capture_output=True, text=True, errors='replace').stderr
    off = a if b is not None else 0.0
    ss = [float(x) + off for x in re.findall(r'silence_start:\s*([-\d.]+)', det)]
    se = [float(x) + off for x in re.findall(r'silence_end:\s*([-\d.]+)', det)]
    return list(zip(ss, se + [b if b is not None else dur] * (len(ss) - len(se))))


def islands_between(sils, a, b, min_len=0.12):
    """What is not silence between a and b, at least min_len long."""
    isl, cur = [], a
    for s, e in sorted(sils):
        if s - cur >= min_len:
            isl.append((cur, min(s, b)))
        cur = max(cur, e)
    if b - cur >= min_len:
        isl.append((cur, b))
    return isl


FINE = {}
LEVELS = [(2, 0.08), (4, 0.05)]      # dB above the island threshold, min length (s)


def fine_split(a, b, level=0):
    """An island re-split on shorter, quieter silences (a breath inside a
    sentence). Level 1 is finer still: the 50 ms between two words."""
    if level not in FINE:
        FINE[level] = silences(args.noise - LEVELS[level][0], LEVELS[level][1])
    return islands_between([(s, e) for s, e in FINE[level] if s > a and e < b], a, b)


islands = islands_between(silences(args.noise, args.min_sil), 0.0, dur)
say(f'islands of sound: {len(islands)} (silences >= {args.min_sil}s at -{args.noise:g} dB)')


# 3. the words, island by island (stt.py: whisper or ElevenLabs, one contract) ----
def norm(word):
    w = unicodedata.normalize('NFD', word.lower())
    w = ''.join(c for c in w if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]', '', w)


def toks(text):
    text = re.sub(r'[\[(*][^\])*]*[\])*]', ' ', text)      # [Music], (laughs), *noise*
    return [t for t in (norm(x) for x in re.split(r"[\s'’\-]+", text)) if t]


def key(s):
    return (round(s[0], 3), round(s[1], 3))


STT_CACHE = f'{base}.stt.json'
TAG = {'engine': ENGINE, 'lang': args.lang,
       'model': os.path.basename(args.model) if ENGINE == 'whisper' else stt.SCRIBE_MODEL}
WORDS = {}           # key(span) -> [(start, end, word)], joined-footage time: what the cut reads
TIMED = {}           # the same, kept spans only, starts from the DTW pass (whisper): what the subtitles show
if use_stt and ENGINE == 'whisper' and os.path.exists(STT_CACHE):
    try:
        c = json.load(open(STT_CACHE, encoding='utf-8'))
        if c.get('tag') == TAG:
            WORDS, TIMED = ({tuple(map(float, k.split(':'))): [tuple(w) for w in v] for k, v in c.get(n, {}).items()}
                            for n in ('spans', 'timed'))
    except (ValueError, KeyError, AttributeError):
        pass
SCRIBE = None        # ElevenLabs: the words of each island, from the one call
MODEL = None


def transcribe(spans):
    """[(a, b, text)] — each span heard ON ITS OWN; its words, timed, in WORDS."""
    global SCRIBE, MODEL
    todo = [k for k, s in enumerate(spans) if key(s) not in WORDS]
    if todo:
        if ENGINE == 'elevenlabs':
            if SCRIBE is None:
                SCRIBE = stt.assign(stt.scribe(WAV, args.lang, FF), islands)
            lo, hi = min(a for a, _b in spans), max(b for _a, b in spans)
            pool = [w for (a, b), ws in zip(islands, SCRIBE) if a < hi and lo < b for w in ws]
            every = stt.assign(pool, spans)
            got = [every[k] for k in todo]
        else:
            if MODEL is None:
                MODEL = stt.model_path(args.model)
                say(f'transcript: whisper.cpp ({os.path.basename(MODEL)}), each island on its own...')
            got = stt.whisper_spans(WAV, spans, todo, dur, MODEL, args.lang, WHISPER, FF)
        for k, ws in zip(todo, got):
            WORDS[key(spans[k])] = ws
    return [(a, b, ' '.join(t for _s, _e, t in WORDS[key((a, b))])) for a, b in spans]


def text_of(span):
    return ' '.join(t for _s, _e, t in WORDS.get(key(span), []))


# 4. decisions: what goes ---------------------------------------------------------
LEAD = LEADINS.get(args.lang, set())
LINKS = LINKS_.get(args.lang, set())
FILL = FILLERS.get(args.lang, set().union(*FILLERS.values()))


def no_speech(text):
    t = ''.join(toks(text))
    return not t or any(p in t for p in PHANTOMS)


def only_fillers(text):
    t = toks(text)
    return bool(t) and all(x in FILL for x in t)


def strip_leadin(t):
    k = 0
    while k < len(t) - 1 and t[k] in LEAD:
        k += 1
    return t[k:]


def starts_like(abandoned, rest):
    """How much the letters of `abandoned` are the BEGINNING of `rest` (0-1).
    Letters, not words: whisper writes "GitStatus" once and "git status" the
    next time. Both must start together (first letter aligned)."""
    a, s = ''.join(abandoned), ''.join(rest)
    if len(a) < 2 or len(s) < len(a):
        return 0.0
    best = 0.0
    for k in range(-2, 3):
        m = difflib.SequenceMatcher(None, a, s[:max(1, len(a) + k)], autojunk=False)
        b0 = m.get_matching_blocks()[0]
        if b0.a == 0 and b0.b == 0 and b0.size >= 1:
            best = max(best, m.ratio())
    return best


def is_start_of(abandoned, rest, run=1):
    # 0.74: measured on real footage — true false starts 0.75-1.00, a sentence
    # that simply goes on with a similar opening 0.71. Over a run of several
    # islands the first 8 letters must match too: a shared END ("...as long as
    # it is not public, it works") is not a shared beginning.
    a, r = strip_leadin(abandoned), strip_leadin(rest)
    if run > 1:
        ha, hr = ''.join(a)[:8], ''.join(r)[:8]
        if difflib.SequenceMatcher(None, ha, hr[:len(ha)], autojunk=False).ratio() < 0.6:
            return False
    return starts_like(a, r) >= 0.74


def restarts(ti, tj, adjacent=False):
    """tj starts the sentence of ti again, the end may differ ("Git add is for
    choosing..." then "Git add is for adding..."): the first 12 letters (>= 2
    words) match at >= 0.85. For neighbouring islands, also: the first 3 words
    are the same once the linking words are set aside ("and you don't want it
    | and that you don't want it"), or ti is said again whole within the first
    words of tj ("something | there is something important")."""
    ti, tj = strip_leadin(ti), strip_leadin(tj)
    if not ti or not tj:
        return False
    if adjacent:
        a_, b_ = skip_links(ti), skip_links(tj)
        if len(a_) >= 3 and a_[:3] == b_[:3] and len(''.join(a_[:3])) >= 7:
            return True
        n = len(ti)
        if n >= 2 and len(''.join(ti)) >= 6 and any(tj[k:k + n] == ti for k in range(1, 4)):
            return True
    if ti[0][0] != tj[0][0]:
        return False
    o, k = '', 0
    while k < len(ti) and (len(o) < 12 or k < 2):
        o += ti[k]
        k += 1
    if len(o) < 12 or k < 2:
        return False
    s = ''.join(tj)[:len(o)]
    return len(s) == len(o) and difflib.SequenceMatcher(None, o, s, autojunk=False).ratio() >= 0.85


def skip_links(t):
    k = 0
    while k < min(2, len(t) - 1) and t[k] in LINKS:
        k += 1
    return t[k:]


def sentence_done(text):
    return text.rstrip(' "»)').endswith(('.', '!', '?', '…', ':', ','))


def false_starts(items, gap=10.0, span=6):
    """items = [(a, b, text)] in order. The indexes to drop: for each i, the
    shortest run i..j-1 whose text is the beginning of what follows. The LAST
    take stays."""
    T = [toks(t) for _a, _b, t in items]
    drop, why, i = set(), {}, 0
    while i < len(items):
        found = None
        for j in range(i + 1, min(i + 1 + span, len(items))):
            if items[j][0] - items[j - 1][1] > gap:
                break
            ab = [t for k in range(i, j) for t in T[k]]
            nxt = [t for k in range(j, min(j + span, len(items))) for t in T[k]]
            if ab and (is_start_of(ab, nxt, j - i) or (j - i <= 3 and restarts(T[i], T[j], adjacent=j == i + 1))):
                found = j
                break
        if found is None:
            i += 1
            continue
        j = found
        ab = ''.join(t for k in range(i, j) for t in T[k])
        glued = i > 0 and items[i][0] - items[i - 1][1] < 0.6 and not sentence_done(items[i - 1][2])
        if len(ab) <= 4 and glued:   # one short word after an unfinished sentence: not enough
            i += 1
            continue
        for k in range(i, j):
            drop.add(k)
            why[k] = f'retake, said again at {items[j][0]:.2f}: "{items[j][2][:60]}"'
        i = j
    return drop, why


def repeats_itself(text):
    """The same words twice in a row inside one island ("the the server")."""
    t = toks(text)
    for n in range(1, 5):
        for i in range(len(t) - 2 * n + 1):
            if len(''.join(t[i:i + n])) >= 3 and t[i:i + n] == t[i + n:i + 2 * n]:
                return ' '.join(t[i:i + 2 * n])
    return None


def tail_restarted(ti, nexts):
    """Is the END of an island (with, maybe, the next islands) the beginning of
    what follows ("...one VPS. As long as it is not public, it works | well." then
    "As long as it is not public, it works well.")? nexts = token lists."""
    for m in range(len(nexts)):
        extra = [t for n in nexts[:m] for t in n]
        rest = [t for n in nexts[m:] for t in n]
        for p in range(1, len(ti)):
            q = ti[p:] + extra
            if len(''.join(q)) >= 8 and (is_start_of(q, rest) or restarts(q, rest)):
                return True
    return False


protect, extra_cuts = windows(args.protect), windows(args.cut)


def protected(a, b):
    return any(pa < b and a < pb for pa, pb in protect)


log = {}            # (a, b) -> (status, text)
warnings = []       # (source time, message)
if use_stt:
    items = transcribe(islands)
    live = []
    for a, b, t in items:
        if protected(a, b):
            live.append((a, b, t))
        elif no_speech(t):
            log[(a, b)] = ('no-speech', t)
        elif only_fillers(t) and not args.keep_fillers:
            log[(a, b)] = ('filler', t)
        else:
            live.append((a, b, t))

    def refine(item, nexts, level=0):
        """Re-split an island on finer silences, transcribe each piece ALONE and
        judge the pieces (and the next islands) again: this is where the repeats
        whisper swallowed come out ("and so you have | and so now you have" read
        as one sentence). Only false starts and lone fillers go; a piece whisper
        hears nothing in stays (it is inside speech: a breath, a soft syllable).
        Returns (pieces to keep, next islands that turned out to be part of the
        abandoned take), or None if nothing changes."""
        a, b, t = item
        pieces = fine_split(a, b, level)
        if len(pieces) < 2:
            return None
        sub = transcribe(pieces)
        fill = {k for k, p in enumerate(sub) if only_fillers(p[2]) and not args.keep_fillers}
        judged = [k for k, p in enumerate(sub) if k not in fill and not no_speech(p[2])]
        drop, reason = false_starts([sub[k] for k in judged] + nexts)
        gone = [(nexts[k - len(judged)], reason[k]) for k in drop
                if k >= len(judged) and not protected(*nexts[k - len(judged)][:2])]
        reason = {judged[k]: r for k, r in reason.items() if k < len(judged)}
        drop = {judged[k] for k in drop if k < len(judged)}
        if not drop and not fill:
            return None
        kept = [p for k, p in enumerate(sub) if k not in drop and k not in fill]
        for k, p in enumerate(sub):
            if k in drop:
                log[p[:2]] = ('retake', reason[k])
            elif k in fill:
                log[p[:2]] = ('filler', p[2])
            else:
                log[p[:2]] = ('kept', p[2])
        log.pop((a, b), None)
        for it, why in gone:
            log[it[:2]] = ('retake', why)
        return kept, [it[:2] for it, _w in gone]

    if not args.keep_retakes:
        # a. false starts between islands: the last take stays
        drop, reason = false_starts(live)
        drop = {k for k in drop if not protected(*live[k][:2])}
        for k in sorted(drop):
            log[live[k][:2]] = ('retake', reason[k])
        live = [x for k, x in enumerate(live) if k not in drop]
        # b. every island re-split and re-read piece by piece, with the next ones;
        #    finer still when its end looks said again and the first split found nothing
        new, gone = [], set()
        for k, it in enumerate(live):
            if it[:2] in gone:
                continue
            nexts = [x for x in live[k + 1:k + 3] if x[:2] not in gone and x[0] - it[1] < 10.0]
            res = None if protected(*it[:2]) else refine(it, nexts)
            if res is None and not protected(*it[:2]):
                rep = repeats_itself(it[2])
                tail = nexts and tail_restarted(toks(it[2]), [toks(x[2]) for x in nexts])
                if rep or tail:
                    res = refine(it, nexts, level=1)
                    if res is None:
                        warnings.append((it[0], f'"{it[2][-60:]}" ' + (
                            f'repeats "{rep}"' if rep else f'is said again in "{nexts[-1][2][:40]}"')
                            + ', no silence to cut in: kept'))
            if res is None:
                new.append(it)
            else:
                new += res[0]
                gone.update(res[1])
        live = [x for x in new if x[:2] not in gone]
    for a, b, t in live:
        log.setdefault((a, b), ('kept', t))
else:
    live = [(a, b, '') for a, b in islands]


for (a, b), (st, t) in sorted(log.items()):
    if st == 'retake':
        say(f'  cut {a:7.2f} -> {b:7.2f}  {st}  "{text_of((a, b))[:70]}"')

# 5. kept segments ---------------------------------------------------------------
def snap_in(a, b):
    """Snap the bounds to the frame grid, inwards.

    `trim` cuts on a frame, `atrim` on a sample: a segment that does not
    last a whole number of frames drifts video against audio, and the drift
    adds up at every cut. So we shave at most one frame per edge.
    """
    i = math.ceil(a / FRAME + 0.5)
    j = math.floor(b / FRAME + 0.5)
    if j <= i:
        j = i + 1
    return max(0.0, (i - 0.5) * FRAME), (j - 0.5) * FRAME


def merge(spans):
    spans, outl = sorted(spans), []
    for a, b in spans:
        if outl and a <= outl[-1][1]:
            outl[-1] = (outl[-1][0], max(outl[-1][1], b))
        else:
            outl.append((a, b))
    return outl


live.sort()
keep = []
for k, (a, b, _t) in enumerate(live):
    lo = (live[k - 1][1] + a) / 2 if k else 0.0            # never reach into the neighbour
    hi = (b + live[k + 1][0]) / 2 if k + 1 < len(live) else dur
    keep.append((max(lo, a - args.pad), min(hi, b + args.pad + 0.02)))
keep = merge(keep + [(max(0, a), min(dur, b)) for a, b in protect])
for ca, cb in extra_cuts:                                   # --cut: carve out
    nk = []
    for a, b in keep:
        if cb <= a or ca >= b:
            nk.append((a, b))
            continue
        if ca > a:
            nk.append((a, ca))
        if cb < b:
            nk.append((cb, b))
    keep = nk
segs = [snap_in(a, b) for a, b in keep if b - a >= 2 * FRAME]
for a, b, t in live:                                        # an island cut by hand leaves the transcript
    if any(ca <= (a + b) / 2 <= cb for ca, cb in extra_cuts):
        log[(a, b)] = ('cut', t)
live = [x for x in live if log.get(x[:2], ('kept',))[0] != 'cut']
if os.environ.get('EDIT_VIDEO_SEGMENTS'):                 # for dev/check_edit.py
    open(os.environ['EDIT_VIDEO_SEGMENTS'], 'w', encoding='utf-8').writelines(f'{a:.6f}\t{b:.6f}\n' for a, b in segs)
if not segs:
    sys.exit('nothing kept: is there any speech in the clips? (a quiet recording: try --noise 40)')
kept_dur = sum(b - a for a, b in segs)
n_ret = sum(1 for s, _t in log.values() if s == 'retake')
n_emp = sum(1 for s, _t in log.values() if s in ('no-speech', 'filler'))
say(f'kept {len(segs)} segments: {dur:.1f}s -> {kept_dur:.1f}s '
    f'({n_ret} retakes and {n_emp} islands without speech dropped)')


def to_out(t):
    """A time on the joined footage -> the same instant in the edited video."""
    cum = 0.0
    for a, b in segs:
        if t < a:
            return cum
        if t <= b:
            return cum + t - a
        cum += b - a
    return cum


# 6. the cut ---------------------------------------------------------------------
TIMELINE = f'{base}.timeline.json'
signature = hashlib.sha1(json.dumps(
    [[os.path.abspath(r), os.path.getsize(r), int(os.path.getmtime(r))] for r in args.rushes]
    + [[round(a, 6), round(b, 6)] for a, b in segs] + [TONEMAP, 2]).encode()).hexdigest()
try:
    before = json.load(open(TIMELINE, encoding='utf-8')).get('cut_signature')
except (OSError, ValueError, AttributeError):
    before = None
if before == signature and os.path.exists(CUT) and not args.rough:
    say(f'the cut did not change: {os.path.basename(CUT)} kept as it is')
else:
    F = 0.01                                                # 10 ms fade: no click at the joins
    v = ''.join(f'[0:v]trim={a:.6f}:{b:.6f},setpts=PTS-STARTPTS[v{i}];' for i, (a, b) in enumerate(segs))
    a_ = ''.join(f'[0:a]atrim={a:.6f}:{b:.6f},asetpts=PTS-STARTPTS,afade=t=in:d={F},'
                 f'afade=t=out:st={max(0, b - a - F):.6f}:d={F}[a{i}];' for i, (a, b) in enumerate(segs))
    pairs = ''.join(f'[v{i}][a{i}]' for i in range(len(segs)))
    fg = f'{work}/fg.txt'
    open(fg, 'w', encoding='utf-8').write(
        v + a_ + f'{pairs}concat=n={len(segs)}:v=1:a=1[vc][a];[vc]null{TONEMAP}[v]')
    say(f'rendering the cut ({kept_dur:.0f}s)...')
    run([FF, '-y', '-i', merged, '-filter_complex_script', fg, '-map', '[v]', '-map', '[a]',
         '-c:v', 'libx264', '-crf', '18', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
         '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', CUT])
say(f'-> {CUT}')
width, height = map(int, probe(CUT, 'stream=width,height', 'v:0').split(',')[:2])


# 7. the words of the edited video -----------------------------------------------
def fixed(words, fixes):
    """--fix "HEARD=MEANT": a misheard word (or words) replaced wherever it is said,
    its time shared out between the new words."""
    for spec in fixes:
        if '=' not in spec:
            sys.exit(f'--fix wants HEARD=MEANT, not "{spec}"')
        heard, meant = spec.split('=', 1)
        h, m = [norm(x) for x in heard.split() if norm(x)], meant.split()
        if not h or not m:
            continue
        res, i = [], 0
        while i < len(words):
            if [norm(w[2]) for w in words[i:i + len(h)]] == h:
                s, e = words[i][0], words[i + len(h) - 1][1]
                end = re.search(r'[.,;:!?…]+$', words[i + len(h) - 1][2])
                tail = end.group(0) if end and not re.search(r'[.,;:!?…]$', meant) else ''
                total, cur = sum(len(x) for x in m), s
                for j, x in enumerate(m):
                    d = (e - s) * len(x) / total
                    res.append((cur, cur + d, x + (tail if j == len(m) - 1 else '')))
                    cur += d
                i += len(h)
            else:
                res.append(words[i])
                i += 1
        words = res
    return words


if use_stt and ENGINE == 'whisper' and stt.dtw_preset(args.model):
    kept = sorted(x[:2] for x in live)
    todo = [k for k, s in enumerate(kept) if key(s) not in TIMED and WORDS.get(key(s))]
    if todo:
        say(f'word timing: the {len(todo)} kept islands heard again (DTW)...')
        got = stt.whisper_spans(WAV, kept, todo, dur, MODEL or stt.model_path(args.model), args.lang,
                                WHISPER, FF, dtw=True)
        for k, ws in zip(todo, got):
            TIMED[key(kept[k])] = stt.retime(WORDS[key(kept[k])], ws)

out_words = []                       # [(start, end, word)], time of the edited video
for a, b, _t in sorted(live):
    for s, e, w in TIMED.get(key((a, b))) or WORDS.get(key((a, b)), []):
        mid = (s + e) / 2
        if any(sa <= mid <= sb for sa, sb in segs):
            os_ = to_out(s)
            out_words.append((round(os_, 3), round(max(os_, to_out(e)), 3), w))
out_words = fixed(sorted(out_words), args.fix)

# 8. the finish: 9:16 (and 16:9) with subtitles, title, boards, end card ----------
finals, views_out, boards = [], [], []
if not args.rough:
    style = finish.load_style(settings.USER_STYLE, args.style)
    cta = '' if args.no_cta else (args.cta if args.cta is not None else
                                  (style['end_card'].get('text') or finish.CTA.get(args.lang, finish.CTA['en'])))
    if args.boards:
        try:
            raw_boards = json.load(open(args.boards, encoding='utf-8-sig'))
        except (OSError, ValueError) as e:
            sys.exit(f'--boards {args.boards}: {e}')
        boards = finish.resolve_boards(raw_boards if isinstance(raw_boards, list) else raw_boards.get('boards', []),
                                       out_words, kept_dur)
    burn = settings.has_filter(FF, 'ass')
    rcli, why = finish.remotion_cli(cfg['remotion']) if (args.title or cta or boards) else (None, None)
    if not burn:
        say(f'this ffmpeg ({FF}) has no libass: no subtitles burned in (the .srt is written all the same)'
            + ('' if rcli or not (args.title or cta or boards)
               else ', and no title, board nor end card (no Node for Remotion either)')
            + f'. Install {settings.INSTALL_LIBASS}')
    elif (args.title or cta or boards) and not rcli:
        say(f'title, boards and end card drawn by ffmpeg ({why})')
    if not cfg['subtitles']:
        say('subtitles off (config or --no-subtitles): the .srt is written all the same')
    formats = [(out, False)]
    audio = finish.loudness_filter(FF, CUT, style.get('loudness'))
    fps = round(1 / FRAME, 3)
    title_sec = min(style['title']['duration'], kept_dur) if args.title else 0.0
    cta_start = max(kept_dur - style['end_card']['duration'], title_sec)
    if cta and kept_dur - cta_start < 1.0:                  # a very short video: the title says it all
        say(f'no end card: the video ({kept_dur:.1f}s) is too short for a title and an end card')
        cta = ''
    if not cta:
        cta_start = kept_dur
    cut_dur = float(probe(CUT, 'stream=duration', 'v:0'))
    for path, wide in formats:
        L = finish.layout(width, height, wide, args.fit, style)
        L['fps'] = fps
        joins = [sum(y - x for x, y in segs[:n + 1]) for n in range(len(segs) - 1)]     # where pauses were cut
        views = (finish.plan_views(out_words, kept_dur, args.scene, boards, bool(args.title), cta_start, joins)
                 if not wide else [(0.0, kept_dur, 'full')])
        if not wide:
            views_out = views
            if args.scene == 'auto' and len(views) == 1:
                say('scene: full frame only (nothing for the top of a split: give a --title or --boards)')
            elif args.scene == 'auto':
                n_split = sum(1 for v in views if v[2] == 'split')
                say(f'scene: {len(views)} turns, {n_split} split (' + ', '.join(
                    f'{v[2]} {v[0]:.1f}-{v[1]:.1f}s' for v in views[:6]) + (', ...' if len(views) > 6 else '') + ')')
        items = finish.overlay_items(L, style, views, args.title, title_sec, cta, cta_start, kept_dur,
                                     [] if wide else boards)
        cards, left = [], items
        if rcli and items:
            clip = finish.remotion_overlay(rcli, work, f'overlay{int(wide)}', items, L, style, cut_dur, fps)
            if clip:
                cards.append((clip, 0.0))
                left = []
        ass = None
        if burn:
            ass = f'{base}.ass'
            n = finish.build_ass(ass, L, out_words if cfg['subtitles'] else [], left, style, views)
            if n:                                       # a plain name: nothing to escape in the filtergraph
                shutil.copy(ass, os.path.join(work, f'subs{int(wide)}.ass'))
            else:
                ass = None
        kinds = sorted({it['kind'] for it in items})
        drawn = ', '.join(x for x in [
            'subtitles' if ass and out_words and cfg['subtitles'] else '',
            (', '.join(kinds) + (' (Remotion)' if not left else ' (ffmpeg)')) if items and (cards or ass) else ''] if x)
        say(f'rendering {L["W"]}x{L["H"]} ({L["fit"]}{", " + drawn if drawn else ""})...')
        finish.render(FF, CUT, path, L, work, views, style,
                      os.path.join(work, f'subs{int(wide)}.ass') if ass else None,
                      cards, audio, style.get('font_file'), cut_dur)
        finals.append(path)
        say(f'-> {path}')


# 9. the timeline, the transcript, the list of takes ------------------------------
def peaks(rate=50):
    """Loudness of the EDITED sound, `rate` values a second, 0-100."""
    with wave.open(WAV) as w:
        sr = w.getframerate()
        data = array.array('h', w.readframes(w.getnframes()))
    if sys.byteorder == 'big':
        data.byteswap()
    step, vals = sr // rate, []
    for a, b in segs:
        i, j = int(a * sr), int(b * sr)
        for k in range(i, j, step):
            s = data[k:min(k + step, j)]
            vals.append(max(max(s), -min(s)) if s else 0)
    top = max(vals, default=0) or 1
    return [round(100 * v / top) for v in vals]


with open(TIMELINE, 'w', encoding='utf-8') as f:
    json.dump({
        'video': os.path.basename(out), 'cut': os.path.basename(CUT),
        'finals': [os.path.basename(p) for p in finals], 'cut_signature': signature,
        'width': width, 'height': height, 'fps': round(1 / FRAME, 3), 'lang': args.lang,
        'stt': ENGINE if use_stt else None,
        'source_duration': round(dur, 3), 'duration': round(kept_dur, 3),
        'segments': [[round(a, 3), round(b, 3)] for a, b in segs],
        'islands': [{'a': round(a, 3), 'b': round(b, 3), 'start': round(to_out(a), 3),
                     'end': round(to_out(b), 3), 'text': t} for a, b, t in sorted(live)],
        'words': [{'start': s, 'end': e, 'text': w} for s, e, w in out_words],
        'removed': [{'at': round(to_out(a), 3), 'a': a, 'b': b, 'why': st, 'text': text_of((a, b)) or t}
                    for (a, b), (st, t) in sorted(log.items()) if st != 'kept'],
        'warnings': [{'at': round(to_out(t), 3), 'text': m} for t, m in sorted(warnings)],
        'scene': args.scene, 'views': [[round(a, 3), round(b, 3), v] for a, b, v in views_out],
        'boards': boards,
        'peaks_per_second': 50, 'peaks': peaks(),
    }, f, ensure_ascii=False)
say(f'-> {TIMELINE}')

# the state of this video, for picking it up later (the `short-video` skill reads it): which clips, the
# options of this run (run again = the same ones plus the new), what is done. Other skills add
# their step (publish) to `steps`; a run of the edit keeps them.
STATE = f'{base}.state.json'
try:
    state = json.load(open(STATE, encoding='utf-8'))
except (OSError, ValueError):
    state = {}
options, after = [], None
for a in sys.argv[1:]:
    if after:                                              # a path given after its flag: made absolute
        options.append(os.path.abspath(a))
        after = None
    elif a in ('-o', '--out', '--boards', '--style'):
        options.append(a)
        after = a
    elif a.split('=', 1)[0] in ('--out', '--boards', '--style') and '=' in a:
        options.append(a.split('=', 1)[0] + '=' + os.path.abspath(a.split('=', 1)[1]))
    elif os.path.abspath(a) not in {os.path.abspath(r) for r in args.rushes}:
        options.append(a)
state.update({
    'video': os.path.basename(base), 'clips': [os.path.abspath(r) for r in args.rushes],
    'command': [os.path.abspath(__file__), *[os.path.abspath(r) for r in args.rushes], *options],
    'final': os.path.basename(out) if not args.rough else None,
    'duration': round(kept_dur, 3), 'lang': args.lang, 'title': args.title,
    'boards': os.path.abspath(args.boards) if args.boards else None,
})
steps = state.setdefault('steps', {})
steps['edit'] = {'done': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
                 'rough': bool(args.rough)}
with open(STATE, 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=1)

if use_stt:
    def ts(t):
        ms = int(round(t * 1000))
        return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'

    cues, cur = [], []                                      # <= 7 words, a new cue after each sentence
    for n, w in enumerate(out_words):
        cur.append(w)
        nxt = out_words[n + 1] if n + 1 < len(out_words) else None
        if (len(cur) >= 7 or not nxt or nxt[0] - w[1] > 0.6
                or w[2].rstrip('"»”)').endswith(('.', '!', '?', '…'))):
            end = w[1] + 0.2 if not nxt else min(w[1] + 0.2, nxt[0])
            cues.append((cur[0][0], max(end, cur[0][0] + 0.3), ' '.join(x[2] for x in cur)))
            cur = []
    with open(f'{base}.srt', 'w', encoding='utf-8') as f:
        for n, (a, b, t) in enumerate(cues, 1):
            f.write(f'{n}\n{ts(a)} --> {ts(b)}\n{t}\n\n')
    with open(f'{base}.txt', 'w', encoding='utf-8') as f:
        f.write(' '.join(w for _s, _e, w in out_words).strip() + '\n')
    with open(f'{base}.takes.tsv', 'w', encoding='utf-8') as f:
        f.write(f'# stt={ENGINE} lang={args.lang}\n'
                '# start\tend\tstatus\ttext   (times on the joined footage, before cuts)\n')
        for (a, b), (st, t) in sorted(log.items()):
            f.write(f'{a:.3f}\t{b:.3f}\t{st}\t{text_of((a, b)) or t}\n')
    if ENGINE == 'whisper':
        with open(STT_CACHE, 'w', encoding='utf-8') as f:
            json.dump({'tag': TAG, 'spans': {f'{a:.3f}:{b:.3f}': ws for (a, b), ws in WORDS.items()},
                       'timed': {f'{a:.3f}:{b:.3f}': ws for (a, b), ws in TIMED.items()}}, f, ensure_ascii=False)
    say(f'-> {base}.txt + {base}.srt + {base}.takes.tsv')
    for t, msg in sorted(warnings):
        say(f'  to check at {to_out(t):.1f}s in the video: {msg}')

shutil.rmtree(work, ignore_errors=True)
