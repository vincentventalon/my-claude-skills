"""stt.py — word-level transcription, two engines, ONE contract.

Whatever the engine, the cut and the subtitles receive the same thing: for
each span of the audio (an island of sound, or a piece of one), the words
heard in it, in order:

    [(start, end, text), ...]   seconds on the audio given, start <= end,
                                every word inside its span, punctuation
                                stuck to its word ("honest," not "honest ,")

  whisper     (default) whisper.cpp on this computer: free, nothing leaves it.
              Each span is transcribed ON ITS OWN (whisper glues two takes
              into one sentence when it hears them together), word by word
              (-ml 1 -sow), one whisper-cli call for all of them (the model
              loads once). Then the KEPT spans only are heard a second time
              with DTW (-dtw, the model's attention; flash attention off,
              which it needs and which makes the text a little worse, hence
              two passes) and each word takes its DTW start, 60 ms earlier
              (retime). Measured against Scribe on the 354 kept words of a
              real 6 min rush: 22 ms off in the median, 111 ms at the 90th
              percentile (the plain timestamps: 90 and 282 ms). A model with
              no DTW preset (a custom ggml file) keeps the plain timestamps.
  elevenlabs  ElevenLabs Scribe (scribe_v1): paid, more exact on names and on
              the retakes whisper smooths over. ONE call for the whole audio,
              word timestamps; each word then goes to the span it starts in.
              Key: ELEVENLABS_API_KEY (environment, or ~/.config/video-editing/env).
              The answer is kept in ~/.cache/video-editing/elevenlabs/: running
              again, even with other settings, never pays twice.

No silent fallback from one engine to the other: a missing key, a refused key
or an empty quota stops with what to do.

For tests only: VIDEO_EDITING_SCRIBE_URL points the Scribe call elsewhere (a
local server that plays back a recorded answer), VIDEO_EDITING_SCRIBE_MODEL
changes the model id.
"""
import difflib, hashlib, json, os, re, subprocess, sys, tempfile, time, unicodedata, urllib.error, urllib.request, uuid, wave

MODELS_URL = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/'
MODEL_DIRS = [os.path.join(os.path.expanduser('~'), '.cache', 'whisper-cpp'),
              os.path.join(os.path.expanduser('~'), '.local', 'share', 'whisper-cpp', 'models')]
SCRIBE_URL = os.environ.get('VIDEO_EDITING_SCRIBE_URL', 'https://api.elevenlabs.io/v1/speech-to-text')
SCRIBE_MODEL = os.environ.get('VIDEO_EDITING_SCRIBE_MODEL', 'scribe_v1')
SCRIBE_CACHE = os.path.join(os.path.expanduser('~'), '.cache', 'video-editing', 'elevenlabs')
PUNCT = set(':;,.!?…»«"“”()-–—')
DTW_LEAD = 0.06          # DTW starts land ~60-90 ms late (measured): the word lights up a hair early
DTW_PRESETS = {'tiny', 'tiny.en', 'base', 'base.en', 'small', 'small.en', 'medium', 'medium.en',
               'large.v1', 'large.v2', 'large.v3', 'large.v3.turbo'}


# Windows: a .exe that cannot start because a DLL is missing (0xC0000135, 0xC0000139, 0xC000007B)
DLL_MISSING = {3221225781, 3221225785, 3221225595, -1073741515, -1073741511, -1073741701}


def say(msg):
    print(msg, file=sys.stderr)


def whisper_failed(binary, code, err):
    """What to say when whisper-cli stops (instead of a traceback)."""
    if code in DLL_MISSING:
        return (f'{binary} cannot start (code {code}): a DLL is missing, most often the Microsoft Visual C++ '
                'Redistributable (winget install Microsoft.VCRedist.2015+.x64; the `set-up-video-tools` skill checks it)')
    return f'whisper-cli stopped (code {code}): {(err or "").strip()[-600:]}'


# --- whisper ------------------------------------------------------------------------
def find_model(name):
    """An existing ggml-*.bin: the path given, else ggml-<name>.bin in a known folder. None if absent."""
    if os.path.exists(os.path.expanduser(name)):
        return os.path.expanduser(name)
    for d in MODEL_DIRS:
        p = os.path.join(d, f'ggml-{name}.bin')
        if os.path.exists(p):
            return p
    return None


def model_path(name):
    """find_model, else download ggml-<name>.bin into ~/.cache/whisper-cpp/ (once)."""
    found = find_model(name)
    if found:
        return found
    fn = f'ggml-{name}.bin'
    dest = os.path.join(MODEL_DIRS[0], fn)
    os.makedirs(MODEL_DIRS[0], exist_ok=True)
    say(f'downloading model {fn} (once; 1.6 GB for large-v3-turbo, 0.5 GB for small)...')
    tmp = dest + '.part'
    urllib.request.urlretrieve(MODELS_URL + fn, tmp,
        lambda n, b, t: say(f'  {n * b / 1e6:.0f} / {t / 1e6:.0f} MB') if n % 200 == 0 else None)
    os.replace(tmp, dest)
    return dest


def dtw_preset(model):
    """'ggml-large-v3-turbo-q5_0.bin' -> 'large.v3.turbo' (whisper-cli -dtw), None if unknown."""
    n = os.path.basename(model).removeprefix('ggml-').removesuffix('.bin')
    n = re.sub(r'-q\d(_\d)?$', '', n).replace('-', '.')
    return n if n in DTW_PRESETS else None


def json_words(path, dtw):
    """[(start, end, text)] of whisper-cli -ojf -ml 1 -sow: one segment per word; the
    start from DTW when there is one."""
    data = json.loads(open(path, encoding='utf-8', errors='replace').read())
    out = []
    for seg in data.get('transcription', []):
        text = seg.get('text', '').strip()
        if not text:
            continue
        s, e = seg['offsets']['from'] / 1000, seg['offsets']['to'] / 1000
        toks = [t for t in seg.get('tokens', []) if not t.get('text', '').startswith('[_')]
        if dtw and toks and toks[0].get('t_dtw', -1) >= 0:
            s = max(0.0, toks[0]['t_dtw'] / 100 - DTW_LEAD)
        out.append((s, max(s, e), text))
    return out


def srt_words(srt):
    """[(start, end, text)] of a word-per-cue SRT from whisper-cli (-ml 1 -sow)."""
    def ts(x):
        h, m, r = x.strip().split(':')
        s, ms = r.replace('.', ',').split(',')
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    out = []
    for blk in re.split(r'\n\s*\n', srt.strip()):
        lines = blk.strip().split('\n')
        if len(lines) >= 3 and ' --> ' in lines[1]:
            text = ' '.join(lines[2:]).strip()
            if text:
                t1, t2 = lines[1].split(' --> ')
                out.append((ts(t1), ts(t2), text))
    return out


def tidy(words):
    """Punctuation alone glued to the word before; bracketed noises ([Music],
    (laughs), *click*) kept as they are — the cut reads them as no speech."""
    out = []
    for s, e, t in words:
        t = t.strip()
        if not t:
            continue
        if all(c in PUNCT for c in t) and out:
            ps, pe, pt = out[-1]
            out[-1] = (ps, max(pe, e), pt + ('' if t[0] in ',.…' else ' ') + t)
            continue
        out.append((s, e, t))
    return out


def whisper_spans(wav, spans, todo, dur, model, lang, binary, ff, dtw=False):
    """Words of spans[k] for k in todo, each span transcribed ON ITS OWN with a
    little air on each side that never reaches into the neighbouring span.
    Times on `wav`; each word clamped inside its span. dtw=True: the timing
    pass (word starts from DTW), for retime()."""
    with tempfile.TemporaryDirectory() as d:
        with wave.open(wav) as w:
            sr, params = w.getframerate(), w.getparams()
            files, starts = [], []
            for k in todo:
                a, b = spans[k]
                lo = spans[k - 1][1] + 0.02 if k else 0.0
                hi = spans[k + 1][0] - 0.02 if k + 1 < len(spans) else dur
                fa, fb = max(lo, a - 0.15), min(hi, b + 0.15)
                w.setpos(max(0, int(fa * sr)))
                f = os.path.join(d, f'{k}.wav')
                with wave.open(f, 'wb') as o:
                    o.setparams(params)
                    o.writeframes(w.readframes(max(1, int((fb - fa) * sr))))
                files.append(f)
                starts.append(fa)
        threads = str(min(8, os.cpu_count() or 4))
        binary, model = os.path.abspath(binary), os.path.abspath(model)     # whisper-cli runs from `d`
        dtw = dtw_preset(model) if dtw else None
        timing = ['-nfa', '-dtw', dtw] if dtw else []          # DTW wants flash attention off
        for n in range(0, len(files), 150):          # command-line length, on Windows
            # the pieces by their bare name, from their folder: whisper-cli reads its arguments in the
            # Windows code page, a name like 12.wav never needs it (nor makes the line long)
            try:
                subprocess.run([binary, '-m', model, '-l', lang, '-t', threads, '-np', '-ml', '1', '-sow',
                                '-osrt', '-ojf'] + timing + [os.path.basename(f) for f in files[n:n + 150]],
                               cwd=d, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            except subprocess.CalledProcessError as e:
                sys.exit(whisper_failed(binary, e.returncode, e.stderr))
        out = []
        for k, f, fa in zip(todo, files, starts):
            a, b = spans[k]
            try:
                heard = json_words(f + '.json', dtw)
            except (OSError, ValueError, KeyError):           # no JSON: the SRT, plain timestamps
                heard = srt_words(open(f + '.srt', encoding='utf-8', errors='replace').read()
                                  if os.path.exists(f + '.srt') else '')
            ws, last = [], a
            for s, e, t in tidy(heard):
                s = min(max(fa + s, a, last), b)
                e = min(max(fa + e, s), b)
                ws.append((round(s, 3), round(e, 3), t))
                last = s
            out.append(ws)
    return out


def _norm(word):
    w = unicodedata.normalize('NFD', word.lower())
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in w if unicodedata.category(c) != 'Mn'))


def retime(words, timed):
    """The words the cut read, each with the start the timing pass gave the same
    word (matched in order); a word it heard differently keeps its own start.
    Starts never go backwards."""
    m = difflib.SequenceMatcher(None, [_norm(t) for *_x, t in words], [_norm(t) for *_x, t in timed],
                                autojunk=False)
    new = list(words)
    for blk in m.get_matching_blocks():
        for j in range(blk.size):
            s0, e0, t0 = words[blk.a + j]
            s1 = timed[blk.b + j][0]
            new[blk.a + j] = (s1, max(e0, s1), t0)
    out, last = [], None
    for s, e, t in new:
        s = s if last is None else max(s, last)
        out.append((round(s, 3), round(max(e, s), 3), t))
        last = s
    return out


# --- ElevenLabs Scribe ----------------------------------------------------------------
def scribe_key():
    k = os.environ.get('ELEVENLABS_API_KEY', '').strip()
    if not k:
        sys.exit('stt=elevenlabs but ELEVENLABS_API_KEY is not set: put it in the environment or in '
                 '~/.config/video-editing/env (one line ELEVENLABS_API_KEY=..., chmod 600), '
                 'or run with --stt whisper (free, local)')
    return k


def _post(data, fields):
    """multipart/form-data POST of the audio + fields; the parsed JSON answer."""
    bnd = uuid.uuid4().hex
    body = b''.join(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                    for k, v in fields)
    body += (f'--{bnd}\r\nContent-Disposition: form-data; name="file"; filename="audio.flac"\r\n'
             f'Content-Type: audio/flac\r\n\r\n').encode() + data + f'\r\n--{bnd}--\r\n'.encode()
    for attempt in range(4):
        req = urllib.request.Request(SCRIBE_URL, data=body, method='POST', headers={
            'xi-api-key': scribe_key(), 'Content-Type': f'multipart/form-data; boundary={bnd}',
            'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            msg = e.read().decode('utf-8', errors='replace')[:300]
            low = msg.lower()
            if e.code == 401:
                sys.exit(f'ElevenLabs refused the key (401): check ELEVENLABS_API_KEY. {msg}')
            if e.code == 402 or 'quota' in low or 'credit' in low:
                sys.exit(f'ElevenLabs: no credits left ({e.code}). Top up on elevenlabs.io, or run '
                         f'with --stt whisper (free, local). Nothing was cut. {msg}')
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 * 2 ** attempt)
                continue
            sys.exit(f'ElevenLabs error {e.code}: {msg}')
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            if attempt < 3:
                time.sleep(2 * 2 ** attempt)
                continue
            sys.exit(f'ElevenLabs cannot be reached ({e}). Check the connection, or run with --stt whisper.')


def scribe_words(res):
    """[(start, end, text)] of a Scribe answer: the `word` entries only (no
    spacing, no audio event), a zero-length word dropped (made up), the
    punctuation Scribe sends as its own entry glued to the word before."""
    if 'transcripts' in res and 'words' not in res:        # multichannel answer: first channel
        res = (res.get('transcripts') or [{}])[0]
    out = []
    for w in res.get('words') or []:
        if w.get('type', 'word') != 'word' or w.get('start') is None:
            continue
        t = (w.get('text') or '').strip()
        s, e = float(w['start']), float(w.get('end') if w.get('end') is not None else w['start'])
        if not t or (e - s < 0.005 and any(c.isalnum() for c in t)):
            continue
        out.append((round(s, 3), round(max(s, e), 3), t))
    return tidy(out)


def scribe(wav, lang, ff):
    """Scribe on the whole `wav`: [(start, end, text)], times on the wav. One paid
    call per audio and language, ever (cache)."""
    fields = [('model_id', SCRIBE_MODEL), ('timestamps_granularity', 'word'),
              ('tag_audio_events', 'false'), ('diarize', 'false')]
    if lang and lang != 'auto':
        fields.append(('language_code', lang))
    with wave.open(wav) as w:
        pcm = w.readframes(w.getnframes())
    h = hashlib.sha1(pcm + json.dumps(fields).encode()).hexdigest()
    cached = os.path.join(SCRIBE_CACHE, f'{h}.json')
    if os.path.exists(cached):
        say('transcript: ElevenLabs Scribe (cached answer, nothing paid)')
        return scribe_words(json.load(open(cached, encoding='utf-8')))
    scribe_key()                                           # no key: stop before any work
    say(f'transcript: ElevenLabs Scribe ({SCRIBE_MODEL}), one call for the whole audio...')
    with tempfile.TemporaryDirectory() as d:
        flac = os.path.join(d, 'audio.flac')
        subprocess.run([ff, '-v', 'error', '-y', '-i', wav, '-c:a', 'flac', flac], check=True)
        data = open(flac, 'rb').read()
    res = _post(data, fields)
    if not isinstance(res, dict) or not ('words' in res or 'transcripts' in res):
        sys.exit(f'ElevenLabs answered something unexpected: {str(res)[:200]}')
    os.makedirs(SCRIBE_CACHE, exist_ok=True)
    with open(cached, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False)
    return scribe_words(res)


def assign(words, spans, early=0.25):
    """Each word to the span its start falls in (or starts up to `early` s before:
    the silence threshold sometimes eats a soft attack). A word that starts in a
    silence the cut removes belongs to no span. Times clamped inside the span."""
    out = [[] for _ in spans]
    order = sorted(range(len(spans)), key=lambda k: spans[k][0])
    # the early margin never reaches back into the span before
    reach = {k: min(early, spans[k][0] - spans[order[n - 1]][1]) if n else early for n, k in enumerate(order)}
    for s, e, t in words:
        hit = next((k for k in order if spans[k][0] <= s < spans[k][1]), None)
        if hit is None:
            hit = next((k for k in order if spans[k][0] - reach[k] <= s < spans[k][0]), None)
        if hit is None:
            continue
        a, b = spans[hit]
        s2 = min(max(s, a), b)
        out[hit].append((round(s2, 3), round(min(max(e, s2), b), 3), t))
    return out
