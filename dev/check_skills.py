#!/usr/bin/env python3
"""check_skills.py — every skills/<name>/SKILL.md opens on a front matter with a `name` equal to its
folder and a `description`: Claude Code and `npx skills add` both install a skill under that name.
Standard library only; run by .githooks/pre-commit and the CI."""
import pathlib, re, sys

root = pathlib.Path(__file__).resolve().parent.parent / 'skills'
bad = []
for d in sorted(p for p in root.iterdir() if p.is_dir()):
    f = d / 'SKILL.md'
    if not f.exists():
        bad.append(f'{d.name}: no SKILL.md')
        continue
    m = re.match(r'---\n(.*?)\n---\n', f.read_text(encoding='utf-8'), re.S)
    if not m:
        bad.append(f'{d.name}: SKILL.md does not open on a --- front matter ---')
        continue
    head = m.group(1)
    name = re.search(r'^name:\s*(.+?)\s*$', head, re.M)
    if not name or name.group(1).strip('"\'') != d.name:
        bad.append(f'{d.name}: name is {name.group(1) if name else "missing"}, should be {d.name}')
    if not re.search(r'^description:', head, re.M):
        bad.append(f'{d.name}: no description')
for b in bad:
    print('check_skills: ' + b, file=sys.stderr)
if not bad:
    print(f'check_skills: {sum(1 for p in root.iterdir() if p.is_dir())} skills ok')
sys.exit(1 if bad else 0)
