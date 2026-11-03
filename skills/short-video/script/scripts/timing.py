#!/usr/bin/env python3
"""Compte les mots d'un script et donne sa durée au débit de parole.

    python3 timing.py script.md                  # débit par défaut : 2,5 à 3 mots par seconde
    python3 timing.py script.md --cible 60-75    # la durée visée, en secondes
    python3 timing.py script.md --debit 3.4      # ton débit mesuré (un nombre, ou 3-3.5)
    python3 timing.py --mesure video.txt 64      # ton débit : les mots d'un transcript ÷ sa durée
    echo "un texte à dire" | python3 timing.py -

Dans un script.md, seul le texte à dire compte : les lignes qui commencent par
« > » sous « ## Script », découpées en blocs par les titres « ### ». Ce qui est
entre crochets [ ] est une indication de jeu, pas du texte à dire. Un texte
sans aucune ligne « > » est compté en entier.

Les deux fins (« ### FIN INSTAGRAM » et « ### FIN TIKTOK ») ont le même créneau :
une seule joue par vidéo, le total ne compte que la plus longue.

Il signale aussi ce qu'il faut relire : un hook de plus de 4 s, une couture sans
« mais » ni « donc », une présentation par le prénom, trop de mots appuyés, les
mots de la liste anti-slop (../references/anti-slop.md, blocs ```slop), et les
deux fins : « commente » et le mot côté Instagram, le lien court côté TikTok,
le même mot, sans accent dans le lien.
Ce sont des points à relire, pas des fautes : le texte reste à toi.

Python 3, bibliothèque standard seule. N'écrit rien.
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

DEBIT = (2.5, 3.0)          # mots par seconde, parole naturelle face caméra
HOOK_MAX_S = 4.0
FRAPPES_PAR_30S = 5

COUTURES = (
    # français
    "mais", "donc", "sauf que", "alors que", "du coup", "resultat", "cependant",
    "pourtant", "sauf", "seulement",
    # anglais
    "but", "so", "therefore", "except", "which means", "that's why", "thats why",
    "yet", "still", "except that", "result",
)
ET_PUIS = ("et puis", "ensuite", "apres ca", "and then", "next", "then")
SANS_COUTURE = re.compile(r"\b(cta|fin|end|outro|hook|lock)", re.I)
# les deux fins alternatives : une par plateforme, au même créneau
FIN_ALTERNATIVE = re.compile(r"\b(fin\s+(instagram|tiktok)|(instagram|tiktok)\s+ending)\b", re.I)
LIEN_COURT = re.compile(r"\b[\w-]+(?:\.[\w-]+)+/([^\s.,;:!?»\"')]+)")
PRESENTATION = re.compile(
    r"\bmoi,? c'?est [A-ZÀ-Ý]|\bje m'?appelle\b|\bmy name is\b|\bi'?m [A-Z][a-z]+ and\b")


def sans_accents(s):
    s = unicodedata.normalize("NFD", s.replace("’", "'"))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def nettoie(ligne):
    ligne = re.sub(r"\[[^\]]*\]", " ", ligne)          # indications de jeu
    return re.sub(r"[*_`]", "", ligne).strip()


def mots(texte):
    return [t for t in texte.split() if re.search(r"\w", t)]


def lit_blocs(texte):
    """[(nom, [lignes à dire brutes])] ; un seul bloc « texte » si aucune ligne « > »."""
    lignes = texte.splitlines()
    debut, fin = 0, len(lignes)
    for i, l in enumerate(lignes):
        if re.match(r"^##\s+script\b", l.strip(), re.I):
            debut = i + 1
            for j in range(i + 1, len(lignes)):
                if re.match(r"^##\s", lignes[j]):
                    fin = j
                    break
            break
    blocs, nom = [], None
    for l in lignes[debut:fin]:
        if l.startswith("### "):
            nom = l[4:].strip()
            blocs.append((nom, []))
        elif l.lstrip().startswith(">"):
            if not blocs:
                blocs.append(("texte", []))
            blocs[-1][1].append(l.lstrip()[1:].strip())
    blocs = [(n, b) for n, b in blocs if b]
    if not blocs:
        blocs = [("texte", [l for l in lignes if l.strip()])]
    return blocs


def liste_slop():
    ref = Path(__file__).resolve().parent.parent / "references" / "anti-slop.md"
    if not ref.exists():
        return []
    sortie, dedans = [], False
    for l in ref.read_text(encoding="utf-8").splitlines():
        if l.strip().startswith("```"):
            dedans = l.strip() == "```slop"
            continue
        if dedans:
            terme = l.split("#")[0].strip()
            if terme:
                sortie.append(terme)
    return sortie


def chrono(s):
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def plage(a, b, unite=" s"):
    a, b = round(a), round(b)
    return f"{a}{unite}" if a == b else f"{a}-{b}{unite}"


def debit_arg(v):
    v = v.replace(",", ".")
    if "-" in v:
        a, b = (float(x) for x in v.split("-", 1))
    else:
        a = b = float(v)
    if a <= 0 or b <= 0:
        raise argparse.ArgumentTypeError("un débit est un nombre de mots par seconde, > 0")
    return (min(a, b), max(a, b))


def cible_arg(v):
    a, _, b = v.replace(",", ".").partition("-")
    return (float(a), float(b or a))


def main():
    p = argparse.ArgumentParser(description="Durée d'un script au débit de parole.")
    p.add_argument("fichier", nargs="?", help="script.md, un .txt, ou - pour l'entrée standard")
    p.add_argument("--debit", type=debit_arg, default=DEBIT, help="mots par seconde (défaut 2.5-3)")
    p.add_argument("--cible", type=cible_arg, help="durée visée en secondes, ex. 60-75")
    p.add_argument("--mesure", nargs=2, metavar=("TRANSCRIPT", "SECONDES"),
                   help="calcule ton débit à partir d'une vidéo déjà tournée")
    a = p.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if a.mesure:
        n = len(mots(Path(a.mesure[0]).read_text(encoding="utf-8")))
        s = float(a.mesure[1].replace(",", "."))
        d = n / s
        print(f"ton débit : {d:.1f} mots/s ({n} mots en {s:g} s) -> --debit {d:.1f}")
        return 0
    if not a.fichier:
        p.error("donne un fichier (ou - pour l'entrée standard)")

    texte = sys.stdin.read() if a.fichier == "-" else Path(a.fichier).read_text(encoding="utf-8")
    lent, vite = a.debit
    blocs = lit_blocs(texte)
    slop = [(t, re.compile(r"(?<![a-z0-9])" + re.escape(sans_accents(t)) + r"(?![a-z0-9])"))
            for t in liste_slop()]

    largeur = max(12, *(len(n) for n, _ in blocs)) if blocs else 12
    print(f"débit : {lent:g}-{vite:g} mots/s" if lent != vite else f"débit : {lent:g} mots/s")
    print(f"{'bloc':<{largeur}}  {'mots':>4}  {'durée':>8}  fin vers")
    total, points, fins, mots_fins = 0, [], None, {}
    for i, (nom, brut) in enumerate(blocs):
        propre = [nettoie(l) for l in brut]
        n = sum(len(mots(l)) for l in propre)
        alt = FIN_ALTERNATIVE.search(nom)
        if alt:                                   # même créneau que l'autre fin : la plus longue compte
            debut, longue = fins if fins else (total, 0)
            fins = (debut, max(longue, n))
            total, bout = debut + fins[1], debut + n
            plateforme = "instagram" if "instagram" in nom.lower() else "tiktok"
            mots_fins[plateforme] = " ".join(propre)
        else:
            fins = None
            total += n
            bout = total
        fin = chrono(bout / vite) if lent == vite else f"{chrono(bout / vite)}-{chrono(bout / lent)}"
        print(f"{nom:<{largeur}}  {n:>4}  {plage(n / vite, n / lent):>8}  {fin}"
              + ("  (une seule des deux fins joue)" if alt and len(mots_fins) == 2 else ""))

        if i == 0 and n / vite > HOOK_MAX_S:
            points.append(f"hook ≈ {plage(n / vite, n / lent)} ({n} mots) : au-delà de 4 s, "
                          "propose une version plus courte à côté")
        if i >= 2 and not SANS_COUTURE.search(nom) and propre:
            ouverture = sans_accents(propre[0])
            if any(ouverture.startswith(m + " ") or ouverture.startswith(m + ",")
                   for m in ET_PUIS):
                points.append(f"« {nom} » s'ouvre sur « et puis / ensuite » : "
                              "une couture veut un mais ou un donc")
            elif not any(re.match(re.escape(c) + r"\b", ouverture) for c in COUTURES):
                points.append(f"« {nom} » ne s'ouvre ni sur mais ni sur donc : "
                              "à justifier ou à corriger")
        for l in brut:
            if "[relance]" in l.lower():
                suite = sans_accents(nettoie(l))
                if not any(re.match(re.escape(c) + r"\b", suite) for c in COUTURES):
                    points.append(f"relance de « {nom} » sans mais ni donc : « {nettoie(l)[:50]} »")
        frappes = sum(len(re.findall(r"\*\*[^*]+\*\*", l)) for l in brut)
        if frappes and frappes > FRAPPES_PAR_30S * max(1.0, (n / lent) / 30):
            points.append(f"« {nom} » : {frappes} mots appuyés, c'est trop pour sa durée "
                          "(3 à 5 par 30 s) : le reste doit couler")
        for l in propre:
            if PRESENTATION.search(l):
                points.append(f"présentation par le prénom dans « {nom} » : l'autorité se dit "
                              "par un fait, pas par un nom")
            norm = sans_accents(l)
            for terme, motif in slop:
                if motif.search(norm):
                    points.append(f"anti-slop, à relire : « {terme} » dans « {nom} »")

    ig, tt = mots_fins.get("instagram"), mots_fins.get("tiktok")
    lien = LIEN_COURT.search(tt) if tt else None
    if ig is not None and not re.search(r"\bcomment", sans_accents(ig)):
        points.append("« FIN INSTAGRAM » ne dit pas « commente » : c'est le mot auquel le montage la reconnaît")
    if tt is not None and not lien:
        points.append("« FIN TIKTOK » ne dit pas de lien court (domaine/mot) : rien ne répond à un "
                      "commentaire sur TikTok, le lien se dit")
    if lien:
        mot_lien = lien.group(1)
        if mot_lien != sans_accents(mot_lien):
            points.append(f"le mot du lien « {mot_lien} » : sans accent et en minuscules "
                          f"(« {sans_accents(mot_lien)} »)")
        if ig and sans_accents(mot_lien) not in re.findall(r"[a-z0-9-]+", sans_accents(ig)):
            points.append(f"le mot du lien « {mot_lien} » n'est pas dans la fin Instagram : le même mot "
                          "dans les deux fins")

    duree = (total / vite, total / lent)
    print(f"{'TOTAL':<{largeur}}  {total:>4}  {plage(*duree):>8}")
    if a.cible:
        lo, hi = a.cible
        if duree[0] >= lo and duree[1] <= hi:
            print(f"dans la cible ({plage(lo, hi)})")
        elif duree[1] < lo:
            points.append(f"trop court pour la cible {plage(lo, hi)} : ne remplis pas, "
                          "dis-le et laisse trancher")
        elif duree[0] > hi:
            points.append(f"trop long pour la cible {plage(lo, hi)} : coupe dans le corps, "
                          "jamais la fin")
        else:
            print(f"à la limite de la cible ({plage(lo, hi)}) selon le débit : "
                  "mesure le tien (--mesure)")
    print()
    if points:
        print(f"{len(points)} point(s) à relire :")
        for x in points:
            print(f"- {x}")
    else:
        print("rien à relire")
    return 0


if __name__ == "__main__":
    sys.exit(main())
