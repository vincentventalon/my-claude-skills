#!/usr/bin/env python3
"""check_skills.py — the repo is skills/<category>/<name>/SKILL.md (two categories: seo and
short-video). Every SKILL.md opens on a front matter with a `name` equal to its folder and a
`description`: Claude Code and `npx skills add` both install a skill under that name. A category holds
only skills (no stray SKILL.md at the category level, no skill left at the root of skills/).
A skill is named after what it does for the user, in words (edit-my-video, find-outliers-in-my-niche):
at least three hyphenated words, never a bare noun (edit, outliers). The one exception is the front
door of a pack, named after the pack (short-video).
Standard library only; run by .githooks/pre-commit and the CI."""
import pathlib, re, sys

root = pathlib.Path(__file__).resolve().parent.parent / 'skills'
bad, count = [], 0
for cat in sorted(p for p in root.iterdir() if p.is_dir()):
    if (cat / 'SKILL.md').exists():
        bad.append(f'{cat.name}: is a category, yet holds a SKILL.md (a skill goes in skills/<category>/<name>/)')
        continue
    skills = sorted(p for p in cat.iterdir() if p.is_dir())
    if not skills:
        bad.append(f'{cat.name}: empty category')
    for d in skills:
        count += 1
        label = f'{cat.name}/{d.name}'
        f = d / 'SKILL.md'
        if not f.exists():
            bad.append(f'{label}: no SKILL.md')
            continue
        m = re.match(r'---\n(.*?)\n---\n', f.read_text(encoding='utf-8'), re.S)
        if not m:
            bad.append(f'{label}: SKILL.md does not open on a --- front matter ---')
            continue
        head = m.group(1)
        name = re.search(r'^name:\s*(.+?)\s*$', head, re.M)
        if not name or name.group(1).strip('"\'') != d.name:
            bad.append(f'{label}: name is {name.group(1) if name else "missing"}, should be {d.name}')
        if not re.search(r'^description:', head, re.M):
            bad.append(f'{label}: no description')
        if d.name != cat.name and len(d.name.split('-')) < 3:
            bad.append(f'{label}: a skill is named after what it does, in at least three words (edit-my-video), not {d.name}')
# A skill name is unique across categories: both installers flatten them.
names = [d.name for cat in root.iterdir() if cat.is_dir() for d in cat.iterdir() if d.is_dir()]
for n in sorted(set(n for n in names if names.count(n) > 1)):
    bad.append(f'{n}: the same skill name in two categories')
for b in bad:
    print('check_skills: ' + b, file=sys.stderr)
if not bad:
    print(f'check_skills: {count} skills ok in {sum(1 for p in root.iterdir() if p.is_dir())} categories')
sys.exit(1 if bad else 0)
