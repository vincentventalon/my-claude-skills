"""finish.py — the cut becomes the video you post (edit_video.py calls it).

  - 9:16, 1080x1920, for TikTok, Instagram Reels and YouTube Shorts: a rush
    filmed upright fills the screen; filmed sideways, it sits in the middle
    on a blurred copy of itself (--fit fill crops it to fill instead);
  - 16:9, 1920x1080, for YouTube (--youtube), when the rush is horizontal;
  - the subtitles burned in, a few words at a time, the word being said lit up;
  - a title on top for the first seconds, an end card (the call to action)
    on the last ones;
  - the voice evened out toward -14 LUFS (what the platforms play at): one
    linear gain, measured first, that never pushes a peak past -1.5 dBTP.

The subtitles, the title and the end card are ONE .ass file (<video>.ass,
plain text: a word can be fixed in it by hand) burned in by ffmpeg's libass.
Their look comes from style.json: the one next to scripts/, then
~/.config/video-editing/style.json, then --style FILE, each one saying only
what it changes. With Node 18+ and the remotion/ folder, Remotion draws the
title and the end card instead (animated, rounded boxes), laid over the video;
without Node the .ass draws them, and the video comes out all the same.
"""
import json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
STYLE = os.path.join(SKILL, 'style.json')
FONTS = os.path.join(SKILL, 'fonts')
REMOTION = os.path.join(SKILL, 'remotion')

# The end card when the user gave none (--cta), in the language of the video.
CTA = {'fr': 'Abonne-toi pour la suite', 'en': 'Follow for more', 'es': 'Sígueme para más',
       'de': 'Folge mir für mehr', 'it': 'Seguimi per altri video', 'pt': 'Me segue para mais'}


def say(msg):
    print(msg, file=sys.stderr)


# --- style ------------------------------------------------------------------------------
def merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merge(base[k], v)
        else:
            base[k] = v
    return base


def load_style(user=None, extra=None):
    """The shipped style.json, then the user's (if it exists), then --style."""
    st = json.load(open(STYLE, encoding='utf-8'))
    for p in (user if user and os.path.exists(user) else None, extra):
        if p and os.path.exists(p):
            try:
                merge(st, json.load(open(p, encoding='utf-8')))
            except ValueError as e:
                sys.exit(f'{p} is not valid JSON ({e})')
        elif p:
            sys.exit(f'style file not found: {p}')
    return st


def ass_color(c):
    """'#RRGGBB' (or '#RRGGBBAA', AA = opacity) -> '&HAABBGGRR' (ASS: AA = transparency)."""
    c = c.lstrip('#')
    r, g, b = c[0:2], c[2:4], c[4:6]
    a = 255 - int(c[6:8], 16) if len(c) == 8 else 0
    return f'&H{a:02X}{b}{g}{r}'.upper()


def ass_inline(c):
    """'#RRGGBB' -> '&HBBGGRR&', the colour inside an override tag."""
    c = c.lstrip('#')
    return f'&H{c[4:6]}{c[2:4]}{c[0:2]}&'.upper()


def ass_time(t):
    cs = max(0, int(round(t * 100)))
    return f'{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}'


def esc(t):
    return t.replace('\\', '/').replace('{', '(').replace('}', ')').replace('\n', ' ')


# --- where things go ------------------------------------------------------------------
def layout(src_w, src_h, wide, fit, st):
    """The frame (W x H), how the video sits in it, and the height of the
    centre of the subtitles, the title and the end card."""
    W, H = (1920, 1080) if wide else (1080, 1920)
    if fit == 'auto':
        fit = 'fill' if (src_h >= src_w) == (H >= W) else 'frame'
    L = {'W': W, 'H': H, 'fit': fit, 'k': st.get('wide_scale', 0.72) if wide else 1.0}
    key = 'y_wide' if wide else 'y'
    for part in ('captions', 'title', 'end_card'):
        L[part] = st[part].get(key, st[part]['y']) * H
    if fit == 'frame':
        cw, ch = W, round(W * src_h / src_w / 2) * 2
        if ch > H:
            cw, ch = round(H * src_w / src_h / 2) * 2, H
        top = (H - ch) // 2
        L.update(cw=cw, ch=ch, top=top)
        if ch < H * 0.8:                       # room above and below the card: text goes there
            L['title'] = L['end_card'] = top * 0.62
            L['captions'] = top + ch + (H - top - ch) * 0.32
    return L


# --- the .ass -----------------------------------------------------------------------------
SENT_END = ('.', '!', '?', '…')
CLAUSE_END = (',', ';', ':')


def display(word, st):
    """What a subtitle shows of a word: no "--" of a cut word, no . , ; : unless
    asked (? and ! stay), upper case if asked."""
    w = re.sub(r'-{2,}$', '', word.strip())
    if not st.get('punctuation', False):
        w = re.sub(r'[.,;:…]+$', '', w)
        w = re.sub(r'^[«“"(]+|[»”")]+$', '', w).strip()
    return w.upper() if st.get('uppercase', True) else w


def groups(words, st):
    """Words -> lines of a few words: a new line after max_words, past
    max_chars, after a pause, at the end of a sentence or a clause."""
    out, cur = [], []
    for s, e, raw, txt in words:
        if cur:
            joined = len(' '.join(x[3] for x in cur) + ' ' + txt)
            prev = cur[-1]
            if (len(cur) >= st['max_words'] or joined > st['max_chars'] or s - prev[1] > 0.45
                    or prev[2].rstrip('"»”)').endswith(SENT_END + CLAUSE_END)):
                out.append(cur)
                cur = []
        cur.append((s, e, raw, txt))
    if cur:
        out.append(cur)
    return out


def caption_events(words, st, x, y):
    """One Dialogue per word: the line it belongs to, the word being said in
    the highlight colour. The line pops in when it appears."""
    ws = [(s, e, raw, display(raw, st)) for s, e, raw in words]
    ws = [w for w in ws if w[3]]
    lines = groups(ws, st)
    hi, base = ass_inline(st['highlight']), ass_inline(st['color'])
    ev = []
    for n, g in enumerate(lines):
        start = g[0][0]
        end = g[-1][1] + 0.5
        if n + 1 < len(lines):
            nxt = lines[n + 1][0][0]
            end = nxt if nxt - g[-1][1] < 0.3 else min(end, nxt)
        for k, (s, e, _raw, _t) in enumerate(g):
            a = start if k == 0 else s
            b = g[k + 1][0] if k + 1 < len(g) else end
            if ass_time(b) <= ass_time(a):
                continue
            text = ' '.join((f'{{\\1c{hi}}}{esc(w[3])}{{\\1c{base}}}' if j == k else esc(w[3]))
                            for j, w in enumerate(g))
            pop = ('\\fscx88\\fscy88\\t(0,90,\\fscx104\\fscy104)\\t(90,150,\\fscx100\\fscy100)'
                   if k == 0 and st.get('pop', True) else '')
            ev.append(f'Dialogue: 1,{ass_time(a)},{ass_time(b)},Caption,,0,0,0,,{{\\an5\\pos({x:.0f},{y:.0f}){pop}}}{text}')
    return ev


def styled(text, st):
    """*word* -> the highlight colour; ' | ' -> a new line."""
    hi, base = ass_inline(st['highlight']), ass_inline(st['color'])
    t = esc(text.upper() if st.get('uppercase') else text)
    t = re.sub(r'\*([^*]+)\*', lambda m: f'{{\\1c{hi}}}{m.group(1)}{{\\1c{base}}}', t)
    return t.replace(' | ', '\\N').replace('|', '\\N')


def build_ass(path, L, words, title, cta, dur, st, title_sec, cta_start):
    """Write the .ass: the subtitles, plus the title (0 -> title_sec) and the end
    card (cta_start -> the end) when they are not drawn by Remotion. Returns
    the number of events."""
    k = L['k']
    font = st.get('font', 'Anton')
    c, t, e = st['captions'], st['title'], st['end_card']
    W, H = L['W'], L['H']
    marg = round(W * 0.08)

    def style(name, s, size, bold, border, outline, shadow, outc, backc):
        return (f'Style: {name},{font},{round(size * k)},{ass_color(s["color"])},{ass_color(s["color"])},'
                f'{outc},{backc},{-1 if bold else 0},0,0,0,100,100,0,0,{border},{round(outline * k)},'
                f'{round(shadow * k)},5,{marg},{marg},0,1')
    head = ['[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {W}', f'PlayResY: {H}', 'WrapStyle: 0',
            'ScaledBorderAndShadow: yes', 'YCbCr Matrix: TV.709', '',
            '[V4+ Styles]',
            'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
            'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, '
            'Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
            style('Caption', c, c['size'], c.get('bold', False), 1, c['outline_width'], c['shadow'],
                  ass_color(c['outline']), '&H80000000'),
            # BorderStyle 3: an opaque box behind each line, in the outline colour
            style('Title', t, t['size'], t.get('bold', False), 3, t.get('padding', 22), 0,
                  ass_color(t['box']), ass_color(t['box'])),
            style('EndCard', e, e['size'], e.get('bold', False), 3, e.get('padding', 26), 0,
                  ass_color(e['box']), ass_color(e['box'])),
            '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    ev = caption_events(words, c, W / 2, L['captions']) if words else []
    if title:
        ev.append(f'Dialogue: 2,{ass_time(0)},{ass_time(title_sec)},Title,,0,0,0,,{{\\an5\\pos({W / 2:.0f},{L["title"]:.0f})'
                  f'\\fad(120,250)\\fscx92\\fscy92\\t(0,160,\\fscx100\\fscy100)}}{styled(title, t)}')
    if cta:
        ev.append(f'Dialogue: 2,{ass_time(cta_start)},{ass_time(dur + 1)},EndCard,,0,0,0,,{{\\an5\\pos({W / 2:.0f},{L["end_card"]:.0f})'
                  f'\\fad(100,0)\\fscx60\\fscy60\\t(0,140,\\fscx108\\fscy108)\\t(140,240,\\fscx100\\fscy100)}}'
                  f'{styled(cta, e)}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(head + ev) + '\n')
    return len(ev)


# --- Remotion: the title and the end card, animated (optional) -----------------------------
def remotion_cli(enabled):
    """(npx, None) when Remotion can draw the cards, else (None, why not)."""
    if not enabled:
        return None, 'remotion is off'
    node, npx = shutil.which('node'), shutil.which('npx')
    if not node or not npx:
        return None, 'Node not found (nodejs.org, 18 or later)'
    try:
        v = subprocess.run([node, '--version'], capture_output=True, text=True, errors='replace').stdout.strip()
        if int(v.lstrip('v').split('.')[0]) < 18:
            return None, f'Node {v} is too old (18 or later)'
    except (OSError, ValueError):
        return None, 'Node does not answer'
    if not os.path.isdir(os.path.join(REMOTION, 'node_modules')):
        npm = shutil.which('npm')
        say('remotion: first use, npm install in remotion/ (about a minute, once)...')
        r = subprocess.run([npm or 'npm', 'install', '--no-audit', '--no-fund'], cwd=REMOTION,
                           capture_output=True, text=True, errors='replace')
        if r.returncode:
            return None, 'npm install failed: ' + (r.stderr or r.stdout).strip()[-300:]
    return npx, None


def remotion_card(npx, work, name, text, kind, part, L, st, seconds, fps):
    """Render one card (title or end card) as a transparent ProRes 4444 clip."""
    font_file = ''
    src = os.path.expanduser(st.get('font_file') or '') or (
        os.path.join(FONTS, 'Anton-Regular.ttf') if st.get('font', 'Anton') == 'Anton' else '')
    if src and os.path.exists(src):
        os.makedirs(os.path.join(REMOTION, 'public', 'fonts'), exist_ok=True)
        font_file = os.path.basename(src)
        shutil.copy(src, os.path.join(REMOTION, 'public', 'fonts', font_file))
    props = {'kind': kind, 'text': text, 'font': st.get('font', 'Anton'), 'fontFile': font_file,
             # a CSS px is bigger than an ASS font size (line height): 0.85 keeps both renders alike
             'size': round(part['size'] * L['k'] * 0.85), 'color': part['color'], 'box': part['box'],
             'highlight': part['highlight'], 'uppercase': bool(part.get('uppercase')),
             'y': L['title' if kind == 'title' else 'end_card'] / L['H'],
             'width': L['W'], 'height': L['H'], 'fps': fps, 'seconds': seconds}
    pf = os.path.join(work, f'{name}.props.json')
    json.dump(props, open(pf, 'w', encoding='utf-8'), ensure_ascii=False)
    out = os.path.join(work, f'{name}.mov')
    r = subprocess.run([npx, 'remotion', 'render', 'src/index.ts', 'Card', out, f'--props={pf}',
                        '--codec=prores', '--prores-profile=4444', '--pixel-format=yuva444p10le',
                        '--image-format=png', '--log=error'], cwd=REMOTION, capture_output=True, text=True, errors='replace')
    if r.returncode or not os.path.exists(out):
        say(f'remotion: the {kind} could not be rendered, ffmpeg draws it instead '
            f'({(r.stderr or r.stdout).strip()[-200:]})')
        return None
    return out


# --- sound --------------------------------------------------------------------------------
def loudness_filter(ff, src, target):
    """Two-pass loudnorm: measure the whole voice, then one linear gain to `target` LUFS."""
    if target is None:
        return None
    r = subprocess.run([ff, '-hide_banner', '-nostats', '-i', src, '-vn', '-af',
                        f'loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'],
                       capture_output=True, text=True, errors='replace')
    m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', r.stderr, re.S)
    if not m:
        return None
    v = json.loads(m.group(0))
    if 'inf' in v['input_i']:
        return None
    return (f'loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={v["input_i"]}:measured_TP={v["input_tp"]}:'
            f'measured_LRA={v["input_lra"]}:measured_thresh={v["input_thresh"]}:offset={v["target_offset"]}:'
            f'linear=true:print_format=none,aresample=48000')


# --- the render -----------------------------------------------------------------------------
def render(ff, cut, out, L, work, ass=None, cards=(), audio_filter=None, font_file=None, dur=None):
    """cut -> out: framed into L, the .ass burned in, the card clips laid over
    (cards = [(clip, start)]). One encode; the sound ends with the picture."""
    W, H = L['W'], L['H']
    if L['fit'] == 'fill':
        g = [f'[0:v]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1[v0]']
    else:
        w4, h4 = W // 4 // 2 * 2, H // 4 // 2 * 2
        g = [f'[0:v]split=2[s1][s2]',
             f'[s1]scale={w4}:{h4}:force_original_aspect_ratio=increase,crop={w4}:{h4},boxblur=10:2,'
             f'scale={W}:{H},eq=brightness=-0.10:saturation=0.85[bg]',
             f'[s2]scale={L["cw"]}:{L["ch"]}:flags=lanczos,setsar=1[fg]',
             f'[bg][fg]overlay=(W-w)/2:{L["top"]},setsar=1[v0]']
    last = 'v0'
    if ass:
        shutil.copytree(FONTS, os.path.join(work, 'fonts'), dirs_exist_ok=True)
        if font_file and os.path.exists(os.path.expanduser(font_file)):
            shutil.copy(os.path.expanduser(font_file), os.path.join(work, 'fonts'))
        g.append(f'[{last}]ass={os.path.basename(ass)}:fontsdir=fonts[v1]')
        last = 'v1'
    inputs = ['-i', cut]
    for n, (clip, start) in enumerate(cards, 1):
        inputs += ['-i', clip]
        g.append(f'[{n}:v]setpts=PTS+{start:.3f}/TB[c{n}]')
        g.append(f'[{last}][c{n}]overlay=0:0:eof_action=pass:format=auto[o{n}]')
        last = f'o{n}'
    g.append(f'[{last}]format=yuv420p[v]')
    trim = f',atrim=end={dur:.6f}' if dur else ''
    g.append(f'[0:a]{audio_filter or "anull"}{trim}[a]')
    fg = os.path.join(work, f'fg-{os.path.basename(out)}.txt')
    open(fg, 'w', encoding='utf-8').write(';\n'.join(g))
    r = subprocess.run([ff, '-hide_banner', '-y', *inputs, '-filter_complex_script', fg,
                        '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
                        '-profile:v', 'high', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out],
                       cwd=work, capture_output=True, text=True, errors='replace')
    if r.returncode:
        sys.exit(f'the final render failed:\n{r.stderr[-1500:]}')
