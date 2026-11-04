#!/usr/bin/env python3
"""Audit your own TikTok or Instagram account: what works, measured.

    python3 audit.py @your_account --platform tiktok -n 30 --followers 1200 --lang fr

One anonymous pass (yt-dlp, no cookies, no login, no password):

  1. the list of the last N videos with their counters (one request);
  2. the first 10 seconds of each video, smallest format, a pause between two
     videos, transcribed locally by whisper.cpp: the hook is what is said in
     the first 5 seconds, verbatim;
  3. the numbers: the median, each video against it (x median), the outliers,
     the length that works, the cadence, the hooks of the 5 best against the
     5 worst, the hashtags, the videos that make people comment.

Instagram does not let an anonymous reader list a profile (yt-dlp itself
marks that reader as broken): the script says so, does not insist, and the
manual way takes over: --csv FILE, your own numbers (an export, or typed),
see references/manual.md.

Writes ./audit-<account>-<date>/: catalogue.csv, hooks.tsv, chiffres.json,
images/ (3 frames of the first 3 seconds of each video) and AUDIT.md: every
number filled in, the reading left to Claude at each `<!-- CLAUDE:` marker.
Run it again: the listing and the hooks already read are reused, nothing is
fetched twice (--refresh reads the listing again).

Python 3.10+, standard library only. yt-dlp, ffmpeg and whisper-cli (the
same binary and model as the `edit-my-video` skill) are called as commands.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(errors='replace')

CONFIG = Path.home() / '.config' / 'video-editing' / 'config.json'
MODEL_DIRS = [Path.home() / '.cache' / 'whisper-cpp',      # the same as the `edit-my-video` skill
              Path.home() / '.local' / 'share' / 'whisper-cpp' / 'models']
MODELS_URL = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/'
MAX_N = 50        # an audit reads your last videos, not your whole account
HOOK_S = 5.0      # the hook = what is said in the first 5 seconds
CLIP_S = 10       # seconds downloaded per video: enough to finish the hook sentence
TOP = 5


def say(msg=''):
    print(msg, flush=True)


def die(msg, code=2):
    print(msg, file=sys.stderr, flush=True)
    sys.exit(code)


# --- arguments ---------------------------------------------------------------
ap = argparse.ArgumentParser(description='Audit your own TikTok or Instagram account.')
ap.add_argument('account', help='@your_account, or the profile link')
ap.add_argument('--platform', choices=['tiktok', 'instagram'],
                help='found from the link; required with a bare @account')
ap.add_argument('-n', '--count', type=int, default=30, help=f'last N videos (default 30, max {MAX_N})')
ap.add_argument('--followers', type=int, help='follower count, read by the user in their app')
ap.add_argument('--csv', help='manual way: a CSV of your own numbers (references/manual.md)')
ap.add_argument('--lang', help='spoken language for whisper: fr, en, es... (default: config, else auto)')
ap.add_argument('--report', choices=['fr', 'en'], default='fr', help='language of the files written')
ap.add_argument('--out', default='.', help='where to create audit-<account>-<date>/ (default: here)')
ap.add_argument('--delay', type=float, default=3.0, help='seconds between two videos (default 3, plus jitter)')
ap.add_argument('--min-age-days', type=float, default=3.0,
                help='younger videos are still growing: listed apart, out of the median (default 3)')
ap.add_argument('--no-hooks', action='store_true', help='no download, no transcription: numbers only')
ap.add_argument('--model', help='whisper model name or path (default: config, else large-v3-turbo)')
ap.add_argument('--tz', help='time zone for the posting hours, e.g. Europe/Paris (default: this computer)')
ap.add_argument('--date-order', choices=['dmy', 'mdy'],
                help='--csv dates like 03/04/2026: day first (dmy) or month first (mdy)')
ap.add_argument('--refresh', action='store_true', help='read the listing again instead of reusing it')
args = ap.parse_args()

R = args.report


def t(fr, en):
    return fr if R == 'fr' else en


if not 1 <= args.count <= MAX_N:
    die(f'-n must be between 1 and {MAX_N}: an audit reads your last videos, not the whole account.')

try:
    CFG = json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {}
except ValueError as e:
    say(f'warning: {CONFIG} unreadable ({e}), ignored')
    CFG = {}
FF = os.path.expanduser(CFG.get('ffmpeg') or os.environ.get('FFMPEG') or 'ffmpeg')
LANG = args.lang or CFG.get('lang') or 'auto'
MODEL = args.model or CFG.get('whisper_model') or 'large-v3-turbo'
if str(CFG.get('stt', '')).lower() not in ('', 'whisper', 'whisper.cpp', 'whisper-cpp'):
    say(f'config stt={CFG.get("stt")}: the hooks are 5 seconds long, whisper.cpp reads them locally, '
        'no paid transcription here.')

TZ = None
if args.tz:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(args.tz)


def local(ts):
    return dt.datetime.fromtimestamp(ts, TZ) if TZ else dt.datetime.fromtimestamp(ts)


# --- account -----------------------------------------------------------------
def parse_account(s, platform):
    s = s.strip()
    m = re.search(r'tiktok\.com/@([\w.\-]+)', s)
    if m:
        return m.group(1), 'tiktok'
    m = re.search(r'instagram\.com/([\w.\-]+)', s)
    if m and m.group(1).lower() not in ('p', 'reel', 'reels', 'tv', 'stories', 'explore'):
        return m.group(1), 'instagram'
    h = s.lstrip('@').strip('/')
    if not re.fullmatch(r'[\w.\-]+', h):
        die(f'"{s}" is not an account: give @your_account or the profile link.')
    if not platform:
        die('TikTok or Instagram? Pass --platform tiktok or --platform instagram.')
    return h, platform


HANDLE, PLATFORM = parse_account(args.account, args.platform)
PLAT = {'tiktok': 'TikTok', 'instagram': 'Instagram'}[PLATFORM]
NOW = time.time()
TODAY = local(NOW).strftime('%Y-%m-%d')
OUT = Path(args.out).expanduser() / f'audit-{HANDLE}-{TODAY}'
RAW = OUT / '.brut'
IMG = OUT / 'images'


# --- numbers in the wild -------------------------------------------------------
def num(v):
    """'3 264', '1,2 k', '12.5K', '1.234', 3264 -> float, or None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    for c in (' ', '\xa0', ' ', ' '):
        s = s.replace(c, '')
    if s in ('', '-', '--', 'n/a', 'na', 'none', 'null', '—'):
        return None
    mult = 1.0
    if s.endswith('k'):
        mult, s = 1e3, s[:-1]
    elif s.endswith('m'):
        mult, s = 1e6, s[:-1]
    if re.fullmatch(r'\d{1,3}([.,]\d{3})+', s) and mult == 1.0:
        s = re.sub(r'[.,]', '', s)
    s = s.replace(',', '.')
    try:
        return float(s) * mult
    except ValueError:
        return None


def duration(v):
    if v is None:
        return None
    s = str(v).strip().lower().rstrip('s').strip()
    m = re.fullmatch(r'(\d+):(\d{1,2})(?::(\d{1,2}))?', s)
    if m:
        a, b, c = m.groups()
        return int(a) * 3600 + int(b) * 60 + int(c) if c else int(a) * 60 + int(b)
    return num(s)


def parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    if re.fullmatch(r'\d{10}', s):
        return int(s)
    try:
        d = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
        return int(d.timestamp())
    except ValueError:
        pass
    m = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?', s)
    if m:
        y, mo, d, h, mi = m.groups()
    else:
        m = re.match(r'(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})(?:[ ,]+(\d{1,2}):(\d{2}))?', s)
        if not m:
            return None
        a, b, y, h, mi = m.groups()
        a, b = int(a), int(b)
        if a > 12:
            d, mo = a, b
        elif b > 12:
            mo, d = a, b
        elif (args.date_order or ('dmy' if R == 'fr' else 'mdy')) == 'dmy':
            d, mo = a, b
        else:
            mo, d = a, b
        y = int(y) + (2000 if int(y) < 100 else 0)
    try:
        return int(dt.datetime(int(y), int(mo), int(d), int(h or 12), int(mi or 0)).timestamp())
    except ValueError:
        return None


def norm(s):
    s = unicodedata.normalize('NFD', str(s).lower().replace('’', "'"))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return ' '.join(re.sub(r"[^a-z0-9']+", ' ', s).split())


def hashtags(text):
    return sorted({h.lower() for h in re.findall(r'#(\w+)', text or '')})


def first_line(text, width=110):
    line = next((l.strip() for l in (text or '').splitlines() if l.strip()), '')
    line = re.sub(r'\s*#\w+', '', line).strip() or line
    return line if len(line) <= width else line[:width - 1].rstrip() + '…'


def video(id_, url='', ts=None, dur=None, views=None, likes=None, comments=None,
          shares=None, saves=None, caption='', file=''):
    return {'id': str(id_ or ''), 'url': url or '', 'ts': ts, 'duration_s': dur,
            'views': views, 'likes': likes, 'comments': comments, 'shares': shares,
            'saves': saves, 'caption': caption or '', 'file': file or ''}


# --- 1. the listing ------------------------------------------------------------
def ytdlp():
    y = shutil.which('yt-dlp')
    if not y:
        die('yt-dlp not found. Install it: macOS `brew install yt-dlp`, Windows `winget install yt-dlp`, '
            'Linux `pipx install yt-dlp`. Then run again.', 4)
    return y


def fetch_listing():
    cache = RAW / 'listing.json'
    if cache.exists() and not args.refresh:
        say(f'listing reused: {cache} (--refresh to read it again)')
        return json.loads(cache.read_text(encoding='utf-8'))
    if PLATFORM == 'tiktok':
        url, extra = f'https://www.tiktok.com/@{HANDLE}', 3      # up to 3 pinned videos come first
    else:
        url, extra = f'https://www.instagram.com/{HANDLE}/', 0
    say(f'reading the profile once, anonymously: {url}')
    r = subprocess.run([ytdlp(), '--flat-playlist', '-J', '--playlist-end', str(args.count + extra),
                        '--socket-timeout', '30', '--no-warnings', url],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    entries = []
    if r.returncode == 0:
        try:
            entries = (json.loads(r.stdout or 'null') or {}).get('entries') or []
        except ValueError:
            entries = []
    if not entries:
        err = next((l for l in reversed((r.stderr or '').splitlines()) if l.strip()), 'no video returned')
        if PLATFORM == 'instagram':
            die(f'BLOCKED: Instagram did not let an anonymous reader list @{HANDLE}.\n'
                f'  yt-dlp: {err}\n'
                '  Not retried: insisting gets the network blocked, not the data.\n'
                '  Manual way: your numbers in a CSV (export or typed), then the same command with '
                '--csv FILE. See references/manual.md.', 3)
        die(f'TikTok returned nothing for @{HANDLE}.\n  yt-dlp: {err}\n'
            '  Check the account name and that the account is public. An old yt-dlp breaks often: '
            '`yt-dlp -U` (or `brew upgrade yt-dlp`), then run again once. Still nothing: --csv '
            '(references/manual.md).', 3)
    out = []
    for e in entries:
        vid = str(e.get('id') or '')
        link = e.get('url') or e.get('webpage_url') or ''
        if not str(link).startswith('http'):
            link = (f'https://www.tiktok.com/@{HANDLE}/short-video/{vid}' if PLATFORM == 'tiktok'
                    else f'https://www.instagram.com/reel/{vid}/')
        out.append(video(vid, link, e.get('timestamp'), num(e.get('duration')),
                         num(e.get('view_count')), num(e.get('like_count')), num(e.get('comment_count')),
                         num(e.get('repost_count')), num(e.get('save_count')),
                         e.get('description') or e.get('title') or ''))
    RAW.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    return out


ALIASES = {
    'date': ['date', 'publish time', 'publish date', 'published', 'posted', 'post time', 'timestamp',
             'created', 'heure de publication', 'date de publication', 'publie le', 'publication'],
    'url': ['url', 'link', 'permalink', 'lien', 'permalien'],
    'duration_s': ['duree s', 'duree', 'duration', 'duration sec', 'duration s', 'length', 'longueur'],
    'views': ['vues', 'views', 'plays', 'lectures', 'video views', 'nombre de vues'],
    'likes': ['likes', 'like', "j'aime", "mentions j'aime"],
    'comments': ['commentaires', 'comments'],
    'shares': ['partages', 'shares', 'repartages'],
    'saves': ['enregistrements', 'saves', 'saved', 'sauvegardes'],
    'caption': ['legende', 'caption', 'description', 'titre', 'title', 'texte', 'text'],
    'file': ['fichier', 'file', 'video', 'path', 'chemin'],
    'id': ['id', 'post id', 'media id', 'identifiant', 'shortcode'],
}


def read_csv(path):
    p = Path(path).expanduser()
    if not p.exists():
        die(f'{p}: file not found.')
    raw = p.read_bytes()
    for enc in ('utf-8-sig', 'utf-16', 'cp1252'):
        try:
            text = raw.decode(enc)
            if '\x00' not in text:
                break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(text.splitlines(), dialect))
    if not rows:
        die(f'{p}: empty file.')
    header = [norm(h) for h in rows[0]]
    col = {}
    for exact in (True, False):                 # exact names first, then "Views (lifetime)"-like ones
        for key, names in ALIASES.items():
            if key in col:
                continue
            for i, h in enumerate(header):
                if i not in col.values() and any(h == a if exact else h.startswith(a + ' ') for a in names):
                    col[key] = i
                    break
    unused = [rows[0][i] for i in range(len(header)) if i not in col.values()]
    say(f'CSV columns read: {", ".join(f"{k}={rows[0][i]!r}" for k, i in col.items())}')
    if unused:
        say(f'CSV columns ignored: {", ".join(repr(u) for u in unused)}')
    if 'views' not in col and 'likes' not in col:
        die('No views and no likes column recognized. Rename the columns as in references/manual.md '
            '(date,url,duree_s,vues,likes,commentaires,partages,enregistrements,legende) and run again.')
    out = []
    for n, r in enumerate(rows[1:], 1):
        g = lambda k: r[col[k]] if k in col and col[k] < len(r) else None
        key = g('id') or g('url') or 'r' + hashlib.md5(f'{g("date")}|{g("caption")}'.encode()).hexdigest()[:8]
        v = video(key, g('url') or '', parse_date(g('date')),
                  duration(g('duration_s')), num(g('views')), num(g('likes')), num(g('comments')),
                  num(g('shares')), num(g('saves')), g('caption') or '', g('file') or '')
        if v['views'] is None and v['likes'] is None:
            continue                    # a sub-header ("Lifetime") or a total line
        m = re.search(r'/(?:reels?|p|video)/([\w\-]+)', v['url'])
        if m and v['id'] == v['url']:
            v['id'] = m.group(1)
        out.append(v)
    if not out:
        die(f'{p}: no row with a number in it.')
    future = [v for v in out if v['ts'] and v['ts'] > NOW + 86400]
    if future:
        die(f'{len(future)} date(s) in the future in {p.name}: the day and the month are swapped. '
            'Run again with --date-order dmy (03/10 = 3 October) or mdy (03/10 = March 10).')
    return out


# --- 2. the hooks ---------------------------------------------------------------
def model_path(name):
    p = Path(name).expanduser()
    if p.exists():
        return str(p)
    fn = name if name.endswith('.bin') else f'ggml-{name}.bin'
    for d in MODEL_DIRS:
        if (d / fn).exists():
            return str(d / fn)
    dest = MODEL_DIRS[0] / fn
    if not dest.exists():
        MODEL_DIRS[0].mkdir(parents=True, exist_ok=True)
        say(f'downloading the whisper model {fn} (once, shared with the `edit-my-video` skill; '
            '1.6 GB for large-v3-turbo, 0.5 GB for small)...')
        tmp = str(dest) + '.part'
        urllib.request.urlretrieve(MODELS_URL + fn, tmp, lambda n, b, tot: say(
            f'  {n * b / 1e6:.0f} / {tot / 1e6:.0f} MB') if n % 400 == 0 else None)
        os.replace(tmp, dest)
    return str(dest)


JUNK = re.compile(r"sous-titr|amara\.org|merci d'avoir regard|thanks? for watching|"
                  r"subtitles by|ondertitel|untertitel", re.I)
END = re.compile(r'[.!?…]["»”)]?$')


def safe(s):
    return re.sub(r'[^\w\-]', '_', s)[:80]


def fetch_clip(v, tmp):
    """The first CLIP_S seconds of a video, smallest format. (path, error)."""
    if v['file']:
        p = Path(v['file']).expanduser()
        return (p, None) if p.exists() else (None, f'file not found: {p}')
    if not v['url']:
        return None, 'no link'
    stem = tmp / safe(v['id'])
    cmd = [ytdlp(), '-q', '--no-warnings', '--no-playlist', '--socket-timeout', '30',
           '-S', '+size,+br,+res', '--download-sections', f'*0-{CLIP_S}',
           '-o', str(stem) + '.%(ext)s', v['url']]
    if FF != 'ffmpeg':
        cmd[1:1] = ['--ffmpeg-location', FF]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    files = [f for f in tmp.glob(stem.name + '.*') if not f.name.endswith(('.part', '.ytdl'))]
    if r.returncode == 0 and files:
        return files[0], None
    err = next((l for l in reversed((r.stderr or '').splitlines()) if l.strip()), 'download failed')
    return None, err[-200:]


def join_words(ws):
    return ' '.join(''.join(w[2] for w in ws).split())


def hook_of(words):
    """(hook said in the first 5 s, that sentence finished, words in the first 5 s)."""
    k = 0
    while k < len(words) and words[k][0] < HOOK_S:
        k += 1
    w5 = words[:k]
    sent = list(w5)
    if w5 and not END.search(w5[-1][2].strip()):
        for w in words[k:]:
            if w[0] >= CLIP_S - 0.3:
                break
            sent.append(w)
            if END.search(w[2].strip()):
                break
    n5 = sum(1 for w in w5 if re.search(r'\w', w[2]))
    return join_words(w5), join_words(sent), n5


def get_hooks(videos):
    cache_f = RAW / 'hooks.json'
    cache = json.loads(cache_f.read_text(encoding='utf-8')) if cache_f.exists() else {}
    todo = [v for v in videos if cache.get(v['id'], {}).get('status') not in ('ok', 'no_speech')]
    if args.no_hooks or not todo:
        if todo:
            say('--no-hooks: no download, no transcription; the captions stand in for the hooks.')
        return cache
    whisper = shutil.which('whisper-cli') or shutil.which('whisper-cpp')
    if not shutil.which(FF) and not Path(FF).exists():
        say(f'ffmpeg not found ({FF}): no hooks, the captions stand in. Install it as the '
            '`set-up-video-tools` skill says, then run again: only the hooks are fetched.')
        return cache
    if not whisper:
        say('whisper-cli not found: no hooks, the captions stand in. Install it as the setup '
            'skill says (macOS: brew install whisper-cpp), then run again: only the hooks are fetched.')
        return cache
    try:
        model = model_path(MODEL)
    except Exception as e:                                   # no network, disk full...
        say(f'whisper model unavailable ({e}): no hooks this time.')
        return cache
    IMG.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='audit-'))
    wavs, fails, net, stopped = {}, 0, 0, False
    try:
        for i, v in enumerate(todo, 1):
            if not v['file'] and not v['url']:
                cache[v['id']] = {'status': 'no_source'}
                continue
            if stopped and not v['file']:
                cache[v['id']] = {'status': 'skipped'}
                continue
            if not v['file'] and v['url']:
                if net:
                    time.sleep(args.delay + random.uniform(0, args.delay / 2))
                net += 1
            clip, err = fetch_clip(v, tmp)
            if not clip and not v['file'] and v['url']:      # a CDN hiccup is common: one retry, later
                time.sleep(2 * args.delay + random.uniform(0, args.delay))
                clip, err = fetch_clip(v, tmp)
            if not clip:
                cache[v['id']] = {'status': 'download_failed', 'error': err}
                say(f'  [{i}/{len(todo)}] {v["id"]}: not read ({err})')
                fails += 0 if v['file'] else 1
                if fails >= 2 and not stopped:
                    stopped = True
                    say(f'  two refusals in a row: {PLAT} is blocking, the downloads stop here '
                        '(the captions stand in for the missing hooks).')
                continue
            fails = 0
            wav = tmp / f'{safe(v["id"])}.wav'
            subprocess.run([FF, '-v', 'error', '-y', '-i', str(clip), '-t', str(CLIP_S), '-vn',
                            '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(wav)])
            img = IMG / f'{safe(v["id"])}.jpg'
            subprocess.run([FF, '-v', 'error', '-y', '-ss', '0.2', '-i', str(clip), '-t', '3.3',
                            '-vf', 'fps=2/3,scale=240:-2,tile=3x1', '-frames:v', '1', str(img)])
            if clip.parent == tmp:
                clip.unlink(missing_ok=True)
            if wav.exists():
                wavs[v['id']] = (str(wav), img.exists())
            say(f'  [{i}/{len(todo)}] {v["id"]}: first {CLIP_S} s read')
        if wavs:
            say(f'transcribing {len(wavs)} hooks with whisper.cpp ({Path(model).name}), locally...')
            threads = str(min(8, os.cpu_count() or 4))
            files = [w for w, _ in wavs.values()]
            for n in range(0, len(files), 100):
                subprocess.run([whisper, '-m', model, '-l', LANG, '-t', threads, '-np',
                                '-ml', '1', '-sow', '-oj'] + files[n:n + 100],
                               capture_output=True)
            for vid, (w, has_img) in wavs.items():
                try:
                    data = json.loads(Path(w + '.json').read_bytes().decode('utf-8', 'replace'))
                except (OSError, ValueError):
                    cache[vid] = {'status': 'transcription_failed'}
                    continue
                words = [(s['offsets']['from'] / 1000, s['offsets']['to'] / 1000, s['text'])
                         for s in data.get('transcription', []) if s.get('text', '').strip()
                         and not re.fullmatch(r'\s*[\[(*♪].*', s['text'])]
                hook, sent, n5 = hook_of(words)
                speech = bool(re.search(r'\w', hook)) and not (JUNK.search(hook) and n5 < 15)
                cache[vid] = {'status': 'ok' if speech else 'no_speech',
                              'hook': hook if speech else '', 'sentence': sent if speech else '',
                              'words_5s': n5 if speech else 0,
                              'lang': (data.get('result') or {}).get('language', ''),
                              'image': f'images/{safe(vid)}.jpg' if has_img else ''}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding='utf-8')
    return cache


# --- 3. the numbers --------------------------------------------------------------
def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def per_k(v, key):
    return v[key] * 1000 / v['views'] if v.get(key) is not None and v.get('views') else None


Q_FR = r"^(comment|pourquoi|quel|quelle|quels|quelles|combien|est-ce|c'est quoi|qui|ou|quand|tu sais|vous savez|savez-vous|sais-tu)\b"
Q_EN = r"^(how|why|what|which|who|when|where|do you|did you|is it|are you|can you|have you|would you)\b"
NUMW = (r"\b(deux|trois|quatre|cinq|six|sept|huit|neuf|dix|vingt|trente|cent|mille|million|"
        r"two|three|four|five|six|seven|eight|nine|ten|twenty|hundred|thousand|million)s?\b")
FEATURES = [
    ('question', t('pose une question', 'asks a question'),
     lambda h: '?' in h or re.search(Q_FR + '|' + Q_EN, norm(h)) is not None),
    ('number', t('donne un chiffre', 'gives a number'),
     lambda h: re.search(r'\d', h) is not None or re.search(NUMW, norm(h)) is not None),
    ('you', t('parle à « tu / vous »', 'talks to "you"'),
     lambda h: re.search(r"\b(tu|toi|ton|ta|tes|vous|votre|vos|t'|you|your)\b", norm(h)) is not None),
    ('me', t('parle de soi (« je »)', 'talks about "I"'),
     lambda h: re.search(r"\b(je|j'|moi|mon|ma|mes|i|i'm|my|me)\b", norm(h)) is not None),
]


def compute(videos, hooks):
    for v in videos:
        v['age_d'] = (NOW - v['ts']) / 86400 if v['ts'] else None
        v['hashtags'] = hashtags(v['caption'])
        h = hooks.get(v['id'], {})
        v['hook'], v['sentence'] = h.get('hook', ''), h.get('sentence', '')
        v['words_5s'], v['hook_status'] = h.get('words_5s'), h.get('status', 'not_read')
        v['image'] = h.get('image', '')
    n_views = sum(1 for v in videos if v['views'] is not None)
    if n_views and n_views >= 0.8 * len(videos):
        metric = 'views'
    elif all(v['likes'] is not None and v['comments'] is not None for v in videos):
        metric = 'interactions'
    else:
        metric = 'likes'
    for v in videos:
        if metric == 'views':
            v['m'] = v['views']
        elif metric == 'interactions':
            v['m'] = v['likes'] + v['comments']
        else:
            v['m'] = v['likes']
    measured = [v for v in videos if v['m'] is not None]
    recent = [v for v in measured if v['age_d'] is not None and v['age_d'] < args.min_age_days]
    elig = [v for v in measured if v not in recent]
    missing = [v for v in videos if v['m'] is None]
    median = med([v['m'] for v in elig])
    for v in measured:
        v['x'] = v['m'] / median if median else None
    elig.sort(key=lambda v: (v['x'] if v['x'] is not None else -1), reverse=True)
    for k, v in enumerate(elig, 1):
        v['rank'] = k
        v['status'] = ('outlier' if v['x'] and v['x'] >= 2 else 'flop' if v['x'] is not None
                       and v['x'] <= 0.5 else 'normal')
    for v in recent:
        v['rank'], v['status'] = '', 'recent'
    for v in missing:
        v['rank'], v['status'], v['x'] = '', 'no_number', None
    k = min(TOP, len(elig) // 2) if len(elig) >= 2 else len(elig)
    top, flop = elig[:k], list(reversed(elig[-k:])) if k else []
    flop.sort(key=lambda v: v['x'] if v['x'] is not None else 0)

    total = sum(v['m'] for v in elig) or 0
    mean = total / len(elig) if elig else None
    s = {
        'account': HANDLE, 'platform': PLATFORM, 'date': TODAY, 'metric': metric,
        'source': 'csv' if args.csv else 'yt-dlp (anonymous)',
        'n_read': len(videos), 'n_compared': len(elig), 'n_recent': len(recent),
        'n_missing': len(missing), 'min_age_days': args.min_age_days,
        'median': median, 'mean': mean, 'mean_over_median': mean / median if median and mean else None,
        'top_share': sum(v['m'] for v in top) / total if total else None, 'k': k,
        'n_outliers': sum(1 for v in elig if v['status'] == 'outlier'),
        'n_flops': sum(1 for v in elig if v['status'] == 'flop'),
        'followers': args.followers,
        'median_over_followers': median / args.followers if median and args.followers else None,
        'top': [v['id'] for v in top], 'flop': [v['id'] for v in flop],
    }
    dated = sorted([v for v in measured if v['ts']], key=lambda v: v['ts'])
    if dated:
        s['first'], s['last'] = local(dated[0]['ts']).strftime('%Y-%m-%d'), local(dated[-1]['ts']).strftime('%Y-%m-%d')
    if len(dated) >= 2:
        span = (dated[-1]['ts'] - dated[0]['ts']) / 86400
        gaps = [((b['ts'] - a['ts']) / 86400, a, b) for a, b in zip(dated, dated[1:])]
        g = max(gaps, key=lambda x: x[0])
        s['per_week'] = (len(dated) - 1) / span * 7 if span > 0 else None
        s['gap_median_d'] = med([x[0] for x in gaps])
        s['gap_max_d'] = g[0]
        s['gap_max'] = [local(g[1]['ts']).strftime('%Y-%m-%d'), local(g[2]['ts']).strftime('%Y-%m-%d')]
    # length
    s['duration_median'] = med([v['duration_s'] for v in elig])
    s['duration_top'] = med([v['duration_s'] for v in top])
    s['duration_flop'] = med([v['duration_s'] for v in flop])
    buckets = []
    for lo, hi in ((0, 30), (30, 60), (60, 90), (90, 10 ** 6)):
        b = [v for v in elig if v['duration_s'] is not None and lo <= v['duration_s'] < hi]
        buckets.append({'from': lo, 'to': hi, 'n': len(b), 'x_median': med([v['x'] for v in b]),
                        'n_outliers': sum(1 for v in b if v['status'] == 'outlier')})
    s['buckets'] = buckets
    durs = sorted(v['duration_s'] for v in top if v['duration_s'] is not None)
    if len(durs) >= 2:
        q = statistics.quantiles(durs, n=4, method='inclusive')
        lo, hi = 5 * math.floor(q[0] / 5), 5 * math.ceil(q[2] / 5)
        s['target_duration'] = [lo, max(hi, lo + 5)]
    elif durs:
        s['target_duration'] = [5 * math.floor(durs[0] / 5), 5 * math.ceil(durs[0] / 5) + 5]
    # engagement per 1,000 views
    if metric == 'views':
        s['per_1000'] = {key: med([per_k(v, key) for v in elig])
                         for key in ('likes', 'comments', 'shares', 'saves')}
        for v in measured:
            v['comments_k'] = per_k(v, 'comments')
            v['saves_k'] = per_k(v, 'saves')
        talk = sorted([v for v in elig if v.get('comments_k') is not None],
                      key=lambda v: v['comments_k'], reverse=True)
    else:
        talk = sorted([v for v in elig if v['comments'] is not None], key=lambda v: v['comments'], reverse=True)
    s['talk'] = [v['id'] for v in talk[:3] if (v['comments'] or 0) > 0]
    # posting hours
    blocks = []
    for lo, hi, fr, en in ((0, 6, 'nuit (0 h - 6 h)', 'night (0-6)'), (6, 12, 'matin (6 h - 12 h)', 'morning (6-12)'),
                           (12, 18, 'après-midi (12 h - 18 h)', 'afternoon (12-18)'),
                           (18, 24, 'soir (18 h - 24 h)', 'evening (18-24)')):
        b = [v for v in elig if v['ts'] and lo <= local(v['ts']).hour < hi]
        blocks.append({'label': t(fr, en), 'n': len(b), 'x_median': med([v['x'] for v in b])})
    s['hours'] = blocks
    # hashtags
    counts = {}
    for v in elig:
        for h in v['hashtags']:
            counts[h] = counts.get(h, 0) + 1
    tags = []
    for h, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        if n < 3:
            continue
        w = [v['x'] for v in elig if h in v['hashtags']]
        wo = [v['x'] for v in elig if h not in v['hashtags']]
        tags.append({'tag': h, 'n': n, 'x_with': med(w), 'x_without': med(wo) if len(wo) >= 3 else None,
                     'everywhere': n >= 0.9 * len(elig)})
    s['hashtags'] = tags[:15]
    # hooks
    heard = [v for v in elig if v['hook_status'] in ('ok', 'no_speech')]
    s['n_hooks'] = len(heard)
    feats = []
    for key, label, f in FEATURES:
        row = {'key': key, 'label': label}
        for name, group in (('top', top), ('flop', flop), ('all', elig)):
            g = [v for v in group if v['hook_status'] == 'ok']
            row[name] = [sum(1 for v in g if f(v['hook'])), len(g)]
        feats.append(row)
    s['hook_features'] = feats
    s['words_5s'] = {name: med([v['words_5s'] for v in group if v['hook_status'] == 'ok'])
                     for name, group in (('top', top), ('flop', flop), ('all', elig))}
    s['silent_5s'] = {name: [sum(1 for v in group if v['hook_status'] == 'no_speech'),
                             sum(1 for v in group if v['hook_status'] in ('ok', 'no_speech'))]
                      for name, group in (('top', top), ('flop', flop), ('all', elig))}
    return s, elig, recent, missing, top, flop, talk[:3]


# --- 4. the files ------------------------------------------------------------------
def fint(x):
    if x is None:
        return '—'
    s = f'{int(round(x)):,}'
    return s.replace(',', ' ') if R == 'fr' else s


def fdec(x, d=1):
    if x is None:
        return '—'
    s = f'{x:.{d}f}'
    return s.replace('.', ',') if R == 'fr' else s


def fx(x):
    if x is None:
        return '—'
    return '×' + (fint(x) if x >= 100 else fdec(x, 2 if x < 1 else 1))


def frate(x):
    return fdec(x, 0 if x is not None and x >= 10 else 1)


def plural(n, fr, en):
    """plural(3, 'vidéo', 'video') -> '3 vidéos'."""
    word = t(fr, en)
    return f'{n} {word}' if n == 1 else f'{n} {word}s'


def fpct(x):
    return '—' if x is None else f'{round(100 * x)} %' if R == 'fr' else f'{round(100 * x)}%'


def fdur(x):
    return '—' if x is None else f'{int(round(x))} s' if R == 'fr' else f'{int(round(x))} s'


def fday(ts):
    return local(ts).strftime('%Y-%m-%d') if ts else '—'


def cell(s):
    return (s or '').replace('|', '/').replace('\n', ' ').replace('[', '(').replace(']', ')').strip()


def frac(p):
    return f'{p[0]}/{p[1]}' if p and p[1] else '—'


METRIC = {'views': (t('vues', 'views'), t('vues', 'views')),
          'interactions': (t('interactions (likes + commentaires)', 'interactions (likes + comments)'),
                           t('interactions', 'interactions')),
          'likes': (t('likes', 'likes'), t('likes', 'likes'))}


def hook_cell(v):
    if v['hook_status'] == 'ok':
        return f'« {cell(v["sentence"] or v["hook"])} »' if R == 'fr' else f'"{cell(v["sentence"] or v["hook"])}"'
    if v['hook_status'] == 'no_speech':
        return t('*(rien de dit : musique ou texte seul)*', '*(nothing said: music or on-screen text only)*')
    return t('*(non lu)*', '*(not read)*')


def video_table(rows, s):
    unit = METRIC[s['metric']][1]
    out = [t(f'| # | vidéo | date | {unit} | × médiane | durée | dit dans les 5 premières secondes |',
             f'| # | video | date | {unit} | × median | length | said in the first 5 seconds |'),
           '|---|---|---|---|---|---|---|']
    for v in rows:
        label = cell(first_line(v['caption'], 45)) or v['id']
        link = f'[{label}]({v["url"]})' if v['url'] else label
        out.append(f'| {v["rank"]} | {link} | {fday(v["ts"])} | {fint(v["m"])} | {fx(v["x"])} | '
                   f'{fdur(v["duration_s"])} | {hook_cell(v)} |')
    return '\n'.join(out)


def write_audit(s, elig, recent, missing, top, flop, talk):
    mname, unit = METRIC[s['metric']]
    L = []
    w = L.append
    w(f'# {t("Audit", "Audit")} {PLAT} · @{HANDLE} · {TODAY}')
    w('')
    period = t(f'du {s.get("first", "—")} au {s.get("last", "—")}', f'from {s.get("first", "—")} to {s.get("last", "—")}')
    fol = (t(f'{fint(s["followers"])} abonnés (donnés par toi)', f'{fint(s["followers"])} followers (given by you)')
           if s['followers'] else t('abonnés non donnés', 'followers not given'))
    w(f'{s["n_read"]} {t("vidéos", "videos")} {period} · {fol} · '
      f'{t("médiane", "median")} {fint(s["median"])} {unit}')
    w('')
    src = (t('lus sans connexion (yt-dlp anonyme)', 'read without logging in (anonymous yt-dlp)')
           if not args.csv else t(f'donnés par toi ({Path(args.csv).name})',
                                  f'given by you ({Path(args.csv).name})'))
    w(t(f'Chiffres du {TODAY}, {src}. Les {unit} sont cumulées à date : une vidéo plus ancienne a eu plus '
        f'de temps pour en gagner. Les vidéos de moins de {fdec(args.min_age_days, 0)} jours grandissent '
        'encore : elles sont listées à part et restent hors de la médiane.',
        f'Numbers of {TODAY}, {src}. {unit.capitalize()} are cumulative: an older video had more time to '
        f'collect them. Videos younger than {fdec(args.min_age_days, 0)} days are still growing: listed '
        'apart, out of the median.'))
    if s['metric'] != 'views':
        w('')
        w(t(f'**Pas de vues dans ces données** : le classement se fait sur les {mname}, jamais mélangé avec '
            'des vues.', f'**No views in this data**: the ranking uses {mname}, never mixed with views.'))
    if s['n_compared'] < 10:
        w('')
        w(t(f'**Échantillon mince** : {s["n_compared"]} vidéos comparées. Les écarts ci-dessous se décrivent, '
            'ils ne prouvent rien.', f'**Thin sample**: {s["n_compared"]} videos compared. The gaps below '
            'describe, they prove nothing.'))
    w('')
    w(t('<!-- CLAUDE: en une phrase, le constat principal, avec son chiffre. -->',
        '<!-- CLAUDE: in one sentence, the main finding, with its number. -->'))
    w('')
    w(t('## Les chiffres', '## The numbers'))
    w('')
    w('| | |')
    w('|---|---|')
    w(t(f'| vidéos comparées | {s["n_compared"]}', f'| videos compared | {s["n_compared"]}')
      + (t(f' (+ {s["n_recent"]} trop récente{"s" if s["n_recent"] > 1 else ""}, à part)',
           f' (+ {s["n_recent"]} too recent, apart)') if s['n_recent'] else '')
      + (t(f' (+ {s["n_missing"]} sans chiffre)', f' (+ {s["n_missing"]} without a number)')
         if s['n_missing'] else '') + ' |')
    w(t(f'| médiane | {fint(s["median"])} {unit} |', f'| median | {fint(s["median"])} {unit} |'))
    w(t(f'| moyenne | {fint(s["mean"])} {unit}, {fx(s["mean_over_median"])} la médiane |',
        f'| mean | {fint(s["mean"])} {unit}, {fx(s["mean_over_median"])} the median |'))
    w(t(f'| les {s["k"]} meilleures | {fpct(s["top_share"])} des {unit} |',
        f'| the best {s["k"]} | {fpct(s["top_share"])} of the {unit} |'))
    w(t(f'| à ×2 la médiane ou plus | {plural(s["n_outliers"], "vidéo", "video")} |',
        f'| at ×2 the median or more | {plural(s["n_outliers"], "vidéo", "video")} |'))
    w(t(f'| à ×0,5 la médiane ou moins | {plural(s["n_flops"], "vidéo", "video")} |',
        f'| at ×0.5 the median or less | {plural(s["n_flops"], "vidéo", "video")} |'))
    if s['median_over_followers'] is not None:
        w(t(f'| médiane ÷ abonnés | {fdec(s["median_over_followers"], 2)} |',
            f'| median ÷ followers | {fdec(s["median_over_followers"], 2)} |'))
    w(t(f'| durée médiane | {fdur(s["duration_median"])} |', f'| median length | {fdur(s["duration_median"])} |'))
    if s.get('per_week') is not None:
        w(t(f'| cadence | {fdec(s["per_week"])} vidéos par semaine ; écart médian {fdec(s["gap_median_d"])} j ; '
            f'plus long trou {fdec(s["gap_max_d"])} j (du {s["gap_max"][0]} au {s["gap_max"][1]}) |',
            f'| cadence | {fdec(s["per_week"])} videos a week; median gap {fdec(s["gap_median_d"])} d; '
            f'longest gap {fdec(s["gap_max_d"])} d ({s["gap_max"][0]} to {s["gap_max"][1]}) |'))
    if s.get('per_1000'):
        p = {k: frate(x) for k, x in s['per_1000'].items()}
        w(t(f'| pour 1 000 vues (médianes) | {p["likes"]} likes · {p["comments"]} commentaires · '
            f'{p["shares"]} partages · {p["saves"]} enregistrements |',
            f'| per 1,000 views (medians) | {p["likes"]} likes · {p["comments"]} comments · '
            f'{p["shares"]} shares · {p["saves"]} saves |'))
    w('')
    w(t('Une moyenne à ×2 la médiane ou plus : le compte est porté par quelques vidéos. '
        'La médiane, elle, est ta vidéo habituelle : c\'est contre elle que tout se compare ici.',
        'A mean at ×2 the median or more: a few videos carry the account. The median is your usual '
        'video: everything here is compared against it.'))
    w('')
    w(t(f'## Les {s["k"]} meilleures', f'## The best {s["k"]}'))
    w('')
    w(video_table(top, s))
    w('')
    w(t('Le détail (likes, commentaires, partages, enregistrements, légende) est dans `catalogue.csv`'
        + (', les trois premières secondes en images dans `images/`.' if IMG.exists() else '.'),
        'The details (likes, comments, shares, saves, caption) are in `catalogue.csv`'
        + (', the first three seconds as pictures in `images/`.' if IMG.exists() else '.')))
    w('')
    w(t('<!-- CLAUDE: pour chacune, pourquoi elle a marché : le hook (verbatim ci-dessus), la durée contre la '
        'durée médiane, le sujet (légende), les enregistrements ou commentaires pour 1 000 vues contre la '
        'médiane, ce que montre l\'image. Seulement ce que les chiffres et les verbatims montrent ; une '
        'hypothèse se dit hypothèse. -->',
        '<!-- CLAUDE: for each, why it worked: the hook (verbatim above), its length against the median '
        'length, the topic (caption), saves or comments per 1,000 views against the median, what the '
        'picture shows. Only what the numbers and the verbatims show; a guess is called a guess. -->'))
    w('')
    w(t(f'## Les {s["k"]} moins bonnes', f'## The worst {s["k"]}'))
    w('')
    w(video_table(flop, s))
    w('')
    w(t('## La durée', '## Length'))
    w('')
    w(t('| durée | vidéos | × médiane (médiane de la tranche) | à ×2 ou plus |',
        '| length | videos | × median (bucket median) | at ×2 or more |'))
    w('|---|---|---|---|')
    for b in s['buckets']:
        name = (t(f'moins de {b["to"]} s', f'under {b["to"]} s') if b['from'] == 0 else
                t(f'{b["from"]} s et plus', f'{b["from"]} s and over') if b['to'] > 10 ** 5 else
                f'{b["from"]}-{b["to"]} s')
        xm = fx(b['x_median']) if b['n'] >= 3 else (t('trop peu', 'too few') if b['n'] else '—')
        w(f'| {name} | {b["n"]} | {xm} | {b["n_outliers"]} |')
    w('')
    w(t(f'Les {s["k"]} meilleures durent {fdur(s["duration_top"])} (médiane), les {s["k"]} moins bonnes '
        f'{fdur(s["duration_flop"])}, ton compte {fdur(s["duration_median"])}. Une tranche de moins de 3 vidéos '
        'ne se juge pas.',
        f'The best {s["k"]} last {fdur(s["duration_top"])} (median), the worst {s["k"]} '
        f'{fdur(s["duration_flop"])}, your account {fdur(s["duration_median"])}. A bucket under 3 videos '
        'is not judged.'))
    w('')
    w(t(f'## Les hooks : les {s["k"]} meilleures contre les {s["k"]} moins bonnes',
        f'## Hooks: the best {s["k"]} against the worst {s["k"]}'))
    w('')
    if s['n_hooks']:
        w(t(f'| dans les 5 premières secondes | les {s["k"]} meilleures | les {s["k"]} moins bonnes | tout le compte |',
            f'| in the first 5 seconds | the best {s["k"]} | the worst {s["k"]} | whole account |'))
        w('|---|---|---|---|')
        for f in s['hook_features']:
            w(f'| {f["label"]} | {frac(f["top"])} | {frac(f["flop"])} | {frac(f["all"])} |')
        ws = s['words_5s']
        w(t(f'| mots dits (médiane) | {fdec(ws["top"], 0)} | {fdec(ws["flop"], 0)} | {fdec(ws["all"], 0)} |',
            f'| words said (median) | {fdec(ws["top"], 0)} | {fdec(ws["flop"], 0)} | {fdec(ws["all"], 0)} |'))
        sl = s['silent_5s']
        w(t(f'| rien de dit | {frac(sl["top"])} | {frac(sl["flop"])} | {frac(sl["all"])} |',
            f'| nothing said | {frac(sl["top"])} | {frac(sl["flop"])} | {frac(sl["all"])} |'))
        w('')
        w(t(f'Sur {s["k"]} vidéos, un écart est une piste à tester, pas une preuve. Les verbatims sont dans les '
            'deux tableaux plus haut et dans `hooks.tsv` (tous, classés).',
            f'On {s["k"]} videos, a gap is a lead to test, not a proof. The verbatims are in the two tables '
            'above and in `hooks.tsv` (all of them, ranked).'))
    else:
        w(t('Hooks non lus (pas de téléchargement ou pas de whisper) : les légendes les remplacent dans les '
            'tableaux, ce n\'est pas ce qui est dit.', 'Hooks not read (no download or no whisper): the captions '
            'stand in for them in the tables, which is not what is said.'))
    w('')
    w(t('<!-- CLAUDE: lis les verbatims et les images (images/) des meilleures et des moins bonnes : ce que les '
        'gagnantes ont en commun (forme de la première phrase, promesse, texte à l\'écran, visage, '
        'mouvement) que les autres n\'ont pas. Chiffres à l\'appui (2/5 contre 0/5). -->',
        '<!-- CLAUDE: read the verbatims and the pictures (images/) of the best and the worst: what the '
        'winners share (shape of the first sentence, promise, on-screen text, face, movement) that the '
        'others lack. With the counts (2/5 against 0/5). -->'))
    w('')
    w(t('## Les hashtags', '## Hashtags'))
    w('')
    if s['hashtags']:
        w(t('| hashtag | vidéos | × médiane avec | × médiane sans |', '| hashtag | videos | × median with | × median without |'))
        w('|---|---|---|---|')
        for h in s['hashtags']:
            wo = t('partout : rien à comparer', 'everywhere: nothing to compare') if h['everywhere'] else fx(h['x_without'])
            w(f'| #{h["tag"]} | {h["n"]} | {fx(h["x_with"])} | {wo} |')
        w('')
        w(t('Le hashtag suit le sujet : un écart dit surtout quel sujet marche, pas quel hashtag.',
            'A hashtag follows the topic: a gap mostly says which topic works, not which hashtag.'))
    else:
        w(t('Aucun hashtag dans 3 vidéos ou plus.', 'No hashtag in 3 videos or more.'))
    w('')
    w(t('## Quand tu publies', '## When you post'))
    w('')
    w(t('| heure de publication | vidéos | × médiane |', '| posting time | videos | × median |'))
    w('|---|---|---|')
    for b in s['hours']:
        xm = fx(b['x_median']) if b['n'] >= 3 else (t('trop peu', 'too few') if b['n'] else '—')
        w(f'| {b["label"]} | {b["n"]} | {xm} |')
    w('')
    w(t(f'Heure de cet ordinateur{f" ({args.tz})" if args.tz else ""}. Personne ne tire son heure au sort : '
        'une heure qui gagne porte souvent aussi un meilleur sujet.',
        f'This computer\'s time{f" ({args.tz})" if args.tz else ""}. Nobody picks their posting time at '
        'random: a winning hour often carries a better topic too.'))
    w('')
    w(t('## Ce que les commentaires demandent', '## What the comments ask for'))
    w('')
    if talk:
        w(t('Les vidéos qui font le plus parler :', 'The videos that make people talk the most:'))
        w('')
        pk = (s.get('per_1000') or {}).get('comments')
        for v in talk:
            label = cell(first_line(v['caption'], 60)) or v['id']
            rate = (t(f', {frate(v["comments_k"])} pour 1 000 vues (médiane du compte {frate(pk)})',
                      f', {frate(v["comments_k"])} per 1,000 views (account median {frate(pk)})')
                    if v.get('comments_k') is not None else '')
            w(f'- [{label}]({v["url"]}) : {fint(v["comments"])} {t("commentaires", "comments")}{rate}')
        w('')
    w(t('<!-- CLAUDE: le texte des commentaires ne se lit pas sans connexion. Si l\'utilisateur a collé ceux de '
        'ces vidéos (commentaires.txt), dis ce qu\'ils demandent (questions, une suite, un lien, un outil), '
        'avec le nombre de fois. Sinon, écris qu\'ils n\'ont pas été lus et comment le faire. -->',
        '<!-- CLAUDE: comment text cannot be read without logging in. If the user pasted the comments of these '
        'videos (commentaires.txt), say what they ask for (questions, a part 2, a link, a tool), with how '
        'many times. Otherwise say they were not read and how to do it. -->'))
    if recent:
        w('')
        w(t('## Trop récentes pour juger', '## Too recent to judge'))
        w('')
        w(t(f'| vidéo | date | {unit} | × médiane (provisoire) |', f'| video | date | {unit} | × median (for now) |'))
        w('|---|---|---|---|')
        for v in sorted(recent, key=lambda v: v['ts'] or 0, reverse=True):
            label = cell(first_line(v['caption'], 45)) or v['id']
            w(f'| [{label}]({v["url"]}) | {fday(v["ts"])} | {fint(v["m"])} | {fx(v["x"])} |')
    w('')
    w(t('## 3 choses à tester', '## 3 things to test'))
    w('')
    w(t('<!-- CLAUDE: 3 recommandations concrètes pour les prochaines vidéos. Chacune : ce qu\'on change, le '
        'chiffre qui la motive (avec n), comment on saura (× médiane des 3 à 5 prochaines). Un écart aux '
        'gagnantes se présente comme un test, jamais comme une certitude. Aucune sans chiffre. -->',
        '<!-- CLAUDE: 3 concrete recommendations for the next videos. Each: what to change, the number behind '
        'it (with n), how we will know (× median of the next 3 to 5). A gap to the winners is a test, never '
        'a certainty. None without a number. -->'))
    w('')
    w(t('## Pour le montage', '## For the edit'))
    w('')
    w(t('La skill de montage relit ce bloc avant de monter : garde les clés, change les valeurs.',
        'The editing skill reads this block before it edits: keep the keys, change the values.'))
    w('')
    td = s.get('target_duration')
    ex = [v for v in top if v['hook_status'] == 'ok'][:2]
    w('```text')
    w(f'platform: {PLATFORM}')
    w(f'account: @{HANDLE}')
    w(f'audit_date: {TODAY}')
    w(f'target_duration_s: {f"{td[0]}-{td[1]}" if td else "?"}'
      + t(f'   # les {s["k"]} meilleures (médiane {fdur(s["duration_top"])}) ; compte {fdur(s["duration_median"])}',
          f'   # the best {s["k"]} (median {fdur(s["duration_top"])}); account {fdur(s["duration_median"])}'))
    w(t('hook_style: <!-- CLAUDE: la forme des hooks gagnants, en une ligne -->',
        'hook_style: <!-- CLAUDE: the shape of the winning hooks, in one line -->'))
    for v in ex:
        w(f'hook_example: {v["sentence"] or v["hook"]}')
    w(t('title_on_screen: <!-- CLAUDE: oui | non | à tester, d\'après les images des meilleures -->',
        'title_on_screen: <!-- CLAUDE: yes | no | to test, from the pictures of the best -->'))
    w('```')
    w('')
    w(t('## Méthode et limites', '## Method and limits'))
    w('')
    w(t(f'- × médiane = {mname} de la vidéo ÷ médiane des {s["n_compared"]} vidéos comparées. ×2 et plus : '
        'au-dessus ; ×0,5 et moins : en dessous. Des seuils de lecture, pas des tests statistiques.',
        f'- × median = the video\'s {mname} ÷ the median of the {s["n_compared"]} videos compared. ×2 and '
        'more: above; ×0.5 and less: below. Reading thresholds, not statistical tests.'))
    if s['n_hooks']:
        w(t(f'- Hook = ce qui est dit dans les {int(HOOK_S)} premières secondes (phrase finie, {CLIP_S} s au plus), '
            f'transcrit sur ta machine par whisper.cpp ({Path(MODEL).name}), sur les {CLIP_S} premières secondes '
            'téléchargées dans le plus petit format. Whisper peut se tromper d\'un mot.',
            f'- Hook = what is said in the first {int(HOOK_S)} seconds (sentence finished, {CLIP_S} s at most), '
            f'transcribed on your machine by whisper.cpp ({Path(MODEL).name}) from the first {CLIP_S} seconds, '
            'downloaded in the smallest format. Whisper can get a word wrong.'))
    if args.csv:
        w(t(f'- Chiffres : ton fichier ({Path(args.csv).name}).' + (' Hooks lus sans connexion, un seul passage, '
            f'{fdec(args.delay, 0)} s ou plus entre deux vidéos.' if s['n_hooks'] else ''),
            f'- Numbers: your file ({Path(args.csv).name}).' + (' Hooks read without logging in, one pass, '
            f'{fdec(args.delay, 0)} s or more between two videos.' if s['n_hooks'] else '')))
    else:
        w(t(f'- Lecture anonyme, un seul passage, {fdec(args.delay, 0)} s ou plus entre deux vidéos, {args.count} '
            'vidéos au plus. Aucune connexion, aucun mot de passe.',
            f'- Anonymous read, one pass, {fdec(args.delay, 0)} s or more between two videos, {args.count} '
            'videos at most. No login, no password.'))
    unread = [v for v in elig + recent if v['hook_status'] not in ('ok', 'no_speech')]
    if unread and not args.no_hooks:
        w(t(f'- Hooks non lus : {len(unread)} (voir la colonne statut de `hooks.tsv`).',
            f'- Hooks not read: {len(unread)} (see the status column of `hooks.tsv`).'))
    w(t('- Pas mesuré : la rétention (temps de visionnage), la portée, d\'où viennent les vues, les abonnés '
        'gagnés. Seule ton app les donne.',
        '- Not measured: retention (watch time), reach, where the views come from, followers gained. Only '
        'your app has them.'))
    w(t(f'- {s["n_compared"]} vidéos, c\'est peu : chaque écart est une piste à tester sur les suivantes.',
        f'- {s["n_compared"]} videos is a small sample: each gap is a lead to test on the next ones.'))
    w('')
    f = OUT / 'AUDIT.md'
    if f.exists() and '<!-- CLAUDE:' not in f.read_text(encoding='utf-8'):   # already written: keep it
        keep = OUT / f'AUDIT-{t("avant", "before")}-{local(NOW).strftime("%H%M%S")}.md'
        f.rename(keep)
        say(f'the AUDIT.md already written is kept as {keep.name}')
    f.write_text('\n'.join(L), encoding='utf-8')


def write_tables(s, elig, recent, missing):
    rows = elig + sorted(recent, key=lambda v: v['ts'] or 0, reverse=True) + missing
    head = (t('rang,x_mediane,statut,date,heure,duree_s,vues,likes,commentaires,partages,enregistrements,'
              'url,hashtags,legende,id', 'rank,x_median,status,date,time,duration_s,views,likes,comments,'
              'shares,saves,url,hashtags,caption,id')).split(',')
    st = {'outlier': t('au-dessus', 'outlier'), 'flop': t('en dessous', 'flop'), 'normal': 'normal',
          'recent': t('trop récente', 'too recent'), 'no_number': t('sans chiffre', 'no number')}
    iv = lambda x: '' if x is None else int(round(x))
    with open(OUT / 'catalogue.csv', 'w', newline='', encoding='utf-8') as f:
        cw = csv.writer(f)
        cw.writerow(head)
        for v in rows:
            d = local(v['ts']) if v['ts'] else None
            cw.writerow([v['rank'], '' if v.get('x') is None else round(v['x'], 2), st[v['status']],
                         d.strftime('%Y-%m-%d') if d else '', d.strftime('%H:%M') if d else '',
                         iv(v['duration_s']), iv(v['views']), iv(v['likes']), iv(v['comments']),
                         iv(v['shares']), iv(v['saves']), v['url'], ' '.join('#' + h for h in v['hashtags']),
                         ' '.join(v['caption'].split()), v['id']])
    hs = {'ok': 'ok', 'no_speech': t('rien de dit', 'nothing said'), 'skipped': t('pas tenté (site bloquant)', 'skipped (site blocking)'),
          'download_failed': t('téléchargement refusé', 'download refused'), 'not_read': t('non lu', 'not read'),
          'transcription_failed': t('transcription ratée', 'transcription failed'),
          'no_source': t('ni lien ni fichier', 'no link, no file')}
    head = (t('rang\tx_mediane\tdate\tduree_s\thook_5s\tphrase\tmots_5s\tlegende_1re_ligne\tstatut\timage\turl',
              'rank\tx_median\tdate\tduration_s\thook_5s\tsentence\twords_5s\tcaption_first_line\tstatus\timage\turl'))
    with open(OUT / 'hooks.tsv', 'w', encoding='utf-8') as f:
        f.write(head + '\n')
        for v in rows:
            clean = lambda x: ' '.join(str(x or '').replace('\t', ' ').split())
            f.write('\t'.join(clean(x) for x in (
                v['rank'], '' if v.get('x') is None else round(v['x'], 2), fday(v['ts']), iv(v['duration_s']),
                v['hook'], v['sentence'], v['words_5s'] if v['words_5s'] is not None else '',
                first_line(v['caption'], 200), hs.get(v['hook_status'], v['hook_status']), v['image'], v['url'])) + '\n')
    (OUT / 'chiffres.json').write_text(json.dumps(s, ensure_ascii=False, indent=1, default=str), encoding='utf-8')


# --- main --------------------------------------------------------------------------
def main():
    if args.csv:
        videos = read_csv(args.csv)
        RAW.mkdir(parents=True, exist_ok=True)
        (RAW / 'listing.json').write_text(json.dumps(videos, ensure_ascii=False, indent=1), encoding='utf-8')
    else:
        videos = fetch_listing()
    dated = [v for v in videos if v['ts']]
    if len(dated) == len(videos):
        videos.sort(key=lambda v: v['ts'], reverse=True)
    videos = videos[:args.count]
    say(f'{len(videos)} videos: @{HANDLE} on {PLAT}')
    hooks = get_hooks(videos)
    s, elig, recent, missing, top, flop, talk = compute(videos, hooks)
    if len(elig) < 3:
        die(f'{len(elig)} video(s) to compare: a median needs 3 at least (videos younger than '
            f'{args.min_age_days:g} days and videos without a number are left out). Take a larger -n, '
            'or more lines in the CSV.')
    write_tables(s, elig, recent, missing)
    write_audit(s, elig, recent, missing, top, flop, talk)
    unit = METRIC[s['metric']][1]
    say('')
    say(f'-> {OUT}/  AUDIT.md, catalogue.csv, hooks.tsv, chiffres.json' + (', images/' if IMG.exists() else ''))
    say(f'{s["n_compared"]} compared, median {fint(s["median"])} {unit}, mean/median {fx(s["mean_over_median"])}, '
        f'{s["n_outliers"]} at x2+, {s["n_flops"]} at x0.5-' + (f', {s["n_recent"]} too recent' if s['n_recent'] else ''))
    for name, group in (('top ', top), ('flop', flop)):
        for v in group:
            said = v['sentence'] or v['hook'] or f'({first_line(v["caption"], 60) or v["id"]})'
            say(f'  {name} {fx(v["x"]):>7} {fint(v["m"]):>9} {fdur(v["duration_s"]):>6}  {said[:90]}')
    n = (OUT / 'AUDIT.md').read_text(encoding='utf-8').count('<!-- CLAUDE:')
    say(f'AUDIT.md: {n} "<!-- CLAUDE:" markers left to write.')


if __name__ == '__main__':
    main()
