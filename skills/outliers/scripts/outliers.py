#!/usr/bin/env python3
"""What blew up for the accounts you watch, each video against its own account.

    python3 outliers.py                            # every account of ./watchlist.txt
    python3 outliers.py @un_compte tiktok:autre    # these accounts only
    python3 outliers.py @un_compte --add           # ...and add them to the watchlist
    python3 outliers.py instagram:un_compte --csv ses_chiffres.csv

For each account, one anonymous pass (yt-dlp, no cookies, no login):

  1. the list of its last N videos with their counters (one request);
  2. the account's median over the videos old enough to be judged, and each
     video against it (x median): x3 or more is an outlier. Videos younger
     than 3 days are listed apart, sponsored ones (said in the caption) are
     left out;
  3. the first 10 seconds of each outlier, smallest format, a pause between
     two videos, transcribed locally by whisper.cpp: the hook is what is said
     in the first 5 seconds, verbatim; 3 frames of the first 3 seconds;
  4. what comes back: the words and the hook openings shared by 2 outliers or
     more, on one account or across several, with how many videos on the same
     words did not take off; the length of the outliers.

TikTok only for anonymous reading: Instagram refuses it (yt-dlp itself marks
that reader as broken). An Instagram account comes in by hand: --csv.

Writes ./outliers-<date>/: catalogue.csv, hooks.tsv, chiffres.json, images/
and OUTLIERS.md, every number filled in, the reading left to Claude at each
`<!-- CLAUDE:` marker. Run again the same day: nothing is fetched twice, a
refusal is not retried.

The reading, hook and number helpers are copied from the audit skill of the
same repository (skills/audit/scripts/audit.py): that script parses its
arguments as soon as it is imported, and a skill can be installed alone, so
an import between the two would break. A fix in one belongs in the other.

Python 3.10+, standard library only. yt-dlp, ffmpeg and whisper-cli (the same
binary, model and settings as the edit skill) are called as commands.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
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
from collections import Counter
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(errors='replace')

CONFIG = Path.home() / '.config' / 'video-editing' / 'config.json'
MODEL_DIRS = [Path.home() / '.cache' / 'whisper-cpp',      # the same as the edit skill
              Path.home() / '.local' / 'share' / 'whisper-cpp' / 'models']
MODELS_URL = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/'
MAX_N = 50          # the last videos of each account, not its whole history
EXTRA_RECENT = 15   # listed on top of N: the videos too young to judge (a daily poster has 3 to 12)
HOOK_S = 5.0        # the hook = what is said in the first 5 seconds
CLIP_S = 10         # seconds downloaded per video: enough to finish the hook sentence
MIN_MEDIAN = 5      # fewer videos to compare: no median, nothing ranked
THIN = 10           # under this, an account's outliers are a thin sample
MAX_CANDIDATES = 10
MAX_GROUPS = 12


def say(msg=''):
    print(msg, flush=True)


def die(msg, code=2):
    print(msg, file=sys.stderr, flush=True)
    sys.exit(code)


# --- arguments ---------------------------------------------------------------
ap = argparse.ArgumentParser(description="What blew up for the accounts you watch: each video against "
                                         "its own account's median.")
ap.add_argument('accounts', nargs='*',
                help='@account, tiktok:account, instagram:account or a profile link (none: the watchlist)')
ap.add_argument('--watchlist', default='watchlist.txt',
                help='one account per line, its language after it if you like (default: ./watchlist.txt)')
ap.add_argument('--add', action='store_true', help='add the accounts given to the watchlist, then run')
ap.add_argument('-n', '--count', type=int, default=30,
                help=f'last N videos old enough to judge, per account (default 30, max {MAX_N}); '
                     'the younger ones come on top, apart')
ap.add_argument('--min', type=float, default=3.0, dest='threshold',
                help='outlier threshold, x the account median (default 3)')
ap.add_argument('--min-age-days', type=float, default=3.0,
                help='younger videos are still growing: apart, out of the median (default 3)')
ap.add_argument('--csv', action='append', default=[], metavar='[ACCOUNT=]FILE',
                help='an account read by hand (Instagram): its numbers in a CSV, see references/manual.md')
ap.add_argument('--hooks', choices=['outliers', 'all', 'none'], default='outliers',
                help='whose first seconds are read and transcribed (default: the outliers)')
ap.add_argument('--lang', help='spoken language for whisper when the watchlist line gives none '
                               '(default: config, else auto)')
ap.add_argument('--report', choices=['fr', 'en'], default='fr', help='language of the files written')
ap.add_argument('--out', default='.', help='where to create outliers-<date>/ (default: here)')
ap.add_argument('--delay', type=float, default=3.0, help='seconds between two requests (3 at least, plus jitter)')
ap.add_argument('--model', help='whisper model name or path (default: config, else large-v3-turbo)')
ap.add_argument('--date-order', choices=['dmy', 'mdy'],
                help='--csv dates like 03/04/2026: day first (dmy) or month first (mdy)')
args = ap.parse_args()

R = args.report


def t(fr, en):
    return fr if R == 'fr' else en


if not 1 <= args.count <= MAX_N:
    die(f'-n must be between 1 and {MAX_N}: the last videos of each account, not its whole history.')
if args.threshold <= 1:
    die('--min must be above 1 (3 = three times the account median).')
if args.delay < 3:
    say('--delay under 3 s: kept at 3 s, reading gently is the rule.')
    args.delay = 3.0

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

NOW = time.time()
TODAY = dt.datetime.fromtimestamp(NOW).strftime('%Y-%m-%d')
OUT = Path(args.out).expanduser() / f'outliers-{TODAY}'
RAW = OUT / '.brut'
IMG = OUT / 'images'
FTHR = (f'{args.threshold:.0f}' if float(args.threshold).is_integer()
        else f'{args.threshold:.1f}'.replace('.', ',' if R == 'fr' else '.'))


# --- accounts and the watchlist ------------------------------------------------
NOT_ACCOUNTS = ('p', 'reel', 'reels', 'tv', 'stories', 'explore')
LANG_RE = re.compile(r'[a-z]{2,3}|auto')


def account(handle, platform, lang=None):
    return {'handle': handle, 'platform': platform, 'lang': lang, 'csv': None,
            'key': f'{platform}-{handle.lower()}', 'videos': [], 'error': None}


def parse_spec(s, lang=None):
    s = (s or '').strip()
    m = re.search(r'tiktok\.com/@([\w.\-]+)', s)
    if m:
        return account(m.group(1), 'tiktok', lang)
    m = re.search(r'instagram\.com/([\w.\-]+)', s)
    if m and m.group(1).lower() not in NOT_ACCOUNTS:
        return account(m.group(1), 'instagram', lang)
    m = re.fullmatch(r'(tiktok|tt|instagram|insta|ig):@?([\w.\-]+)/?', s, re.I)
    if m:
        plat = 'instagram' if m.group(1).lower() in ('instagram', 'insta', 'ig') else 'tiktok'
        return account(m.group(2), plat, lang)
    h = s.lstrip('@').strip('/')
    return account(h, 'tiktok', lang) if re.fullmatch(r'[\w.\-]+', h) else None


def label(a):
    return f'@{a["handle"]}' + (' (Instagram)' if a['platform'] == 'instagram' else '')


def spec_line(a):
    base = f'@{a["handle"]}' if a['platform'] == 'tiktok' else f'instagram:{a["handle"]}'
    return base + (f' {a["lang"]}' if a['lang'] else '')


def read_watchlist(path):
    good, bad = [], []
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = re.sub(r'(^|\s)#.*', '', line).strip()      # "# ..." is a comment
        if not line:
            continue
        parts = line.split()
        lang = parts[1].lower() if len(parts) > 1 and LANG_RE.fullmatch(parts[1].lower()) else None
        a = parse_spec(parts[0], lang)
        (good if a else bad).append(a or line)
    return good, bad


WATCH_HEAD = ('# Accounts to watch, one per line: @account (TikTok), or instagram:account (by hand, --csv).\n'
              '# The language spoken in its videos after a space if you like: @account en. # starts a comment.\n')


def add_to_watchlist(path, accounts):
    have = {a['key'] for a in read_watchlist(path)[0]} if path.exists() else set()
    new = [a for a in accounts if a['key'] not in have]
    if new:
        text = path.read_text(encoding='utf-8-sig') if path.exists() else WATCH_HEAD
        if text and not text.endswith('\n'):
            text += '\n'
        path.write_text(text + ''.join(spec_line(a) + '\n' for a in new), encoding='utf-8')
    return new


# --- numbers in the wild (copied from the audit skill) ---------------------------
def num(v):
    """'3 264', '1,2 k', '12.5K', '1.234', 3264 -> float, or None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    for c in (' ', '\xa0', '\u202f', '\u2009'):
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


def fold(s):
    s = unicodedata.normalize('NFD', str(s).lower().replace('’', "'"))
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def norm(s):
    return ' '.join(re.sub(r"[^a-z0-9']+", ' ', fold(s)).split())


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


# --- 1. the lists ------------------------------------------------------------------
_last = [0.0]


def pace(factor=1.0):
    """A pause since the end of the previous request: 3 s or more, plus jitter."""
    if _last[0]:
        wait = _last[0] + factor * args.delay + random.uniform(0, args.delay / 2) - time.time()
        if wait > 0:
            time.sleep(wait)


def done():
    _last[0] = time.time()


def fetch_listing(a, ytdlp):
    """(videos, error, asked the network). A list read today is reused; a refusal today is not retried."""
    d = RAW / a['key']
    cache, refused = d / 'listing.json', d / 'refus.txt'
    if cache.exists():
        return json.loads(cache.read_text(encoding='utf-8')), None, False
    if refused.exists():
        why = refused.read_text(encoding='utf-8').strip()
        return None, t(f'refusé plus tôt aujourd\'hui ({why}), pas retenté',
                       f'refused earlier today ({why}), not retried'), False
    url = f'https://www.tiktok.com/@{a["handle"]}'
    pace()
    say(f'  {label(a)}: reading the list once, anonymously ({url})')
    end = args.count + 3 + EXTRA_RECENT                                   # + pinned ones + too young ones
    r = subprocess.run([ytdlp, '--flat-playlist', '-J', '--playlist-end', str(end),
                        '--socket-timeout', '30', '--no-warnings', url],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    done()
    entries = []
    if r.returncode == 0:
        try:
            entries = (json.loads(r.stdout or 'null') or {}).get('entries') or []
        except ValueError:
            entries = []
    d.mkdir(parents=True, exist_ok=True)
    if not entries:
        err = next((l for l in reversed((r.stderr or '').splitlines()) if l.strip()), 'no video returned')
        refused.write_text(err[-200:], encoding='utf-8')
        return None, err[-200:], True
    out = []
    for e in entries:
        vid = str(e.get('id') or '')
        link = e.get('url') or e.get('webpage_url') or ''
        if not str(link).startswith('http'):
            link = f'https://www.tiktok.com/@{a["handle"]}/video/{vid}'
        out.append(video(vid, link, e.get('timestamp'), num(e.get('duration')),
                         num(e.get('view_count')), num(e.get('like_count')), num(e.get('comment_count')),
                         num(e.get('repost_count')), num(e.get('save_count')),
                         e.get('description') or e.get('title') or ''))
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    return out, None, True


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
    """An account read by hand (copied from the audit skill)."""
    p = Path(path).expanduser()
    if not p.exists():
        die(f'{p}: file not found.')
    raw = p.read_bytes()
    text = raw.decode('utf-8', 'replace')
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
    say(f'  {p.name}: columns read: {", ".join(f"{k}={rows[0][i]!r}" for k, i in col.items())}')
    if 'views' not in col and 'likes' not in col:
        die(f'{p.name}: no views and no likes column recognized. Rename the columns as in '
            'references/manual.md (date,lien,duree_s,vues,likes,commentaires,legende) and run again.')
    out = []
    for r in rows[1:]:
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


# --- 2. the numbers, account by account --------------------------------------------
SPONSORED = re.compile(      # the usual markers, whole: a video ABOUT sponsoring (#sponsoring) is not one
    r'#(ad|ads|pub|publicite|sponso|sponsored|sponsorise|sponsorisee|partenariat|partenariatremunere|'
    r'paidpartnership|partner|werbung|anuncio|publi|advertisement|collabpayante)(?!\w)|paid partnership|'
    r'partenariat remunere|en partenariat avec|sponsorise par|sponsorisee par|sponsored by|'
    r'in partnership with|collaboration commerciale|publicite pour')


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def compute_account(a, videos):
    if videos and all(v['ts'] for v in videos):
        videos.sort(key=lambda v: v['ts'], reverse=True)
    young = [v for v in videos if v['ts'] and (NOW - v['ts']) / 86400 < args.min_age_days]
    videos = young + [v for v in videos if v not in young][:args.count]   # N old enough, the young on top
    for v in videos:
        v['acct'], v['platform'] = a['key'], a['platform']
        v['age_d'] = (NOW - v['ts']) / 86400 if v['ts'] else None
        v['hashtags'] = hashtags(v['caption'])
        v['sponsored'] = bool(SPONSORED.search(fold(v['caption'])))
        v.update(hook='', sentence='', words_5s=None, hook_status='not_read', image='', terms={})
    n_views = sum(1 for v in videos if v['views'] is not None)
    if n_views and n_views >= 0.8 * len(videos):
        metric = 'views'
    elif videos and all(v['likes'] is not None and v['comments'] is not None for v in videos):
        metric = 'interactions'
    else:
        metric = 'likes'
    for v in videos:
        v['m'] = (v['views'] if metric == 'views' else
                  v['likes'] + v['comments'] if metric == 'interactions' else v['likes'])
    measured = [v for v in videos if v['m'] is not None]
    recent = [v for v in measured if v['age_d'] is not None and v['age_d'] < args.min_age_days]
    spons = [v for v in measured if v['sponsored'] and v not in recent]
    elig = [v for v in measured if v not in recent and v not in spons]
    missing = [v for v in videos if v['m'] is None]
    median = med([v['m'] for v in elig]) if len(elig) >= MIN_MEDIAN else None
    for v in videos:
        v['x'] = v['m'] / median if median and v['m'] is not None else None
    elig.sort(key=lambda v: v['x'] if v['x'] is not None else -1, reverse=True)
    for k, v in enumerate(elig, 1):
        v['rank'] = k if median else ''
        v['status'] = ('unranked' if not median else 'outlier' if v['x'] >= args.threshold else 'normal')
    for group, status in ((recent, 'recent'), (spons, 'sponsored'), (missing, 'no_number')):
        for v in group:
            v['rank'], v['status'] = '', status
    for v in videos:     # views only grow: a young video already at the threshold is a hit, its x a floor
        v['ahead'] = v['status'] == 'recent' and (v['x'] or 0) >= args.threshold
    outs = [v for v in elig if v['status'] == 'outlier']
    dated = sorted(v['ts'] for v in videos if v['ts'])
    a['videos'] = elig + sorted(recent, key=lambda v: v['ts'] or 0, reverse=True) + spons + missing
    a['stats'] = {
        'account': a['handle'], 'platform': a['platform'], 'source': 'csv' if a['csv'] else 'yt-dlp (anonymous)',
        'metric': metric, 'n_read': len(videos), 'n_compared': len(elig), 'n_recent': len(recent),
        'n_sponsored': len(spons), 'n_missing': len(missing), 'median': median,
        'mean_over_median': (statistics.mean(v['m'] for v in elig) / median) if median else None,
        'n_outliers': len(outs), 'thin': bool(median) and len(elig) < THIN,
        'too_few': not median,
        'n_ahead': sum(1 for v in recent if v['ahead']),
        'best_x': elig[0]['x'] if elig and median else None,
        'first': dt.datetime.fromtimestamp(dated[0]).strftime('%Y-%m-%d') if dated else None,
        'last': dt.datetime.fromtimestamp(dated[-1]).strftime('%Y-%m-%d') if dated else None,
        'duration_median': med([v['duration_s'] for v in elig]),
        'duration_outliers': med([v['duration_s'] for v in outs]),
    }


# --- 3. the hooks (copied from the audit skill, several accounts) ----------------------
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
        say(f'downloading the whisper model {fn} (once, shared with the edit skill; '
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


def hkey(v):
    return f'{v["platform"]}:{v["id"]}'


def fetch_clip(v, tmp, ytdlp, factor=1.0):
    """The first CLIP_S seconds of a video, smallest format. (path, error)."""
    if v['file']:
        p = Path(v['file']).expanduser()
        return (p, None) if p.exists() else (None, f'file not found: {p}')
    if not v['url']:
        return None, 'no link'
    stem = tmp / safe(v['id'])
    cmd = [ytdlp, '-q', '--no-warnings', '--no-playlist', '--socket-timeout', '30',
           '-S', '+size,+br,+res', '--download-sections', f'*0-{CLIP_S}',
           '-o', str(stem) + '.%(ext)s', v['url']]
    if FF != 'ffmpeg':
        cmd[1:1] = ['--ffmpeg-location', FF]
    pace(factor)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    done()
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


def get_hooks(targets):
    """targets = [(account, video)]. Each video is tried once a day: a refusal is cached, not retried."""
    cache_f = RAW / 'hooks.json'
    cache = json.loads(cache_f.read_text(encoding='utf-8')) if cache_f.exists() else {}
    todo = [(a, v) for a, v in targets if hkey(v) not in cache]
    if not todo:
        return cache
    whisper = shutil.which('whisper-cli') or shutil.which('whisper-cpp')
    if not shutil.which(FF) and not Path(FF).exists():
        say(f'ffmpeg not found ({FF}): no hooks, the captions stand in. Install it as the setup skill '
            'says, then run again: only the hooks are fetched.')
        return cache
    if not whisper:
        say('whisper-cli not found: no hooks, the captions stand in. Install it as the setup skill says '
            '(macOS: brew install whisper-cpp), then run again: only the hooks are fetched.')
        return cache
    try:
        model = model_path(MODEL)
    except Exception as e:                                   # no network, disk full...
        say(f'whisper model unavailable ({e}): no hooks this time.')
        return cache
    ytdlp = shutil.which('yt-dlp')
    IMG.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='outliers-'))
    say(f'reading the first {CLIP_S} s of {len(todo)} video(s), one at a time, {args.delay:g} s or more apart...')
    wavs, fails, stopped = {}, 0, False
    try:
        for i, (a, v) in enumerate(todo, 1):
            k = hkey(v)
            if not v['file'] and not v['url']:
                cache[k] = {'status': 'no_source'}
                continue
            if not v['file'] and not ytdlp:
                continue                                     # not cached: read once yt-dlp is there
            if stopped and not v['file']:
                cache[k] = {'status': 'skipped'}
                continue
            clip, err = fetch_clip(v, tmp, ytdlp)
            if not clip and not v['file']:                   # a CDN hiccup is common: one retry, later
                clip, err = fetch_clip(v, tmp, ytdlp, factor=2.0)
            if not clip:
                cache[k] = {'status': 'download_failed', 'error': err}
                say(f'  [{i}/{len(todo)}] {label(a)} {v["id"]}: not read ({err})')
                fails += 0 if v['file'] else 1
                if fails >= 2 and not stopped:
                    stopped = True
                    say('  two refusals in a row: the site is blocking, the downloads stop here '
                        '(the captions stand in for the missing hooks; not retried today).')
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
                wavs[k] = (str(wav), img.exists(), a['lang'] or LANG, v['id'])
            say(f'  [{i}/{len(todo)}] {label(a)} {v["id"]}: first {CLIP_S} s read')
        by_lang = {}
        for k, (w, _, lang, _) in wavs.items():
            by_lang.setdefault(lang, []).append(w)
        threads = str(min(8, os.cpu_count() or 4))
        for lang, files in by_lang.items():
            say(f'transcribing {len(files)} hook(s) with whisper.cpp ({Path(model).name}, {lang}), locally...')
            for n in range(0, len(files), 100):
                subprocess.run([whisper, '-m', model, '-l', lang, '-t', threads, '-np',
                                '-ml', '1', '-sow', '-oj'] + files[n:n + 100], capture_output=True)
        for k, (w, has_img, lang, vid) in wavs.items():
            try:
                data = json.loads(Path(w + '.json').read_bytes().decode('utf-8', 'replace'))
            except (OSError, ValueError):
                cache[k] = {'status': 'transcription_failed'}
                continue
            words = [(s['offsets']['from'] / 1000, s['offsets']['to'] / 1000, s['text'])
                     for s in data.get('transcription', []) if s.get('text', '').strip()
                     and not re.fullmatch(r'\s*[\[(*♪].*', s['text'])]
            hook, sent, n5 = hook_of(words)
            speech = bool(re.search(r'\w', hook)) and not (JUNK.search(hook) and n5 < 15)
            cache[k] = {'status': 'ok' if speech else 'no_speech',
                        'hook': hook if speech else '', 'sentence': sent if speech else '',
                        'words_5s': n5 if speech else 0,
                        'lang': (data.get('result') or {}).get('language', ''),
                        'image': f'images/{safe(vid)}.jpg' if has_img else ''}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        RAW.mkdir(parents=True, exist_ok=True)
        cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding='utf-8')
    return cache


# --- 4. what comes back ---------------------------------------------------------------
STOP = set('''
monde chose choses gens truc trucs donne donner prend prendre mettre quelqu'un personne
le la les un une des du de au aux et ou mais donc car ni que qui quoi quand comment pourquoi est sont suis
etre avoir ont avons avez ait cet cette ces ceux celle celui cela ceci ils elles nous vous toi moi lui leur
leurs mon mes ton tes son ses notre nos votre vos dans sur sous avec sans pour par entre chez vers depuis
pendant apres avant plus moins tres tout tous toute toutes rien bien fait faire fais faut peut peux veux
veut vais vas aussi alors comme oui non deja encore ici voici voila quel quelle quels quelles dont meme
autre autres jamais toujours trop peu beaucoup vraiment juste parce quoi dit dire vois voir sais savoir
c'est j'ai qu'il qu'on n'est d'un d'une ete etait sera seront cest jai quil quon nest dun dune
the and for you your with this that from are was were have has had not but all can how why what who when
where will just get got its they them their our out about into more most some any one two like make made
here there then than also only very really over after before because every much many now this these those
been being does did doing which would could should yeah okay ok
jour jours fois partie part episode video videos tiktok insta instagram reel reels
abonne abonnes abonnez abonnetoi suis-moi suivez follow followers lien link bio commente commentaire
commentaires comment comments like likes partage partager share enregistre save dm
'''.split())
GENERIC_TAG = re.compile(r'(fyp\w*|foryou\w*|pourtoi\w*|fy|viral\w*|trend\w*|tiktok\w*|xyzbca\w*|explore\w*|'
                         r'reels?|instagram\w*|capcut\w*|stitch|duet|pourvous|parati\w*)')
ACRO = re.compile(r'\b[A-Z][A-Z0-9]{1,4}\b')


def stem(w):
    return w[:-1] if len(w) > 4 and w.endswith('s') and not w.endswith('ss') else w


def title_of(caption):
    """The opening of a caption, where the topic is: its first sentence (two when the first is short),
    30 words at most, without the hashtags. The rest of a long caption is body text, and noise here."""
    text = ' '.join(re.sub(r'#\w+', ' ', caption or '').split())
    parts = re.split(r'(?<=[.!?…])\s+', text)
    head = parts[0] + (' ' + parts[1] if len(parts) > 1 and len(parts[0].split()) < 8 else '')
    return ' '.join(head.split()[:30])


def terms_of(v):
    """{stem: the word as written}: the caption's opening, its hashtags, and the hook when every
    video's hook was read (--hooks all)."""
    text = title_of(v['caption'])
    if args.hooks == 'all' and v['hook_status'] == 'ok':
        text += ' ' + v['sentence']
    out = {}
    for word in re.findall(r'[^\W_]+', text.lower()):        # l'IA -> l, ia ; the accents kept for display
        k = norm(word)
        if len(k) >= 3 and not k.isdigit() and k not in STOP:
            out.setdefault(stem(k), word)
    for w in ACRO.findall(text):                     # IA, AI, SEO, CV: short but not empty
        w = norm(w)
        if w not in STOP and not w.isdigit():
            out.setdefault(w, w.upper())
    for h in v['hashtags']:
        h = norm(h).replace(' ', '')
        if h and not GENERIC_TAG.fullmatch(h) and h not in STOP:
            out.setdefault('#' + h, '#' + h)
    return out


def hit(v):
    return v['status'] == 'outlier' or v['ahead']


def what_comes_back(accts):
    """Terms shared by 2 hits or more (outliers, and young videos already at the threshold), with every
    compared video on the same term."""
    for a in accts:                  # a word or hashtag in half of an account's videos is its signature
        vids = a['videos']           # (its name, its usual hashtags, its call to action), not a topic
        for v in vids:
            v['terms'] = terms_of(v)
        seen = Counter(st for v in vids for st in v['terms'])
        signature = {st for st, n in seen.items() if len(vids) >= 4 and n >= 0.5 * len(vids)}
        for v in vids:
            v['terms'] = {st: w for st, w in v['terms'].items() if st not in signature}
    pool = [v for a in accts for v in a['videos'] if v['status'] in ('outlier', 'normal') or v['ahead']]
    index, written = {}, {}
    for v in pool:
        for st, word in v['terms'].items():
            index.setdefault(st, []).append(v)
            written.setdefault(st, Counter())[word] += 1
    merged = {}
    for st, vids in index.items():
        outs = [v for v in vids if hit(v)]
        if len(outs) >= 2:
            key = (frozenset(id(v) for v in outs), frozenset(id(v) for v in vids))
            merged.setdefault(key, []).append(st)
    groups = []
    for sts in merged.values():
        vids = index[sts[0]]
        outs = sorted((v for v in vids if hit(v)), key=lambda v: -v['x'])
        others = [v for v in vids if not hit(v)]
        sts.sort(key=lambda s: -sum(written[s].values()))
        groups.append({'terms': [written[s].most_common(1)[0][0] for s in sts],
                       'outliers': outs, 'others': others, 'n_videos': len(vids),
                       'accounts': Counter(v['acct'] for v in outs)})
    groups.sort(key=lambda g: (-len(g['outliers']), -len(g['outliers']) / g['n_videos'],
                               -len(g['accounts']), -max(v['x'] for v in g['outliers'])))
    return groups[:MAX_GROUPS]


def openings(outs):
    """The first two words of the hooks, when 2 outliers or more share them."""
    seen = {}
    for v in outs:
        if v['hook_status'] == 'ok':
            w = norm(v['sentence'] or v['hook']).split()
            if len(w) >= 2:
                seen.setdefault(' '.join(w[:2]), []).append(v)
    return sorted(((k, vs) for k, vs in seen.items() if len(vs) >= 2), key=lambda kv: -len(kv[1]))


def duration_buckets(accts):
    pool = [v for a in accts for v in a['videos'] if v['status'] in ('outlier', 'normal')]
    out = []
    for lo, hi in ((0, 30), (30, 60), (60, 90), (90, 10 ** 6)):
        b = [v for v in pool if v['duration_s'] is not None and lo <= v['duration_s'] < hi]
        out.append({'from': lo, 'to': hi, 'n': len(b), 'n_outliers': sum(1 for v in b if v['status'] == 'outlier')})
    return out


def candidates(outs, groups):
    """The highest x median, a few per account so that one account does not fill the list (10 from a
    single account, 5 each from two, 3 each from four or more); then the hits sharing words with another
    one that did not make it, up to 5 more. Shared words are a lead, not a verdict: Claude reads them."""
    rep = {}
    for g in groups:
        for v in g['outliers']:
            rep.setdefault(id(v), g)
    n_acc = len({v['acct'] for v in outs}) or 1
    cap = max(3, -(-MAX_CANDIDATES // n_acc))
    per, picked = Counter(), []
    for v in outs:                                   # already sorted by x
        if per[v['acct']] < cap and len(picked) < MAX_CANDIDATES:
            per[v['acct']] += 1
            picked.append((v, rep.get(id(v))))
    inside = {id(v) for v, _ in picked}
    picked += [(v, rep[id(v)]) for v in outs if id(v) in rep and id(v) not in inside][:5]
    return picked


# --- 5. the files ------------------------------------------------------------------------
def fint(x):
    if x is None:
        return '—'
    s = f'{int(round(x)):,}'
    return s.replace(',', ' ') if R == 'fr' else s


def fdec(x, d=1):
    if x is None:
        return '—'
    s = f'{x:.{d}f}'
    return s.replace('.', ',') if R == 'fr' else s


def fx(x):
    if x is None:
        return '—'
    return '×' + (fint(x) if x >= 100 else fdec(x, 2 if x < 1 else 1))


def fxh(v):
    """x median, with * when the video is under the minimum age (a floor: its views only grow)."""
    return fx(v['x']) + ('*' if v.get('ahead') else '')


def fdur(x):
    return '—' if x is None else f'{int(round(x))} s'


def fday(ts):
    return dt.datetime.fromtimestamp(ts).strftime('%Y-%m-%d') if ts else '—'


def plural(n, fr, en):
    word = t(fr, en)
    return f'{n} {word}' if n == 1 else f'{n} {word}s'


def cell(s):
    return (s or '').replace('|', '/').replace('\n', ' ').replace('[', '(').replace(']', ')').strip()


def quote(s):
    return f'« {s} »' if R == 'fr' else f'"{s}"'


UNIT = {'views': ('vues', 'views'), 'interactions': ('interactions', 'interactions'), 'likes': ('likes', 'likes')}


def unit(a):
    return t(*UNIT[a['stats']['metric']])


def fm(v, a):
    return fint(v['m']) + ('' if a['stats']['metric'] == 'views' else ' ' + unit(a))


def vlabel(v, width=45):
    text = cell(first_line(v['caption'], width)) or v['id']
    return f'[{text}]({v["url"]})' if v['url'] else text


def hook_cell(v):
    if v['hook_status'] == 'ok':
        return quote(cell(v['sentence'] or v['hook']))
    if v['hook_status'] == 'no_speech':
        return t('*(rien de dit : musique ou texte seul)*', '*(nothing said: music or on-screen text only)*')
    return t('*(non lu)*', '*(not read)*')


def write_tables(accts, groups, ops, buckets, cands, by_key):
    head = t('compte,plateforme,rang,x_mediane,statut,date,duree_s,vues,likes,commentaires,partages,'
             'enregistrements,sponsorisee,url,hashtags,legende,id',
             'account,platform,rank,x_median,status,date,duration_s,views,likes,comments,shares,saves,'
             'sponsored,url,hashtags,caption,id').split(',')
    st = {'outlier': 'outlier', 'normal': 'normal', 'recent': t('trop récente', 'too recent'),
          'sponsored': t('sponsorisée', 'sponsored'), 'no_number': t('sans chiffre', 'no number'),
          'unranked': t('non classée', 'unranked')}
    iv = lambda x: '' if x is None else int(round(x))
    with open(OUT / 'catalogue.csv', 'w', newline='', encoding='utf-8') as f:
        cw = csv.writer(f)
        cw.writerow(head)
        for a in accts:
            for v in a['videos']:
                cw.writerow(['@' + a['handle'], a['platform'], v['rank'],
                             '' if v['x'] is None else round(v['x'], 2), st[v['status']],
                             fday(v['ts']) if v['ts'] else '', iv(v['duration_s']), iv(v['views']),
                             iv(v['likes']), iv(v['comments']), iv(v['shares']), iv(v['saves']),
                             t('oui', 'yes') if v['sponsored'] else '', v['url'],
                             ' '.join('#' + h for h in v['hashtags']), ' '.join(v['caption'].split()), v['id']])
    hs = {'ok': 'ok', 'no_speech': t('rien de dit', 'nothing said'),
          'skipped': t('pas tenté (site bloquant)', 'skipped (site blocking)'),
          'download_failed': t('téléchargement refusé', 'download refused'), 'not_read': t('non lu', 'not read'),
          'transcription_failed': t('transcription ratée', 'transcription failed'),
          'no_source': t('ni lien ni fichier', 'no link, no file')}
    head = t('compte\tx_mediane\tstatut\tdate\tduree_s\thook_5s\tphrase\tmots_5s\tlegende_1re_ligne\tlecture\timage\turl',
             'account\tx_median\tstatus\tdate\tduration_s\thook_5s\tsentence\twords_5s\tcaption_first_line\tread\timage\turl')
    clean = lambda x: ' '.join(str(x if x is not None else '').replace('\t', ' ').split())
    with open(OUT / 'hooks.tsv', 'w', encoding='utf-8') as f:
        f.write(head + '\n')
        for a in accts:
            for v in a['videos']:
                if v['hook_status'] == 'not_read':
                    continue
                f.write('\t'.join(clean(x) for x in (
                    '@' + a['handle'], '' if v['x'] is None else round(v['x'], 2), st[v['status']],
                    fday(v['ts']), iv(v['duration_s']), v['hook'], v['sentence'], v['words_5s'],
                    first_line(v['caption'], 200), hs.get(v['hook_status'], v['hook_status']),
                    v['image'], v['url'])) + '\n')
    vref = lambda v: {'account': '@' + by_key[v['acct']]['handle'], 'id': v['id'], 'url': v['url'],
                      'x_median': round(v['x'], 2) if v['x'] is not None else None, 'value': v['m'],
                      'duration_s': v['duration_s'], 'date': fday(v['ts']), 'young': v['ahead'],
                      'hook': v['sentence'] or v['hook']}
    data = {
        'date': TODAY, 'n_videos_per_account': args.count, 'threshold': args.threshold,
        'min_age_days': args.min_age_days, 'hooks': args.hooks,
        'accounts': [dict(a['stats'], error=a['error']) if a.get('stats') else
                     {'account': a['handle'], 'platform': a['platform'], 'error': a['error']} for a in accts],
        'outliers': [vref(v) for a in accts for v in a['videos'] if v['status'] == 'outlier'],
        'ahead': [vref(v) for a in accts for v in a['videos'] if v['ahead']],
        'comes_back': [{'terms': g['terms'], 'n_outliers': len(g['outliers']), 'n_videos': g['n_videos'],
                        'accounts': {'@' + by_key[k]['handle']: n for k, n in g['accounts'].items()},
                        'outliers': [vref(v) for v in g['outliers']],
                        'x_median_others': med([v['x'] for v in g['others']])} for g in groups],
        'hook_openings': [{'opening': k, 'outliers': [vref(v) for v in vs]} for k, vs in ops],
        'durations': buckets,
        'candidates': [vref(v) for v, _ in cands],
    }
    (OUT / 'chiffres.json').write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding='utf-8')


def write_report(accts, outs, hits, groups, ops, buckets, cands, by_key):
    L = []
    w = L.append
    read = [a for a in accts if a.get('stats')]
    w(f'# Outliers · {TODAY}')
    w('')
    w(t(f'{plural(len(accts), "compte", "account")} · les {args.count} dernières vidéos de chacun assez vieilles '
        f'pour être jugées · outlier = ×{FTHR} la médiane de son propre compte ou plus',
        f'{plural(len(accts), "compte", "account")} · the last {args.count} videos of each old enough to be '
        f'judged · outlier = ×{FTHR} its own account\'s median or more'))
    w('')
    w(t('Chaque vidéo se compare à la médiane de son compte, jamais aux vues d\'un autre : 50 000 vues sont un '
        'flop pour un gros compte et un exploit pour un petit. Les vues sont cumulées à date ; les vidéos de '
        f'moins de {fdec(args.min_age_days, 0)} jours grandissent encore : à part, hors de la médiane. Les '
        'vidéos sponsorisées (dit dans la légende) sont hors du calcul : la pub a payé leurs vues.',
        'Each video is compared to its own account\'s median, never to another account\'s views: 50,000 views '
        'are a flop for a big account and a feat for a small one. Views are cumulative; videos younger than '
        f'{fdec(args.min_age_days, 0)} days are still growing: apart, out of the median. Sponsored videos '
        '(said in the caption) are out of the math: ads paid for their views.'))
    w('')
    w(t('<!-- CLAUDE: en une phrase, le constat principal (le coup répété le plus net, sinon le plus gros '
        'outlier), avec ses chiffres. -->',
        '<!-- CLAUDE: in one sentence, the main finding (the clearest repeated hit, else the biggest outlier), '
        'with its numbers. -->'))
    w('')
    # accounts
    w(t('## Les comptes', '## The accounts'))
    w('')
    w(t('| compte | vidéos lues | période | médiane | outliers | à part | note |',
        '| account | videos read | period | median | outliers | apart | note |'))
    w('|---|---|---|---|---|---|---|')
    for a in accts:
        s = a.get('stats')
        if not s:
            w(f'| {label(a)} | — | — | — | — | — | {t("pas lu", "not read")} : {cell(a["error"])} |')
            continue
        apart = ', '.join(x for x in (
            t(f'{s["n_recent"]} récente{"s" if s["n_recent"] > 1 else ""}', f'{s["n_recent"]} recent') if s['n_recent'] else '',
            t(f'{s["n_sponsored"]} sponsorisée{"s" if s["n_sponsored"] > 1 else ""}', f'{s["n_sponsored"]} sponsored') if s['n_sponsored'] else '',
            t(f'{s["n_missing"]} sans chiffre', f'{s["n_missing"]} without a number') if s['n_missing'] else '') if x) or '—'
        note = []
        if s['too_few']:
            note.append(t(f'trop peu de vidéos comparables ({s["n_compared"]}) : rien de classé',
                          f'too few videos to compare ({s["n_compared"]}): nothing ranked'))
        elif s['thin']:
            note.append(t(f'échantillon mince ({s["n_compared"]} comparées)', f'thin sample ({s["n_compared"]} compared)'))
        if a['csv']:
            note.append(t(f'chiffres donnés à la main ({Path(a["csv"]).name})', f'numbers given by hand ({Path(a["csv"]).name})'))
        if s['metric'] != 'views':
            note.append(t(f'pas de vues : classé sur les {unit(a)}', f'no views: ranked on {unit(a)}'))
        period = f'{s["first"]} → {s["last"]}' if s['first'] else '—'
        w(f'| {label(a)} | {s["n_read"]} | {period} | {fint(s["median"])} {unit(a)} | '
          f'{s["n_outliers"] if not s["too_few"] else "—"} | {apart} | {t(" ; ", "; ").join(note) or "—"} |')
    w('')
    # outliers
    w(t('## Les outliers', '## The outliers'))
    w('')
    if outs:
        w(t('| # | compte | vidéo | date | vues | × médiane | durée | dit dans les 5 premières secondes |',
            '| # | account | video | date | views | × median | length | said in the first 5 seconds |'))
        w('|---|---|---|---|---|---|---|---|')
        for k, v in enumerate(outs, 1):
            a = by_key[v['acct']]
            w(f'| {k} | {label(a)} | {vlabel(v)} | {fday(v["ts"])} | {fm(v, a)} | {fx(v["x"])} | '
              f'{fdur(v["duration_s"])} | {hook_cell(v)} |')
        w('')
        w(t('Toutes les vidéos et leurs chiffres (likes, commentaires, partages, enregistrements, légende) sont '
            'dans `catalogue.csv`, les hooks dans `hooks.tsv`'
            + (', les trois premières secondes de chaque outlier en images dans `images/`.' if any(IMG.glob('*.jpg')) else '.'),
            'Every video and its numbers (likes, comments, shares, saves, caption) are in `catalogue.csv`, the '
            'hooks in `hooks.tsv`' + (', the first three seconds of each outlier as pictures in `images/`.'
                                      if any(IMG.glob('*.jpg')) else '.')))
    else:
        w(t(f'Aucune vidéo jugée à ×{FTHR} la médiane ou plus sur ces comptes. La section par compte donne la '
            'meilleure de chacun.', f'No judged video at ×{FTHR} the median or more on these accounts. The '
            'section of each account gives its best one.'))
    n_young = len(hits) - len(outs)
    if n_young:
        w('')
        w(t(f'Et {plural(n_young, "vidéo", "video")} de moins de {fdec(args.min_age_days, 0)} jours déjà à '
            f'×{FTHR} ou plus (« Trop récentes », plus bas) : leurs vues ne font que monter, leur × est un '
            'plancher. Elles comptent comme des coups dans « Ce qui revient » et les candidats, marquées *.',
            f'And {plural(n_young, "vidéo", "video")} under {fdec(args.min_age_days, 0)} days already at '
            f'×{FTHR} or more ("Too recent", below): their views only grow, their × is a floor. They count as '
            'hits in "What comes back" and the candidates, marked *.'))
    w('')
    # what comes back
    w(t('## Ce qui revient', '## What comes back'))
    w('')
    if groups:
        w(t('Les mots que 2 coups ou plus partagent (légendes sans leurs hashtags courants'
            + (', hooks' if args.hooks == 'all' else '') + '), avec toutes les vidéos comparées qui portent les '
            'mêmes mots : un sujet qui sort 3 fois sur 4 est une recette, un sujet qui sort 2 fois sur 12 est '
            f'un mot courant. Un coup = un outlier, ou une vidéo de moins de {fdec(args.min_age_days, 0)} jours '
            f'déjà à ×{FTHR} (marquée *).',
            'The words 2 hits or more share (captions without their usual hashtags'
            + (', hooks' if args.hooks == 'all' else '') + '), with every compared video carrying the same '
            'words: a topic that hits 3 times out of 4 is a recipe, one that hits 2 times out of 12 is a '
            f'common word. A hit = an outlier, or a video under {fdec(args.min_age_days, 0)} days already at '
            f'×{FTHR} (marked *).'))
        w('')
        w(t('| mots | coups | chez | coups / vidéos qui en parlent | × médiane des autres |',
            '| words | hits | on | hits / videos about it | × median of the others |'))
        w('|---|---|---|---|---|')
        for g in groups:
            xs = ' · '.join(fxh(v) for v in g['outliers'])
            on = ', '.join(f'{label(by_key[k])} ({n})' for k, n in g['accounts'].most_common())
            w(f'| {cell(", ".join(g["terms"][:4]))} | {len(g["outliers"])} : {xs} | {on} | '
              f'{len(g["outliers"])} / {g["n_videos"]} | {fx(med([v["x"] for v in g["others"]]))} |')
        w('')
    else:
        w(t('Aucun mot partagé par 2 coups ou plus dans les légendes.',
            'No word shared by 2 hits or more in the captions.'))
        w('')
    if ops:
        w(t('Les hooks des coups qui commencent pareil :', 'Hooks of the hits that open the same way:'))
        w('')
        for k, vs in ops:
            w(f'- {quote(k + "…")} : ' + ', '.join(f'{label(by_key[v["acct"]])} {fxh(v)}' for v in vs))
        w('')
    if outs and any(b['n'] for b in buckets):
        w(t('| durée | vidéos comparées | outliers |', '| length | videos compared | outliers |'))
        w('|---|---|---|')
        for b in buckets:
            name = (t(f'moins de {b["to"]} s', f'under {b["to"]} s') if b['from'] == 0 else
                    t(f'{b["from"]} s et plus', f'{b["from"]} s and over') if b['to'] > 10 ** 5 else
                    f'{b["from"]}-{b["to"]} s')
            w(f'| {name} | {b["n"]} | {b["n_outliers"]} |')
        w('')
    w(t('<!-- CLAUDE: les coups répétés : un sujet ou une forme qui sort 2 fois ou plus à l\'outlier, chez un '
        'compte ou chez plusieurs, avec ses chiffres (« 3 outliers sur 4 vidéos du sujet chez @un_compte : ×4,2, '
        '×3,5, ×3,1 ; la 4e ×1,1 »). Fusionne les mots d\'un même sujet, écarte le bruit (un mot courant, un '
        'nom propre sans sujet). Lis aussi les hooks et les images : une même forme (même ouverture de phrase, '
        'titre à l\'écran, démo, durée) compte comme un sujet. Un coup isolé se dit isolé. Pas de coup '
        'répété : dis-le en une phrase. -->',
        '<!-- CLAUDE: the repeated hits: a topic or a form that hits 2 times or more, on one account or across '
        'several, with its numbers ("3 outliers out of 4 videos on it at @an_account: ×4.2, ×3.5, ×3.1; the 4th '
        '×1.1"). Merge the words of one topic, drop the noise (a common word, a name with no topic). Read the '
        'hooks and the pictures too: a shared form (same opening, title on screen, demo, length) counts as a '
        'topic. A lone hit is called lone. No repeated hit: say it in one sentence. -->'))
    w('')
    # per account
    w(t('## Par compte', '## Account by account'))
    for a in accts:
        s = a.get('stats')
        w('')
        w(f'### {label(a)}')
        w('')
        if not s:
            w(t(f'Pas lu : {a["error"]}.', f'Not read: {a["error"]}.'))
            continue
        w(t(f'{s["n_read"]} vidéos' + (f' du {s["first"]} au {s["last"]}' if s['first'] else '')
            + f' · médiane {fint(s["median"])} {unit(a)} · moyenne {fx(s["mean_over_median"])} la médiane · '
            f'durée médiane {fdur(s["duration_median"])}',
            f'{s["n_read"]} videos' + (f' from {s["first"]} to {s["last"]}' if s['first'] else '')
            + f' · median {fint(s["median"])} {unit(a)} · mean {fx(s["mean_over_median"])} the median · '
            f'median length {fdur(s["duration_median"])}'))
        w('')
        mine = [v for v in a['videos'] if v['status'] == 'outlier']
        young = [v for v in a['videos'] if v['ahead']]
        if s['too_few']:
            w(t(f'Trop peu de vidéos comparables ({s["n_compared"]}, il en faut {MIN_MEDIAN}) : pas de médiane, '
                'rien de classé. Un -n plus grand, ou plus de lignes dans le CSV.',
                f'Too few videos to compare ({s["n_compared"]}, {MIN_MEDIAN} needed): no median, nothing ranked. '
                'A larger -n, or more lines in the CSV.'))
            continue
        if mine or young:
            for v in sorted(mine + young, key=lambda v: -v['x']):
                w(f'- {fxh(v)} · {fm(v, a)} · {fdur(v["duration_s"])} · {fday(v["ts"])} · {vlabel(v, 70)}')
            w('')
            if mine:
                w(t(f'Ses outliers durent {fdur(s["duration_outliers"])} (médiane), le compte {fdur(s["duration_median"])}.',
                    f'Its outliers last {fdur(s["duration_outliers"])} (median), the account {fdur(s["duration_median"])}.'))
            if young:
                w(t(f'* moins de {fdec(args.min_age_days, 0)} jours : × provisoire, un plancher.',
                    f'* under {fdec(args.min_age_days, 0)} days: × for now, a floor.'))
            if s['thin']:
                w(t(f'Échantillon mince ({s["n_compared"]} vidéos comparées) : à décrire, pas à conclure.',
                    f'Thin sample ({s["n_compared"]} videos compared): describe, conclude nothing.'))
            w('')
            w(t(f'<!-- CLAUDE: {label(a)} : pour chaque outlier, pourquoi il a marché d\'après ce qu\'on voit : le '
                'hook (verbatim dans « Les outliers »), le sujet, la durée contre la durée médiane du compte, les '
                'images (titre à l\'écran, visage, démo). Puis ce que ses outliers ont en commun et que ses autres '
                'vidéos n\'ont pas, chiffres à l\'appui. Une hypothèse se dit hypothèse. -->',
                f'<!-- CLAUDE: {label(a)}: for each outlier, why it worked from what can be seen: the hook (verbatim '
                'in "The outliers"), the topic, its length against the account\'s median length, the pictures '
                '(title on screen, face, demo). Then what its outliers share that its other videos lack, with '
                'the counts. A guess is called a guess. -->'))
        else:
            best = [v for v in a['videos'] if v['status'] == 'normal'][:3]
            w(t(f'Aucune vidéo à ×{FTHR} ou plus. Les meilleures :', f'No video at ×{FTHR} or more. The best:'))
            w('')
            for v in best:
                w(f'- {fx(v["x"])} · {fm(v, a)} · {fdur(v["duration_s"])} · {fday(v["ts"])} · {vlabel(v, 70)}')
    w('')
    # recent
    recent = [(a, v) for a in read for v in a['videos'] if v['status'] == 'recent']
    if recent:
        w(t(f'## Trop récentes pour juger (moins de {fdec(args.min_age_days, 0)} jours)',
            f'## Too recent to judge (under {fdec(args.min_age_days, 0)} days)'))
        w('')
        w(t('| compte | vidéo | date | vues | × médiane (provisoire) | dit dans les 5 premières secondes |',
            '| account | video | date | views | × median (for now) | said in the first 5 seconds |'))
        w('|---|---|---|---|---|---|')
        for a, v in sorted(recent, key=lambda av: -(av[1]['x'] or 0)):
            ahead = t(' (déjà en avance)', ' (already ahead)') if v['ahead'] else ''
            w(f'| {label(a)} | {vlabel(v)} | {fday(v["ts"])} | {fm(v, a)} | {fx(v["x"])}{ahead} | {hook_cell(v)} |')
        w('')
    # candidates and the 5 to remake
    w(t('## Les candidats', '## The candidates'))
    w('')
    if cands:
        w(t('Le pré-tri du script : le plus haut × médiane, quelques-uns par compte pour qu\'un seul ne remplisse '
            'pas la liste, puis les coups qui partagent des mots avec un autre. « mots partagés » : les mots du '
            'tableau « Ce qui revient » (coups / vidéos qui en parlent), une piste à lire, pas un verdict.',
            'The script\'s pre-sort: the highest × median, a few per account so that one account does not fill '
            'the list, then the hits sharing words with another one. "shared words": the words of the "What '
            'comes back" table (hits / videos about it), a lead to read, not a verdict.'))
        w('')
        w(t('| # | compte | × médiane | mots partagés | dit dans les 5 premières secondes | vidéo |',
            '| # | account | × median | shared words | said in the first 5 seconds | video |'))
        w('|---|---|---|---|---|---|')
        for k, (v, g) in enumerate(cands, 1):
            rep = f'{cell(", ".join(g["terms"][:2]))} ({len(g["outliers"])}/{g["n_videos"]})' if g else '—'
            w(f'| {k} | {label(by_key[v["acct"]])} | {fxh(v)} | {rep} | {hook_cell(v)} | {vlabel(v, 40)} |')
        if any(v['ahead'] for v, _ in cands):
            w('')
            w(t(f'* moins de {fdec(args.min_age_days, 0)} jours : × provisoire, un plancher.',
                f'* under {fdec(args.min_age_days, 0)} days: × for now, a floor.'))
    else:
        w(t('Aucun coup : rien à refaire cette fois. Un -n plus grand ou d\'autres comptes.',
            'No hit: nothing to remake this time. A larger -n or other accounts.'))
    w('')
    w(t('## Les 5 à refaire', '## 5 to remake'))
    w('')
    w('<!-- a-refaire v1 : ' + t('une ligne par idée, colonnes dans cet ordre (references/a-refaire.md). '
                                 'La skill script lit ce tableau.',
                                 'one row per idea, columns in this order (references/a-refaire.md). '
                                 'The script skill reads this table.') + ' -->')
    w(t('| # | sujet | hook d\'origine | pourquoi ça a marché (les chiffres) | ton angle | source |',
        '| # | topic | original hook | why it worked (the numbers) | your angle | source |'))
    w('|---|---|---|---|---|---|')
    w(t('<!-- CLAUDE: cinq lignes, une par idée, prises dans les candidats (ou un autre outlier, en le disant). '
        'Ordre de choix : un sujet que l\'utilisateur peut traiter chez lui (hors de son sujet = dehors, quel que '
        'soit le ×) ; un coup répété avant un coup isolé ; 2 idées par compte au plus. sujet : quelques mots. '
        'hook d\'origine : le verbatim entre « », puis le compte. pourquoi : des chiffres seulement (× médiane, '
        'vues contre la médiane du compte, répété avec n ou isolé, durée contre celle du compte). ton angle : une '
        'phrase dans la voix de l\'utilisateur, ce que lui dirait depuis sa propre expérience, jamais le hook '
        'd\'origine recopié. source : le lien. Pas de barre verticale dans une cellule. Moins de 5 bons : moins '
        'de lignes, et dis pourquoi sous le tableau. -->',
        '<!-- CLAUDE: five rows, one per idea, taken from the candidates (or another outlier, saying so). '
        'Picking order: a topic the user can make their own (off their topic = out, whatever the ×); a repeated '
        'hit before a lone one; 2 ideas per account at most. topic: a few words. original hook: the verbatim in '
        '"", then the account. why: numbers only (× median, views against the account median, repeated with n '
        'or lone, length against the account\'s). your angle: one sentence in the user\'s voice, what they would '
        'say from their own experience, never the original hook copied. source: the link. No vertical bar in a '
        'cell. Fewer than 5 good ones: fewer rows, and say why under the table. -->'))
    w('')
    w(t('Chaque ligne est un test, pas une recette garantie : ta version se juge à × ta propre médiane, sur 3 à 5 '
        'vidéos. La structure d\'un hook se reprend, ses mots non.',
        'Each row is a test, not a sure recipe: your version is judged at × your own median, over 3 to 5 videos. '
        'A hook\'s structure can be reused, its words cannot.'))
    w('')
    # method
    w(t('## Méthode et limites', '## Method and limits'))
    w('')
    w(t(f'- × médiane = les vues de la vidéo ÷ la médiane des vidéos comparées de son compte (assez vieilles, '
        f'pas sponsorisées). ×{FTHR} et plus : outlier. Un seuil de lecture, pas un test statistique ; il faut '
        f'{MIN_MEDIAN} vidéos comparables pour une médiane, moins de {THIN} est un échantillon mince.',
        f'- × median = the video\'s views ÷ the median of its account\'s compared videos (old enough, not '
        f'sponsored). ×{FTHR} and more: outlier. A reading threshold, not a statistical test; a median needs '
        f'{MIN_MEDIAN} comparable videos, under {THIN} is a thin sample.'))
    w(t('- Sponsorisée = la légende le dit (#ad, #pub, #sponsorisé, partenariat…). Une pub qui ne le dit pas '
        'passe pour une vidéo normale.',
        '- Sponsored = the caption says so (#ad, #sponsored, paid partnership...). An ad that does not say so '
        'passes for a normal video.'))
    if any(v['hook_status'] in ('ok', 'no_speech') for a in read for v in a['videos']):
        w(t(f'- Hook = ce qui est dit dans les {int(HOOK_S)} premières secondes (phrase finie, {CLIP_S} s au plus), '
            f'transcrit sur cette machine par whisper.cpp ({Path(MODEL).name}), lu pour '
            + ('chaque vidéo' if args.hooks == 'all' else 'les outliers et les récentes déjà en avance')
            + '. Whisper peut se tromper d\'un mot.',
            f'- Hook = what is said in the first {int(HOOK_S)} seconds (sentence finished, {CLIP_S} s at most), '
            f'transcribed on this computer by whisper.cpp ({Path(MODEL).name}), read for '
            + ('every video' if args.hooks == 'all' else 'the outliers and the recent ones already ahead')
            + '. Whisper can get a word wrong.'))
    w(t(f'- Lecture anonyme, un seul passage, {fdec(args.delay, 0)} s ou plus entre deux requêtes. Aucune '
        'connexion, aucun mot de passe. Instagram refuse cette lecture : ses comptes viennent d\'un CSV.',
        f'- Anonymous read, one pass, {fdec(args.delay, 0)} s or more between two requests. No login, no '
        'password. Instagram refuses this reading: its accounts come from a CSV.'))
    w(t('- Un outlier peut venir d\'ailleurs que la vidéo : une tendance, un duo, une reprise par un gros compte, '
        'une pub non dite. Le tableau dit ce qui a sur-performé, pas pourquoi : les hooks, les images et les '
        'répétitions aident, une hypothèse reste une hypothèse.',
        '- An outlier can come from outside the video: a trend, a duet, a repost by a big account, an untold ad. '
        'The table says what over-performed, not why: hooks, pictures and repeats help, a guess stays a guess.'))
    w(t('- Pas mesuré : la rétention, la portée, le texte des commentaires (il ne se lit pas sans connexion).',
        '- Not measured: retention, reach, the text of the comments (it cannot be read without logging in).'))
    w('')
    f = OUT / 'OUTLIERS.md'
    if f.exists() and '<!-- CLAUDE:' not in f.read_text(encoding='utf-8'):     # already written: keep it
        keep = OUT / f'OUTLIERS-{t("avant", "before")}-{dt.datetime.now().strftime("%H%M%S")}.md'
        f.rename(keep)
        say(f'the OUTLIERS.md already written is kept as {keep.name}')
    f.write_text('\n'.join(L), encoding='utf-8')


# --- main ------------------------------------------------------------------------------
def main():
    given = []
    for s in args.accounts:
        a = parse_spec(s)
        if not a:
            die(f'"{s}" is not an account: @account, tiktok:account, instagram:account or a profile link.')
        given.append(a)
    from_csv = []
    for s in args.csv:
        if '=' in s and not Path(s).expanduser().exists():
            spec, f = s.split('=', 1)
            a = parse_spec(spec)
        elif len(given) == 1:
            a, f = given[0], s
        else:
            a, f = parse_spec(Path(s).stem), s
        if not a:
            die(f'--csv {s}: which account? Write --csv @account=FILE.')
        a['csv'] = f
        from_csv.append(a)
    wl = Path(args.watchlist).expanduser()
    cited = given + [a for a in from_csv if a['key'] not in {g['key'] for g in given}]
    if args.add:
        if not cited:
            die('--add: no account given to add.')
        new = add_to_watchlist(wl, cited)
        say(f'{wl}: ' + (f'added {", ".join(label(a) for a in new)}' if new else 'already there, nothing added'))
    if given:
        run = list(given)
    elif wl.exists():
        run, bad = read_watchlist(wl)
        if bad:
            say(f'{wl}: lines not understood, skipped: {"; ".join(bad)}')
        if not run and not from_csv:
            die(f'{wl} has no account in it: one per line, like @an_account.')
    elif from_csv:
        run = []
    else:
        die(f'No account: give one (@an_account), or write {wl.name} in this folder, one account per line.')
    keys = {a['key']: a for a in run}
    for a in from_csv:
        if a['key'] in keys:
            keys[a['key']]['csv'] = a['csv']
        else:
            run.append(a)
            keys[a['key']] = a
    seen, accts = set(), []
    for a in run:
        if a['key'] not in seen:
            seen.add(a['key'])
            accts.append(a)
    by_key = {a['key']: a for a in accts}
    say(f'{len(accts)} account(s), the last {args.count} videos of each old enough to judge (the younger '
        f'ones apart), read anonymously -> {OUT}')
    ytdlp = shutil.which('yt-dlp')
    if not ytdlp and any(a['platform'] == 'tiktok' and not a['csv'] for a in accts):
        die('yt-dlp not found. Install it: macOS `brew install yt-dlp`, Windows `winget install yt-dlp`, '
            'Linux `pipx install yt-dlp`. Then run again.', 4)
    RAW.mkdir(parents=True, exist_ok=True)
    refusals, stopped = 0, False
    for a in accts:
        if a['csv']:
            videos = read_csv(a['csv'])
            if a['platform'] == 'tiktok' and videos and all('instagram.com' in v['url'] for v in videos if v['url']) \
                    and any(v['url'] for v in videos):
                a['platform'], a['key'] = 'instagram', 'instagram-' + a['handle'].lower()
                by_key[a['key']] = a
        elif a['platform'] == 'instagram':
            a['error'] = t('Instagram refuse la lecture anonyme ; ses chiffres viennent d\'un CSV (--csv)',
                           'Instagram refuses anonymous reading; its numbers come from a CSV (--csv)')
            say(f'  {label(a)}: Instagram refuses anonymous reading, not tried. Its numbers by hand: --csv FILE '
                '(references/manual.md).')
            continue
        elif stopped:
            a['error'] = t('pas tenté : TikTok a refusé deux comptes de suite', 'not tried: TikTok refused two accounts in a row')
            continue
        else:
            videos, err, asked = fetch_listing(a, ytdlp)
            if videos is None:
                a['error'] = err
                say(f'  {label(a)}: nothing read ({err})')
                if asked:
                    refusals += 1
                    if refusals >= 2:
                        stopped = True
                        say('  two accounts refused in a row: TikTok is blocking, the other accounts wait for '
                            'another day.')
                continue
            if asked:
                refusals = 0
        compute_account(a, videos)
        s = a['stats']
        say(f'  {label(a)}: {s["n_read"]} videos, median {fint(s["median"])} {unit(a)}, '
            f'{s["n_outliers"]} at x{FTHR}+' + (' (too few to rank)' if s['too_few'] else ''))
    read = [a for a in accts if a.get('stats')]
    if not read:
        die('No account could be read: nothing written. ' + ' '.join(f'{label(a)}: {a["error"]}.' for a in accts)
            + ' Not retried today.', 3)
    for a in read:
        by_key[a['key']] = a
    if args.hooks != 'none':
        targets = [(a, v) for a in read for v in a['videos']
                   if (v['status'] in ('outlier', 'normal', 'unranked', 'recent') if args.hooks == 'all' else hit(v))]
        hooks = get_hooks(targets)
        for a in read:
            for v in a['videos']:
                h = hooks.get(hkey(v), {})
                v['hook'], v['sentence'] = h.get('hook', ''), h.get('sentence', '')
                v['words_5s'], v['hook_status'] = h.get('words_5s'), h.get('status', 'not_read')
                v['image'] = h.get('image', '')
    outs = sorted((v for a in read for v in a['videos'] if v['status'] == 'outlier'), key=lambda v: -v['x'])
    hits = sorted((v for a in read for v in a['videos'] if hit(v)), key=lambda v: -v['x'])
    groups = what_comes_back(read)
    ops = openings(hits)
    buckets = duration_buckets(read)
    cands = candidates(hits, groups)
    write_tables(read, groups, ops, buckets, cands, by_key)
    write_report(accts, outs, hits, groups, ops, buckets, cands, by_key)
    say('')
    say(f'-> {OUT}/  OUTLIERS.md, catalogue.csv, hooks.tsv, chiffres.json' + (', images/' if any(IMG.glob('*.jpg')) else ''))
    say(f'{len(outs)} outlier(s) at x{FTHR}+ over {len(read)} account(s)'
        + (f', and {len(hits) - len(outs)} video(s) under {args.min_age_days:g} days already there'
           if len(hits) > len(outs) else ''))
    for v in hits[:15]:
        a = by_key[v['acct']]
        said = v['sentence'] or v['hook'] or f'({first_line(v["caption"], 60) or v["id"]})'
        young = t(' (récente)', ' (recent)') if v['ahead'] else ''
        say(f'  {fx(v["x"]):>7} {fint(v["m"]):>9} {fdur(v["duration_s"]):>6}  {label(a):<22} {said[:80]}{young}')
    for g in groups[:5]:
        say(f'  comes back: {", ".join(g["terms"][:3])}: {len(g["outliers"])} outliers / {g["n_videos"]} videos')
    if wl.exists():
        listed = {a['key'] for a in read_watchlist(wl)[0]}
        missing = [a for a in cited if a['key'] not in listed]
    else:
        missing = cited
    if missing:
        say(f'not in {wl.name}: {", ".join(label(a) for a in missing)} (ask the user; yes = the same command '
            'with --add, nothing is fetched twice)')
    n = (OUT / 'OUTLIERS.md').read_text(encoding='utf-8').count('<!-- CLAUDE:')
    say(f'OUTLIERS.md: {n} "<!-- CLAUDE:" markers left to write.')


if __name__ == '__main__':
    main()
