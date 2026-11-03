"""finish.py — the cut becomes the video you post (edit_video.py calls it).

  - 9:16, 1080x1920, for TikTok, Instagram Reels and YouTube Shorts, in two
    views (the SCENE):
      full   the camera fills the screen (a sideways rush sits in the middle
             on a blurred copy of itself; --fit fill crops it instead);
      split  a flat top zone (the background of the style) over the camera,
             a card with rounded corners on the lower 58 %: the title and the
             boards in the top zone, the subtitles on the seam. A rush filmed
             upright shows the slice of it that starts 7 % down (the head of a
             selfie), a sideways one sits in the card whole, not cropped.
    By default (auto) the video opens in full frame for the hook, then the
    two views take turns at the boundaries between sentences (plan_views);
  - 16:9, 1920x1080, for YouTube (--youtube), when the rush is horizontal:
    full frame;
  - the subtitles burned in, a few words at a time, the word being said lit up;
  - a title on top for the first seconds, an end card (the call to action)
    on the last ones, the boards (a figure, a list, a sentence) on the words
    that say them;
  - the voice evened out toward -14 LUFS (what the platforms play at): one
    linear gain, measured first, that never pushes a peak past -1.5 dBTP.

The subtitles are a .ass file (<video>.ass, plain text: a word can be fixed in
it by hand) burned in by ffmpeg's libass. With Node 18+ and the remotion/
folder, Remotion draws the title, the end card and the boards (animated) in
one transparent clip laid over the video; without Node the .ass draws them
too, and the video comes out all the same. Their look comes from style.json:
the one next to scripts/, then ~/.config/video-editing/style.json, then
--style FILE, each one saying only what it changes. The geometry of the split
is fixed (SEAM, CARD_*, SOURCE_TOP below): fitting it to one's own framing is
the paid version.
"""
import json, math, os, re, shutil, struct, subprocess, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
STYLE = os.path.join(SKILL, 'style.json')
FONTS = os.path.join(SKILL, 'fonts')
REMOTION = os.path.join(SKILL, 'remotion')
FONT_FILES = {'Inter ExtraBold': 'Inter-ExtraBold.ttf', 'Anton': 'Anton-Regular.ttf'}   # shipped in fonts/

# The end card when the user gave none (--cta), in the language of the video.
CTA = {'fr': 'Abonne-toi pour la suite', 'en': 'Follow for more', 'es': 'Sígueme para más',
       'de': 'Folge mir für mehr', 'it': 'Seguimi per altri video', 'pt': 'Me segue para mais'}

# THE SPLIT, fixed (on the 1080x1920 frame): the seam at 42 % of the height, the camera card under
# it, 24 px from the edges, corners rounded at 36 px. An upright rush shows its slice that starts 7 %
# down: the head of a selfie held at arm's length, chin included on a close framing.
SEAM, CARD_INSET, CARD_RADIUS, SOURCE_TOP = 0.42, 24, 36, 0.07
SAFE_TOP = 0.07            # the top bar of TikTok and Instagram: nothing drawn above
# THE TURNS (scene auto): full frame for the hook, at least HOOK_MIN s (up to the first sentence
# that ends after it), then a view lasts from RUN_MIN to RUN_MAX s, switching between two sentences,
# never shorter than VIEW_MIN s.
HOOK_MIN, RUN_MIN, RUN_MAX, VIEW_MIN = 3.0, 4.0, 8.0, 2.0
BOARD_MIN, BOARD_HOLD = 2.5, 8.0   # a board stays to the end of the sentence that says it (BOARD_MIN s at
                                  # least), never past the next board, BOARD_HOLD s at most
BOARD_KINDS = ('text', 'stat', 'list')
SENT_END = ('.', '!', '?', '…')
CLAUSE_END = (',', ';', ':')


def say(msg):
    print(msg, file=sys.stderr)


def even(x):
    return int(round(x / 2)) * 2


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
                merge(st, json.load(open(p, encoding='utf-8-sig')))     # -sig: saved by Notepad
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
def split_geometry(src_w, src_h, W=1080, H=1920):
    """The split on a W x H frame: the seam, the camera card (x, y, w, h), and how the rush
    fills it (scale, then crop). Upright: a slice of the rush, the card down to the bottom;
    sideways (or square): the whole rush at the card's width, under the seam."""
    seam = even(H * SEAM)
    x, w = CARD_INSET, W - 2 * CARD_INSET
    sh = even(w * src_h / src_w)                               # the rush at the card's width
    h = H - CARD_INSET - seam
    if src_h > src_w and sh >= h:
        top = max(0, min(even(sh * SOURCE_TOP), sh - h))
        return {'seam': seam, 'x': x, 'y': seam, 'w': w, 'h': h, 'scale': (w, sh), 'crop': (w, h, 0, top)}
    return {'seam': seam, 'x': x, 'y': seam, 'w': w, 'h': min(sh, h), 'scale': (w, sh),
            'crop': (w, min(sh, h), 0, 0) if sh > h else None}


def layout(src_w, src_h, wide, fit, st):
    """The frame (W x H), how the video sits in it in each view, and the height of the
    centre of each text: L['y'][view][part]."""
    W, H = (1920, 1080) if wide else (1080, 1920)
    if fit == 'auto':
        fit = 'fill' if (src_h >= src_w) == (H >= W) else 'frame'
    L = {'W': W, 'H': H, 'fit': fit, 'k': st.get('wide_scale', 0.72) if wide else 1.0, 'wide': wide}
    key = 'y_wide' if wide else 'y'
    full = {part: st[part].get(key, st[part]['y']) * H for part in ('captions', 'title', 'end_card')}
    if fit == 'frame':
        cw, ch = W, round(W * src_h / src_w / 2) * 2
        if ch > H:
            cw, ch = round(H * src_w / src_h / 2) * 2, H
        top = (H - ch) // 2
        L.update(cw=cw, ch=ch, top=top)
        if ch < H * 0.8:                       # room above and below the card: text goes there
            full['title'] = full['end_card'] = top * 0.62
            full['captions'] = top + ch + (H - top - ch) * 0.32
    full['board'] = full['title']
    L['y'] = {'full': full}
    if not wide:
        g = split_geometry(src_w, src_h, W, H)
        L['split'] = g
        zone = (H * SAFE_TOP + g['seam'] - 0.06 * H) / 2         # the middle of the top zone, above the subtitles
        L['y']['split'] = {'captions': g['seam'], 'title': zone, 'end_card': zone, 'board': zone}
    return L


# --- the views: full frame and split, in turns ---------------------------------------
def sentences(words):
    """[(start, end)] of each sentence: it ends on . ! ? … or before a pause of 0.6 s."""
    out, cur = [], None
    for n, (s, e, w) in enumerate(words):
        cur = (cur[0], e) if cur else (s, e)
        nxt = words[n + 1] if n + 1 < len(words) else None
        if not nxt or nxt[0] - e > 0.6 or w.rstrip('"»”)').endswith(('.', '!', '?', '…')):
            out.append(cur)
            cur = None
    return out


def resolve_boards(boards, words, dur):
    """boards.json -> [{at, end, text, kind}], sorted. A board is placed by `at` (s of the
    edited video) or by `say` (the words that say it, the first time after the previous board)."""
    def n(x):
        return re.sub(r'[^\w]+', '', x.lower())
    out, after = [], 0.0
    for b in boards:
        text, kind = str(b.get('text', '')).strip(), b.get('kind', 'text')
        if not text:
            continue
        if kind not in BOARD_KINDS:
            sys.exit(f'boards: kind "{kind}" unknown (text, stat or list)')
        at = b.get('at')
        if at is None and b.get('say'):
            want = [n(x) for x in str(b['say']).split() if n(x)]
            for i in range(len(words)):
                if words[i][0] >= after - 0.01 and [n(w[2]) for w in words[i:i + len(want)]] == want:
                    at = words[i][0]
                    break
            if at is None:
                say(f'board "{text}": the words "{b["say"]}" are not said after {after:.1f}s, left out')
                continue
        if at is None or not 0 <= float(at) < dur:
            say(f'board "{text}": no time in the video (at {at}), left out')
            continue
        out.append({'at': round(float(at), 3), 'text': text, 'kind': kind, 'until': b.get('until')})
        after = float(at)
    out.sort(key=lambda x: x['at'])
    ends = [e for _s, e in sentences(words)]
    for i, b in enumerate(out):
        nxt = out[i + 1]['at'] if i + 1 < len(out) else dur
        if b.get('until'):
            end = float(b['until'])
        else:                                  # to the end of its sentence, BOARD_MIN s at least
            end = next((e + 0.3 for e in ends if e + 0.3 >= b['at'] + BOARD_MIN), dur)
        b['end'] = round(max(b['at'] + 0.5, min(end, nxt, b['at'] + BOARD_HOLD, dur)), 3)
        del b['until']
    return out


def soft_bounds(words, sents, joins):
    """Where a view may change inside a sentence longer than RUN_MAX s (whisper often writes no
    full stop): after a comma, or at a join of the cut (a pause that was taken out), never closer
    than RUN_MIN / 2 s to the ends of the sentence."""
    out = []
    for a, b in sents:
        if b - a <= RUN_MAX:
            continue
        cand = [round((w[1] + words[n + 1][0]) / 2, 3) for n, w in enumerate(words[:-1])
                if a <= w[1] < b and w[2].rstrip('"»”)').endswith(CLAUSE_END)]
        cand += [j for j in joins if a < j < b]
        last = a
        for c in sorted(set(cand)):
            if c - last >= RUN_MIN / 2 and b - c >= RUN_MIN / 2:
                out.append(c)
                last = c
    return out


def plan_views(words, dur, mode, boards, has_header, cta_start, joins=()):
    """[(start, end, 'full' | 'split')] covering the video. auto: full frame for the hook (up to
    the first sentence end past HOOK_MIN s); then a sentence with a board on it is split, the others
    full frame; a full-frame run longer than RUN_MAX s turns split (the title at the top) at the next
    sentence, a split run longer than RUN_MAX s turns full frame (the board, if any, over the camera);
    without boards the two take turns every RUN_MIN to RUN_MAX s. A split needs
    something at the top (a board, or the title): with neither, full frame only. Views only change
    between two sentences (inside one longer than RUN_MAX s: after a comma, or where a pause was
    cut, `soft_bounds`), never once the end card is up."""
    if mode in ('full', 'split'):
        return [(0.0, dur, mode)]
    sents = sentences(words)
    bounds = [round((a[1] + b[0]) / 2, 3) for a, b in zip(sents, sents[1:])]
    bounds = sorted(bounds + soft_bounds(words, sents, joins))
    bounds = [b for b in bounds if b < cta_start - 0.3]
    hook = next((b for b in bounds if b >= HOOK_MIN), None)
    if hook is None or not (boards or has_header):
        return [(0.0, dur, 'full')]
    cuts = [hook] + [b for b in bounds if b > hook] + [dur]
    views, cur, run = [(0.0, hook, 'full')], 'full', hook
    place = {}                                 # board -> the view it is shown in, decided when it comes up
    for a, b in zip(cuts, cuts[1:]):
        here = [i for i, x in enumerate(boards) if x['at'] < b - 0.6 and x['end'] > a + 0.6]   # on it for real
        for i in here:
            if i not in place:                 # after RUN_MAX s of split, a new board goes over the camera
                place[i] = 'full' if cur == 'split' and run + max(0.0, boards[i]['at'] - a) >= RUN_MAX else 'split'
        if boards:
            if any(place[i] == 'split' for i in here):
                v = 'split'
            elif here:
                v = 'full'
            elif has_header and ((cur == 'split' and run < RUN_MIN) or (cur == 'full' and run >= RUN_MAX)):
                v = 'split'                    # the title at the top: a short split held, a long full frame broken
            else:
                v = 'full'
        else:
            v = cur if run < RUN_MIN else ('split' if cur == 'full' else 'full')
        if v == cur:
            run += b - a
            views[-1] = (views[-1][0], b, v)
        else:
            views.append((a, b, v))
            cur, run = v, b - a
    out = [views[0]]                           # a view shorter than VIEW_MIN s would flash: it joins the one before
    for a, b, v in views[1:]:
        if b - a < VIEW_MIN or v == out[-1][2]:
            out[-1] = (out[-1][0], b, out[-1][2])
        else:
            out.append((a, b, v))
    return out


def view_at(views, t):
    for a, b, v in views:
        if a <= t < b:
            return v
    return views[-1][2]


def overlay_items(L, st, views, title, title_sec, cta, cta_start, dur, boards):
    """What is drawn over the video, besides the subtitles: [{kind, start, end, text, y, size,
    colours...}], cut to the views. Full frame: the title over the camera for its first seconds,
    the end card. Split: the boards, the title kept at the top between them, the end card."""
    items, sp = [], st.get('split', {})
    T, E, B = st['title'], st['end_card'], st.get('boards', {})
    k = L['k']

    def add(kind, a, b, text, view, board=None):
        # a board that would only flash across a change of view (less than 1.2 s over the camera,
        # 0.6 s at the top) waits for the next view instead
        shortest = (1.2 if view == 'full' else 0.6) if kind == 'board' else 0.05
        if b - a < shortest or not text:
            return
        y = L['y'][view]['board' if kind in ('board', 'header') else 'title' if kind == 'title' else 'end_card']
        if kind == 'end':
            part = {'size': E['size'] * (1.25 if view == 'split' else 1), 'color': E['color'], 'box': E['box'],
                    'highlight': E['highlight'], 'uppercase': E.get('uppercase', False)}
        elif view == 'full':
            part = {'size': T['size'], 'color': T['color'], 'box': T['box'], 'highlight': T['highlight'],
                    'uppercase': T.get('uppercase', False)}
        elif view == 'full' and kind == 'board':
            part = {'size': B.get('size', T['size']) * 0.8, 'color': T['color'], 'box': T['box'],
                    'highlight': T['highlight'], 'uppercase': T.get('uppercase', False)}
        else:                                  # on the flat top zone: no box
            part = {'size': B.get('size', T['size']) if kind == 'board' else sp.get('title_size', T['size']),
                    'color': sp.get('text', '#FFFFFF'), 'box': '', 'highlight': sp.get('highlight', T['highlight']),
                    'uppercase': T.get('uppercase', False)}
        items.append({'kind': kind, 'board': board, 'start': round(a, 3), 'end': round(b, 3), 'text': text,
                      'y': round(y), 'size': round(part['size'] * k), 'color': part['color'], 'box': part['box'],
                      'highlight': part['highlight'], 'muted': B.get('muted', '#9AA1AD'),
                      'uppercase': bool(part['uppercase'])})

    for a, b, v in views:
        top_end = min(b, cta_start) if cta else b
        if v == 'full' and title:
            add('title', a, min(top_end, title_sec), title, v)
        if v == 'full':                        # a board over the camera (the hook, --scene full): in a box
            for x in boards:
                if x['end'] > a and x['at'] < top_end:
                    add('board', max(x['at'], a, title_sec if title else 0), min(x['end'], top_end), x['text'], v, x['kind'])
        if v == 'split' and not L['wide']:
            t = a
            for x in boards:
                if x['end'] <= a or x['at'] >= top_end:
                    continue
                s, e = max(x['at'], a), min(x['end'], top_end)
                if e - s < 0.6:
                    continue
                if title and s - t >= 0.6:
                    add('header', t, s, title, v)
                add('board', s, e, x['text'], v, x['kind'])
                t = e
            if title and top_end - t >= 0.6:
                add('header', t, top_end, title, v)
        if cta and b > cta_start:
            add('end', max(a, cta_start), dur + 1, cta, v)
    return items


# --- the .ass -----------------------------------------------------------------------------


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


def caption_events(words, st, x, ys, views):
    """One Dialogue per word: the line it belongs to, the word being said in
    the highlight colour. The line pops in when it appears, at the height of the
    view it starts in (ys[view]), and never outlives that view."""
    ws = [(s, e, raw, display(raw, st)) for s, e, raw in words]
    ws = [w for w in ws if w[3]]
    lines = groups(ws, st)
    hi, base = ass_inline(st['highlight']), ass_inline(st['color'])
    switches = [a for a, _b, _v in views[1:]]
    ev = []
    for n, g in enumerate(lines):
        start = g[0][0]
        end = g[-1][1] + 0.5
        if n + 1 < len(lines):
            nxt = lines[n + 1][0][0]
            end = nxt if nxt - g[-1][1] < 0.3 else min(end, nxt)
        end = min([end] + [s for s in switches if s > start + 0.05])
        y = ys[view_at(views, start)]
        for k, (s, e, _raw, _t) in enumerate(g):
            a = start if k == 0 else s
            b = g[k + 1][0] if k + 1 < len(g) else end
            b = min(b, end)
            if ass_time(b) <= ass_time(a):
                continue
            text = ' '.join((f'{{\\1c{hi}}}{esc(w[3])}{{\\1c{base}}}' if j == k else esc(w[3]))
                            for j, w in enumerate(g))
            pop = ('\\fscx88\\fscy88\\t(0,90,\\fscx104\\fscy104)\\t(90,150,\\fscx100\\fscy100)'
                   if k == 0 and st.get('pop', True) else '')
            ev.append(f'Dialogue: 1,{ass_time(a)},{ass_time(b)},Caption,,0,0,0,,{{\\an5\\pos({x:.0f},{y:.0f}){pop}}}{text}')
    return ev


def styled(text, color, highlight, uppercase=False):
    """*word* -> the highlight colour; ' | ' -> a new line."""
    hi, base = ass_inline(highlight), ass_inline(color)
    t = esc(text.upper() if uppercase else text)
    t = re.sub(r' ([:;!?»])', r'\\h\1', t).replace('« ', '«\\h')     # French spacing: never broken
    t = re.sub(r'\*([^*]+)\*', lambda m: f'{{\\1c{hi}}}{m.group(1)}{{\\1c{base}}}', t)
    return t.replace(' | ', '\\N').replace('|', '\\N')


def item_event(it, W):
    """An overlay item drawn by libass instead of Remotion (no Node): a box behind each line when
    the item has one (style Box), plain text on the split's top zone (style Plain)."""
    pos = f'\\an5\\pos({W / 2:.0f},{it["y"]:.0f})\\fs{it["size"]}'
    anim = ('\\fad(100,0)\\fscx60\\fscy60\\t(0,140,\\fscx108\\fscy108)\\t(140,240,\\fscx100\\fscy100)'
            if it['kind'] == 'end' else '\\fad(120,200)\\fscx92\\fscy92\\t(0,160,\\fscx100\\fscy100)')
    box = f'\\3c{ass_inline(it["box"])}' if it['box'] else ''
    if it['kind'] == 'board' and it['board'] == 'stat':
        parts = it['text'].split('|')
        big = styled(parts[0].strip(), it['highlight'], it['highlight'], it['uppercase'])
        rest = '\\N'.join(styled(x.strip(), it['muted'], it['highlight'], it['uppercase']) for x in parts[1:])
        text = f'{{\\fs{round(it["size"] * 1.9)}\\1c{ass_inline(it["highlight"])}}}{big}' + (f'\\N{{\\fs{round(it["size"] * 0.62)}\\1c{ass_inline(it["muted"])}}}{rest}' if rest else '')
    elif it['kind'] == 'board' and it['board'] == 'list':
        text = '\\N'.join(f'{{\\1c{ass_inline(it["highlight"])}}}{i}  {{\\1c{ass_inline(it["color"])}}}'
                          + styled(x.strip(), it['color'], it['highlight'], it['uppercase'])
                          for i, x in enumerate((p for p in it['text'].split('|') if p.strip()), 1))
        pos += f'\\fs{round(it["size"] * 0.78)}'
    else:
        text = styled(it['text'], it['color'], it['highlight'], it['uppercase'])
    return (f'Dialogue: 2,{ass_time(it["start"])},{ass_time(it["end"])},{"Box" if it["box"] else "Plain"},,0,0,0,,'
            f'{{{pos}{box}\\1c{ass_inline(it["color"])}{anim}}}{text}')


def build_ass(path, L, words, items, st, views):
    """Write the .ass: the subtitles, plus the overlay items (title, boards, end card) when
    Remotion does not draw them. Returns the number of events."""
    k = L['k']
    font = st.get('font', 'Inter ExtraBold')
    c = st['captions']
    W, H = L['W'], L['H']
    marg = round(W * 0.08)

    def style(name, color, size, bold, border, outline, shadow, outc, backc):
        return (f'Style: {name},{font},{round(size * k)},{ass_color(color)},{ass_color(color)},'
                f'{outc},{backc},{-1 if bold else 0},0,0,0,100,100,0,0,{border},{round(outline * k)},'
                f'{round(shadow * k)},5,{marg},{marg},0,1')
    head = ['[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {W}', f'PlayResY: {H}', 'WrapStyle: 0',
            'ScaledBorderAndShadow: yes', 'YCbCr Matrix: TV.709', '',
            '[V4+ Styles]',
            'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
            'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, '
            'Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
            style('Caption', c['color'], c['size'], c.get('bold', False), 1, c['outline_width'], c['shadow'],
                  ass_color(c['outline']), '&H80000000'),
            # BorderStyle 3: an opaque box behind each line, in the outline colour (set per event)
            style('Box', '#000000', 90, False, 3, 22, 0, '&H00FFFFFF', '&H00FFFFFF'),
            style('Plain', '#FFFFFF', 90, False, 1, 0, 0, '&H00000000', '&H00000000'),
            '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    ys = {v: L['y'][v]['captions'] for v in L['y']}
    ev = caption_events(words, c, W / 2, ys, views) if words else []
    ev += [item_event(it, W) for it in items]
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(head + ev) + '\n')
    return len(ev)


# --- Remotion: the title, the boards, the end card, animated (optional) --------------------
def remotion_cli(enabled):
    """(the command that runs the Remotion CLI, None) when Remotion can draw the overlay, else
    (None, why not). node runs the CLI itself, not npx: on Windows npx is a .cmd, run through
    cmd.exe, which reads %, ^ and & in the paths its own way."""
    if not enabled:
        return None, 'remotion is off'
    node = shutil.which('node')
    if not node:
        return None, 'Node not found (nodejs.org, 18 or later)'
    try:
        v = subprocess.run([node, '--version'], capture_output=True, text=True, errors='replace').stdout.strip()
        if int(v.lstrip('v').split('.')[0]) < 18:
            return None, f'Node {v} is too old (18 or later)'
    except (OSError, ValueError):
        return None, 'Node does not answer'
    cli = os.path.join(REMOTION, 'node_modules', '@remotion', 'cli', 'remotion-cli.js')
    if not os.path.exists(cli):
        npm = shutil.which('npm')                   # npm.cmd on Windows: a fixed command line, nothing to mangle
        if not npm:
            return None, 'npm not found (it comes with Node)'
        say('remotion: first use, npm install in remotion/ (about a minute, once)...')
        try:
            r = subprocess.run([npm, 'install', '--no-audit', '--no-fund'], cwd=REMOTION,
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
        except OSError as e:
            return None, f'npm install failed: {e}'
        if r.returncode or not os.path.exists(cli):
            return None, 'npm install failed: ' + (r.stderr or r.stdout).strip()[-300:]
    return [node, cli], None


def font_file_of(st):
    """The font file for Remotion and libass: style font_file, else the shipped one for the font."""
    src = os.path.expanduser(st.get('font_file') or '')
    if not src and st.get('font') in FONT_FILES:
        src = os.path.join(FONTS, FONT_FILES[st['font']])
    return src if src and os.path.exists(src) else ''


def remotion_overlay(cli, work, name, items, L, st, seconds, fps):
    """Render every overlay item, the whole length of the video, as one transparent ProRes 4444
    clip (it starts at 0). None when it fails: the .ass draws them instead."""
    font_file = ''
    src = font_file_of(st)
    if src:
        os.makedirs(os.path.join(REMOTION, 'public', 'fonts'), exist_ok=True)
        font_file = os.path.basename(src)
        shutil.copy(src, os.path.join(REMOTION, 'public', 'fonts', font_file))
    props = {'font': st.get('font', 'Inter ExtraBold'), 'fontFile': font_file, 'width': L['W'], 'height': L['H'],
             'fps': fps, 'seconds': seconds,
             # a CSS px is bigger than an ASS font size (line height): 0.85 keeps both renders alike
             'items': [dict(it, size=round(it['size'] * 0.85)) for it in items]}
    pf = os.path.join(work, f'{name}.props.json')
    json.dump(props, open(pf, 'w', encoding='utf-8'), ensure_ascii=False)
    out = os.path.join(work, f'{name}.mov')
    r = subprocess.run([*cli, 'render', 'src/index.ts', 'Overlay', out, f'--props={pf}',
                        '--codec=prores', '--prores-profile=4444', '--pixel-format=yuva444p10le',
                        '--image-format=png', '--log=error'], cwd=REMOTION, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if r.returncode or not os.path.exists(out):
        say(f'remotion: the overlay could not be rendered, ffmpeg draws it instead '
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


# --- the split's frame: the background with the card cut out, as a PNG ---------------------
def card_frame_png(path, W, H, g, color):
    """W x H RGBA: the background colour everywhere but inside the camera card (rounded
    corners, antialiased), which is transparent. Standard library only (zlib)."""
    c = color.lstrip('#')
    r_, g_, b_ = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    x0, y0, x1, y1, rad = g['x'], g['y'], g['x'] + g['w'], g['y'] + g['h'], CARD_RADIUS
    solid = bytes((r_, g_, b_, 255))
    rows = []
    for y in range(H):
        if y < y0 or y >= y1:
            rows.append(b'\x00' + solid * W)
            continue
        dy = max(0.0, (y0 + rad) - (y + 0.5), (y + 0.5) - (y1 - rad))
        if dy <= 0:                                            # straight sides: a clean cut
            rows.append(b'\x00' + solid * x0 + b'\x00\x00\x00\x00' * (x1 - x0) + solid * (W - x1))
            continue
        half = math.sqrt(max(0.0, rad * rad - dy * dy))        # inside the arc: x from x0 + rad - half
        left = x0 + rad - half
        row = bytearray(solid * W)
        for x in range(x0, x1):
            cx = x + 0.5
            d = min(cx - left, (x1 - rad + half) - cx)         # distance to the edge, px
            a = 0 if d >= 0.5 else 255 if d <= -0.5 else round(255 * (0.5 - d))
            row[4 * x + 3] = a
        rows.append(b'\x00' + bytes(row))
    raw = zlib.compress(b''.join(rows), 6)

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 6, 0, 0, 0))
                + chunk(b'IDAT', raw) + chunk(b'IEND', b''))
    return path


# --- the render -----------------------------------------------------------------------------
def render(ff, cut, out, L, work, views, st, ass=None, cards=(), audio_filter=None, font_file=None, dur=None):
    """cut -> out: each view composed (full frame, split), the split shown over the full frame
    during its turns, the .ass burned in, the overlay clips laid over (cards = [(clip, start)]).
    One encode; the sound ends with the picture."""
    W, H = L['W'], L['H']
    used = {v for _a, _b, v in views}
    inputs, g = ['-i', cut], []
    if 'full' in used:
        g.append('[0:v]split=2[f0][s0]' if 'split' in used else '[0:v]null[f0]')
        if L['fit'] == 'fill':
            g.append(f'[f0]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1[full]')
        else:
            w4, h4 = W // 4 // 2 * 2, H // 4 // 2 * 2
            g += [f'[f0]split=2[f1][f2]',
                  f'[f1]scale={w4}:{h4}:force_original_aspect_ratio=increase,crop={w4}:{h4},boxblur=10:2,'
                  f'scale={W}:{H},eq=brightness=-0.10:saturation=0.85[bg]',
                  f'[f2]scale={L["cw"]}:{L["ch"]}:flags=lanczos,setsar=1[fg]',
                  f'[bg][fg]overlay=(W-w)/2:{L["top"]},setsar=1[full]']
    else:
        g.append('[0:v]null[s0]')
    if 'split' in used:
        sg = L['split']
        frame = card_frame_png(os.path.join(work, f'split-{W}x{H}.png'), W, H, sg,
                               st.get('split', {}).get('background', '#17181C'))
        inputs += ['-loop', '1', '-framerate', str(round(L.get('fps', 30), 3)), '-t', f'{dur or 36000:.3f}', '-i', frame]
        crop = ',crop={}:{}:{}:{}'.format(*sg['crop']) if sg['crop'] else ''
        g += [f'[s0]scale={sg["scale"][0]}:{sg["scale"][1]}:flags=lanczos{crop},setsar=1,'
              f'pad={W}:{H}:{sg["x"]}:{sg["y"]}:black[cam]',
              '[cam][1:v]overlay=0:0:shortest=1,setsar=1[split]']
    if used == {'split'}:
        last = 'split'
    elif used == {'full'}:
        last = 'full'
    else:
        when = '+'.join(f'between(t,{a:.3f},{b - 0.001:.3f})' for a, b, v in views if v == 'split')
        g.append(f"[full][split]overlay=0:0:enable='{when}'[v0]")
        last = 'v0'
    if ass:
        shutil.copytree(FONTS, os.path.join(work, 'fonts'), dirs_exist_ok=True)
        if font_file and os.path.exists(os.path.expanduser(font_file)):
            shutil.copy(os.path.expanduser(font_file), os.path.join(work, 'fonts'))
        g.append(f'[{last}]ass={os.path.basename(ass)}:fontsdir=fonts[v1]')
        last = 'v1'
    first = len(inputs) // 2 if 'split' not in used else 2
    for n, (clip, start) in enumerate(cards):
        inputs += ['-i', clip]
        i = first + n
        g.append(f'[{i}:v]setpts=PTS+{start:.3f}/TB[c{n}]')
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
                       cwd=work, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        sys.exit(f'the final render failed:\n{r.stderr[-1500:]}')
