"""settings.py — where each setting comes from, and the tools it points to.

Order, the first one that says something wins:
  1. the command line (--stt, --model, --ffmpeg, --lang, -o, --subtitles /
     --no-subtitles, --remotion / --no-remotion);
  2. ~/.config/video-editing/config.json, every key optional:
       {"stt": "whisper" | "elevenlabs", "whisper_model": "large-v3-turbo",
        "ffmpeg": "/path/to/ffmpeg", "lang": "fr", "output_dir": "~/Videos/edited",
        "subtitles": true, "remotion": true}
  3. the default below (ffmpeg: the first one found that can burn subtitles).

The ElevenLabs key is NEVER in config.json: only ELEVENLABS_API_KEY in the
environment, or a line ELEVENLABS_API_KEY=... in ~/.config/video-editing/env
(mode 600), read when it exists. Nothing here prints a key.

    python scripts/edit_video.py --config     # the resolved settings, and where each comes from
"""
import glob, json, os, re, shutil, subprocess, sys

CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.config', 'video-editing')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
ENV_FILE = os.path.join(CONFIG_DIR, 'env')
USER_STYLE = os.path.join(CONFIG_DIR, 'style.json')

DEFAULTS = {'stt': 'whisper', 'whisper_model': 'large-v3-turbo', 'ffmpeg': None, 'lang': 'en',
            'output_dir': '~/Videos/edited', 'subtitles': True, 'remotion': True}

# ffmpeg builds that carry libass (the subtitles), looked at before the one on the PATH:
# Homebrew's `ffmpeg` formula has no libass, `ffmpeg-full` has it.
FFMPEG_CANDIDATES = ['/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg', '/usr/local/opt/ffmpeg-full/bin/ffmpeg']
# Windows: where the `set-up-video-tools` skill unzips whisper.cpp (no PATH to touch), and where winget puts ffmpeg
# (found without reopening the terminal after `winget install Gyan.FFmpeg`).
LOCAL_APPDATA = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
WHISPER_DIR_WINDOWS = os.path.join(LOCAL_APPDATA, 'whisper.cpp')
INSTALL_LIBASS = ('an ffmpeg with libass: macOS `brew install ffmpeg-full` (found by itself, '
                  'no need to touch the PATH); Windows `winget install Gyan.FFmpeg` (the full build); '
                  'Linux `sudo apt install ffmpeg`')


def say(msg):
    print(msg, file=sys.stderr)


def load_env_file():
    """KEY=value lines of ~/.config/video-editing/env into the environment, without
    overriding what is already set. Returns 'environment', 'env file' or None for the key."""
    origin = 'environment' if os.environ.get('ELEVENLABS_API_KEY') else None
    if os.path.exists(ENV_FILE):
        if os.name == 'posix' and os.stat(ENV_FILE).st_mode & 0o077:
            say(f'warning: {ENV_FILE} can be read by other users: chmod 600 "{ENV_FILE}"')
        for line in open(ENV_FILE, encoding='utf-8-sig').read().splitlines():   # -sig: saved by Notepad
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip().removeprefix('export ').strip()
            v = v.strip().strip('"').strip("'")
            if k and v and not os.environ.get(k):
                os.environ[k] = v
                if k == 'ELEVENLABS_API_KEY':
                    origin = 'env file'
    return origin


def read_file():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        data = json.load(open(CONFIG_FILE, encoding='utf-8-sig'))
    except (OSError, ValueError) as e:
        sys.exit(f'{CONFIG_FILE} is not valid JSON ({e}): fix it or delete it')
    if not isinstance(data, dict):
        sys.exit(f'{CONFIG_FILE} must hold a JSON object')
    return data


_LIBASS = {}


def has_filter(ff, name):
    """Does this ffmpeg know the filter `name` (ass, subtitles, zscale...)?"""
    if (ff, name) not in _LIBASS:
        try:
            out = subprocess.run([ff, '-hide_banner', '-filters'], capture_output=True, text=True, errors='replace').stdout
        except OSError:
            out = ''
        _LIBASS[(ff, name)] = bool(re.search(rf'^\s*\S+\s+{re.escape(name)}\s', out, re.M))
    return _LIBASS[(ff, name)]


def windows_ffmpegs():
    """Windows: where `winget install Gyan.FFmpeg` puts ffmpeg (its link, then the package itself)."""
    if os.name != 'nt':
        return []
    w = os.path.join(LOCAL_APPDATA, 'Microsoft', 'WinGet')
    return [os.path.join(w, 'Links', 'ffmpeg.exe')] + sorted(
        glob.glob(os.path.join(w, 'Packages', 'Gyan.FFmpeg*', '*', 'bin', 'ffmpeg.exe')), reverse=True)


def find_ffmpeg():
    """The first ffmpeg found that can burn subtitles, else the first ffmpeg found."""
    seen = []
    for c in [os.environ.get('FFMPEG')] + FFMPEG_CANDIDATES + [shutil.which('ffmpeg')] + windows_ffmpegs():
        if c and (os.path.exists(c) or shutil.which(c)) and c not in seen:
            seen.append(c)
            if has_filter(c, 'ass'):
                return c
    return seen[0] if seen else None


def find_whisper():
    """whisper-cli on the PATH (whisper-cli.exe on Windows), else where setup unzipped it on Windows.
    Never main.exe: in the Windows zips it is only a stub that says it is deprecated."""
    w = shutil.which('whisper-cli') or shutil.which('whisper-cpp')
    if not w and os.name == 'nt':
        w = next((p for p in (os.path.join(WHISPER_DIR_WINDOWS, 'Release', 'whisper-cli.exe'),
                              os.path.join(WHISPER_DIR_WINDOWS, 'whisper-cli.exe')) if os.path.exists(p)), None)
    return w


def ffprobe_for(ff):
    """The ffprobe next to that ffmpeg, else $FFPROBE, else the one on the PATH."""
    if ff:
        d, name = os.path.split(ff)
        sib = os.path.join(d, name.replace('ffmpeg', 'ffprobe'))
        if d and os.path.exists(sib):
            return sib
    return os.environ.get('FFPROBE') or shutil.which('ffprobe') or 'ffprobe'


def as_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')


def resolve(cli):
    """cli: {key: value or None}. Returns (values, sources)."""
    data = read_file()
    vals, src = {}, {}
    for k, d in DEFAULTS.items():
        if cli.get(k) is not None:
            vals[k], src[k] = cli[k], 'command line'
        elif data.get(k) not in (None, ''):
            vals[k], src[k] = data[k], 'config file'
        else:
            vals[k], src[k] = d, 'default'
    stt = str(vals['stt']).strip().lower()
    stt = {'scribe': 'elevenlabs', 'eleven': 'elevenlabs', 'whisper.cpp': 'whisper'}.get(stt, stt)
    if stt not in ('whisper', 'elevenlabs'):
        sys.exit(f'stt must be "whisper" or "elevenlabs", not "{vals["stt"]}" ({src["stt"]})')
    vals['stt'] = stt
    vals['subtitles'], vals['remotion'] = as_bool(vals['subtitles']), as_bool(vals['remotion'])
    if vals['ffmpeg'] is None:
        vals['ffmpeg'], src['ffmpeg'] = find_ffmpeg(), 'auto-detected'
    else:
        vals['ffmpeg'] = os.path.expanduser(vals['ffmpeg'])
    if not vals['ffmpeg'] or not (os.path.exists(vals['ffmpeg']) or shutil.which(vals['ffmpeg'])):
        sys.exit(f'ffmpeg not found ({src["ffmpeg"]}: {vals["ffmpeg"]}). Install {INSTALL_LIBASS}.')
    vals['ffprobe'] = ffprobe_for(vals['ffmpeg'])
    vals['output_dir'] = os.path.expanduser(str(vals['output_dir']))
    return vals, src


def node_version():
    node = shutil.which('node')
    if not node:
        return None
    try:
        v = subprocess.run([node, '--version'], capture_output=True, text=True, errors='replace').stdout.strip()
        return v if v.startswith('v') else None
    except OSError:
        return None


def describe(vals, src, key_origin, whisper_bin, model_file, remotion_dir, out_given):
    """The `--config` report."""
    W = 18
    rows = [('config file', CONFIG_FILE + ('' if os.path.exists(CONFIG_FILE) else '  (none: defaults)'), '')]
    for k in DEFAULTS:
        v = vals[k]
        shown = json.dumps(v) if isinstance(v, bool) else str(v)
        note = src[k]
        if k == 'ffmpeg':
            note += ', ' + ('burns subtitles (libass)' if has_filter(v, 'ass') else
                            'NO libass: no subtitles burned in -> install ' + INSTALL_LIBASS)
        if k == 'whisper_model':
            note += ', ' + (f'file {model_file}' if model_file else 'not downloaded yet (downloads itself on first run)')
        if k == 'output_dir' and out_given:
            note += ' (-o given: not used)'
        if k == 'remotion':
            nv = node_version()
            ready = os.path.isdir(os.path.join(remotion_dir, 'node_modules'))
            note += ', ' + (f'node {nv}, ' + ('installed' if ready else 'npm install on first use')
                            if nv else 'Node not found: title and end card drawn by ffmpeg')
        rows.append((k, shown, note))
    rows.append(('ffprobe', vals['ffprobe'], ''))
    rows.append(('whisper-cli', whisper_bin or 'not found', '' if whisper_bin else
                 'needed for stt=whisper: the `set-up-video-tools` skill installs it'))
    rows.append(('ELEVENLABS_API_KEY', f'set ({key_origin})' if key_origin else 'not set',
                 'needed for stt=elevenlabs' if not key_origin else ''))
    rows.append(('style', USER_STYLE if os.path.exists(USER_STYLE) else 'the one shipped with the skill', ''))
    return '\n'.join(f'{k:<{W}} {v}' + (f'   [{n}]' if n else '') for k, v, n in rows)
