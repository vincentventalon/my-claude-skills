#!/usr/bin/env python3
"""Audit SEO technique d'un site : est-ce que Google arrive à lire tes pages ?

Usage :
  python3 audit.py monsite.com [--dossier ./seo] [--max 300] [--sans-inspection] [--sans-lighthouse]

Mesure, ne modifie rien. Lit robots.txt et le ou les sitemaps, puis l'accueil, chaque page du
sitemap et les pages trouvées par les liens (jusqu'à --max pages). Pour chaque page : code HTTP,
redirections, temps de réponse, title, description, H1, canonique, noindex, hreflang, langue,
viewport, JSON-LD, Open Graph, images, dates, et ses liens, en séparant ceux du texte de ceux de la
navigation. Puis les liens cassés, les images lourdes, HTTPS, HSTS, le cache, les variantes
http / www / slash final. Si la skill `search-console` est installée à côté et branchée : inspection
d'URL de chaque page du sitemap (150 au plus) et pages vues par Google hors sitemap. Si Node est
là : Lighthouse sur 3 pages (mobile).

Écrit <dossier>/<site>/seo-audit/ : AUDIT.md (le rapport, avec des marqueurs <!-- CLAUDE: -->
là où il faut juger), pages.csv, liens.csv, audit.json. Python 3.10+, bibliothèque standard.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(errors="replace")

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import lecture as lec  # noqa: E402
import rapport  # noqa: E402
import reseau as net  # noqa: E402

sys.path.insert(1, os.path.join(ICI, "..", "..", "search-console", "scripts"))
try:
    import gsc_api as g  # la skill `search-console`, installée à côté
except ImportError:
    g = None

# --- seuils (références : references/constats.md) ---
TITLE_MAX, TITLE_MIN = 60, 20          # caractères
DESC_MAX, DESC_MIN = 160, 50
IMAGE_LOURDE = 200_000                  # octets
TTFB_LENT = 800                         # ms, mesuré depuis cet ordinateur
MOTS_VIDE = 100                         # mots lus dans le HTML brut
CACHE_MIN = 7 * 86400                   # s, pour CSS et JS
LCP_BON, CLS_BON, TBT_BON = 2500, 0.1, 200
EXTERNES_MAX, IMAGES_MAX, FICHIERS_MAX, ASSETS_MAX = 30, 200, 100, 12
GABARIT_PART, GABARIT_MIN = 0.5, 6      # même lien sur plus de la moitié des pages (6 au moins)
GOOGLE_HORS_SITEMAP_MAX = 20
FICHIER = re.compile(r"\.(pdf|zip|gz|rar|7z|dmg|exe|msi|docx?|xlsx?|pptx?|csv|txt|json|xml|rss|atom|mp3|mp4|mov|"
                     r"webm|avi|jpe?g|png|gif|webp|avif|svg|ico|woff2?|ttf|otf|eot|css|js|mjs|map)$", re.I)
LEGALE = re.compile(r"(mentions|legal|l%c3%a9gal|confidential|privacy|cgu|cgv|terms|tos\b|cookie|conditions|rgpd|"
                    r"gdpr|impressum|disclaimer|politique)", re.I)
HREFLANG = re.compile(r"^(x-default|[a-z]{2,3}(-[a-z]{4})?(-([a-z]{2}|\d{3}))?)$", re.I)


class Arret(Exception):
    pass


def dire(msg=""):
    print(msg, flush=True)


def jumeau(h):
    return h[4:] if h.startswith("www.") else "www." + h


def hote_de(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def site_saisi(s):
    s = s.strip()
    if s.startswith("sc-domain:"):
        s = s[len("sc-domain:"):]
    return hote_de(s if "//" in s else "https://" + s)


# --- sitemaps ---------------------------------------------------------------

def lire_sitemap(url, fichiers, urls, profondeur=0):
    if url in {f["url"] for f in fichiers} or profondeur > 3 or len(fichiers) >= 50:
        return
    r = net.suivre(url, "GET")
    info = {"url": url, "statut": r["statut"], "type": r["entetes"].get("content-type", "").split(";")[0],
            "gzip": False, "genre": "", "n": 0, "erreur": r["erreur"], "chaine": r["chaine"]}
    fichiers.append(info)
    if r["statut"] != 200:
        return
    brut = r["corps"]
    if brut[:2] == b"\x1f\x8b":
        import gzip
        info["gzip"] = True
        try:
            brut = gzip.decompress(brut)
        except OSError:
            info["genre"] = "illisible"
            return
    xml = brut.decode("utf-8", "replace")
    debut = xml.lstrip()[:500].lower()
    if "<html" in debut or "<!doctype html" in debut:
        info["genre"] = "html"
        return
    if "<sitemapindex" in xml:
        info["genre"] = "index"
        enfants = [x.strip() for x in re.findall(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\]]+?)\s*(?:\]\]>)?\s*</loc>", xml)]
        info["n"] = len(enfants)
        for e in enfants:
            lire_sitemap(e.replace("&amp;", "&"), fichiers, urls, profondeur + 1)
        return
    if "<urlset" not in xml:
        info["genre"] = "illisible"
        return
    info["genre"] = "urlset"
    for bloc in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\]]+?)\s*(?:\]\]>)?\s*</loc>", bloc)
        if not loc:
            continue
        lm = re.search(r"<lastmod>\s*([^<]+?)\s*</lastmod>", bloc)
        urls.append({"loc": loc.group(1).replace("&amp;", "&"), "lastmod": lm.group(1) if lm else "",
                     "fichier": url})
        info["n"] += 1


# --- Search Console ------------------------------------------------------------

def categorie_couverture(ir):
    v = (ir.get("verdict") or "").upper()
    c = (ir.get("coverageState") or "").lower()
    if v == "ERREUR":
        return "erreur"
    if v == "PASS":
        return "indexée"
    for motif, cat in (("inconnue", "inconnue"), ("ne reconnaît pas", "inconnue"), ("unknown", "inconnue"), ("détectée", "détectée"),
                       ("discovered", "détectée"), ("explorée", "explorée"), ("crawled", "explorée"),
                       ("noindex", "noindex"), ("robots", "bloquée par robots.txt"), ("soft", "soft 404"),
                       ("404", "introuvable"), ("introuvable", "introuvable"), ("not found", "introuvable"),
                       ("redirect", "redirection"), ("canoni", "canonique"), ("double", "canonique"),
                       ("duplicate", "canonique")):
        if motif in c:
            return cat
    return "autre"


def travail_gsc(prop, cibles_sitemap, accueil, hotes, maxi, sortie):
    """Tourne en fond pendant l'exploration. Remplit `sortie`, ne lève jamais."""
    try:
        try:
            sortie["sitemaps"] = [{
                "path": s.get("path"), "lastDownloaded": s.get("lastDownloaded", ""),
                "lastSubmitted": s.get("lastSubmitted", ""), "errors": int(s.get("errors", 0) or 0),
                "warnings": int(s.get("warnings", 0) or 0), "isPending": s.get("isPending", False),
                "submitted": sum(int(c.get("submitted", 0) or 0) for c in s.get("contents", []))}
                for s in g.sitemaps(prop)]
        except g.Panne as e:
            sortie["erreurs"].append("sitemaps : " + str(e).splitlines()[0])
        fin = dt.date.today() - dt.timedelta(days=3)
        debut = fin - dt.timedelta(days=89)
        sortie["fenetre"] = [debut.isoformat(), fin.isoformat()]
        agg = {}
        try:
            rows, _ = g.recherche(prop, debut.isoformat(), fin.isoformat(), ["page"], data_state="final")
            for r in rows:
                u = lec.normaliser(r["keys"][0])
                a = agg.setdefault(u, [0, 0])
                a[0] += int(r["clicks"])
                a[1] += int(r["impressions"])
        except g.Panne as e:
            sortie["erreurs"].append("pages vues par Google : " + str(e).splitlines()[0])
        sortie["pages_google"] = [{"url": u, "clics": c, "impressions": i}
                                  for u, (c, i) in sorted(agg.items(), key=lambda x: (-x[1][1], x[0]))]
        connues = {lec.normaliser(u) for u in cibles_sitemap}
        hors = [p["url"] for p in sortie["pages_google"] if hote_de(p["url"]) in hotes and p["url"] not in connues
                and lec.normaliser(accueil) != p["url"]]
        cibles, vus = [], set()
        for u, pourquoi in [(accueil, "accueil")] + [(u, "sitemap") for u in cibles_sitemap] + \
                [(u, "vue par Google, hors sitemap") for u in hors[:GOOGLE_HORS_SITEMAP_MAX]]:
            n = lec.normaliser(u)
            if n not in vus:
                vus.add(n)
                cibles.append((u, pourquoi))
        sortie["non_inspectees"] = max(0, len(cibles) - maxi)
        cibles = cibles[:maxi]

        def une(item):
            u, pourquoi = item
            try:
                ir = g.inspecter(prop, u)
            except g.Panne as e:
                ir = {"verdict": "ERREUR", "coverageState": str(e).splitlines()[0][:200]}
            return {"url": lec.normaliser(u), "demandee": u, "pourquoi": pourquoi,
                    "verdict": ir.get("verdict", ""), "couverture": ir.get("coverageState", ""),
                    "categorie": categorie_couverture(ir), "indexation": ir.get("indexingState", ""),
                    "robots": ir.get("robotsTxtState", ""), "recuperation": ir.get("pageFetchState", ""),
                    "dernier_crawl": (ir.get("lastCrawlTime") or "")[:10],
                    "canonique_google": ir.get("googleCanonical", ""),
                    "canonique_declaree": ir.get("userCanonical", ""),
                    "explore_comme": ir.get("crawledAs", "")}

        with ThreadPoolExecutor(4) as ex:
            sortie["inspections"] = list(ex.map(une, cibles))
    except Exception as e:  # rien de Search Console ne doit faire tomber l'audit
        sortie["erreurs"].append(f"{e.__class__.__name__} : {e}")


# --- Lighthouse ---------------------------------------------------------------

def travail_lighthouse(urls, sortie):
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        sortie["etat"] = "Node n'est pas installé (npx introuvable) : Lighthouse sauté. https://nodejs.org pour l'ajouter."
        return
    for u in urls:
        cmd = [npx, "--yes", "lighthouse@latest", u, "--quiet", "--chrome-flags=--headless", "--output=json",
               "--output-path=stdout", "--only-categories=performance,seo", "--form-factor=mobile"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        except subprocess.TimeoutExpired:
            sortie["pages"].append({"url": u, "erreur": "plus de 3 minutes, abandonné"})
            continue
        except OSError as e:
            sortie["etat"] = f"Lighthouse n'a pas pu se lancer ({e})."
            return
        sortie_json = p.stdout[p.stdout.find("{"):] if "{" in p.stdout else ""
        try:
            j = json.loads(sortie_json)
        except ValueError:
            err = " ".join(l.strip() for l in p.stderr.strip().splitlines()[-3:])[:240]
            if "chrome" in err.lower() and ("install" in err.lower() or "found" in err.lower()):
                sortie["etat"] = "Lighthouse n'a pas trouvé Chrome sur cet ordinateur : sauté."
                return
            sortie["pages"].append({"url": u, "erreur": err or f"code {p.returncode}"})
            continue
        if j.get("runtimeError"):
            sortie["pages"].append({"url": u, "erreur": j["runtimeError"].get("message", "")[:200]})
            continue
        au = j.get("audits", {})

        def val(k):
            return au.get(k, {}).get("numericValue")

        echecs = [au[r["id"]].get("title", r["id"]) for r in j.get("categories", {}).get("seo", {}).get("auditRefs", [])
                  if r.get("weight", 0) > 0 and au.get(r["id"], {}).get("score") == 0]
        sortie["pages"].append({
            "url": u,
            "performance": round(100 * (j["categories"].get("performance", {}).get("score") or 0)),
            "seo": round(100 * (j["categories"].get("seo", {}).get("score") or 0)),
            "lcp_ms": round(val("largest-contentful-paint") or 0),
            "cls": round(val("cumulative-layout-shift") or 0, 3),
            "tbt_ms": round(val("total-blocking-time") or 0),
            "echecs_seo": echecs, "version": j.get("lighthouseVersion", "")})
    sortie["etat"] = "ok"


# --- l'audit ------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", help="monsite.com, https://monsite.com/ ou sc-domain:monsite.com")
    ap.add_argument("--dossier", help="dossier racine des données (défaut ./seo, le même que search-console)")
    ap.add_argument("--max", type=int, default=300, help="pages lues au plus (défaut 300)")
    ap.add_argument("--sans-inspection", "--sans-search-console", dest="sans_gsc", action="store_true",
                    help="ne pas appeler Search Console")
    ap.add_argument("--sans-lighthouse", action="store_true", help="ne pas lancer Lighthouse")
    ap.add_argument("--inspection-max", type=int, default=150, help="URL inspectées au plus (quota : 2 000/jour)")
    ap.add_argument("--fils", type=int, default=5, help="requêtes en parallèle (4 à 6, défaut 5)")
    ap.add_argument("--delai", type=float, default=0.25, help="pause après chaque requête, par fil (défaut 0,25 s)")
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    a.fils = max(1, min(a.fils, 6))
    net.DELAI = max(0.0, a.delai)
    debut_audit = dt.datetime.now().replace(microsecond=0)

    # 1. le site et son accueil
    saisi = site_saisi(a.site)
    if not saisi or "." not in saisi:
        raise Arret(f"« {a.site} » n'est pas un nom de site. Exemple : python3 audit.py monsite.com")
    dire(f"Audit de {saisi}")
    r0 = net.suivre(f"https://{saisi}/")
    if r0["statut"] == 0:
        r1 = net.suivre(f"http://{saisi}/")
        if r1["statut"] == 0:
            raise Arret(f"{saisi} ne répond pas ({r0['erreur']}). Vérifie l'adresse, ou réessaie plus tard.")
        r0 = r1
    accueil = lec.normaliser(r0["url_finale"])
    hote = hote_de(accueil)
    schema = urllib.parse.urlsplit(accueil).scheme
    hotes = {hote, jumeau(hote)}
    if r0["statut"] in (401, 403, 429, 503) and not r0["chaine"]:
        dire(f"  ! l'accueil répond {r0['statut']} : le site refuse peut-être les robots (pare-feu). Je continue.")

    def interne(u):
        return hote_de(u) in hotes

    # 2. Search Console (facultatif)
    prop, note_gsc = None, ""
    if a.sans_gsc:
        note_gsc = "Search Console sautée (--sans-inspection)."
    elif g is None:
        note_gsc = ("Search Console non branchée : installe la skill `search-console` à côté de celle-ci et suis "
                    "son guide, puis relance l'audit.")
    else:
        try:
            g.racine(a.dossier)
            prop = g.resoudre_site(a.site)
        except g.Panne as e:
            note_gsc = ("Search Console non branchée (" + str(e).splitlines()[0].rstrip(".") +
                        ") : suis le guide de la skill `search-console`, puis relance l'audit.")
        except Exception as e:
            note_gsc = f"Search Console non branchée ({e.__class__.__name__}) : suis le guide de la skill `search-console`."
    dire("  Search Console : " + (prop or note_gsc))

    racine = os.path.abspath(os.path.expanduser(a.dossier or os.environ.get("GSC_DOSSIER") or "seo"))
    if prop:
        nom = g.nom_dossier(prop)
    else:
        nu = hote[4:] if hote.startswith("www.") else hote
        nom = hote if os.path.isdir(os.path.join(racine, hote)) and not os.path.isdir(os.path.join(racine, nu)) else nu
    dossier_site = os.path.join(racine, nom)
    sortie_dir = os.path.join(dossier_site, "seo-audit")
    os.makedirs(sortie_dir, exist_ok=True)

    # 3. robots.txt
    rr = net.suivre(f"{schema}://{hote}/robots.txt")
    robots_txt = net.texte(rr) if rr["statut"] == 200 else ""
    groupes, sm_robots = net.lire_robots(robots_txt)
    regles = net.regles_pour(groupes)
    robots = {"url": f"{schema}://{hote}/robots.txt", "statut": rr["statut"], "erreur": rr["erreur"],
              "type": rr["entetes"].get("content-type", "").split(";")[0],
              "html": "<html" in robots_txt[:600].lower() or "<!doctype" in robots_txt[:600].lower(),
              "sitemaps": sm_robots, "regles": [[("Allow" if p else "Disallow"), m] for p, m in regles],
              "tout_bloque": any((not p) and m.strip() == "/" for p, m in regles)}
    dire(f"  robots.txt : {rr['statut']}, {len(sm_robots)} sitemap(s) déclaré(s)")

    # 4. sitemaps
    fichiers, sm = [], []
    for u in sm_robots:
        lire_sitemap(u, fichiers, sm)
    if not sm_robots:
        for chemin_sm in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml", "/wp-sitemap.xml"):
            avant = len(fichiers)
            lire_sitemap(f"{schema}://{hote}{chemin_sm}", fichiers, sm)
            if any(f["statut"] == 200 and f["genre"] in ("urlset", "index") for f in fichiers[avant:]):
                break
    vus_sm, doublons_sm, sitemap = set(), [], []
    for e in sm:
        n = lec.normaliser(e["loc"])
        if n in vus_sm:
            doublons_sm.append(e["loc"])
            continue
        vus_sm.add(n)
        e["url"] = n
        sitemap.append(e)
    dire(f"  sitemap : {len(sitemap)} URL dans {len([f for f in fichiers if f['genre'] == 'urlset'])} fichier(s)")

    # 5. tâches de fond : Search Console et Lighthouse
    gsc = {"propriete": prop, "sitemaps": [], "pages_google": [], "inspections": [], "erreurs": [],
           "non_inspectees": 0, "fenetre": []}
    lh = {"etat": "", "pages": []}
    fonds = []
    if prop:
        locs = [e["loc"] for e in sitemap if interne(e["url"])]
        t = threading.Thread(target=travail_gsc, args=(prop, locs, accueil, hotes, a.inspection_max, gsc), daemon=True)
        t.start()
        fonds.append(t)
    lh_urls = [accueil] + [e["url"] for e in sitemap if interne(e["url"]) and e["url"] != accueil
                           and not FICHIER.search(urllib.parse.urlsplit(e["url"]).path)][:2]
    if a.sans_lighthouse:
        lh["etat"] = "Lighthouse sauté (--sans-lighthouse)."
    else:
        t = threading.Thread(target=travail_lighthouse, args=(lh_urls, lh), daemon=True)
        t.start()
        fonds.append(t)

    # 6. exploration : accueil + sitemap, puis les pages trouvées par les liens
    R, finales = {}, {}

    def charger(u):
        fichier = bool(FICHIER.search(urllib.parse.urlsplit(u).path))
        r = net.suivre(u, "HEAD" if fichier else "GET", lire=not fichier)
        res = {"url": u, "statut": r["statut"], "chaine": r["chaine"], "url_finale": lec.normaliser(r["url_finale"]),
               "ttfb_ms": r["ttfb_ms"], "erreur": r["erreur"], "entetes": r["entetes"],
               "type": r["entetes"].get("content-type", "").split(";")[0].strip().lower()}
        if not fichier and r["statut"] == 200 and ("html" in res["type"] or not res["type"]) \
                and interne(res["url_finale"]):
            res["page"] = lec.lire(net.texte(r), r["url_finale"])
        return res

    file_ = [accueil] + [e["url"] for e in sitemap if interne(e["url"])]
    file_ = list(dict.fromkeys(file_))
    pages_lues, fichiers_lus, non_lues, vague = 0, 0, 0, 0
    with ThreadPoolExecutor(a.fils) as ex:
        while file_ and vague < 8:
            pages_lot = [u for u in file_ if not FICHIER.search(urllib.parse.urlsplit(u).path)]
            fich_lot = [u for u in file_ if FICHIER.search(urllib.parse.urlsplit(u).path)]
            reste_p, reste_f = max(0, a.max - pages_lues), max(0, FICHIERS_MAX - fichiers_lus)
            non_lues += max(0, len(pages_lot) - reste_p)
            lot = pages_lot[:reste_p] + fich_lot[:reste_f]
            pages_lues += min(len(pages_lot), reste_p)
            fichiers_lus += min(len(fich_lot), reste_f)
            if not lot:
                break
            dire(f"  lecture : {len(lot)} URL (vague {vague + 1})…")
            nouveaux = set()
            for res in ex.map(charger, lot):
                R[res["url"]] = res
                finales.setdefault(res["url_finale"], res)
                p = res.get("page")
                if not p:
                    continue
                for l in p["liens"]:
                    if interne(l["url"]):
                        nouveaux.add(lec.sans_suivi(l["url"])[0])
                for c in p["canoniques"][:1]:
                    cu = lec.normaliser(urllib.parse.urljoin(res["url_finale"], c))
                    if interne(cu):
                        nouveaux.add(cu)
            file_ = sorted(u for u in nouveaux if u not in R and u not in finales)
            vague += 1

    pages = {}
    for res in R.values():
        if res.get("page") and res["url_finale"] not in pages:
            pages[res["url_finale"]] = res
    dans_sitemap = {e["url"] for e in sitemap}
    lastmod = {e["url"]: e["lastmod"] for e in sitemap}

    def cible(u):
        """(url finale, statut, nombre de redirections) d'une URL interne, si elle a été lue."""
        propre = lec.sans_suivi(u)[0]
        r = R.get(propre) or R.get(u) or finales.get(propre)
        if r:
            return r["url_finale"], r["statut"], len(r["chaine"])
        return propre, None, None

    # 7. les liens : gabarit, texte ou navigation, entrants et sortants
    cles = Counter()
    for url, res in pages.items():
        cles.update({(l["url"], l["texte"], l["place"]) for l in res["page"]["liens"]
                     if interne(l["url"]) and l["zone"] in ("texte", "bloc de liens")})
    seuil_gabarit = max(GABARIT_MIN, math.ceil(GABARIT_PART * len(pages)))
    gabarit = {k: n for k, n in cles.items() if n >= seuil_gabarit} if len(pages) >= 8 else {}
    entrants_t, entrants_b, entrants_n = defaultdict(set), defaultdict(set), defaultdict(set)
    sortants_t, sortants_b, sortants_n = defaultdict(set), defaultdict(set), defaultdict(set)
    liens, externes, suivi_internes, casses, vers_redir = [], Counter(), [], [], []
    zones = Counter()
    for url in sorted(pages):
        p = pages[url]["page"]
        for l in p["liens"]:
            zone = l["zone"]
            if zone in ("texte", "bloc de liens") and (l["url"], l["texte"], l["place"]) in gabarit:
                zone = f"gabarit ({gabarit[(l['url'], l['texte'], l['place'])]} pages)"
            if not interne(l["url"]):
                externes[l["url"]] += 1
                liens.append({"source": url, "cible": l["url"], "cible_finale": "", "zone": zone, "texte": l["texte"],
                              "statut_cible": "", "redirections": "", "interne": "non", "suivi": "",
                              "nofollow": "oui" if l["nofollow"] else ""})
                continue
            fin, statut, sauts = cible(l["url"])
            params = lec.sans_suivi(l["url"])[1]
            if fin == url:
                continue
            genre = zone if zone in ("texte", "bloc de liens") else "navigation"
            zones[genre] += 1
            {"texte": entrants_t, "bloc de liens": entrants_b, "navigation": entrants_n}[genre][fin].add(url)
            {"texte": sortants_t, "bloc de liens": sortants_b, "navigation": sortants_n}[genre][url].add(fin)
            if params:
                suivi_internes.append((url, l["url"], params))
            if statut is not None and (statut == 0 or statut >= 400):
                casses.append((url, l["url"], statut, l["texte"]))
            elif sauts:
                vers_redir.append((url, l["url"], fin))
            liens.append({"source": url, "cible": l["url"], "cible_finale": fin, "zone": zone, "texte": l["texte"],
                          "statut_cible": statut if statut is not None else "non lue",
                          "redirections": sauts if sauts is not None else "", "interne": "oui",
                          "suivi": " ".join(params), "nofollow": "oui" if l["nofollow"] else ""})

    # 8. images, liens externes, assets, variantes, page inexistante (en parallèle)
    imgs = defaultdict(lambda: {"pages": set(), "alt_absent": 0, "moderne": False})
    for url, res in pages.items():
        for im in res["page"]["images"]:
            d = imgs[lec.normaliser(im["src"])]
            d["pages"].add(url)
            d["moderne"] = d["moderne"] or im["moderne"]
            if im["alt"] is None:
                d["alt_absent"] += 1
    a_tester = sorted(imgs, key=lambda u: (-len(imgs[u]["pages"]), u))[:IMAGES_MAX]
    ext_tester = sorted(externes, key=lambda u: (-externes[u], u))[:EXTERNES_MAX]
    assets = []
    for u in [accueil] + lh_urls[1:2]:
        if u in pages:
            assets += [x for x in pages[u]["page"]["assets"] if x not in assets]
    assets = assets[:ASSETS_MAX]
    graine = hashlib.sha1(hote.encode()).hexdigest()[:8]
    inexistante = f"{schema}://{hote}/seo-audit-page-qui-n-existe-pas-{graine}"
    exemple = next((e["url"] for e in sitemap if e["url"] in R and R[e["url"]]["statut"] == 200
                    and not R[e["url"]]["chaine"] and e["url"] != accueil
                    and not FICHIER.search(urllib.parse.urlsplit(e["url"]).path)), None)
    variante_slash = None
    if exemple:
        ps = urllib.parse.urlsplit(exemple)
        autre = ps.path[:-1] if ps.path.endswith("/") else ps.path + "/"
        variante_slash = urllib.parse.urlunsplit((ps.scheme, ps.netloc, autre, ps.query, ""))

    def tete(u):
        r = net.suivre(u, "HEAD")
        return u, {"statut": r["statut"], "finale": r["url_finale"], "erreur": r["erreur"],
                   "taille": int(r["entetes"].get("content-length") or 0) or None,
                   "type": r["entetes"].get("content-type", "").split(";")[0].strip().lower(),
                   "cache": r["entetes"].get("cache-control", ""), "chaine": r["chaine"]}

    def page_brute(u):
        r = net.suivre(u, "GET")
        p = lec.lire(net.texte(r), r["url_finale"]) if r["statut"] == 200 else None
        return u, {"statut": r["statut"], "chaine": r["chaine"], "finale": lec.normaliser(r["url_finale"]),
                   "erreur": r["erreur"], "canonique": (p["canoniques"][0] if p and p["canoniques"] else ""),
                   "hsts": r["entetes"].get("strict-transport-security", "")}

    dire(f"  vérifications : {len(a_tester)} images, {len(ext_tester)} liens externes, {len(assets)} fichiers CSS/JS…")
    variantes_urls = [f"http://{hote}/", f"https://{jumeau(hote)}/", f"http://{jumeau(hote)}/"]
    with ThreadPoolExecutor(a.fils) as ex:
        f_img = ex.map(tete, a_tester)
        f_ext = ex.map(tete, ext_tester)
        f_ass = ex.map(tete, [u for _, u in assets])
        f_var = ex.map(page_brute, variantes_urls + [inexistante] + ([variante_slash] if variante_slash else []))
        res_img, res_ext, res_ass, res_var = dict(f_img), dict(f_ext), dict(f_ass), dict(f_var)

    # 9. on attend les tâches de fond
    if fonds:
        dire("  on attend Search Console et Lighthouse…")
    for t in fonds:
        t.join(timeout=max(5, 600 - (time.monotonic() - t0)))
    if not lh["etat"] and not a.sans_lighthouse:
        lh["etat"] = "Lighthouse n'a pas fini à temps : sauté."
    insp = {i["url"]: i for i in gsc["inspections"]}

    # 10. le tableau des pages
    lignes_pages = []
    lignes = {u: res for u, res in R.items()}
    for fu, res in pages.items():
        if fu not in lignes:  # page atteinte seulement par redirection : sa propre ligne
            lignes[fu] = dict(res, url=fu, chaine=[])
    for url in sorted(lignes):
        res = lignes[url]
        p = None if res["chaine"] else res.get("page")
        ir = insp.get(url, {})
        can = p["canoniques"][0] if p and p["canoniques"] else ""
        can_abs = lec.normaliser(urllib.parse.urljoin(url, can)) if can else ""
        xrt = (res["entetes"].get("x-robots-tag") or "") if not res["chaine"] else ""
        lignes_pages.append({
            "url": url, "dans_sitemap": "oui" if url in dans_sitemap else "non", "statut": res["statut"],
            "url_finale": res["url_finale"] if res["chaine"] else "", "redirections": len(res["chaine"]),
            "erreur": res["erreur"], "type": res["type"],
            "ttfb_ms": res["ttfb_ms"] if res["ttfb_ms"] is not None and not res["chaine"] else "",
            "noindex": "oui" if p and (p["noindex"] or "noindex" in xrt.lower()) else "",
            "x_robots_tag": xrt,
            "mots": p["mots"] if p else "", "title": (p["titres"][0] if p and p["titres"] else ""),
            "longueur_title": len(p["titres"][0]) if p and p["titres"] else "",
            "nb_title": len(p["titres"]) if p else "",
            "description": (p["description"] or "") if p else "",
            "longueur_description": (len(p["description"] or "")) if p else "",
            "nb_h1": len(p["h1"]) if p else "", "h1": (p["h1"][0] if p and p["h1"] else ""),
            "canonique": can_abs, "nb_canoniques": len(p["canoniques"]) if p else "",
            "lang": (p["lang"] or "") if p else "", "viewport": ("oui" if p["viewport"] else "non") if p else "",
            "hreflang": " ".join(f"{c}={u}" for c, u in p["hreflang"]) if p else "",
            "jsonld": " ".join(p["jsonld_types"]) if p else "", "jsonld_erreurs": p["jsonld_erreurs"] if p else "",
            "og": " ".join(sorted(k[3:] for k in p["og"])) if p else "",
            "images": len(p["images"]) if p else "",
            "images_sans_alt": sum(1 for i in p["images"] if i["alt"] is None) if p else "",
            "dates": " ; ".join(f"{k}={v}" for k, v in p["dates"].items()) if p else "",
            "lastmod_sitemap": lastmod.get(url, ""),
            "entrants_texte": len(entrants_t.get(url, ())), "entrants_blocs": len(entrants_b.get(url, ())),
            "entrants_nav": len(entrants_n.get(url, ())),
            "sortants_texte": len(sortants_t.get(url, ())), "sortants_blocs": len(sortants_b.get(url, ())),
            "sortants_nav": len(sortants_n.get(url, ())),
            "liens_externes": len({l["url"] for l in p["liens"] if not interne(l["url"])}) if p else "",
            "gsc_categorie": ir.get("categorie", ""), "gsc_couverture": ir.get("couverture", ""),
            "gsc_dernier_crawl": ir.get("dernier_crawl", ""), "gsc_canonique_google": ir.get("canonique_google", ""),
        })

    A = {
        "site": hote, "saisi": a.site, "accueil": accueil, "date": debut_audit.isoformat(),
        "dossier": sortie_dir, "propriete": prop, "note_gsc": note_gsc,
        "options": {"max": a.max, "fils": a.fils, "delai": net.DELAI, "inspection_max": a.inspection_max},
        "accueil_reponse": {"statut": r0["statut"], "chaine": r0["chaine"], "hsts": r0["entetes"].get("strict-transport-security", ""),
                            "ttfb_ms": r0["ttfb_ms"]},
        "robots": robots, "sitemap_fichiers": fichiers, "sitemap": sitemap, "sitemap_doublons": doublons_sm,
        "pages_lues": pages_lues, "pages_non_lues": non_lues, "fichiers_lus": fichiers_lus,
        "seuil_gabarit": seuil_gabarit if gabarit else None, "gabarit": len(gabarit), "zones": dict(zones),
        "images": {u: {"pages": len(imgs[u]["pages"]), "alt_absent": imgs[u]["alt_absent"], "moderne": imgs[u]["moderne"],
                       **res_img.get(u, {})} for u in sorted(imgs)},
        "images_testees": len(a_tester),
        "externes": {u: {"occurrences": externes[u], **res_ext.get(u, {})} for u in sorted(externes)},
        "externes_testes": len(ext_tester),
        "assets": [{"type": t, "url": u, **res_ass.get(u, {})} for t, u in assets],
        "variantes": {u: res_var.get(u) for u in variantes_urls},
        "inexistante": {"url": inexistante, **(res_var.get(inexistante) or {})},
        "slash": {"exemple": exemple, "variante": variante_slash, **(res_var.get(variante_slash) or {})} if variante_slash else None,
        "casses": casses, "vers_redirections": vers_redir, "suivi_internes": suivi_internes,
        "gsc": gsc, "lighthouse": lh, "lighthouse_urls": lh_urls,
        "pages": lignes_pages,
    }
    A["duree_s"] = round(time.monotonic() - t0)
    constats, bien, resume = rapport.analyser(A, pages, R, (entrants_t, entrants_b, entrants_n),
                                              (sortants_t, sortants_b), interne)
    A["constats"], A["ok"], A["resume"] = constats, bien, resume

    # 11. les fichiers
    precedent = None
    pj = os.path.join(sortie_dir, "audit.json")
    if os.path.exists(pj):
        try:
            with open(pj, encoding="utf-8") as f:
                old = json.load(f)
            precedent = {"date": old.get("date", ""), "resume": old.get("resume", {})}
        except (OSError, ValueError):
            precedent = None
    pm = os.path.join(sortie_dir, "AUDIT.md")
    if os.path.exists(pm) and precedent and precedent["date"][:10]:
        archive = os.path.join(sortie_dir, f"AUDIT-{precedent['date'][:10]}.md")
        if not os.path.exists(archive) and precedent["date"][:10] != debut_audit.date().isoformat():
            shutil.copyfile(pm, archive)
    A["precedent"] = precedent
    cols_p = list(lignes_pages[0].keys()) if lignes_pages else ["url"]
    with open(os.path.join(sortie_dir, "pages.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols_p)
        w.writeheader()
        w.writerows(lignes_pages)
    cols_l = ["source", "cible", "cible_finale", "zone", "texte", "statut_cible", "redirections", "interne", "suivi",
              "nofollow"]
    with open(os.path.join(sortie_dir, "liens.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols_l)
        w.writeheader()
        w.writerows(sorted(liens, key=lambda l: (l["source"], l["interne"] != "oui", l["cible"], l["zone"], l["texte"])))
    journal = os.path.join(dossier_site, "journal.csv")
    if not os.path.exists(journal):
        with open(journal, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["en_ligne", "ajustement", "url", "attendu_index", "requete", "attendu", "relire_le",
                                    "statut", "constat", "constat_le"])
    A["journal"] = rapport.lire_journal(journal)
    A["duree_s"] = round(time.monotonic() - t0)
    with open(pj, "w", encoding="utf-8") as f:
        json.dump(A, f, ensure_ascii=False, indent=1, default=list)
    with open(pm, "w", encoding="utf-8") as f:
        f.write(rapport.markdown(A))

    # 12. le bloc imprimé
    dire("")
    for ligne in rapport.bloc_resume(A):
        dire(ligne)
    dire(f"\nRAPPORT {pm}")
    dire(f"DÉTAIL  {os.path.join(sortie_dir, 'pages.csv')} · liens.csv · audit.json")
    n = open(pm, encoding="utf-8").read().count("<!-- CLAUDE:")
    dire(f"AUDIT.md : {n} marqueurs « <!-- CLAUDE: » à remplir. Durée : {A['duree_s']} s.")


if __name__ == "__main__":
    try:
        main()
    except Arret as e:
        sys.exit("ERREUR : " + str(e))
    except KeyboardInterrupt:
        sys.exit("Interrompu.")
