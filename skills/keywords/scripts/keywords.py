#!/usr/bin/env python3
"""Quoi écrire ensuite : les mots-clés tirés de ce que ton site a déjà dans Search Console,
complétés par les suggestions Google, avec un verdict par candidat (nouvelle page, ou renforcer
une page qui existe). Sans outil payant.

Usage :
  python3 keywords.py monsite.com [--dossier ./seo] [--theme "mot"] [--sans-suggestions]
                      [--langue fr --pays fr] [--marque "mon nom"] [--rafraichir]
  python3 keywords.py monsite.com --verifier "requête"

1. Search Console, par la skill search-console installée à côté (obligatoire ici) : requêtes x
   pages, requêtes seules, pages seules, sur les 28 derniers jours finaux et les 28 d'avant.
   Les fichiers de ./seo/<site>/donnees/ (écrits par search-console) sont repris s'ils ont moins
   de 2 jours, sinon le script appelle l'API et garde ses appels dans keywords/donnees/.
2. Les gisements : déjà classé sans page dédiée, page 2, gros gisements lointains,
   cannibalisation, requêtes neuves, questions. Ce qui fait moins de 10 impressions sur 28 jours
   est sous le bruit et montré à part.
3. Google Suggest (gratuit, sans clé) : chaque graine, puis « graine a », « graine c »...
   60 appels au plus, 2 s entre deux. Un refus (403, 429) arrête les suggestions, pas le rapport.

Écrit ./seo/<site>/keywords/ : MOTS-CLES.md (tous les chiffres posés par le script, des
marqueurs <!-- CLAUDE: --> là où Claude juge), candidats.csv, suggestions.csv, donnees/.
--verifier refait un contrôle frais d'une requête (28 derniers jours, données provisoires
comprises) avant d'écrire une page : les gisements bougent.

Python 3.10+, bibliothèque standard seulement.
"""
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(errors="replace")

ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ici, "..", "..", "search-console", "scripts"))
try:
    import gsc_api as g
except ImportError:
    g = None

UA = "skill-keywords/1"
PLANCHER = 10             # impressions sur 28 j : en dessous, c'est du bruit
PAGE2_MIN = 20            # impressions minimales d'une requête en page 2
LOIN_MIN = 50             # impressions minimales d'un gros gisement lointain (par groupe)
PART_CANNIBALE = 0.20     # part des impressions d'une requête à partir de laquelle une page compte
CANNIBALE_MIN = (30, 10)  # impressions minimales d'une requête testée (site établi, petit site)
SEUIL_ETABLI, SEUIL_NEUF = 200, 30   # clics sur 28 j, les mêmes que search-console
FRAIS_HEURES = 48         # au-delà, les données reprises sont trop vieilles
UBIQUITE = 0.25           # un mot présent dans 25 % des requêtes ne sert pas à grouper (« paris »)
SUGGEST_MAX, SUGGEST_DELAI = 60, 2.0
GRAINES_MAX = 15
LETTRES = "acegikmoqsuwy"  # une lettre sur deux
TITRES_MAX = 80
LIGNES = 25               # lignes par tableau dans le rapport (tout est dans candidats.csv)
BLOCS_PAR_GISEMENT, BLOCS_MAX = 3, 15

STOP = set("""
a ai aie as au aux avec avoir c ca ce ceci cela celle celles celui ces cet cette chez combien
comment d dans de des du elle elles en es est et etre eu fait faire faut il ils j je l la le les
leur leurs lui m ma mais me meme mes moi mon n ne ni nos notre nous on ont ou par pas peu peut plus
pour pourquoi qu quand que quel quelle quelles quels qui quoi s sa sans se sera ses si son sont
sous sur t ta te tes toi ton tous tout toute toutes tres tu un une vos votre vous y
about after all also am an and any are at be been before being but by can could did do does doing
for from get got had has have he her here him his how i if in into is it its just more most my no
not of off on only or other our out over own same she should so some such than that the their them
then there these they this those through to too under up very was we were what when where which
while who whom whose why will with would you your vs versus much many way per
""".split())
TLD = set("com net org fr io co eu mt uk de be ch ca es it info app dev gov edu ai me tv".split())
PAGES_HTML = ("", ".html", ".htm", ".php", ".asp", ".aspx")
QUESTIONS = set("""
comment pourquoi combien quel quelle quels quelles ou quand qui que qu est peut faut quoi lequel
laquelle how why what when where which who whom whose can could is are do does did should will would
am was were
""".split())
MODIFS = set("""
best top good great cheap cheapest free guide list new latest idea tip example review online official
complete ultimate easy simple near meilleur meilleure gratuit gratuite liste exemple avis idee conseil
astuce nouveau nouvelle ligne complet facile cher month monthly hour hourly year yearly annual today now
mois mensuel heure an annee annuel aujourd hui
""".split())


class Arret(Exception):
    """Erreur lisible par un humain, sans trace Python."""


PANNES = (Arret,) + ((g.Panne,) if g else ())


def dire(msg=""):
    print(msg, flush=True)


# --- mots ---------------------------------------------------------------------------------------

def normaliser(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[\W_]+", " ", s).strip()


def racine_mot(w):
    """Un singulier grossier, le même des deux côtés (requête et page) : beaches, beach -> beach."""
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("ches", "shes", "sses", "xes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


MODIFS = {racine_mot(m) for m in MODIFS}


def mots(q):
    """Les mots qui portent le sens : sans mots vides, sans chiffres, au singulier grossier."""
    out = []
    for w in normaliser(q).split():
        if len(w) < 2 or w.isdigit() or w in STOP:
            continue
        r = racine_mot(w)
        if r not in out:
            out.append(r)
    return out


def est_question(q):
    n = normaliser(q).split()
    return "?" in q or (bool(n) and n[0] in QUESTIONS)


def index_page(url, titre):
    chemin = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    t = normaliser(chemin + " " + (titre or ""))
    return {racine_mot(w) for w in t.split()}, t.replace(" ", "")


def porte(mot, idx):
    toks, compact = idx
    return mot in toks or (len(mot) >= 4 and mot in compact)


def couverture(mq, idx):
    if not mq:
        return None
    return sum(1 for m in mq if porte(m, idx)) / len(mq)


# --- chiffres -----------------------------------------------------------------------------------

def fusion(a, b):
    c, i = a[0] + b[0], a[1] + b[1]
    p = (a[2] * a[1] + b[2] * b[1]) / i if i else min(a[2], b[2])
    return (c, i, p)


def sans_fragment(u):
    return u.split("#", 1)[0]


def lire_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ecrire_csv(path, entete, lignes):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(entete)
        w.writerows(lignes)


def ligne(r):
    return (int(r["clics"]), int(r["impressions"]), float(r["position"]))


def charger_q(path):
    out = {}
    for r in lire_csv(path):
        q = r["requete"]
        out[q] = fusion(out[q], ligne(r)) if q in out else ligne(r)
    return out


def charger_qp(path):
    out = {}
    for r in lire_csv(path):
        q, p = r["requete"], sans_fragment(r["page"])
        d = out.setdefault(q, {})
        d[p] = fusion(d[p], ligne(r)) if p in d else ligne(r)
    return out


def charger_p(rows):
    out = {}
    for r in rows:
        p = sans_fragment(r["page"])
        out[p] = fusion(out[p], ligne(r)) if p in out else ligne(r)
    return out


def age_heures(path):
    return (time.time() - os.path.getmtime(path)) / 3600


FICHIERS_SC = ["requetes_w1.csv", "requetes_w0.csv", "requetes_pages_w1.csv", "requetes_pages_w0.csv",
               "pages_jours.csv", "jours.csv", "meta.json"]
FICHIERS_KW = ["requetes_w1.csv", "requetes_w0.csv", "requetes_pages_w1.csv", "requetes_pages_w0.csv",
               "pages_w1.csv", "pages_w0.csv", "meta.json"]


def depuis_search_console(site_dir):
    """Les fichiers de search-console (collecte.py), s'ils sont complets et récents."""
    d = os.path.join(site_dir, "donnees")
    if not all(os.path.exists(os.path.join(d, f)) for f in FICHIERS_SC):
        return None
    if age_heures(os.path.join(d, "requetes_pages_w1.csv")) > FRAIS_HEURES:
        return None
    with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    D = {"w1": meta["w1"], "w0": meta["w0"], "origine": "search-console",
         "source": f"reprises de donnees/ (collecte search-console du {meta.get('collecte_le', '?')[:16].replace('T', ' ')})"}
    D["Q"] = {w: charger_q(os.path.join(d, f"requetes_{w}.csv")) for w in ("w1", "w0")}
    D["QP"] = {w: charger_qp(os.path.join(d, f"requetes_pages_{w}.csv")) for w in ("w1", "w0")}
    jours = lire_csv(os.path.join(d, "jours.csv"))
    pj = lire_csv(os.path.join(d, "pages_jours.csv"))
    D["P"], D["totaux"] = {}, {}
    for w in ("w1", "w0"):
        a, b = D[w]
        D["P"][w] = charger_p([r for r in pj if a <= r["date"] <= b])
        sel = [r for r in jours if a <= r["date"] <= b]
        D["totaux"][w] = [sum(int(r["clics"]) for r in sel), sum(int(r["impressions"]) for r in sel)]
    D["sitemap"] = []
    sm = os.path.join(d, "sitemap_urls.txt")
    if os.path.exists(sm):
        D["sitemap"] = [l.strip() for l in open(sm, encoding="utf-8") if l.strip()]
    return D


def depuis_cache(cache):
    if not all(os.path.exists(os.path.join(cache, f)) for f in FICHIERS_KW):
        return None
    if age_heures(os.path.join(cache, "meta.json")) > FRAIS_HEURES:
        return None
    with open(os.path.join(cache, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    D = {"w1": meta["w1"], "w0": meta["w0"], "totaux": meta["totaux"], "origine": "cache",
         "source": f"reprises de keywords/donnees/ (appel API du {meta['collecte_le'][:16].replace('T', ' ')})"}
    D["Q"] = {w: charger_q(os.path.join(cache, f"requetes_{w}.csv")) for w in ("w1", "w0")}
    D["QP"] = {w: charger_qp(os.path.join(cache, f"requetes_pages_{w}.csv")) for w in ("w1", "w0")}
    D["P"] = {w: charger_p(lire_csv(os.path.join(cache, f"pages_{w}.csv"))) for w in ("w1", "w0")}
    D["sitemap"] = []
    return D


def exiger_gsc():
    if g is None:
        raise Arret("Search Console non branchée : cette skill lit tes requêtes dans Search Console.\n"
                    "Installe la skill search-console à côté de celle-ci (même dossier skills/), suis son guide\n"
                    "(references/installation.md), puis relance.")


def collecter(site, cache):
    """Les appels API : ~8 requêtes, une minute au plus."""
    exiger_gsc()
    g.token()
    iso = dt.date.isoformat
    today = dt.date.today()
    rows, _ = g.recherche(site, iso(today - dt.timedelta(days=75)), iso(today), ["date"], data_state="final")
    if not rows:
        raise Arret(f"{site} ne renvoie aucune donnée de recherche (site trop neuf, ou propriété vide).")
    L = dt.date.fromisoformat(max(r["keys"][0] for r in rows))
    w1 = (L - dt.timedelta(days=27), L)
    w0 = (L - dt.timedelta(days=55), L - dt.timedelta(days=28))
    totaux = {}
    for nom, (a, b) in (("w1", w1), ("w0", w0)):
        sel = [r for r in rows if iso(a) <= r["keys"][0] <= iso(b)]
        totaux[nom] = [int(sum(r["clicks"] for r in sel)), int(sum(r["impressions"] for r in sel))]
    travaux = [(nom, dims, fichier, cols) for nom in ("w1", "w0")
               for dims, fichier, cols in ((["query"], "requetes", ["requete"]),
                                           (["query", "page"], "requetes_pages", ["requete", "page"]),
                                           (["page"], "pages", ["page"]))]

    def un(t):
        nom, dims, fichier, cols = t
        a, b = w1 if nom == "w1" else w0
        r, _ = g.recherche(site, iso(a), iso(b), dims, data_state="final")
        return t, r

    os.makedirs(cache, exist_ok=True)
    with ThreadPoolExecutor(3) as ex:
        for (nom, dims, fichier, cols), r in ex.map(un, travaux):
            ecrire_csv(os.path.join(cache, f"{fichier}_{nom}.csv"), cols + ["clics", "impressions", "position"],
                       [x["keys"][:len(dims)] + [int(x["clicks"]), int(x["impressions"]), round(x["position"], 2)]
                        for x in r])
    meta = {"site": site, "collecte_le": dt.datetime.now().isoformat(timespec="seconds"),
            "w1": [iso(w1[0]), iso(w1[1])], "w0": [iso(w0[0]), iso(w0[1])], "totaux": totaux}
    with open(os.path.join(cache, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    D = depuis_cache(cache)
    D["source"] = f"API Search Console, appelée le {meta['collecte_le'][:16].replace('T', ' ')}"
    D["origine"] = "api"
    return D


# --- le web -------------------------------------------------------------------------------------

def telecharger(url, timeout=15, maxi=800_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(maxi)
        typ = r.headers.get("Content-Type", "")
        cs = r.headers.get_content_charset() or "utf-8"
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode(cs, "replace"), typ


def lire_titre(url):
    try:
        txt, typ = telecharger(url)
    except Exception as e:  # un site qui refuse une page ne fait pas planter le reste
        return url, {"titre": None, "lang": None, "erreur": str(e)[:120]}
    if typ and "html" not in typ:
        return url, {"titre": None, "lang": None, "erreur": "pas du HTML"}
    m = re.search(r"<title[^>]*>(.*?)</title>", txt, re.S | re.I)
    lang = re.search(r"<html[^>]*\blang=[\"']?([A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,4})?)", txt, re.I)
    titre = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
    return url, {"titre": titre, "lang": lang.group(1) if lang else None, "erreur": None}


def lire_titres(urls):
    with ThreadPoolExecutor(6) as ex:
        return dict(ex.map(lire_titre, urls))


def urls_sitemap(base):
    """Les URL du sitemap (robots.txt, sinon /sitemap.xml), 5 000 au plus. Vide si rien ne répond."""
    a_lire = []
    try:
        txt, _ = telecharger(urllib.parse.urljoin(base, "/robots.txt"), timeout=10)
        a_lire = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", txt)
    except Exception:
        pass
    a_lire = a_lire or [urllib.parse.urljoin(base, "/sitemap.xml"), urllib.parse.urljoin(base, "/sitemap_index.xml")]
    vus, out = set(), []
    while a_lire and len(vus) < 25 and len(out) < 5000:
        u = a_lire.pop(0)
        if u in vus:
            continue
        vus.add(u)
        try:
            xml, _ = telecharger(u, timeout=15, maxi=20_000_000)
        except Exception:
            continue
        locs = [html.unescape(l.strip()) for l in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml)]
        if "<sitemapindex" in xml:
            a_lire += locs
        else:
            out += locs
        if out and not a_lire:
            break
    return list(dict.fromkeys(out))[:5000]


def appel_suggest(q, langue, pays):
    url = "https://suggestqueries.google.com/complete/search?" + urllib.parse.urlencode(
        {"client": "firefox", "hl": langue, "gl": pays, "ie": "utf-8", "oe": "utf-8", "q": q})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read()
        cs = r.headers.get_content_charset() or "utf-8"
    data = json.loads(raw.decode(cs, "replace"))
    return [s for s in data[1] if isinstance(s, str)]


def suggestions(graines, langue, pays, cache_path):
    """Les appels Suggest, dans un ordre fixe : chaque graine seule, puis « graine a », « graine c »… pour
    les graines qui ont répondu, jusqu'à 60 appels. Un cache de 2 jours évite de redemander."""
    cache = {}
    if os.path.exists(cache_path) and age_heures(cache_path) <= FRAIS_HEURES:
        try:
            with open(cache_path, encoding="utf-8") as f:
                c = json.load(f)
            if c.get("langue") == langue and c.get("pays") == pays:
                cache = c.get("appels", {})
        except (OSError, ValueError):
            cache = {}
    etat = {"faits": 0, "repris": 0, "refus": None, "erreurs": 0}
    res, appels = {}, []

    def un(gr, q):
        if len(appels) >= SUGGEST_MAX:
            return None
        appels.append((gr, q))
        if q in cache:
            res[q] = cache[q]
            etat["repris"] += 1
            return res[q]
        if etat["refus"]:
            return None
        if etat["faits"]:
            time.sleep(SUGGEST_DELAI)
        try:
            res[q] = cache[q] = appel_suggest(q, langue, pays)
            etat["faits"] += 1
            etat["erreurs"] = 0
            return res[q]
        except urllib.error.HTTPError as e:
            etat["refus"] = (f"Google a refusé (HTTP {e.code}) après {etat['faits']} appel(s) : suggestions arrêtées, "
                             "le reste du rapport est complet.")
        except Exception as e:  # réseau, réponse illisible
            etat["erreurs"] += 1
            etat["faits"] += 1
            if etat["erreurs"] >= 3:
                etat["refus"] = (f"trois erreurs de suite ({str(e)[:80]}) : suggestions arrêtées, le reste du "
                                 "rapport est complet.")
        return None

    fertiles = [gr for gr in graines if len(un(gr, gr) or []) >= 3]
    for gr in fertiles:
        for l in LETTRES:
            un(gr, f"{gr} {l}")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"langue": langue, "pays": pays, "appels": cache}, f, ensure_ascii=False, indent=1)
    except OSError:
        pass
    return appels, res, etat["faits"], etat["repris"], etat["refus"]


# --- l'analyse ----------------------------------------------------------------------------------

def court(url, base_host):
    p = urllib.parse.urlparse(url)
    s = p.path or "/"
    if p.query:
        s += "?" + p.query
    return s if (p.hostname or "") == base_host else f"{p.hostname}{s}"


def est_fichier(url):
    """Un PDF, un GPX, une image : Google le montre, mais ce n'est pas une page qu'on renforce."""
    dernier = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
    ext = os.path.splitext(dernier)[1].lower()
    return ext not in PAGES_HTML


def verdict(imp, pos, cov, sert, vise, cannibale, fmt):
    if imp < PLANCHER:
        return "trop tôt (< 10 imp)"
    if cannibale:
        return "trancher la cannibalisation"
    if vise and vise != sert:
        return f"renforcer {fmt(vise)} (elle vise déjà ces mots ; Google montre {fmt(sert) if sert else 'autre chose'})"
    if sert and est_fichier(sert):
        return f"nouvelle page (Google montre un fichier : {fmt(sert)})"
    if pos <= 10:
        return f"renforcer {fmt(sert)}" if cov is None or cov >= 0.5 else "nouvelle page"
    if pos <= 20:
        return f"renforcer {fmt(sert)}"
    return f"renforcer {fmt(sert)}" if cov is not None and cov >= 0.5 else "nouvelle page"


def domaines(q):
    """Les sites nommés dans une requête : « autresite.com pass » -> {"autresite"}."""
    out = set()
    for m in re.finditer(r"[a-z0-9-]+(?:\s*\.\s*[a-z0-9-]+)+", q.lower()):
        parts = [x.strip() for x in m.group(0).split(".")]
        if parts[-1] not in TLD:
            continue
        parts = [x for x in parts[:-1] if x not in ("www", "site", "http", "https") and x not in TLD]
        if parts and len(parts[0]) >= 3:
            out.add(normaliser(parts[0]).replace(" ", ""))
    toks = normaliser(q).split()  # « autresite com pass » : le point oublié
    for i, t in enumerate(toks[1:], 1):
        if t in ("com", "org") and len(toks[i - 1]) >= 3 and toks[i - 1] not in STOP and toks[i - 1] != "www":
            out.add(toks[i - 1])
    return out


def operateur(q):
    return bool(re.search(r"(^|\s)(site|inurl|intitle|filetype)\s*[:.]", q.lower()))


def analyser(D, a, site):
    Q1, Q0 = D["Q"]["w1"], D["Q"]["w0"]
    QP1, QP0 = D["QP"]["w1"], D["QP"]["w0"]
    P1, P0 = D["P"]["w1"], D["P"]["w0"]
    hotes = {}
    for p, v in P1.items():
        h = urllib.parse.urlparse(p).hostname or ""
        hotes[h] = hotes.get(h, 0) + v[1]
    base_host = max(sorted(hotes), key=lambda h: hotes[h]) if hotes else g.nom_dossier(site)
    base = f"https://{base_host}/"
    fmt = lambda u: court(u, base_host)  # noqa: E731
    clics1 = D["totaux"]["w1"][0]
    regime = "établi" if clics1 >= SEUIL_ETABLI else "petit" if clics1 >= SEUIL_NEUF else "neuf"
    cannibale_min = CANNIBALE_MIN[0] if regime == "établi" else CANNIBALE_MIN[1]

    # Marque (ton nom de domaine, plus --marque) et requêtes qui visent un autre site.
    dom = g.nom_dossier(site)
    marques_mots = [normaliser(re.sub(r"^www\.", "", dom).split(".")[0]).replace(" ", "")]
    marques_mots += [normaliser(m).replace(" ", "") for m in (a.marque or [])]
    marques_mots = [m for m in marques_mots if len(m) >= 3]
    compact = lambda q: normaliser(q).replace(" ", "")  # noqa: E731
    est_marque = (lambda q: any(m in compact(q) for m in marques_mots))
    tous = sorted(Q1, key=lambda q: (-Q1[q][1], q))
    marques = [q for q in tous if est_marque(q)]
    reste = [q for q in tous if not est_marque(q)]
    avec_dom = {q: domaines(q) for q in reste}
    etiquettes = {}
    for q, ds in avec_dom.items():
        for d in ds:
            etiquettes.setdefault(d, 0)
    for d in list(etiquettes):  # un nom de site ne sert d'indice seul que s'il vient surtout avec son domaine
        porteurs = [q for q in reste if d in normaliser(q).split() or d in avec_dom[q]]
        if sum(1 for q in porteurs if d in avec_dom[q]) * 2 < len(porteurs):
            del etiquettes[d]
    ailleurs = [q for q in reste if avec_dom[q] or operateur(q) or any(t in etiquettes for t in normaliser(q).split())]
    ailleurs_set = set(ailleurs)
    hors_marque = [q for q in reste if q not in ailleurs_set]
    theme = [m for t in (a.theme or []) for m in mots(t)]
    dans_theme = (lambda q: all(porte(m, (set(mots(q)), compact(q))) for m in theme))
    retenues = [q for q in hors_marque if dans_theme(q)] if theme else hors_marque

    # La forme lisible de chaque racine (« beache » s'affiche « beaches »).
    formes = {}
    for q in hors_marque:
        for w in normaliser(q).split():
            r = racine_mot(w)
            formes.setdefault(r, {})
            formes[r][w] = formes[r].get(w, 0) + Q1[q][1]
    lisible = lambda r: max(sorted(formes.get(r, {r: 1})), key=lambda w: formes.get(r, {r: 1})[w])  # noqa: E731

    # Mots trop présents pour grouper (« paris » sur un site sur Paris).
    freq = {}
    for q in hors_marque:
        for m in mots(q):
            freq[m] = freq.get(m, 0) + 1
    ubiq = {m for m, k in freq.items() if len(hors_marque) >= 20 and k / len(hors_marque) >= UBIQUITE}

    dire("  sitemap…")
    sitemap = D.get("sitemap") or urls_sitemap(base)
    connues = sorted(set(P1) | set(P0) | {sans_fragment(u) for u in sitemap})

    def page_qui_sert(q):
        pages = QP1.get(q) or {}
        if not pages:
            return None, {}
        return sorted(pages, key=lambda p: (-pages[p][1], p))[0], pages

    # Les titles des pages qui servent le plus d'impressions retenues.
    poids = {}
    for q in retenues:
        s, _ = page_qui_sert(q)
        if s and not est_fichier(s):
            poids[s] = poids.get(s, 0) + Q1[q][1]
    a_lire = sorted(poids, key=lambda u: (-poids[u], u))[:TITRES_MAX]
    if base not in a_lire:
        a_lire.append(base)
    dire(f"  titles de {len(a_lire)} pages…")
    titres = lire_titres(a_lire)
    refusees = sorted(u for u, t in titres.items() if t["titre"] is None)
    idx_cache = {}

    def idx(u):
        if u not in idx_cache:
            idx_cache[u] = index_page(u, (titres.get(u) or {}).get("titre") or "")
        return idx_cache[u]

    def qui_vise(mq):
        """La page dont l'URL ou le title porte tous les mots (deux au moins) ; la plus vue d'abord."""
        if len(mq) < 2:
            return None
        ok = [u for u in connues if not est_fichier(u) and all(porte(m, idx(u)) for m in mq)]
        if not ok:
            return None
        return sorted(ok, key=lambda u: (-(P1.get(u) or (0, 0, 0))[1], len(u), u))[0]

    def part_pages(pages, top=4):
        tot = sum(v[1] for v in pages.values()) or 1
        return [(u, pages[u][1] / tot) for u in sorted(pages, key=lambda u: (-pages[u][1], u))[:top]]

    fiches = {}
    for q in retenues:
        c, i, p = Q1[q]
        avant = Q0.get(q) or (0, 0, 0)
        mq = mots(q)
        mc = [m for m in mq if m not in ubiq] or mq  # « paris » sur un site sur Paris : toutes les pages le portent
        sert, pages = page_qui_sert(q)
        fichier = bool(sert and est_fichier(sert))
        cov = (0.0 if fichier else couverture(mc, idx(sert))) if sert else None
        absents = [m for m in mc if sert and (fichier or not porte(m, idx(sert)))]
        parts = part_pages(pages) if pages else []
        canni = (sum(v[1] for v in pages.values()) >= cannibale_min
                 and sum(1 for _, s in parts if s >= PART_CANNIBALE) >= 2)
        vise = sert if cov == 1 else (qui_vise(mc) if i >= PLANCHER else None)
        fiches[q] = {"requete": q, "clics": c, "impressions": i, "impressions_avant": avant[1],
                     "position": p, "position_avant": avant[2] if avant[1] else None,
                     "mots": mq, "page": sert, "titre": (titres.get(sert) or {}).get("titre") if sert else None,
                     "couverture": cov, "absents": [lisible(m) for m in absents], "absents_r": absents, "vise": vise,
                     "mots_cible": mc,
                     "cannibale": canni, "parts": parts, "neuve": q not in Q0, "question": est_question(q)}
        fiches[q]["verdict"] = verdict(i, p, cov, sert, vise, canni, fmt)

    au_dessus = lambda f: f["impressions"] >= PLANCHER  # noqa: E731
    G = {}
    G["deja"] = [f for f in fiches.values() if au_dessus(f) and f["position"] <= 10 and f["page"]
                 and f["couverture"] is not None and f["couverture"] < 1]
    G["page2"] = [f for f in fiches.values() if 10 < f["position"] <= 20 and f["impressions"] >= PAGE2_MIN]
    G["neuves"] = [f for f in fiches.values() if au_dessus(f) and f["neuve"]]
    G["questions"] = [f for f in fiches.values() if au_dessus(f) and f["question"]]
    for k in G:
        G[k].sort(key=lambda f: (-f["impressions"], f["position"], f["requete"]))

    def ordonne(ws, requete):
        tete = [racine_mot(w) for w in normaliser(requete).split()]
        return sorted(ws, key=lambda w: (tete.index(w) if w in tete else 99, w))

    # Les mots qui manquent : Google t'associe à ces mots sur plusieurs requêtes, aucune page ne les porte.
    # D'abord par paire (un mot absent et son voisin : « minimum wage », « average wage »), puis mot seul.
    cles_m = {}
    for f in G["deja"]:
        ab = set(f["absents_r"])
        ws = [m for m in f["mots"] if m not in ubiq]
        for x in ws:
            for y in ws:
                if x < y and (x in ab or y in ab) and x not in MODIFS and y not in MODIFS:
                    cles_m[(x, y)] = cles_m.get((x, y), 0) + f["impressions"]
        for w in ab:
            cles_m[(w,)] = cles_m.get((w,), 0) + f["impressions"] / 1e6  # un mot seul passe après les paires
    pris_m, G["manque"] = set(), []
    paires_m = sorted((k for k in cles_m if len(k) == 2 and cles_m[k] >= LOIN_MIN), key=lambda k: (-cles_m[k], k))
    seuls_m = sorted((k for k in cles_m if len(k) == 1), key=lambda k: (-cles_m[k], k))
    for k in paires_m + seuls_m:
        membres = [f for f in G["deja"] if f["requete"] not in pris_m and all(m in f["mots"] for m in k)
                   and any(m in f["absents_r"] for m in k)]
        if len(membres) < 2 or (len(k) == 2 and sum(f["impressions"] for f in membres) < LOIN_MIN):
            continue
        pris_m |= {f["requete"] for f in membres}
        w = k[0]
        co = {}
        for f in membres:
            for m in f["mots"]:
                if m != w and m not in ubiq:
                    co[m] = co.get(m, 0) + 1
        etiquette = ordonne(list(k) + [m for m in sorted(co, key=lambda m: (-co[m], m))
                                       if m not in k and co[m] / len(membres) >= 0.8][:3 - len(k)],
                            membres[0]["requete"])
        imp = sum(f["impressions"] for f in membres)
        pages = {}
        for f in membres:
            pages[f["page"]] = pages.get(f["page"], 0) + f["impressions"]
        princ = sorted(pages, key=lambda u: (-pages[u], u))[0]
        cov = 0.0 if est_fichier(princ) else couverture(etiquette, idx(princ))
        if len(etiquette) == 1 and cov == 0:  # un mot seul : un synonyme absent du title, pas un sujet à part
            cov = 0.5
        vise = qui_vise(etiquette)
        pos = sum(f["position"] * f["impressions"] for f in membres) / imp
        G["manque"].append({"groupe": " ".join(lisible(m) for m in etiquette), "requetes": len(membres),
                            "impressions": imp, "impressions_avant": sum(f["impressions_avant"] for f in membres),
                            "clics": sum(f["clics"] for f in membres), "position": pos, "page": princ,
                            "titre": (titres.get(princ) or {}).get("titre"), "pages": pages, "couverture": cov,
                            "vise": vise, "membres": membres, "seule": False, "mots_cible": etiquette,
                            "verdict": verdict(imp, pos, cov, princ, vise, False, fmt)})
    G["manque"].sort(key=lambda x: (-x["impressions"], x["groupe"]))

    # Cannibalisation : requête par requête, puis par paire de pages.
    canni = []
    for f in fiches.values():
        if not f["cannibale"]:
            continue
        q = f["requete"]
        p0 = QP0.get(q) or {}
        tot0 = sum(v[1] for v in p0.values())
        f["avant"] = {u: p0.get(u, (0, 0, 0))[1] / tot0 for u, _ in f["parts"]} if tot0 else {}
        tete0 = sorted(p0, key=lambda u: (-p0[u][1], u))[0] if tot0 else None
        f["bascule"] = tete0 is not None and tot0 >= PLANCHER and tete0 != f["parts"][0][0]
        canni.append(f)
    canni.sort(key=lambda f: (-f["impressions"], f["requete"]))
    paires = {}
    for f in canni:
        ps_ = [u for u, s in f["parts"] if s >= PART_CANNIBALE]
        for x in range(len(ps_)):
            for y in range(x + 1, len(ps_)):
                k = tuple(sorted((ps_[x], ps_[y])))
                e = paires.setdefault(k, {"requetes": [], "impressions": 0, "clics": {}, "imp_page": {}, "bascules": 0})
                e["requetes"].append(f)
                e["impressions"] += f["impressions"]
                e["bascules"] += 1 if f["bascule"] else 0
                for u in k:
                    v = QP1[f["requete"]].get(u, (0, 0, 0))
                    e["clics"][u] = e["clics"].get(u, 0) + v[0]
                    e["imp_page"][u] = e["imp_page"].get(u, 0) + v[1]
    for k, e in paires.items():
        garde = sorted(k, key=lambda u: (-e["clics"][u], -e["imp_page"][u], u))[0]
        autre = [u for u in k if u != garde][0]
        e["garde"], e["autre"] = garde, autre
        e["verdict"] = f"trancher : {fmt(garde)} garde (plus de clics), {fmt(autre)} renvoie vers elle"
        e["pages"] = k
    G["canni"] = canni
    G["paires"] = sorted(paires.values(), key=lambda e: (-e["impressions"], e["pages"]))

    # Gros gisements lointains : position 20 à 60, groupés par paires de mots, puis par mot seul.
    loin = [fiches[q] for q in retenues if 20 < Q1[q][2] <= 60]
    exclus = ubiq | set(theme)
    pris, groupes = set(), []
    compte = {}
    for f in loin:
        ws = [m for m in f["mots"] if m not in exclus]
        for x in range(len(ws)):
            for y in range(x + 1, len(ws)):
                k = tuple(sorted((ws[x], ws[y])))
                if k[0] not in MODIFS and k[1] not in MODIFS:
                    compte[k] = compte.get(k, 0) + f["impressions"]
    for k in sorted(compte, key=lambda k: (-compte[k], k)):
        if compte[k] < LOIN_MIN:
            break
        membres = [f for f in loin if f["requete"] not in pris and k[0] in f["mots"] and k[1] in f["mots"]]
        if len(membres) >= 2 and sum(f["impressions"] for f in membres) >= LOIN_MIN:
            pris |= {f["requete"] for f in membres}
            groupes.append((list(k), membres))
    seuls = {}
    for f in loin:
        if f["requete"] in pris:
            continue
        for m in f["mots"]:
            if m not in exclus and m not in MODIFS:
                seuls[m] = seuls.get(m, 0) + f["impressions"]
    for m in sorted(seuls, key=lambda m: (-seuls[m], m)):
        membres = [f for f in loin if f["requete"] not in pris and m in f["mots"]]
        if len(membres) >= 2 and sum(f["impressions"] for f in membres) >= PLANCHER:
            pris |= {f["requete"] for f in membres}
            groupes.append(([m], membres))
    for f in loin:
        if f["requete"] not in pris and f["impressions"] >= PLANCHER:
            pris.add(f["requete"])
            groupes.append((None, [f]))

    def principale(membres):
        pages = {}
        for f in membres:
            for u, v in (QP1.get(f["requete"]) or {}).items():
                pages[u] = pages.get(u, 0) + v[1]
        princ = sorted(pages, key=lambda u: (-pages[u], u))[0] if pages else None
        return princ, (pages.get(princ, 0) / (sum(pages.values()) or 1) if princ else 0)

    # Deux groupes servis par la même page et qui partagent un mot sont le même sujet : on les fond.
    fondus = []
    for cle, membres in sorted(groupes, key=lambda gm: (-sum(f["impressions"] for f in gm[1]), gm[1][0]["requete"])):
        princ, _ = principale(membres)
        cible = None
        if cle and princ:
            for x in fondus:
                if x["cles"] and x["page"] == princ and set(cle) & set(w for c in x["cles"] for w in c):
                    cible = x
                    break
        if cible:
            cible["cles"].append(cle)
            cible["sous"].append(membres)
            cible["membres"] += membres
        else:
            fondus.append({"cles": [cle] if cle else [], "sous": [membres], "membres": list(membres), "page": princ})
    G["loin"], G["loin_petits"] = [], []
    for x in fondus:
        membres = sorted(x["membres"], key=lambda f: (-f["impressions"], f["requete"]))
        imp = sum(f["impressions"] for f in membres)
        pos = sum(f["position"] * f["impressions"] for f in membres) / imp if imp else 0
        princ, part = principale(membres)
        if x["cles"]:
            def ordre(c, sous):
                tete = [racine_mot(w) for w in normaliser(sous[0]["requete"]).split()]
                return sorted(c, key=lambda w: (tete.index(w) if w in tete else 99, w))
            libelles = [" ".join(lisible(w) for w in ordre(c, so)) for c, so in list(zip(x["cles"], x["sous"]))[:3]]
            nom = " / ".join(libelles) + (" …" if len(x["cles"]) > 3 else "")
            mots_cible = x["cles"][0] if len(x["cles"][0]) >= 2 else membres[0]["mots"]
        else:
            nom = membres[0]["requete"]
            mots_cible = membres[0]["mots"]
        mots_cible = [m for m in mots_cible if m not in ubiq] or mots_cible
        fichier = bool(princ and est_fichier(princ))
        cov = (0.0 if fichier else couverture(mots_cible, idx(princ))) if princ else None
        vise = princ if cov == 1 else qui_vise(mots_cible)
        gr = {"groupe": nom, "seule": not x["cles"], "requetes": len(membres), "impressions": imp,
              "verif": nom.split(" / ")[0] if x["cles"] and len(x["cles"][0]) >= 2 else membres[0]["requete"],
              "impressions_avant": sum(f["impressions_avant"] for f in membres), "position": pos,
              "clics": sum(f["clics"] for f in membres), "page": princ, "part_page": part,
              "titre": (titres.get(princ) or {}).get("titre") if princ else None,
              "couverture": cov, "vise": vise, "membres": membres, "mots_cible": mots_cible,
              "verdict": verdict(imp, pos, cov, princ, vise, False, fmt)}
        (G["loin"] if imp >= LOIN_MIN else G["loin_petits"]).append(gr)
    G["loin"].sort(key=lambda x: (-x["impressions"], x["groupe"]))
    G["loin_petits"].sort(key=lambda x: (-x["impressions"], x["groupe"]))

    bruit = [f for f in fiches.values() if f["impressions"] < PLANCHER]
    G["bruit"] = sorted([f for f in bruit if f["position"] <= 20 or f["neuve"] or f["question"]],
                        key=lambda f: (-f["impressions"], f["position"], f["requete"]))
    G["bruit_n"], G["bruit_imp"] = len(bruit), sum(f["impressions"] for f in bruit)

    vis1, vis0 = sum(v[1] for v in Q1.values()), sum(v[1] for v in Q0.values())
    return {"base": base, "base_host": base_host, "fmt": fmt, "regime": regime, "marques_mots": marques_mots,
            "marques": marques, "marques_imp": sum(Q1[q][1] for q in marques), "theme": a.theme or [],
            "ailleurs": ailleurs, "ailleurs_imp": sum(Q1[q][1] for q in ailleurs),
            "retenues": len(retenues), "ubiq": sorted(lisible(m) for m in ubiq), "ubiq_r": ubiq, "titres": titres,
            "refusees": refusees, "connues": len(connues), "sitemap": len(sitemap), "fiches": fiches, "G": G,
            "vis": (vis1, vis0), "n_req": (len(Q1), len(Q0)),
            "n_req10": (sum(1 for v in Q1.values() if v[1] >= PLANCHER), sum(1 for v in Q0.values() if v[1] >= PLANCHER)),
            "n_pages": (sum(1 for v in P1.values() if v[1] > 0), sum(1 for v in P0.values() if v[1] > 0)),
            "au_dela_60": sum(1 for q in retenues if Q1[q][2] > 60)}


# --- le rapport ---------------------------------------------------------------------------------

def n(x):
    return f"{int(round(x)):,}".replace(",", " ")


def pc(x):
    return f"{round(100 * x)} %"


def ps(x):
    return "n/a" if x is None else f"{x:.1f}".replace(".", ",")


def cell(s, lim=70):
    s = str(s if s is not None else "").replace("|", "/").replace("\n", " ")
    return s if len(s) <= lim else s[:lim - 1] + "…"


def table(entete, lignes, lims=None):
    lims = lims or {}
    out = ["| " + " | ".join(entete) + " |", "|" + "|".join("---" for _ in entete) + "|"]
    out += ["| " + " | ".join(cell(c, lims.get(i, 70)) for i, c in enumerate(l)) + " |" for l in lignes]
    return out


def avant_txt(f):
    if not f["impressions_avant"]:
        return "28 jours d'avant : absente"
    return f"28 jours d'avant : {n(f['impressions_avant'])} impressions, position {ps(f['position_avant'])}"


def sugg_pour(S, ws):
    """Les suggestions pas encore servies qui contiennent tous ces mots : les sous-sujets que Google propose."""
    if not S or not ws:
        return []
    return [l[0] for l in S["lignes"] if l[2] == "non" and all(m in mots(l[0]) for m in ws)][:8]


CMD_VERIF = "<!-- CLAUDE: vérifie d'abord : python3 <skill>/scripts/keywords.py {site} --verifier \"{req}\". " \
            "Puis l'angle : ce que les 3 premiers résultats Google pour « {req} » ne donnent pas et que ta page " \
            "donnera, en une phrase. Pas de phrase, pas de page. -->"
CMD_CHOIX = "<!-- CLAUDE: choix final : nouvelle page (son URL), renforcer telle page (quoi : title, H2, section, " \
            "liens), ou rien ; et pourquoi, avec le chiffre. -->"


def ecrire_rapport(D, R, S, site):
    G, fmt = R["G"], R["fmt"]
    nom_site = g.nom_dossier(site)
    w1, w0 = D["w1"], D["w0"]
    t1, t0 = D["totaux"]["w1"], D["totaux"]["w0"]
    vis1, vis0 = R["vis"]
    L = [f"# Mots-clés : {nom_site}", "",
         f"Les 28 derniers jours finaux, du {w1[0]} au {w1[1]}, contre les 28 d'avant, du {w0[0]} au {w0[1]}. "
         f"Données : {D['source']}. Rapport écrit le {dt.date.today().isoformat()} par la skill `keywords`.", "",
         "<!-- CLAUDE: en tête, trois phrases : le gisement le moins cher (avec son chiffre), la page à écrire "
         "ou à renforcer en premier, et ce qui est trop tôt. Rien sans chiffre. -->", "", "## En bref", ""]
    L += table(["", "28 jours d'avant", "28 derniers jours"], [
        ["clics (site entier)", n(t0[0]), n(t1[0])],
        ["impressions (site entier)", n(t0[1]), n(t1[1])],
        ["impressions visibles par requête", f"{n(vis0)} ({pc(vis0 / t0[1]) if t0[1] else 'n/a'})",
         f"{n(vis1)} ({pc(vis1 / t1[1]) if t1[1] else 'n/a'})"],
        ["requêtes distinctes", n(R["n_req"][1]), n(R["n_req"][0])],
        ["requêtes à 10 impressions ou plus", n(R["n_req10"][1]), n(R["n_req10"][0])],
        ["pages avec des impressions", n(R["n_pages"][1]), n(R["n_pages"][0])]])
    part = vis1 / t1[1] if t1[1] else 0
    reg = {"établi": f"site établi ({n(t1[0])} clics sur 28 jours, 200 ou plus)",
           "petit": f"petit site ({n(t1[0])} clics sur 28 jours, de 30 à 199) : la position d'une requête à moins "
                    "de 30 impressions bouge beaucoup d'une semaine à l'autre",
           "neuf": f"site neuf ({n(t1[0])} clics sur 28 jours, moins de 30) : presque tout est neuf et tout bouge "
                   "vite ; ne retiens que ce qui dépasse 10 impressions, et revérifie avant d'écrire"}[R["regime"]]
    L += ["", f"- **La part visible** : la dimension requête ne montre que {pc(part)} des impressions du site. "
          "Google masque les requêtes rares. Tout ce qui suit porte sur cette part, biaisée vers les grosses requêtes.",
          f"- **Le régime** : {reg}.",
          f"- **Requêtes distinctes** : {n(R['n_req'][1])} → {n(R['n_req'][0])} ; à 10 impressions ou plus : "
          f"{n(R['n_req10'][1])} → {n(R['n_req10'][0])}. Le nombre de requêtes où Google te montre est un signal "
          "de croissance plus robuste que leur position."]
    if R["marques"]:
        L.append(f"- **Marque** : {n(len(R['marques']))} requêtes contiennent "
                 + " ou ".join(f"« {m} »" for m in R["marques_mots"])
                 + f" ({n(R['marques_imp'])} impressions), mises à part : on n'écrit pas de page pour son propre nom.")
    if R["ailleurs"]:
        L.append(f"- **Un autre site** : {n(len(R['ailleurs']))} requêtes nomment un autre site ou un opérateur "
                 f"(ex. « {R['ailleurs'][0]} », {n(R['ailleurs_imp'])} impressions) : des gens qui cherchent ce "
                 "site-là, mises à part.")
    if R["theme"]:
        L.append(f"- **Thème** : seules les {n(R['retenues'])} requêtes qui contiennent « {' + '.join(R['theme'])} » "
                 "sont lues ci-dessous (les chiffres d'en-tête restent ceux du site).")
    if R["refusees"]:
        L.append(f"- **Titles illisibles** : {len(R['refusees'])} page(s) sur {len(R['titres'])} n'ont pas répondu "
                 f"(ex. {fmt(R['refusees'][0])}) ; pour elles, seule l'URL est comparée à la requête.")
    L.append("")

    def lignes_req(fs):
        return [[f["requete"], n(f["impressions"]), n(f["clics"]), ps(f["position"]),
                 fmt(f["page"]) if f["page"] else "?", ", ".join(f["absents"]) or "aucun", f["verdict"]]
                for f in fs[:LIGNES]]

    def reste(fs):
        return ["", f"*{n(len(fs) - LIGNES)} autres lignes dans `candidats.csv`.*"] if len(fs) > LIGNES else []

    ENT = ["requête", "imp.", "clics", "pos.", "page qui sert", "mots absents", "verdict"]
    L += ["## 1. Déjà classé sans page dédiée", "",
          "Position 1 à 10, 10 impressions ou plus, mais la page que Google montre ne porte pas tous les mots de la "
          "requête dans son title ni dans son URL. Le gain le moins cher : Google te donne déjà raison. "
          "Verdict par règle : la moitié des mots ou plus déjà portés, renforcer la page (les mots manquants dans le "
          "title ou un H2) ; moins de la moitié, nouvelle page ; une autre page du site porte déjà tous les mots, "
          "renforcer celle-là.", ""]
    if G["manque"]:
        L += ["Les mots qui manquent sur plusieurs requêtes (chaque requête comptée une fois, sous son mot le plus "
              "lourd) :", ""]
        L += table(["mots", "req.", "imp.", "clics", "pos. moy.", "pages qui servent", "exemples", "verdict"],
                   [[x["groupe"], n(x["requetes"]), n(x["impressions"]), n(x["clics"]), ps(x["position"]),
                     ", ".join(fmt(u) for u in sorted(x["pages"], key=lambda u: (-x["pages"][u], u))[:2]),
                     "; ".join(f"{f['requete']} ({n(f['impressions'])})" for f in x["membres"][:3]), x["verdict"]]
                    for x in G["manque"][:15]], {5: 90, 6: 110})
        L += ["", "Requête par requête :", ""]
    L += (table(ENT, lignes_req(G["deja"])) if G["deja"] else ["Aucune requête dans ce cas."]) + reste(G["deja"])
    L += ["", "## 2. Page 2 : à renforcer", "",
          "Position 11 à 20, 20 impressions ou plus. La page existe et Google hésite : on la renforce (contenu, "
          "title, liens internes), on n'en écrit pas une deuxième.", ""]
    L += (table(ENT, lignes_req(G["page2"])) if G["page2"] else ["Aucune requête dans ce cas."]) + reste(G["page2"])
    L += ["", "## 3. Gros gisements lointains", "",
          "Position 20 à 60, requêtes regroupées par mots communs (mots vides retirés"
          + (f", et les mots présents dans un quart des requêtes : {', '.join(R['ubiq'][:6])}" if R["ubiq"] else "")
          + "), 50 impressions ou plus par groupe. Google te voit sur le sujet mais loin : si aucune page ne porte "
          "ces mots, c'est une page à écrire ; si une page les porte, elle est trop faible et se renforce.", ""]
    if G["loin"]:
        L += table(["groupe", "req.", "imp.", "pos. moy.", "page principale (part)", "exemples", "verdict"],
                   [[x["groupe"], n(x["requetes"]), n(x["impressions"]), ps(x["position"]),
                     f"{fmt(x['page'])} ({pc(x['part_page'])})" if x["page"] else "?",
                     "; ".join(f"{f['requete']} ({n(f['impressions'])})" for f in x["membres"][:3]), x["verdict"]]
                    for x in G["loin"][:LIGNES]], {5: 110})
    else:
        L.append("Aucun groupe à 50 impressions ou plus.")
    if G["loin_petits"]:
        L += ["", f"*{n(len(G['loin_petits']))} groupes de 10 à 49 impressions dans `candidats.csv`.*"]
    L += ["", "## 4. Cannibalisation", "",
          f"Requêtes à {CANNIBALE_MIN[0] if R['regime'] == 'établi' else CANNIBALE_MIN[1]} impressions ou plus "
          "servies par deux pages ou plus, chacune avec 20 % des impressions au moins. C'est un constat de "
          "structure, pas la preuve d'une perte de clics : à trancher (une page garde, l'autre renvoie vers elle). "
          "« Bascule » : la page en tête n'est plus la même que sur les 28 jours d'avant, Google alterne.", ""]
    if G["paires"]:
        L += table(["page A", "page B", "requêtes", "imp.", "bascules", "exemples", "verdict par règle"],
                   [[fmt(e["pages"][0]), fmt(e["pages"][1]), n(len(e["requetes"])), n(e["impressions"]),
                     n(e["bascules"]), "; ".join(f["requete"] for f in e["requetes"][:3]), e["verdict"]]
                    for e in G["paires"][:15]], {5: 90, 6: 120})
        L += ["", "Requête par requête :", ""]
        rows = []
        for f in G["canni"][:LIGNES]:
            pp = "; ".join(f"{fmt(u)} {pc(s)}" + (f" (avant {pc(f['avant'][u])})" if f["avant"] else "")
                           for u, s in f["parts"] if s >= PART_CANNIBALE)
            rows.append([f["requete"], n(f["impressions"]), ps(f["position"]), pp, "oui" if f["bascule"] else "non"])
        L += table(["requête", "imp.", "pos.", "pages (part des impressions)", "bascule"], rows, {3: 160})
        L += reste(G["canni"])
    else:
        L.append("Aucune requête partagée à ce niveau.")
    L += ["", "## 5. Requêtes neuves", "",
          f"Apparues sur les 28 derniers jours, absentes des 28 d'avant : {n(len(G['neuves']))} à 10 impressions "
          "ou plus. Une requête neuve n'est pas une hausse mesurée : le site n'y apparaissait pas avant.", ""]
    L += (table(ENT, lignes_req(G["neuves"])) if G["neuves"] else ["Aucune requête neuve à 10 impressions ou plus."]) + reste(G["neuves"])
    L += ["", "## 6. Questions", "",
          "Requêtes qui commencent par comment, pourquoi, combien, quel, où, est-ce, how, why, what, when, can… "
          "La matière d'une FAQ ou d'un H2 sur la page qui sert, sauf verdict contraire.", ""]
    L += (table(ENT, lignes_req(G["questions"])) if G["questions"] else ["Aucune question à 10 impressions ou plus."]) + reste(G["questions"])
    L += ["", "## 7. Suggestions Google", ""]
    if S is None:
        L.append("Pas lancées (`--sans-suggestions`, ou aucune graine).")
    else:
        servies = sum(1 for x in S["lignes"] if x[2] == "oui")
        L.append(f"Graines : {', '.join('« ' + x + ' »' for x in S['graines'])}. Langue `{S['langue']}`, pays "
                 f"`{S['pays']}`. {n(len(S['appels']))} appels ({n(S['faits'])} faits, {n(S['repris'])} repris du cache de "
                 f"2 jours) : chaque graine, puis « graine a », « graine c »… pour les premières. {n(len(S['lignes']))} suggestions uniques, dont {n(servies)} que le "
                 "site sert déjà (Search Console l'y montre).")
        if S["refus"]:
            L += ["", f"**{S['refus']}**"]
        L += ["", "Une suggestion prouve que des gens tapent la requête, pas combien. Celles que le site ne sert pas "
              "encore sont des idées à confronter aux gisements ci-dessus, pas des pages à écrire telles quelles.", ""]
        par_graine = {gr: [0, []] for gr in S["graines"] if any(q == gr or q.startswith(gr + " ") for _, q in S["faits_q"])}
        for sug, gr, servie, *_ in S["lignes"]:
            par_graine.setdefault(gr, [0, []])
            if servie == "non":
                par_graine[gr][1].append(sug)
            else:
                par_graine[gr][0] += 1
        if par_graine:
            L += table(["graine", "servies", "pas encore servies", "les premières pas encore servies"],
                       [[gr, n(v[0]), n(len(v[1])), ", ".join(v[1][:10])] for gr, v in par_graine.items()], {3: 600})
    L += ["", "## 8. Sous le bruit (moins de 10 impressions)", "",
          f"{n(G['bruit_n'])} requêtes sous 10 impressions sur 28 jours ({n(G['bruit_imp'])} impressions en tout). "
          "Aucune page ne s'écrit dessus : des pages écrites sur 7 et 11 impressions ont été déclassées en quelques "
          "semaines. Les plus proches d'un gisement (position 20 au plus, neuves ou questions), à revoir le mois "
          "prochain :", ""]
    L += table(["requête", "imp.", "pos.", "page qui sert", "pourquoi elle est là"],
               [[f["requete"], n(f["impressions"]), ps(f["position"]), fmt(f["page"]) if f["page"] else "?",
                 ", ".join(x for x, ok in (("position ≤ 20", f["position"] <= 20), ("neuve", f["neuve"]),
                                           ("question", f["question"])) if ok)]
                for f in G["bruit"][:15]]) if G["bruit"] else ["Rien."]
    if R["au_dela_60"]:
        L += ["", f"*{n(R['au_dela_60'])} requêtes sont au-delà de la position 60 : hors des gisements de position "
              "(1 à 60), elles ne comptent que dans les neuves et les questions.*"]

    # Les candidats : un bloc chacun, du moins cher au plus cher.
    L += ["", "## Les candidats", "",
          "Les premiers de chaque gisement, du moins cher au plus cher. Chaque bloc porte le verdict de la règle ; "
          "le choix final se fait après la vérification fraîche et la lecture des trois premiers résultats Google.", ""]
    blocs, vus = [], set()
    for cle, nom in (("manque" if G["manque"] else "deja", "déjà classé sans page dédiée"), ("page2", "page 2"),
                     ("paires", "cannibalisation"), ("loin", "gros gisement lointain"), ("questions", "question"),
                     ("neuves", "requête neuve")):
        pris = 0
        for x in G[cle]:
            if pris >= BLOCS_PAR_GISEMENT or len(blocs) >= BLOCS_MAX:
                break
            if cle == "paires":
                k = ("paire",) + x["pages"]
                cles = {f["requete"] for f in x["requetes"]}
            elif cle in ("loin", "manque"):
                k = x["groupe"]
                cles = {f["requete"] for f in x["membres"]}
            else:
                k = x["requete"]
                cles = {k}
                if x["cannibale"]:  # elle a son bloc dans la cannibalisation
                    continue
                if x["couverture"] == 1 and x["position"] <= 5:  # déjà bien servie : rien à faire
                    continue
            if k in vus or (cle != "paires" and cles & vus):
                continue
            vus |= cles | {k}
            blocs.append((nom, cle, x))
            pris += 1
    for i, (nom, cle, x) in enumerate(blocs, 1):
        if cle == "paires":
            a_, b_ = x["pages"]
            req = x["requetes"][0]["requete"]
            L += [f"### {i}. {fmt(a_)} et {fmt(b_)} · {nom}", "",
                  f"- {n(len(x['requetes']))} requête(s) partagée(s), {n(x['impressions'])} impressions sur 28 jours, "
                  f"{n(x['bascules'])} bascule(s) de tête",
                  f"- Sur ces requêtes : {fmt(a_)} {n(x['imp_page'][a_])} impressions, {n(x['clics'][a_])} clics ; "
                  f"{fmt(b_)} {n(x['imp_page'][b_])} impressions, {n(x['clics'][b_])} clics (une recherche qui "
                  "montre les deux pages compte pour chacune : la somme dépasse le total)",
                  "- Requêtes : " + "; ".join(f"{f['requete']} ({n(f['impressions'])}, pos. {ps(f['position'])})"
                                             for f in x["requetes"][:5]),
                  f"- **Verdict par règle : {x['verdict']}**", "",
                  "<!-- CLAUDE: ouvre les deux pages. Même intention : une garde, l'autre renvoie (un lien en tête, "
                  "ou une redirection 301 si elle n'a rien d'autre). Deux intentions (un outil et un article, par "
                  "exemple) : rends-les distinctes (title, H1, premier paragraphe) et relie-les. Avant de parler de "
                  "perte : si les deux baissent ensemble, rien n'était volé. -->", ""]
            continue
        if cle == "manque":
            L += [f"### {i}. les mots « {x['groupe']} » · {nom}", "",
                  f"- {n(x['requetes'])} requêtes en position 1 à 10 servies par une page qui ne porte pas ces mots : "
                  f"{n(x['impressions'])} impressions sur 28 jours (28 jours d'avant : {n(x['impressions_avant'])}), "
                  f"{n(x['clics'])} clics, position moyenne {ps(x['position'])}",
                  "- Requêtes : " + "; ".join(f"{f['requete']} ({n(f['impressions'])}, pos. {ps(f['position'])})"
                                             for f in x["membres"][:6]),
                  "- Pages qui servent : " + "; ".join(f"{fmt(u)} ({n(v)} imp.)" for u, v in
                                                       sorted(x["pages"].items(), key=lambda kv: (-kv[1], kv[0]))[:3])]
            if x.get("titre"):
                L.append(f"- Title de la première : « {x['titre']} »")
            if x["position"] <= 3 and x["clics"] == 0 and x["impressions"] >= 50:
                L.append(f"- 0 clic en position {ps(x['position'])} : Google répond sans doute lui-même sur sa page de résultats")
            if x.get("vise") and x["vise"] != x.get("page"):
                L.append(f"- Page du site qui porte déjà ces mots : {fmt(x['vise'])}")
            sg = sugg_pour(S, x["mots_cible"])
            if sg:
                L.append("- Suggestions Google sur ces mots, pas encore servies : " + ", ".join(sg))
            L += [f"- **Verdict par règle : {x['verdict']}**", "",
                  CMD_VERIF.format(site=nom_site, req=x["groupe"]), CMD_CHOIX, ""]
            continue
        if cle == "loin":
            L += [f"### {i}. " + (f"« {x['groupe']} »" if x["seule"] else f"groupe « {x['groupe']} »") + f" · {nom}", "",
                  f"- {n(x['requetes'])} requête(s), {n(x['impressions'])} impressions sur 28 jours "
                  f"(28 jours d'avant : {n(x['impressions_avant'])}), {n(x['clics'])} clics, position moyenne "
                  f"{ps(x['position'])}",
                  "- Requêtes : " + "; ".join(f"{f['requete']} ({n(f['impressions'])}, pos. {ps(f['position'])})"
                                             for f in x["membres"][:6])]
            req = x["verif"]
        else:
            L += [f"### {i}. « {x['requete']} » · {nom}", "",
                  f"- {n(x['impressions'])} impressions sur 28 jours, {n(x['clics'])} clics, position "
                  f"{ps(x['position'])} ({avant_txt(x)})"]
            req = x["requete"]
        if x.get("page"):
            t = x.get("titre")
            L.append(f"- Page actuelle : {fmt(x['page'])}"
                     + (" (un fichier, pas une page)" if est_fichier(x["page"]) else
                        f" (title « {t} »)" if t else " (title non lu)")
                     + (f", {pc(x['part_page'])} des impressions du groupe" if cle == "loin" else ""))
        else:
            L.append("- Page actuelle : aucune dans les données requête × page")
        if cle != "loin":
            L.append(f"- Mots absents du title et de l'URL : {', '.join(x['absents']) or 'aucun'}")
        if x["position"] <= 3 and x["clics"] == 0 and x["impressions"] >= 50:
            L.append(f"- 0 clic en position {ps(x['position'])} : Google répond sans doute lui-même sur sa page de résultats")
        if x.get("vise") and x["vise"] != x.get("page"):
            L.append(f"- Page du site qui porte déjà ces mots : {fmt(x['vise'])}")
        sg = sugg_pour(S, x["mots_cible"])
        if sg:
            L.append("- Suggestions Google sur ces mots, pas encore servies : " + ", ".join(sg))
        L += [f"- **Verdict par règle : {x['verdict']}**", "", CMD_VERIF.format(site=nom_site, req=req), CMD_CHOIX, ""]
    if not blocs:
        L += ["Aucun candidat au-dessus du plancher. Le site est trop neuf ou le thème trop étroit : relance dans un "
              "mois, ou pars des suggestions Google ci-dessus et de ce que tu sais de ton lecteur.", ""]
    L += ["## Le plan", "",
          "<!-- CLAUDE: le plan de la semaine, dans l'ordre : au plus 3 pages neuves sur un petit site, chacune avec "
          "ses 3 liens internes posés le jour même (skill internal-links) ; les pages à renforcer ; les "
          "cannibalisations à trancher. Chaque ligne avec la requête visée et ce qu'on attend. Quand une page sort "
          "ou change : une ligne dans journal.csv. -->", ""]
    return "\n".join(L) + "\n"


def ecrire_sorties(D, R, S, site, out_dir):
    G = R["G"]
    lignes = []

    def une(nom, f, groupe=False):
        return [nom, f.get("groupe") if groupe else f["requete"], f["requetes"] if groupe else 1, f["impressions"],
                f["impressions_avant"], f["clics"], round(f["position"], 1),
                "" if groupe or f["position_avant"] is None else round(f["position_avant"], 1),
                f["page"] or "", f["titre"] or "", "" if f["couverture"] is None else round(f["couverture"], 2),
                " | ".join(x["requete"] for x in f["membres"][:20]) if groupe else " ".join(f["absents"]),
                f["vise"] or "", f["verdict"]]

    for cle, nom in (("deja", "deja_classe"), ("page2", "page_2"), ("canni", "cannibalisation"),
                     ("neuves", "neuve"), ("questions", "question")):
        lignes += [une(nom, f) for f in G[cle]]
    for cle, nom in (("manque", "mots_absents"), ("loin", "lointain"), ("loin_petits", "lointain_petit")):
        lignes += [une(nom, x, groupe=True) for x in G[cle]]
    lignes += [une("sous_le_bruit", f) for f in G["bruit"]]
    ecrire_csv(os.path.join(out_dir, "candidats.csv"),
               ["gisement", "requete_ou_groupe", "requetes", "impressions_28j", "impressions_28j_avant", "clics_28j",
                "position", "position_avant", "page_qui_sert", "title", "couverture", "mots_absents_ou_requetes",
                "page_qui_vise", "verdict"], lignes)
    if S is not None:
        ecrire_csv(os.path.join(out_dir, "suggestions.csv"),
                   ["suggestion", "graine", "servie", "impressions_28j", "position", "page"], S["lignes"])
    md = ecrire_rapport(D, R, S, site)
    path = os.path.join(out_dir, "MOTS-CLES.md")
    marque = os.path.join(out_dir, "donnees", "mots-cles.sha256")
    if os.path.exists(path):
        with open(path, "rb") as f:
            actuel = hashlib.sha256(f.read()).hexdigest()
        ecrit = open(marque).read().strip() if os.path.exists(marque) else ""
        if actuel != ecrit:  # complété par Claude ou par toi : on le garde à côté
            garde = os.path.join(out_dir, f"MOTS-CLES-avant-{dt.datetime.now().strftime('%Y-%m-%d-%H%M')}.md")
            os.replace(path, garde)
            dire(f"  l'ancien MOTS-CLES.md, complété, est gardé : {os.path.basename(garde)}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    with open(marque, "w") as f:
        f.write(hashlib.sha256(md.encode("utf-8")).hexdigest())
    return path


def preparer_suggestions(D, R, a, out_dir):
    fiches, Q1, Q0 = R["fiches"], D["Q"]["w1"], D["Q"]["w0"]
    lang_html = (R["titres"].get(R["base"]) or {}).get("lang") or ""
    langue = (a.langue or lang_html.split("-")[0] or "fr").lower()
    region = lang_html.split("-")[1].lower() if "-" in lang_html else ""
    pays = (a.pays or region or {"en": "us"}.get(langue, langue)).lower()
    if a.theme:
        graines = list(dict.fromkeys(t.strip() for t in a.theme if t.strip()))
    else:
        graines, ens = [], []
        for q in sorted(fiches, key=lambda q: (-fiches[q]["impressions"], q)):
            k = frozenset(m for m in fiches[q]["mots"] if m not in R["ubiq_r"])
            if not k or any(k >= e for e in ens):  # un mot présent partout, ou une variante d'une graine déjà prise
                continue
            ens.append(k)
            graines.append(q)
            if len(graines) >= GRAINES_MAX:
                break
    if not graines:
        return None
    dire(f"  suggestions Google ({langue}, {pays}) : {SUGGEST_MAX} appels au plus, {SUGGEST_DELAI:.0f} s entre deux, "
         "deux minutes au plus…")
    appels, res, faits, repris, refus = suggestions(graines, langue, pays, os.path.join(out_dir, "donnees", "suggestions.json"))
    cle_q = lambda q: " ".join(sorted(normaliser(q).split()))  # noqa: E731  (mêmes mots, ordre libre)
    exact = {cle_q(q): q for q in list(Q0) + list(Q1)}
    vus, lignes = set(), []
    graines_n = {normaliser(x) for x in graines}
    for gr, q in appels:
        for s in res.get(q, []):
            ns = normaliser(s)
            if ns in vus or ns in graines_n:
                continue
            vus.add(ns)
            src = exact.get(cle_q(s))
            if src and src in Q1:
                c, i, p = Q1[src]
                pg = (fiches.get(src) or {}).get("page") or ""
                lignes.append([s, gr, "oui", i, round(p, 1), pg])
            elif src:
                lignes.append([s, gr, "oui", 0, "", "vue sur les 28 jours d'avant seulement"])
            else:
                lignes.append([s, gr, "non", "", "", ""])
    return {"graines": graines, "langue": langue, "pays": pays, "appels": appels, "faits": faits,
            "repris": repris, "refus": refus, "lignes": lignes, "faits_q": [(gr, q) for gr, q in appels if q in res]}


def verifier(site, expr):
    """Contrôle frais : les 28 derniers jours, données provisoires comprises, requête qui contient expr."""
    today = dt.date.today()
    debut = today - dt.timedelta(days=27)
    rows, _ = g.recherche(site, debut.isoformat(), today.isoformat(), ["query", "page"], data_state="all",
                          filtres=[{"dimension": "query", "operator": "contains", "expression": expr}])
    dire(f"Contrôle frais de « {expr} » sur {site}, du {debut} au {today} (données provisoires comprises).")
    if not rows:
        dire("Aucune impression : Search Console ne montre plus le site sur cette requête. Le gisement est parti, "
             "ou sous le seuil d'anonymisation. Ne pas écrire de page dessus.")
        return
    par_q = {}
    for r in rows:
        q, p = r["keys"]
        par_q.setdefault(q, []).append((p, int(r["clicks"]), int(r["impressions"]), r["position"]))
    tot = sum(int(r["impressions"]) for r in rows)
    dire(f"{len(par_q)} requête(s), {tot} impressions (par page, une requête servie par deux pages compte deux fois).")
    for q in sorted(par_q, key=lambda q: (-sum(x[2] for x in par_q[q]), q))[:25]:
        imp = sum(x[2] for x in par_q[q])
        dire(f"  {q} : {imp} imp.")
        for p, c, i, pos in sorted(par_q[q], key=lambda x: (-x[2], x[0]))[:4]:
            dire(f"      {p}  {i} imp., {c} clics, pos. {pos:.1f}")
    dire("Sous 10 impressions sur la requête visée : trop tôt, pas de page.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", help="monsite.com, https://monsite.com/ ou sc-domain:monsite.com")
    ap.add_argument("--dossier", help="dossier racine des données (défaut ./seo, le même que search-console)")
    ap.add_argument("--theme", action="append", help="un thème : ne lit que ses requêtes et s'en sert de graine (répétable)")
    ap.add_argument("--marque", action="append", help="un nom à mettre à part comme ta marque, en plus du domaine (répétable)")
    ap.add_argument("--sans-suggestions", action="store_true", help="ne pas appeler Google Suggest")
    ap.add_argument("--langue", help="langue des suggestions (fr, en…) ; défaut : la langue de la page d'accueil")
    ap.add_argument("--pays", help="pays des suggestions (fr, be, ca, mt…) ; défaut : déduit de la langue")
    ap.add_argument("--rafraichir", action="store_true", help="rappeler l'API même si les données ont moins de 2 jours")
    ap.add_argument("--verifier", metavar="REQUETE", help="contrôle frais d'une requête avant d'écrire, puis sortie")
    a = ap.parse_args(argv)
    t0 = time.time()

    if a.verifier:
        exiger_gsc()
        g.racine(a.dossier)
        verifier(g.resoudre_site(a.site), a.verifier)
        return
    exiger_gsc()
    root = g.racine(a.dossier)
    site = g.resoudre_site(a.site)
    site_dir = os.path.join(root, g.nom_dossier(site))
    out_dir = os.path.join(site_dir, "keywords")
    cache = os.path.join(out_dir, "donnees")
    os.makedirs(cache, exist_ok=True)
    dire(f"Propriété {site} -> {out_dir}")
    D = None if a.rafraichir else (depuis_search_console(site_dir) or depuis_cache(cache))
    if D is None:
        dire("  Search Console : appel de l'API (requêtes, requêtes x pages, pages, deux fenêtres)…")
        D = collecter(site, cache)
    else:
        dire(f"  Search Console : {D['source']}")
    if not D["Q"]["w1"]:
        raise Arret("Search Console ne montre aucune requête sur les 28 derniers jours : rien à lire pour l'instant. "
                    "Relance quand le site a quelques semaines d'impressions.")
    R = analyser(D, a, site)
    S = None if a.sans_suggestions else preparer_suggestions(D, R, a, out_dir)
    path = ecrire_sorties(D, R, S, site, out_dir)
    G = R["G"]
    t1, vis1 = D["totaux"]["w1"], R["vis"][0]
    dire(f"FENÊTRE    {D['w1'][0]} → {D['w1'][1]} contre {D['w0'][0]} → {D['w0'][1]}")
    dire(f"VOLUME     {t1[0]} clics, {t1[1]} impressions sur 28 j ; régime {R['regime']} ; "
         f"part visible par requête {pc(vis1 / t1[1]) if t1[1] else 'n/a'}")
    dire(f"REQUÊTES   distinctes {R['n_req'][1]} → {R['n_req'][0]} ; à 10 imp. ou plus {R['n_req10'][1]} → {R['n_req10'][0]}")
    dire(f"GISEMENTS  déjà classé sans page dédiée {len(G['deja'])} · page 2 {len(G['page2'])} · "
         f"lointains {len(G['loin'])} groupes · cannibalisation {len(G['canni'])} · neuves {len(G['neuves'])} · "
         f"questions {len(G['questions'])} · sous le bruit {G['bruit_n']}")
    if S is not None:
        dire(f"SUGGEST    {S['faits']} appels (+{S['repris']} du cache), {len(S['lignes'])} suggestions, "
             f"{sum(1 for x in S['lignes'] if x[2] == 'oui')} déjà servies" + (f" ; {S['refus']}" if S["refus"] else ""))
    dire(f"RAPPORT    {path}")
    dire(f"Terminé en {time.time() - t0:.0f} s.")


if __name__ == "__main__":
    try:
        main()
    except Arret as e:
        sys.exit("ERREUR : " + str(e))
    except PANNES as e:  # l'accès Google : le guide est celui de search-console
        sys.exit("ERREUR : " + str(e) + "\n\nLe pas à pas de l'accès Google : references/installation.md de la skill "
                 "search-console (installée à côté de celle-ci).")
    except KeyboardInterrupt:
        sys.exit("Interrompu.")
