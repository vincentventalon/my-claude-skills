#!/usr/bin/env python3
"""sync_from_private.py — carry the editing improvements of a private editing
pipeline over to this public skill, then test. For the maintainer only: the
skill itself never runs this.

The private pipeline is a Claude Code skill in another git repo. Its path is
never written here: pass it in the PRIVATE_SKILL environment variable (or
--private).

    export PRIVATE_SKILL=/path/to/private/skills/tiktok-edit

    python dev/edit/sync_from_private.py status       # 1. what changed in the private code that travels
    #  -> hand the printed diff file to Claude: "port what is worth it into
    #     skills/short-video/edit/scripts/ (rules below)"
    python dev/edit/sync_from_private.py test RUSH.MP4 --lang fr    # 2. real test, old vs new
    python dev/edit/test_stt.py                         #    the Scribe path, no network
    python dev/edit/sync_from_private.py mark          # 3. once ported: remember where we are

Porting rules (the reason this is not a copy):
  - WHAT TRAVELS: everything that turns raw clips into a finished video —
    the cut (islands, transcription per island, retakes, joins, sync),
    the two transcription engines and their one contract (whisper.cpp
    local, ElevenLabs Scribe with the user's own key: stt.py), the
    subtitles burned in (finish.py, style.json), the title, the end card,
    the 9:16 / 16:9 framing, the loudness;
  - WHAT STAYS OUT (paid, https://pifpafcut.com/pro): the review page and
    the audio check in the browser (no scripts/review.*, no edits.json),
    the measured scenes, the motion, the b-roll, the covers, the
    publishing (the skill only says the video is scheduled with Nadia);
  - the scripts stay Python 3.10+ standard library only (urllib for
    Scribe), ffmpeg + whisper.cpp, macOS first, Windows / Linux when it
    costs nothing; Node + Remotion only as an option (without Node the
    video comes out all the same); no key in the repo, no `claude -p`, no
    personal path, no name of a person or an account;
  - the settings file ~/.config/video-editing/config.json is a contract
    with the `setup` skill: its keys (stt, whisper_model, ffmpeg, lang,
    output_dir, subtitles, remotion) do not change name;
  - no interface: Claude applies the user's changes from the terminal
    (--cut / --protect / --fix / --title / --cta);
  - every change is tested on a real rush with `test` (and the Scribe path
    with dev/test_stt.py) before it is kept.

`test` renders the rush twice in a temporary folder (the public script at
--against, default `main`, and the working copy), runs dev/check_edit.py on
both cuts and prints them side by side: duration, A/V desync, words cut at
the joins, repeats left. Nothing is committed and nothing is pushed: the last
line prints the commands to do it by hand.
"""
import argparse, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))           # the repo root (this file: dev/edit/)
SKILL = os.path.join(REPO, 'skills', 'short-video', 'edit')
STATE = os.path.join(HERE, 'private-sync.txt')          # last private commit carried over
WATCHED = ['scripts/salves.py', 'scripts/jump_cuts.py', 'scripts/align.py',
           'scripts/postflight.py', 'references/coupes.md',          # the cut
           'scripts/stt.py', 'scripts/make_ass.py']                   # the two engines, the subtitles
# what must never reach the public repo
LEAKS = ['/Users/', '/home/', 'cockpit', 'pifpafpoum', 'claude -p', 'openai', 'treg', 'metricool',
         'review.py', 'review.html', 'edits.json',   # the review page is not part of this skill
         'sk_', 'xi-api-key: ']                      # a key written down
ALLOWED = ['pifpafcut.com/pro']                      # the one link to the paid version

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('cmd', choices=['status', 'test', 'mark'])
ap.add_argument('rush', nargs='*', help='test: the rush(es) to cut')
ap.add_argument('--private', default=os.environ.get('PRIVATE_SKILL'),
                help='the private skill folder (default: $PRIVATE_SKILL)')
ap.add_argument('--lang', default='fr')
ap.add_argument('--model', default=os.environ.get('WHISPER_MODEL', 'large-v3-turbo'),
                help='whisper model name or ggml-*.bin path (default: $WHISPER_MODEL or large-v3-turbo)')
ap.add_argument('--against', default='main', help='test: git ref to compare with (main)')
ap.add_argument('--out', help='test: folder for the renders (default: a new temp folder)')
args = ap.parse_args()


def git(*a, cwd=REPO, check=True):
    return subprocess.run(['git', *a], cwd=cwd, capture_output=True, text=True, check=check).stdout


def leak_check():
    bad = []
    scope = ['skills/short-video/edit', 'dev/edit']                    # what a sync touches (the other skills have their own rules)
    for f in (git('ls-files', '--', *scope).split()
              + git('ls-files', '--others', '--exclude-standard', '--', *scope).split()):
        if f.startswith('dev/edit/private-sync') or f == 'dev/edit/sync_from_private.py':
            continue
        p = os.path.join(REPO, f)
        try:
            txt = open(p, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(txt.splitlines(), 1):
            low = line.lower()
            for w in LEAKS:
                if w.lower() in low:
                    bad.append(f'{f}:{n}: "{w}" -> {line.strip()[:90]}')
            if low.count('pifpafcut') > sum(low.count(x) for x in ALLOWED):
                bad.append(f'{f}:{n}: "pifpafcut" -> {line.strip()[:90]}')
    print('leak check: ' + ('clean' if not bad else f'{len(bad)} line(s) to look at'))
    for b in bad:
        print('  ' + b)


def need_private():
    if not args.private or not os.path.isdir(args.private):
        sys.exit('set PRIVATE_SKILL (or --private) to the private skill folder')
    return os.path.abspath(args.private)


if args.cmd == 'status':
    priv = need_private()
    head = git('rev-parse', 'HEAD', cwd=priv).strip()
    last = open(STATE).read().split()[0] if os.path.exists(STATE) else None
    print(f'private HEAD {head[:10]}   last carried over: {last[:10] if last else "never"}')
    if not last:
        print('never synced: read these files whole, port, then `mark`:')
        print(''.join(f'  {os.path.join(priv, w)}\n' for w in WATCHED))
        leak_check()
        sys.exit()
    log = git('log', '--format=%h %ad %s', '--date=short', f'{last}..{head}', '--', *WATCHED, cwd=priv)
    if not log.strip():
        print('nothing new in the cutting code since the last sync.')
    else:
        print('commits touching the cut:\n' + ''.join('  ' + l + '\n' for l in log.splitlines()))
        print(git('diff', '--stat', last, head, '--', *WATCHED, cwd=priv, check=False))
        diff = git('diff', last, head, '--', *WATCHED, cwd=priv, check=False)
        fd, path = tempfile.mkstemp(prefix='private-cut-', suffix='.diff')
        os.write(fd, diff.encode())
        os.close(fd)
        print(f'full diff: {path}')
        print('next: ask Claude in this repo — "read that diff and port into skills/short-video/edit/scripts/ '
              'what travels (the cut, the two engines, the subtitles), following the rules at the top of '
              'dev/edit/sync_from_private.py", then run `test` and dev/edit/test_stt.py.')
    leak_check()

elif args.cmd == 'test':
    if not args.rush:
        sys.exit('test: give the rush(es) to cut')
    out = os.path.abspath(args.out) if args.out else tempfile.mkdtemp(prefix='sync-test-')
    os.makedirs(out, exist_ok=True)
    # where edit_video.py lived at that ref: today, then inside the old video-editing plugin
    # (until 2.0.0), then at the root (before the collection)
    for where in ('skills/short-video/edit/scripts/edit_video.py', 'video-editing/skills/video-editing/scripts/edit_video.py',
                  'scripts/edit_video.py'):
        if subprocess.run(['git', 'cat-file', '-e', f'{args.against}:{where}'], cwd=REPO).returncode == 0:
            break
    else:
        sys.exit(f'test: no edit_video.py at {args.against}')
    # the whole skill at that ref (its modules, style.json, fonts, remotion), not the script alone
    import io, tarfile
    tree = os.path.join(out, 'old-tree')
    skill_dir = os.path.dirname(os.path.dirname(where)) or '.'
    tar = subprocess.run(['git', 'archive', args.against, skill_dir if skill_dir != '.' else 'scripts'],
                         cwd=REPO, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(tree, **({'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}))
    nm, nm_old = os.path.join(SKILL, 'remotion', 'node_modules'), os.path.join(tree, skill_dir, 'remotion', 'node_modules')
    if os.path.isdir(nm) and os.path.isdir(os.path.dirname(nm_old)) and not os.path.exists(nm_old):
        os.symlink(nm, nm_old)                    # Remotion's packages are installed, never in git
    old = os.path.join(tree, where)
    new = os.path.join(SKILL, 'scripts', 'edit_video.py')
    model = args.model if os.path.exists(args.model) else os.path.join(
        os.path.expanduser('~'), '.cache', 'whisper-cpp', f'ggml-{args.model}.bin')
    rushes = [os.path.abspath(r) for r in args.rush]
    for tag, script in (('old', old), ('new', new)):
        video, segs = os.path.join(out, f'{tag}.mp4'), os.path.join(out, f'{tag}.segments.tsv')
        print(f'=== {tag}: {os.path.relpath(script, REPO) if tag == "new" else args.against}', flush=True)
        env = dict(os.environ, EDIT_VIDEO_SEGMENTS=segs)
        r = subprocess.run([sys.executable, script, *rushes, '-o', video, '--lang', args.lang,
                            '--model', args.model], env=env, capture_output=True, text=True)
        open(os.path.join(out, f'{tag}.log'), 'w', encoding='utf-8').write(r.stderr)
        print('\n'.join(l for l in r.stderr.splitlines() if not l.startswith('->')))
        if r.returncode:
            print(f'{tag} FAILED (see {out}/{tag}.log)')
            continue
        cut = os.path.join(out, f'{tag}.cut.mp4')                  # the new script: the cut beside the final
        chk = [sys.executable, os.path.join(HERE, 'check_edit.py'), cut if os.path.exists(cut) else video,
               '--lang', args.lang,
               '--model', model]
        if len(rushes) == 1 and os.path.exists(segs):
            chk += ['--source', rushes[0], '--segments', segs]
        print(subprocess.run(chk, capture_output=True, text=True).stdout)
    print(f'renders in {out} — watch old.mp4 and new.mp4 before deciding.')
    leak_check()
    print('\nnothing was committed or pushed. If it is good:\n'
          f'  git -C {REPO} add skills/short-video/edit dev/edit && git -C {REPO} commit -m "..." -- skills/short-video/edit dev/edit && '
          f'git -C {REPO} push -u origin $(git -C {REPO} branch --show-current)')

elif args.cmd == 'mark':
    priv = need_private()
    head = git('rev-parse', 'HEAD', cwd=priv).strip()
    open(STATE, 'w').write(head + '\n')
    print(f'carried over up to private commit {head[:10]} (dev/edit/private-sync.txt, commit it with the port)')
