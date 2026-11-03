#!/usr/bin/env python3
"""Ton site contre ses concurrents, d'après leurs sitemaps publics : ce qu'ils publient, à quel rythme,
et les sujets qu'ils couvrent et pas toi (et l'inverse).

Usage :
  python3 site.py monsite.com concurrent.com [concurrent2.com ...] [--dossier ./seo]
  python3 site.py monsite.com --depuis-serp 3    (les 3 domaines qui reviennent sur le plus de requêtes
                                                  dans serp.csv, tenu par pages.py)
  python3 site.py monsite.com portail.com/guides (un gros portail : seules ses URL sous /guides/ comptent)

Pour chaque site : le sitemap (annoncé dans robots.txt, sinon /sitemap.xml, /sitemap_index.xml,
/sitemap-index.xml, /wp-sitemap.xml ; index de sitemaps et .gz compris), l'inventaire par section
(premier dossier de l'URL) et par année de lastmod, la cadence sur 12 mois d'après lastmod. Puis
l'écart de couverture, par les mots des slugs (la fin de l'URL) : mots vides fr/en retirés, mots
présents dans plus d'un quart des URL d'un site retirés (« malta » sur un site sur Malte), pages de
tags, catégories et auteurs à part. Un sujet = un groupe de pages qui partagent deux mots.

Écrit ./seo/<monsite>/competitors/sites.md (le rapport, marqueurs <!-- CLAUDE: -->), ecarts.csv
(chaque écart, dans les deux sens) et urls.csv (toutes les URL lues, avec section, lastmod, mots).
Un sitemap introuvable ou illisible est dit, et le site passe. Les sitemaps lus restent en cache le
jour même (competitors/.cache/) ; --rafraichir pour les relire.
"""
import argparse
import collections
import csv
import datetime as dt
import heapq
import html
import itertools
import os
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(errors="replace")

ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
import commun as c  # noqa: E402

sys.path.insert(0, os.path.join(ici, "..", "..", "search-console", "scripts"))
try:
    import gsc_api as g  # noqa: E402
except ImportError:
    g = None  # la skill marche sans, en disant ce qu'elle n'a pas pu faire

CHEMINS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml", "/wp-sitemap.xml")
MAX_SOUS = 150        # sous-sitemaps lus au plus par site
MAX_URLS = 50_000     # URL gardées au plus par site
BUDGET_S = 60         # secondes de lecture au plus par site
PART_COMMUNE = 0.25   # un mot dans plus de 25 % des slugs d'un site ne distingue aucun sujet
MAX_MOTS_SLUG = 8
TAXONOMIES = {"tag", "tags", "category", "categories", "categorie", "author", "auteur", "authors", "auteurs",
              "page", "etiquette", "etiquettes", "label", "archive", "archives", "feed", "amp", "wp-content",
              "attachment", "search", "recherche"}
LANGUES = {"fr", "de", "nl", "it", "es", "pt", "pl", "en", "ru", "zh", "ja", "ko", "ar", "sv", "da", "no", "nb",
           "fi", "cs", "sk", "hu", "ro", "bg", "el", "tr", "uk", "he", "mt", "ca", "hr", "sl", "lt", "lv", "et"}
FICHIERS = re.compile(r"\.(jpe?g|png|gif|webp|svg|pdf|xml|txt|zip|mp4|mp3|css|js)$", re.I)


def cdata(s):
    return html.unescape(re.sub(r"^<!\[CDATA\[|\]\]>$", "", s.strip())).strip()


def lire_xml(url):
    d = c.telecharger(url, timeout=20, max_octets=60_000_000, accept="application/xml,text/xml,*/*;q=0.8")
    if not d["ok"]:
        return None, d["erreur"]
    x = d["texte"]
    if re.search(r"<sitemapindex", x[:5000], re.I):
        return ("index", [cdata(m) for m in re.findall(r"<sitemap\b[^>]*>.*?<loc>(.*?)</loc>", x, re.S | re.I)]), ""
    if re.search(r"<urlset", x[:5000], re.I):
        urls = []
        for bloc in re.findall(r"<url\b[^>]*>(.*?)</url>", x, re.S | re.I):
            loc = re.search(r"<loc>(.*?)</loc>", bloc, re.S | re.I)
            if loc:
                lm = re.search(r"<lastmod>(.*?)</lastmod>", bloc, re.S | re.I)
                urls.append((cdata(loc.group(1)), cdata(lm.group(1))[:10] if lm else ""))
        return ("urls", urls), ""
    lignes = [l.strip() for l in x.splitlines() if l.strip()]
    if lignes and all(re.match(r"https?://\S+$", l) for l in lignes[:50]):
        return ("urls", [(l, "") for l in lignes]), ""
    return None, "pas un sitemap (ni urlset ni sitemapindex)" + (" : une page HTML" if "<html" in x[:2000].lower() else "")


def lire_site(domaine, gsc_sitemaps=None):
    """Trouve et lit le sitemap d'un domaine. Ne lève jamais."""
    t0 = time.monotonic()
    essais, depart, base = [], [], None
    for prefixe in ("https://",) if domaine.startswith("www.") else ("https://", "https://www."):
        r = c.telecharger(prefixe + domaine + "/robots.txt", timeout=15, accept="text/plain,*/*")
        essais.append(f"{prefixe}{domaine}/robots.txt : {'lu' if r['ok'] else r['erreur']}")
        if r["ok"]:
            pu = urllib.parse.urlparse(r["url_finale"])
            base = f"{pu.scheme}://{pu.netloc}"
            depart = list(dict.fromkeys(re.findall(r"(?im)^\s*sitemap\s*:\s*(\S+)", r["texte"])))
            if not depart:
                essais[-1] += " (aucune ligne Sitemap:)"
            break
    base = base or "https://" + domaine
    urls, lus, erreurs, tronque = {}, [], [], ""

    def parcourir(points):
        nonlocal tronque
        file = collections.deque(points)
        vus = set(lus)
        while file:
            u = file.popleft()
            if u in vus:
                continue
            vus.add(u)
            if len(lus) >= MAX_SOUS:
                tronque = f"arrêté à {MAX_SOUS} sitemaps"
                return
            if time.monotonic() - t0 > BUDGET_S:
                tronque = f"arrêté après {BUDGET_S} s de lecture"
                return
            res, err = lire_xml(u)
            lus.append(u)
            if res is None:
                erreurs.append(f"{u} : {err}")
                continue
            genre, contenu = res
            if genre == "index":
                # Les séries numérotées (annonces/1.xml, products-2.xml) passent après les autres : sur un
                # gros portail, elles rempliraient la limite avant les guides.
                serie = re.compile(r"[-_/]?\d+\.xml(\.gz)?$|[?&](page|p)=\d+$", re.I)
                file.extend([x for x in contenu if not serie.search(x)] + [x for x in contenu if serie.search(x)])
            else:
                for loc, lm in contenu:
                    if len(urls) >= MAX_URLS:
                        tronque = f"arrêté à {MAX_URLS} URL"
                        return
                    urls.setdefault(loc, lm)

    if depart:
        parcourir(depart)
    if not urls:
        for ch in CHEMINS:
            if base + ch in lus:
                continue
            avant = len(lus)
            parcourir([base + ch])
            if urls:
                break
            if len(lus) > avant and erreurs:
                essais.append(erreurs.pop())
    if not urls and gsc_sitemaps:
        essais.append("sitemaps déclarés dans Search Console : " + ", ".join(gsc_sitemaps))
        parcourir(gsc_sitemaps)
    return {"domaine": domaine, "base": base, "urls": urls, "lus": lus, "erreurs": erreurs, "essais": essais,
            "tronque": tronque, "secondes": round(time.monotonic() - t0, 1)}


def sitemaps_gsc(dossier, site):
    if g is None:
        return None, "Search Console non lue (skill search-console absente)"
    try:
        g.racine(dossier)
        prop = g.resoudre_site(site)
        return [s["path"] for s in g.sitemaps(prop) if s.get("path")], ""
    except g.Panne as e:
        return None, "Search Console non branchée (" + str(e).splitlines()[0][:120] + ")"
    except Exception as e:  # noqa: BLE001
        return None, f"Search Console illisible ({type(e).__name__})"


# --- l'analyse ---------------------------------------------------------------------

def code_langue(seg):
    s = seg.lower()
    return s[:2] if (s in LANGUES or (re.fullmatch(r"[a-z]{2}[-_][a-z]{2}", s) and s[:2] in LANGUES)) else ""


def decrire(url):
    pu = urllib.parse.urlparse(url)
    segs = [urllib.parse.unquote(s) for s in pu.path.split("/") if s]
    section = segs[0].lower() if len(segs) >= 2 else "(racine)"
    taxo = any(s.lower() in TAXONOMIES for s in segs[:2]) or bool(re.search(r"/page/\d+/?$", pu.path))
    slug = ""
    for s in reversed(segs):
        s2 = re.sub(r"\.(html?|php|aspx?)$", "", s, flags=re.I)
        if s2 and not s2.isdigit() and not re.fullmatch(r"[0-9a-f-]{16,}", s2):
            slug = s2
            break
    return section, taxo, slug, (code_langue(segs[0]) if segs else "")


def filtre_langue(s, langue_moi):
    """Un site traduit (/fr/, /de/…) compterait chaque sujet plusieurs fois : on garde une seule langue."""
    prefixees = collections.Counter(p["langue_url"] for p in s["sujets"] if p["langue_url"])
    if sum(prefixees.values()) < 10:
        return ""
    if langue_moi in prefixees and prefixees[langue_moi] >= 10:
        s["sujets"] = [p for p in s["sujets"] if p["langue_url"] == langue_moi]
        garde = f"seules ses URL sous /{langue_moi}/"
    else:
        s["sujets"] = [p for p in s["sujets"] if not p["langue_url"]]
        garde = "seules ses URL sans préfixe de langue"
    return (f"{s['domaine']} est traduit (" + ", ".join(f"/{k}/ {v}" for k, v in sorted(prefixees.items()))
            + f") : {garde} comptent dans l'écart ({nombre(len(s['sujets']))} pages).")


def analyser(sites):
    """sites[0] = le tien. Ajoute à chaque site : pages, mots par URL, index des mots et des paires."""
    for s in sites:
        s["pages"] = []
        for u, lm in sorted(s["urls"].items()):
            pu = urllib.parse.urlparse(u)
            if FICHIERS.search(pu.path) or not c.meme_site(pu.hostname or "", s["domaine"]):
                continue
            if s.get("prefixe") and not (pu.path.rstrip("/") + "/").startswith(s["prefixe"] + "/"):
                continue
            section, taxo, slug, lg = decrire(u)
            s["pages"].append({"url": u, "lastmod": c.date_iso(lm), "langue_url": lg,
                               "section": section, "taxo": taxo, "slug": slug,
                               "bruts": c.mots_bruts(slug.replace("-", " ").replace("_", " "))})
        sujets = [p for p in s["pages"] if not p["taxo"]]
        s["langue"] = c.langue_des_mots([m for p in sujets for m in p["bruts"]])
        marque = set(c.jetons(s["domaine"].split(".")[0]))
        for p in sujets:
            vus = []
            for r, f in c.formes(" ".join(p["bruts"]), marque):
                if r not in vus:
                    vus.append(r)
            p["mots"] = vus[:MAX_MOTS_SLUG]
        s["sujets"] = sujets
    langue_moi = sites[0]["langue"]
    notes_langue = [x for x in (filtre_langue(s, langue_moi) for s in sites[1:]) if x]
    communs = {}
    for s in sites:
        n = len(s["sujets"])
        if n >= 20:
            df = collections.Counter(m for p in s["sujets"] for m in set(p["mots"]))
            for m, k in df.items():
                if k > PART_COMMUNE * n:
                    communs[m] = max(communs.get(m, 0), round(100 * k / n))
    formes = {}
    for s in sites:
        s["mot"], s["paire"] = collections.defaultdict(set), collections.defaultdict(set)
        for p in s["sujets"]:
            p["mots"] = [m for m in p["mots"] if m not in communs]
            for r, f in c.formes(" ".join(p["bruts"])):
                formes.setdefault(r, f)
            for m in p["mots"]:
                s["mot"][m].add(p["url"])
            for a, b in itertools.combinations(sorted(set(p["mots"])), 2):
                s["paire"][(a, b)].add(p["url"])
        s["groupes"] = groupes(s["paire"])
        dans_groupe = {u for _, us in s["groupes"] for u in us}
        s["seules"] = [p for p in s["sujets"] if p["url"] not in dans_groupe and p["mots"]]
        s["mots_page"] = {p["url"]: set(p["mots"]) for p in s["sujets"]}
    return communs, formes, notes_langue


def groupes(paires):
    """Couverture gloutonne : la paire de mots qui réunit le plus de pages pas encore prises, puis la suivante."""
    tas = [(-len(us), p) for p, us in paires.items() if len(us) >= 2]
    heapq.heapify(tas)
    pris, out = set(), []
    while tas:
        k, p = heapq.heappop(tas)
        reste = paires[p] - pris
        if len(reste) < 2:
            continue
        if len(reste) < -k:
            heapq.heappush(tas, (-len(reste), p))
            continue
        out.append((p, sorted(reste)))
        pris |= reste
    return out


def sans_equivalent(pages, autre):
    """Les pages dont aucune page de l'autre site ne partage deux mots (ou le seul mot du slug)."""
    out = []
    for p in pages:
        T = set(p["mots"])
        besoin = min(2, len(T))
        cpt = collections.Counter(u for m in T for u in autre["mot"].get(m, ()))
        if not cpt or max(cpt.values()) < besoin:
            out.append(p)
    return out


def ecarts(moi, lui):
    absents, presents = [], 0
    for (a, b), us in lui["groupes"]:
        deux = len(moi["paire"].get((a, b), ()))
        if deux:
            presents += 1
            continue
        un = len(moi["mot"].get(a, set()) | moi["mot"].get(b, set()))
        absents.append({"mots": (a, b), "lui": len(us), "toi_deux": 0, "toi_un": un, "exemples": us[:3]})
    hubs = []
    for m, us in lui["mot"].items():
        k, mien = len(us), len(moi["mot"].get(m, ()))
        if k >= 10 and k >= 3 * max(mien, 1):
            hubs.append({"mot": m, "lui": k, "toi": mien})
    hubs.sort(key=lambda h: (-h["lui"], h["mot"]))
    return absents, presents, hubs, sans_equivalent(lui["seules"], moi)


# --- le rapport --------------------------------------------------------------------

def nombre(x):
    return f"{x:,}".replace(",", " ")


def mois_precedents(n=12):
    d = dt.date.today().replace(day=1)
    out = []
    for _ in range(n):
        out.append(d.strftime("%Y-%m"))
        d = (d - dt.timedelta(days=1)).replace(day=1)
    return list(reversed(out))


def fiabilite(s):
    dates = [p["lastmod"] for p in s["pages"] if p["lastmod"]]
    if not dates:
        return "pas de lastmod"
    top, k = collections.Counter(dates).most_common(1)[0]
    if len(dates) >= 20 and k > 0.5 * len(dates):
        return f"non fiable : {round(100 * k / len(dates))} % des URL ont la même date ({top}), le site la réécrit"
    return ""


def court_url(u, base):
    pu = urllib.parse.urlparse(u)
    return (pu.path or "/") + (("?" + pu.query) if pu.query else "")


def rapport(sites, communs, formes, jour, notes, notes_langue=()):
    moi, autres = sites[0], [s for s in sites[1:] if s["pages"]]
    L = []
    w = L.append
    noms = [s["domaine"] + s.get("prefixe", "") for s in sites]
    w(f"# {moi['domaine']} contre {', '.join(noms[1:])}")
    w("")
    w(f"Mesuré le {jour} par `site.py`, d'après les sitemaps publics. Un sitemap dit ce qu'un site publie, pas "
      "ce que Google en garde ni ce qui reçoit du trafic.")
    w("")
    for n_ in notes:
        w(f"> {n_}")
        w("")
    w("<!-- CLAUDE: le verdict en deux ou trois phrases : qui publie le plus, sur quoi, à quel rythme, et les "
      "deux ou trois sujets qui manquent le plus à ton site, chacun avec son chiffre (pages chez lui, chez toi). -->")
    w("")
    w("## Les sitemaps")
    w("")
    for s in sites:
        if s.get("prefixe"):
            w(f"> {s['domaine']} : seules les URL sous {s['prefixe']}/ comptent ({nombre(len(s['pages']))} sur "
              f"{nombre(len(s['urls']))} lues).")
            w("")
    w("| site | URL lues | pages de sujet | tags, catégories, auteurs | avec lastmod | langue des slugs | sitemaps lus | lecture |")
    w("|---|---|---|---|---|---|---|---|")
    for s in sites:
        if not s["pages"]:
            w(f"| {s['domaine']} | 0 | — | — | — | — | {len(s['lus'])} | **introuvable ou illisible** |")
            continue
        dl = sum(1 for p in s["pages"] if p["lastmod"])
        lecture = s["tronque"] or f"complète ({s['secondes']} s)"
        w(f"| {s['domaine']} | {nombre(len(s['pages']))} | {nombre(len(s['sujets']))} | "
          f"{nombre(len(s['pages']) - len(s['sujets']))} | {round(100 * dl / len(s['pages']))} % | "
          f"{s['langue']} | {len(s['lus'])} | {lecture} |")
    w("")
    for s in sites:
        if not s["pages"]:
            w(f"**{s['domaine']}** : aucun sitemap lisible. Essais :")
            for e in s["essais"] + s["erreurs"][:5]:
                w(f"- {e}")
            w("")
            w("Sans sitemap, le script ne voit pas ce site : regarde-le à la main (son menu, son blog), ou "
              "compare-le page à page avec `pages.py`.")
            w("")
        elif s["erreurs"]:
            w(f"**{s['domaine']}** : {len(s['erreurs'])} sitemap(s) illisible(s) sur {len(s['lus'])}, ex. "
              f"{s['erreurs'][0]}.")
            w("")
    if not autres:
        w("Aucun concurrent lisible : rien à comparer.")
        return "\n".join(L)
    for n_ in notes_langue:
        w(f"> {n_}")
        w("")
    langues = {s["langue"] for s in [moi] + autres if s["pages"] and s["langue"] != "?"}
    if len(langues) > 1:
        w("**Attention : les slugs ne sont pas tous dans la même langue** (" + ", ".join(
            f"{s['domaine']} {s['langue']}" for s in [moi] + autres if s["pages"]) + "). L'écart par mots ne "
            "compare que des mots identiques : entre deux langues, lis les listes à la main.")
        w("")

    w("## Par section (premier dossier de l'URL)")
    w("")
    for s in [moi] + autres:
        if not s["pages"]:
            continue
        cpt = collections.Counter(p["section"] for p in s["pages"])
        tops = sorted(cpt.items(), key=lambda kv: (-kv[1], kv[0]))
        txt = ", ".join(f"{k} {v}" for k, v in tops[:12])
        if len(tops) > 12:
            txt += f", et {len(tops) - 12} autres sections ({sum(v for _, v in tops[12:])} URL)"
        w(f"- **{s['domaine']}** ({len(cpt)} sections) : {txt}.")
    w("")
    w("« (racine) » : les pages posées directement à la racine du site (monsite.com/ma-page).")
    w("")

    w("## Par année de lastmod")
    w("")
    annees = sorted({p["lastmod"][:4] for s in sites for p in s["pages"] if p["lastmod"]}, reverse=True)[:8]
    w("| année | " + " | ".join(s["domaine"] for s in [moi] + autres) + " |")
    w("|---|" + "---|" * (len(autres) + 1))
    for a in annees:
        w(f"| {a} | " + " | ".join(str(sum(1 for p in s["pages"] if p["lastmod"][:4] == a))
                                   for s in [moi] + autres) + " |")
    w("| sans lastmod | " + " | ".join(str(sum(1 for p in s["pages"] if not p["lastmod"]))
                                     for s in [moi] + autres) + " |")
    w("")
    w("lastmod est la date de dernière modification que le site déclare, pas la date de publication.")
    w("")
    w("## Cadence : pages par mois d'après lastmod (12 derniers mois)")
    w("")
    mois = mois_precedents()
    w("| mois | " + " | ".join(s["domaine"] for s in [moi] + autres) + " |")
    w("|---|" + "---|" * (len(autres) + 1))
    for mo in mois:
        w(f"| {mo} | " + " | ".join(str(sum(1 for p in s["pages"] if p["lastmod"][:7] == mo))
                                    for s in [moi] + autres) + " |")
    w("| **12 mois** | " + " | ".join(f"**{sum(1 for p in s['pages'] if p['lastmod'][:7] >= mois[0])}**"
                                       for s in [moi] + autres) + " |")
    w("")
    for s in [moi] + autres:
        f = fiabilite(s)
        if f:
            w(f"- {s['domaine']} : lastmod {f}. Sa cadence ne se lit pas ici.")
    w("")
    w("Une page modifiée compte dans le mois de sa modification : c'est un rythme de mise à jour, qui "
      "majore le rythme de publication.")
    w("")

    w("## L'écart de couverture")
    w("")
    w("Un sujet = un groupe d'au moins deux pages dont les slugs partagent deux mots (mots vides fr/en retirés, "
      "au singulier). « Absent chez toi » : aucune de tes URL n'a ces deux mots ensemble.")
    if communs:
        w("Mots écartés parce qu'ils sont dans plus d'un quart des URL d'un site (ils ne distinguent aucun "
          "sujet) : " + ", ".join(f"{formes.get(m, m)} ({k} %)" for m, k in sorted(communs.items(),
                                                                                    key=lambda kv: (-kv[1], kv[0]))) + ".")
    w("")
    resultats = {}
    for s in autres:
        resultats[s["domaine"]] = ecarts(moi, s)
    # sujets absents chez toi que plusieurs concurrents couvrent
    if len(autres) >= 2:
        croise = collections.defaultdict(dict)
        for s in autres:
            for p, us in s["paire"].items():
                if len(us) >= 2 and not moi["paire"].get(p):
                    croise[p][s["domaine"]] = len(us)
        multi = sorted(((p, d) for p, d in croise.items() if len(d) >= 2),
                       key=lambda x: (-len(x[1]), -sum(x[1].values()), x[0]))
        mots_croises = collections.defaultdict(dict)
        for s in autres:
            for m, us in s["mot"].items():
                if not moi["mot"].get(m):
                    mots_croises[m][s["domaine"]] = len(us)
        mc = sorted(((m, d) for m, d in mots_croises.items() if len(d) >= 2),
                    key=lambda x: (-len(x[1]), -sum(x[1].values()), x[0]))
        w("### Absents chez toi, couverts par plusieurs concurrents")
        w("")
        if mc:
            w("Les mots que deux concurrents ou plus ont dans leurs URL, et toi dans aucune :")
            w("")
            w("| mot | concurrents | pages chez eux |")
            w("|---|---|---|")
            for m, d in mc[:20]:
                w(f"| {formes.get(m, m)} | {len(d)}/{len(autres)} | " + ", ".join(f"{k} {v}" for k, v in sorted(d.items())) + " |")
            w("")
        if multi:
            w("Les sujets (deux mots ensemble, deux pages ou plus) que deux concurrents ou plus couvrent :")
            w("")
            w("| sujet (mots du slug) | concurrents | pages chez eux |")
            w("|---|---|---|")
            for (a, b), d in multi[:20]:
                w(f"| {formes.get(a, a)} + {formes.get(b, b)} | {len(d)}/{len(autres)} | "
                  + ", ".join(f"{k} {v}" for k, v in sorted(d.items())) + " |")
        elif not mc:
            w("Aucun mot ni sujet que deux concurrents couvrent et toi non.")
        w("")
    for s in autres:
        absents, presents, hubs, seules = resultats[s["domaine"]]
        w(f"### {s['domaine']} : ce qu'il couvre et pas toi")
        w("")
        w(f"{nombre(len(s['sujets']))} pages comparées. {len(s['groupes'])} sujets chez lui (groupes de 2 pages ou "
          f"plus) : {presents} que tu couvres aussi, {len(absents)} absents chez toi. Et {nombre(len(s['seules']))} "
          f"pages seules sur leur sujet, dont {nombre(len(seules))} sans équivalent chez toi (aucune de tes URL ne "
          "partage deux de leurs mots).")
        w("")
        if absents:
            w("| sujet | pages chez lui | chez toi, avec un des deux mots | exemples |")
            w("|---|---|---|---|")
            for e in absents[:25]:
                a, b = e["mots"]
                ex = " · ".join(court_url(u, s["base"]) for u in e["exemples"][:2])
                w(f"| {formes.get(a, a)} + {formes.get(b, b)} | {e['lui']} | {e['toi_un']} | {ex} |")
        w("")
        if seules:
            par_sec = collections.Counter(p["section"] for p in seules)
            w("Ses pages seules sans équivalent chez toi, par section : " + ", ".join(
                f"{k} {v}" for k, v in sorted(par_sec.items(), key=lambda kv: (-kv[1], kv[0]))[:10]) + ". Les "
              "premières :")
            w("")
            for p in sorted(seules, key=lambda p: (-len(p["mots"]), p["url"]))[:20]:
                w(f"- {court_url(p['url'], s['base'])} ({', '.join(formes.get(m, m) for m in p['mots'])})")
            w("")
        if hubs:
            w("Mots sur lesquels il a au moins 10 pages et trois fois plus que toi (un hub, pas une page de "
              "plus) : " + ", ".join(f"{formes.get(h['mot'], h['mot'])} ({h['lui']} chez lui, {h['toi']} chez toi)"
                                     for h in hubs[:12]) + ".")
            w("")
    w("### Ce que tu as et qu'ils n'ont pas")
    w("")
    for s in autres:
        mien = [(p, us) for p, us in moi["groupes"] if not s["paire"].get(p)]
        txt = ", ".join(f"{formes.get(a, a)} + {formes.get(b, b)} ({len(us)})" for (a, b), us in mien[:15])
        miennes = sans_equivalent(moi["seules"], s)
        w(f"- **absent chez {s['domaine']}** : {len(mien)} de tes {len(moi['groupes'])} sujets à plusieurs pages"
          + (f" ({txt})" if txt else "") + f" ; {len(miennes)} de tes {len(moi['seules'])} pages seules, ex. "
          + ", ".join(court_url(p["url"], "") for p in sorted(miennes, key=lambda p: p["url"])[:8]) + ".")
    w("")
    w("<!-- CLAUDE: relis les 15 premiers écarts de chaque concurrent et écarte les faux (pages légales, "
      "produits, pays ou villes hors de ton sujet, mots coupés) ; garde trois sujets, chacun avec son nombre de "
      "pages chez lui et chez toi, et dis s'il appelle une page ou un hub (beaucoup de pages chez lui, aucune ou "
      "presque chez toi). Puis, pour la requête principale de chaque sujet, la suite : pages.py sur sa première "
      "page de Google. -->")
    w("")
    w("## Ce que ce rapport ne mesure pas")
    w("")
    w("Le trafic de ces sites, leurs positions, leurs backlinks, ce que Google indexe vraiment. Un slug ne dit "
      "pas tout d'une page : deux pages au même sujet peuvent avoir des slugs sans mot commun, et un écart peut "
      "être un faux (une page produit, une page légale). Search Console ne donne pas les concurrents : elle ne "
      "voit que ton site.")
    w("")
    return "\n".join(L), resultats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sites", nargs="+", help="ton site d'abord, puis les concurrents (domaines)")
    ap.add_argument("--dossier", help="dossier racine des données (défaut ./seo)")
    ap.add_argument("--depuis-serp", type=int, metavar="N",
                    help="ajoute les N domaines qui reviennent sur le plus de requêtes dans serp.csv")
    ap.add_argument("--rafraichir", action="store_true", help="relire les sitemaps même s'ils sont en cache")
    a = ap.parse_args(argv)

    prefixes = {}
    for s in a.sites:
        pu = urllib.parse.urlparse(s if "//" in s else "https://" + s)
        if pu.path.strip("/"):
            prefixes[c.hote(s)] = "/" + pu.path.strip("/")
    domaines = list(dict.fromkeys(c.hote(s) for s in a.sites))
    root = c.racine(a.dossier)
    dossier = os.path.join(root, domaines[0], "competitors")
    os.makedirs(dossier, exist_ok=True)
    jour = dt.date.today().isoformat()
    notes = []
    if a.depuis_serp:
        chemin = os.path.join(dossier, "serp.csv")
        if not os.path.exists(chemin):
            raise c.Panne(f"{chemin} n'existe pas encore : lance d'abord pages.py sur deux ou trois requêtes.")
        with open(chemin, newline="", encoding="utf-8") as f:
            lignes = list(csv.DictReader(f))
        req, best = collections.defaultdict(set), {}
        for l in lignes:
            d = l["domaine"]
            if c.meme_site(d, domaines[0]):
                continue
            req[d].add(l["requete"])
            best[d] = min(best.get(d, 99), int(l["position"] or 99))
        classes = sorted(req, key=lambda d: (-len(req[d]), best[d], d))
        nreq = len({l["requete"] for l in lignes})
        print(f"Domaines vus dans serp.csv ({nreq} requête(s)) :")
        for d in classes[:15]:
            print(f"  {d} : {len(req[d])} requête(s), meilleure position {best[d]}")
        choisis = [d for d in classes if d not in domaines][:a.depuis_serp]
        domaines += choisis
        notes.append(f"Concurrents pris dans serp.csv ({nreq} requête(s) notée(s)) : " + ", ".join(
            f"{d} ({len(req[d])} requête(s))" for d in choisis) + ".")
    if len(domaines) < 2:
        raise c.Panne("Donne ton site puis au moins un concurrent : python3 site.py monsite.com concurrent.com")
    if len(domaines) > 6:
        raise c.Panne("Six sites au plus d'un coup (le tien et cinq concurrents) : au-delà, le rapport ne se lit plus.")

    gsc, note_gsc = None, ""
    cache_dir = os.path.join(dossier, ".cache")

    def un(d):
        chemin = os.path.join(cache_dir, "sitemap-" + d + ".json")
        if not a.rafraichir:
            x = c.lire_cache(chemin, jour)
            if x:
                return x
        x = lire_site(d, gsc if d == domaines[0] else None)
        x["jour"] = jour
        if x["urls"]:
            c.ecrire_cache(chemin, x)
        return x

    print(f"{domaines[0]} contre {', '.join(domaines[1:])} -> {dossier}")
    with ThreadPoolExecutor(len(domaines)) as ex:
        sites = list(ex.map(un, domaines))
    if not sites[0]["urls"]:
        gsc, note_gsc = sitemaps_gsc(a.dossier, domaines[0])
        if gsc:
            sites[0] = lire_site(domaines[0], gsc)
        else:
            raise c.Panne(f"Aucun sitemap lisible pour ton site {domaines[0]} ({'; '.join(sites[0]['essais'])})"
                          + (f" ; {note_gsc}" if note_gsc else "") + ". Sans lui, rien à comparer : vérifie "
                          f"https://{domaines[0]}/sitemap.xml.")
    for s in sites:
        etat = f"{nombre(len(s['urls']))} URL, {len(s['lus'])} sitemap(s), {s['secondes']} s" if s["urls"] else \
            "aucun sitemap lisible (" + "; ".join(s["essais"][-2:] + s["erreurs"][:1]) + ")"
        print(f"  {s['domaine']} : {etat}{' (' + s['tronque'] + ')' if s['tronque'] else ''}")
    for s in sites:
        s["prefixe"] = prefixes.get(s["domaine"], "")
    communs, formes, notes_langue = analyser(sites)
    md, resultats = rapport(sites, communs, formes, jour, notes, notes_langue)
    garde = c.ecrire_rapport(os.path.join(dossier, "sites.md"), md)
    if garde:
        print(f"  l'ancien rapport est gardé : {garde}")
    with open(os.path.join(dossier, "ecarts.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["concurrent", "sens", "mot_1", "mot_2", "pages_chez_lui", "pages_chez_toi_les_deux_mots",
                     "pages_chez_toi_un_des_mots", "exemples"])
        moi = sites[0]
        for s in sites[1:]:
            if not s["pages"]:
                continue
            absents, _, hubs, seules = resultats[s["domaine"]]
            for e in absents:
                wr.writerow([s["domaine"], "absent_chez_toi", formes.get(e["mots"][0], e["mots"][0]),
                             formes.get(e["mots"][1], e["mots"][1]), e["lui"], 0, e["toi_un"], " ".join(e["exemples"])])
            for p in seules:
                wr.writerow([s["domaine"], "page_seule_absente_chez_toi", " ".join(formes.get(m, m) for m in p["mots"]),
                             "", 1, 0, "", p["url"]])
            for h in hubs:
                wr.writerow([s["domaine"], "hub_chez_lui", formes.get(h["mot"], h["mot"]), "", h["lui"], h["toi"], "",
                             ""])
            for (a_, b_), us in moi["groupes"]:
                if not s["paire"].get((a_, b_)):
                    wr.writerow([s["domaine"], "absent_chez_lui", formes.get(a_, a_), formes.get(b_, b_), 0, len(us),
                                 "", " ".join(us[:3])])
    with open(os.path.join(dossier, "urls.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["site", "url", "section", "lastmod", "taxonomie", "mots"])
        for s in sites:
            for p in s["pages"]:
                wr.writerow([s["domaine"], p["url"], p["section"], p["lastmod"], "oui" if p["taxo"] else "",
                             " ".join(formes.get(m, m) for m in p.get("mots", []))])
    for s in sites[1:]:
        if s["pages"]:
            absents, seules = resultats[s["domaine"]][0], resultats[s["domaine"]][3]
            print(f"  absents chez toi d'après {s['domaine']} : {len(absents)} sujet(s) à plusieurs pages, "
                  f"{len(seules)} page(s) seule(s) ; les plus gros : " + ", ".join(
                f"{formes.get(e['mots'][0], e['mots'][0])}+{formes.get(e['mots'][1], e['mots'][1])} ({e['lui']})"
                for e in absents[:5]))
    print(f"RAPPORT {os.path.join(dossier, 'sites.md')}")
    print(f"  détail : ecarts.csv, urls.csv ; marqueurs à remplir : {md.count('<!-- CLAUDE:')}")


if __name__ == "__main__":
    try:
        main()
    except c.Panne as e:
        sys.exit("ERREUR : " + str(e))
