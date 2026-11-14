#!/usr/bin/env python3
"""Le maillage interne d'un site : les liens dans le texte entre ses pages, mesurés, et les liens à poser.

Usage :
  python3 maillage.py monsite.com [--dossier ./seo] [--max 300] [--min-entrants 3]
  python3 maillage.py monsite.com --noter https://monsite.com/guide [--en-ligne 2026-11-03]

Ce que fait le script :
  1. lit le sitemap (robots.txt, puis /sitemap.xml ; index de sitemaps et .gz compris) et
     télécharge chaque page (5 fils, une pause entre deux pages, robots.txt respecté, --max pages
     au plus, les liens internes hors sitemap compris) ;
  2. sépare dans chaque page le texte principal de la navigation (menu, en-tête, pied de page,
     barre latérale, fil d'Ariane, sommaire, « à lire aussi ») et range chaque lien interne :
     « texte » (dans une phrase), « bloc » (carte, liste de liens, bouton, titre cliquable) ou
     « navigation » (menu, pied de page, ou lien répété sur la moitié des pages au moins) ;
  3. le graphe : orphelines, pages sous le seuil, pages atteintes par le menu seulement, puits,
     hubs et liens sans retour, ancres génériques ou ambiguës, profondeur depuis l'accueil,
     liens cassés, à paramètres, redirigés, non canoniques ou vers une page noindex ;
  4. les propositions : pour chaque page sous le seuil, les pages qui parlent déjà de son sujet
     sans la lier, avec la phrase exacte, l'ancre et un score ;
  5. écrit ./seo/<site>/internal-links/ : MAILLAGE.md (le rapport, avec des marqueurs
     <!-- CLAUDE: --> là où Claude écrit), propositions.csv, pages.csv, graphe.csv.

Si la skill `search-console` a déjà tourné (./seo/<site>/donnees/pages_jours.csv, index.csv), le
score tient compte des impressions de la page source et le rapport montre l'état d'indexation.

--noter ajoute une ligne par page cible dans ./seo/<site>/journal.csv (le format de la skill
search-console), pour mesurer l'effet des liens trois semaines après leur mise en ligne.

Python 3.10+, bibliothèque standard seulement. Deux lancements sur le même site donnent le même
résultat.
"""
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import html as htmllib
import http.client
import math
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(errors="replace")
sys.setrecursionlimit(20000)

NOM = "skill-internal-links"
UA = "Mozilla/5.0 (compatible; skill-internal-links/1)"
FILS = 5               # téléchargements en parallèle
PAUSE = 0.3            # secondes entre deux pages, par fil
TIMEOUT = 20
TAILLE_MAX = 5_000_000
FRAIS_JOURS = 2        # un pages.csv de seo-audit plus vieux n'est pas réutilisé
MAX_PAR_CIBLE = 5      # propositions par page cible
CIBLES_RAPPORT = 25    # pages cibles détaillées dans MAILLAGE.md (toutes dans propositions.csv)
LIGNES_TABLE = 30
MOTS_AUTOUR = 3        # mots hors lien pour qu'un lien compte « dans une phrase »
RATIO_MOT = 4          # un mot seul désigne la cible s'il y est 4 fois plus fréquent que sur le site
RATIO_EXPRESSION = 3   # une expression, si l'un de ses mots l'est 3 fois
PROXIMITE_MOT = 0.10   # un mot courant seul (/tools -> « tool ») ne vaut qu'entre deux pages aussi proches

JOURNAL_COLS = ["en_ligne", "ajustement", "url", "attendu_index", "requete", "attendu", "relire_le", "statut",
                "constat", "constat_le"]


class Panne(Exception):
    """Erreur lisible par un humain, sans trace Python."""


def dire(msg=""):
    print(msg, flush=True)


# --------------------------------------------------------------------------- texte et mots

STOP = set("""
a à au aux avec ce ces cet cette ceci cela ça comme dans de des du elle elles en et est être eux il ils je
la le les leur leurs lui ma mais me même mes moi mon ne nos notre nous on ou où par pas pour qu que qui sa
se ses si son sur ta te tes toi ton tu un une vos votre vous y sans sous chez vers entre plus moins très
tout tous toute toutes autre autres quel quelle quels quelles dont alors aussi bien encore fait faire font
peut peuvent sont était été avoir avez ont as ai suis es c d j l m n s t qu jusqu lorsque puis donc car ni
voici voilà ici là leur selon depuis pendant avant après chaque peu beaucoup trop rien quoi comment
pourquoi quand combien guide guides complet complète complets complètes meilleur meilleure meilleurs
meilleures nouveau nouvelle gratuit gratuite gratuits gratuites mon ma mes ton ta tes votre vos
the and for are but not you your yours with from this that these those have has had was were will would
can could should into about over under after before what when where which who whom why how all any both
each few more most other some such only own same than too very just also our ours their them they its
it's his her him she he we us me my mine is be been being do does did doing a an of to in on at by or as
if so no nor up out off then there here again further once guide guides complete ultimate best top new
free everything things thing way ways tips list
""".split())
GENERIQUES = {
    "ici", "cliquez ici", "clique ici", "cliquer ici", "cliquez", "clique", "lire la suite", "lire plus",
    "en savoir plus", "en lire plus", "voir plus", "voir", "plus", "plus d'infos", "plus d'informations",
    "suite", "la suite", "ce lien", "cet article", "cette page", "lien", "découvrir", "decouvrir", "là",
    "c'est ici", "par ici", "go", "here", "click here", "click", "read more", "learn more", "more", "see more",
    "this link", "this article", "this page", "link", "continue reading", "details", "more info", "find out more",
    "en savoir +", "→", "»", ">", "...", "…",
}
ANNEES = re.compile(r"^(19|20)\d\d$")


def sans_accents(s):
    """Minuscules sans accents, caractère pour caractère (mêmes positions que le texte d'origine)."""
    out = []
    for c in s:
        lc = c.lower()
        d = "".join(x for x in unicodedata.normalize("NFKD", lc) if not unicodedata.combining(x))
        out.append(d[:1] if d else (lc[:1] or c))
    return "".join(out).replace("’", "'").replace("‘", "'")


def mots(s):
    return re.findall(r"[^\W_]+", s)


STOP = {sans_accents(m) for m in STOP}
GENERIQUES = {re.sub(r"\s+", " ", sans_accents(g)).strip(" .:;,!?-–—()[]«»\"'") for g in GENERIQUES} - {""}


def racine_mot(m):
    m = sans_accents(m)
    if len(m) >= 5 and m[-1] in "sx" and not m.endswith("ss"):
        return m[:-1]
    return m


def norme_ancre(s):
    s = re.sub(r"\s+", " ", sans_accents(s)).strip(" .:;,!?-–—()[]«»\"'")
    return s


def court(url, base):
    p = urllib.parse.urlsplit(url)
    if (p.hostname or "").removeprefix("www.") != base:
        return url
    return (p.path or "/") + ("?" + p.query if p.query else "")


def cellule(s, n=None):
    s = re.sub(r"\s+", " ", str(s)).replace("|", "\\|").strip()
    if n and len(s) > n:
        s = s[: n - 1].rstrip() + "…"
    return s


def nombre(x):
    return f"{x:,}".replace(",", " ")


def pct(a, b):
    return f"{100 * a / b:.0f} %" if b else "0 %"


# --------------------------------------------------------------------------- URL

EXT_FICHIERS = re.compile(r"\.(pdf|jpe?g|png|gif|webp|avif|svg|ico|zip|gz|rar|7z|mp4|mov|webm|mp3|wav|ogg|css|js|"
                          r"json|xml|txt|csv|xlsx?|docx?|pptx?|woff2?|ttf|otf|eot|dmg|exe|apk|gpx|kml|kmz|geojson|ics|epub|rss|atom|"
                          r"m4a|flac|heic|tiff?|bmp|psd|ai|eps)$", re.I)


def normaliser(u):
    p = urllib.parse.urlsplit(u.strip())
    scheme = (p.scheme or "https").lower()
    host = (p.hostname or "").lower()
    try:
        port = p.port
    except ValueError:
        port = None
    netloc = host if not port or (scheme, port) in (("http", 80), ("https", 443)) else f"{host}:{port}"
    path = urllib.parse.quote(urllib.parse.unquote(p.path or "/"), safe="/%:@!$&'()*+,;=-._~")
    return urllib.parse.urlunsplit((scheme, netloc, path or "/", p.query, ""))


def sans_query(u):
    p = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def hote_nu(u):
    return (urllib.parse.urlsplit(u).hostname or "").lower().removeprefix("www.")


# --------------------------------------------------------------------------- réseau

_robots = None
_verrou = threading.Lock()


def lire_url(url, accepte="text/html,application/xhtml+xml", essais=2):
    """Télécharge une URL. Rend un dict : code, finale, type, corps (bytes), xrobots, erreur."""
    for i in range(essais):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accepte,
                                                   "Accept-Language": "fr,en;q=0.8"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return {"code": r.status, "finale": r.geturl(), "type": r.headers.get("Content-Type", ""),
                        "corps": r.read(TAILLE_MAX), "xrobots": r.headers.get("X-Robots-Tag", ""),
                        "charset": r.headers.get_content_charset(), "erreur": ""}
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and i < essais - 1:
                time.sleep(5 if e.code == 429 else 2)
                continue
            return {"code": e.code, "finale": e.geturl() or url, "type": "", "corps": b"", "xrobots": "",
                    "charset": None, "erreur": f"HTTP {e.code}"}
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError) as e:
            if i < essais - 1:
                time.sleep(2)
                continue
            raison = getattr(e, "reason", e)
            return {"code": 0, "finale": url, "type": "", "corps": b"", "xrobots": "", "charset": None,
                    "erreur": str(raison)[:120]}
    return {"code": 0, "finale": url, "type": "", "corps": b"", "xrobots": "", "charset": None, "erreur": "?"}


def decoder(corps, charset):
    if not charset:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", corps[:4000], re.I)
        charset = m.group(1).decode("ascii", "replace") if m else "utf-8"
    try:
        return corps.decode(charset, "replace")
    except LookupError:
        return corps.decode("utf-8", "replace")


def charger_robots(base_url):
    global _robots
    rp = urllib.robotparser.RobotFileParser()
    r = lire_url(urllib.parse.urljoin(base_url, "/robots.txt"), accepte="text/plain,*/*")
    texte = decoder(r["corps"], r["charset"]) if r["code"] == 200 else ""
    rp.parse(texte.splitlines())
    _robots = rp
    return texte


def autorise(url):
    if _robots is None:
        return True
    try:
        return _robots.can_fetch(NOM, url)
    except Exception:
        return True


def urls_sitemap(url, vus, profondeur=0):
    if url in vus or profondeur > 3:
        return []
    vus.add(url)
    r = lire_url(url, accepte="application/xml,text/xml,*/*")
    if r["code"] != 200:
        raise ValueError(f"HTTP {r['code'] or r['erreur']}")
    raw = r["corps"]
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    xml = raw.decode("utf-8", "replace")
    if "<urlset" not in xml and "<sitemapindex" not in xml:
        raise ValueError("ce n'est pas un sitemap XML")
    locs = [htmllib.unescape(l.strip()) for l in
            re.findall(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\]]+?)\s*(?:\]\]>)?\s*</loc>", xml)]
    if "<sitemapindex" in xml:
        out = []
        for sub in locs:
            try:
                out += urls_sitemap(sub, vus, profondeur + 1)
            except (ValueError, OSError, EOFError) as e:
                dire(f"  ! sitemap {sub} illisible : {e}")
        return out
    return locs


def trouver_sitemap(base_url, robots_txt):
    declares = [l.split(":", 1)[1].strip() for l in robots_txt.splitlines() if l.lower().startswith("sitemap:")]
    candidats = declares + [urllib.parse.urljoin(base_url, p) for p in
                            ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml", "/wp-sitemap.xml")]
    vus, urls, lus = set(), [], []
    for c in dict.fromkeys(candidats):
        if lus and c not in declares:
            break  # les sitemaps déclarés ont suffi ; sinon le premier emplacement usuel qui répond
        try:
            got = urls_sitemap(c, vus)
        except (ValueError, OSError, EOFError):
            continue
        if got:
            urls += got
            lus.append(urllib.parse.urlsplit(c).path)
    return list(dict.fromkeys(urls)), lus


# --------------------------------------------------------------------------- HTML -> arbre

VIDES = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
FERME_P = {"address", "article", "aside", "blockquote", "details", "div", "dl", "fieldset", "figcaption", "figure",
           "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "main", "nav", "ol", "p", "pre",
           "section", "table", "ul"}
IGNORES = {"script", "style", "noscript", "template", "svg", "math", "iframe", "object", "canvas", "video", "audio",
           "pre", "code", "kbd", "samp", "button", "select", "option", "textarea", "label", "form", "dialog",
           "input", "head", "title"}
BLOCS = {"p", "li", "td", "th", "dd", "dt", "blockquote", "figcaption", "caption", "h1", "h2", "h3", "h4", "h5", "h6",
         "div", "section", "article", "main", "body", "details", "summary", "header", "footer", "nav", "aside", "ul",
         "ol", "dl", "table", "figure", "address", "#doc"}
DANS_LIEN_BLOC = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "img", "figure", "picture", "ul", "ol", "li",
                  "section", "article", "header", "footer", "table", "blockquote"}
TITRES = {"h1", "h2", "h3", "h4", "h5", "h6"}


class Noeud:
    __slots__ = ("tag", "attrs", "enfants", "parent", "force")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.enfants, self.parent, self.force = tag, attrs, [], parent, None


class Arbre(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.racine = Noeud("#doc", {}, None)
        self.pile = [self.racine]

    def _fermer_jusqua(self, tags, arret):
        for i in range(len(self.pile) - 1, 0, -1):
            t = self.pile[i].tag
            if t in tags:
                del self.pile[i:]
                return
            if t in arret:
                return

    def handle_starttag(self, tag, attrs):
        if tag in FERME_P and self.pile[-1].tag == "p":
            self.pile.pop()
        if tag == "li":
            self._fermer_jusqua({"li"}, {"ul", "ol", "menu"})
        elif tag in ("dt", "dd"):
            self._fermer_jusqua({"dt", "dd"}, {"dl"})
        elif tag == "tr":
            self._fermer_jusqua({"tr"}, {"table", "tbody", "thead", "tfoot"})
        elif tag in ("td", "th"):
            self._fermer_jusqua({"td", "th"}, {"tr", "table"})
        elif tag == "option":
            self._fermer_jusqua({"option"}, {"select"})
        elif tag == "a":
            self._fermer_jusqua({"a"}, BLOCS)
        n = Noeud(tag, {k: (v or "") for k, v in attrs}, self.pile[-1])
        self.pile[-1].enfants.append(n)
        if tag not in VIDES:
            self.pile.append(n)

    def handle_startendtag(self, tag, attrs):
        n = Noeud(tag, {k: (v or "") for k, v in attrs}, self.pile[-1])
        self.pile[-1].enfants.append(n)

    def handle_endtag(self, tag):
        for i in range(len(self.pile) - 1, 0, -1):
            if self.pile[i].tag == tag:
                del self.pile[i:]
                return

    def handle_data(self, data):
        self.pile[-1].enfants.append(data)


def tous(n, tags):
    pile = [n]
    while pile:
        x = pile.pop()
        if isinstance(x, str):
            continue
        if x.tag in tags:
            yield x
        pile.extend(reversed(x.enfants))


def texte_de(n):
    out = []
    pile = [n]
    while pile:
        x = pile.pop()
        if isinstance(x, str):
            out.append(x)
        elif x.tag not in ("script", "style", "noscript", "template", "svg"):
            if x.tag == "img" and x.attrs.get("alt"):
                out.append(" " + x.attrs["alt"] + " ")
            pile.extend(reversed(x.enfants))
    return re.sub(r"\s+", " ", "".join(out)).strip()


# --------------------------------------------------------------------------- zones de navigation

JETONS_NAV = {
    "nav", "navbar", "navigation", "menu", "menus", "submenu", "megamenu", "breadcrumb", "breadcrumbs", "ariane",
    "sidebar", "widget", "widgets", "related", "similar", "recommended", "recommendations", "toc", "sommaire",
    "pagination", "pager", "share", "sharing", "partage", "social", "cookie", "cookies", "consent", "newsletter",
    "subscribe", "abonnement", "abonner", "author", "auteur", "comments", "commentaires", "comment", "footer",
    "masthead", "tagcloud", "skip", "offcanvas", "drawer",
}
ROLES = {"navigation": "menu", "banner": "en-tête", "contentinfo": "pied de page", "menu": "menu",
         "menubar": "menu", "search": "recherche", "dialog": "fenêtre", "alertdialog": "fenêtre",
         "toolbar": "menu", "tablist": "menu"}
TAGS_NAV = {"nav": "menu", "header": "en-tête", "footer": "pied de page"}
RE_A_LIRE = re.compile(
    r"^(?:(?:les |nos |des |d')?autres (?:articles|ressources|guides|pages|outils|posts|tutos)"
    r"|(?:à |a )?lire (?:aussi|ensuite)|voir aussi|vous aimerez(?: aussi)?|sur le m[eê]me (?:sujet|th[eè]me)"
    r"|articles? (?:similaires|li[eé]s|connexes|recommand[eé]s|populaires|r[eé]cents)|derniers articles"
    r"|related(?: \w+)?|keep reading|read next|you (?:may|might) also like|more (?:articles|posts|guides|from|stories)"
    r"|recommended(?: \w+)?|popular (?:posts|articles)|recent (?:posts|articles)|latest (?:posts|articles))"
    r"\s*[:.!]?$", re.I)


def jetons(n):
    vals = [n.attrs.get("class", ""), n.attrs.get("id", ""), n.attrs.get("aria-label", ""),
            n.attrs.get("aria-labelledby", "")]
    vals += [k[5:] for k in n.attrs if k.startswith("data-")]
    out = set()
    for v in vals:
        out.update(t for t in re.split(r"[\s_\-:/\[\]().,'’]+", v.lower()) if t)
    return out


def densite_liens(n):
    total, dans = 0, 0
    pile = [(n, False)]
    while pile:
        x, lien = pile.pop()
        if isinstance(x, str):
            k = len(x.strip())
            total += k
            dans += k if lien else 0
        elif x.tag not in IGNORES:
            pile.extend((c, lien or x.tag == "a") for c in x.enfants)
    return dans / total if total else 1.0


def raison_zone(n, dans_principal):
    """Pourquoi ce nœud est de la navigation (None s'il est du contenu)."""
    if n.force:
        return n.force
    role = n.attrs.get("role", "").lower()
    if n.tag in TAGS_NAV:
        return TAGS_NAV[n.tag]
    if role in ROLES:
        return ROLES[role]
    if n.attrs.get("aria-hidden", "").lower() == "true":
        return "caché"
    j = jetons(n)
    if j & JETONS_NAV:
        mot = sorted(j & JETONS_NAV)[0]
        return {"breadcrumb": "fil d'Ariane", "breadcrumbs": "fil d'Ariane", "ariane": "fil d'Ariane",
                "toc": "sommaire", "sommaire": "sommaire", "related": "à lire aussi", "similar": "à lire aussi",
                "recommended": "à lire aussi", "sidebar": "barre latérale", "widget": "barre latérale",
                "footer": "pied de page"}.get(mot, mot)
    if n.tag == "aside" or role == "complementary":
        # Un encadré dans l'article (un conseil, une note) reste du contenu ; une barre latérale non.
        if not dans_principal or densite_liens(n) > 0.5:
            return "barre latérale"
    return None


def marquer_a_lire(racine):
    """« À lire aussi », « Related posts » : la section que ce titre ouvre est de la navigation."""
    for h in tous(racine, {"h2", "h3", "h4", "h5", "p", "span", "div", "strong"}):
        etiquette = h.tag not in TITRES
        if etiquette and len(h.enfants) > 3:
            continue
        t = texte_de(h)
        if not t or len(t) > 40 or not RE_A_LIRE.match(t.strip()):
            continue
        p = h.parent
        if p is None:
            continue
        autres = sum(1 for x in tous(p, {"h1", "h2"}) if x is not h)
        a_plat = p.tag in ("main", "article", "body", "#doc") or autres > 0
        if etiquette:
            # Une simple étiquette (« Related posts » en <p>) ne marque qu'un conteneur qui lui est dédié.
            if not a_plat:
                p.force = "à lire aussi"
            continue
        if a_plat:
            # Section à plat : on marque les frères qui suivent, jusqu'au prochain titre.
            vu = False
            for frere in p.enfants:
                if frere is h:
                    vu = True
                    h.force = "à lire aussi"
                    continue
                if vu and not isinstance(frere, str):
                    if frere.tag in TITRES and frere.tag <= h.tag:
                        break
                    frere.force = "à lire aussi"
        else:
            p.force = "à lire aussi"


# --------------------------------------------------------------------------- lecture d'une page

class Bloc:
    __slots__ = ("tag", "morceaux", "texte", "spans", "section", "zone", "offset", "titre", "liens")

    def __init__(self, tag, section, zone):
        self.tag, self.morceaux, self.section, self.zone = tag, [], section, zone
        self.texte, self.spans, self.offset, self.titre, self.liens = "", [], 0, tag in TITRES, []

    def fermer(self):
        out, spans, pos = [], [], 0
        for t, dl in self.morceaux:
            t = re.sub(r"\s+", " ", t)
            if not t:
                continue
            if (not out or out[-1].endswith(" ")) and t.startswith(" "):
                t = t[1:]
                if not t:
                    continue
            if dl:
                if spans and spans[-1][1] == pos:
                    spans[-1] = (spans[-1][0], pos + len(t))
                else:
                    spans.append((pos, pos + len(t)))
            out.append(t)
            pos += len(t)
        s = "".join(out).rstrip()
        self.texte = s
        self.spans = [(a, min(b, len(s))) for a, b in spans if a < len(s)]
        self.morceaux = None


def lire_page(source_html, url):
    arbre = Arbre()
    try:
        arbre.feed(source_html)
        arbre.close()
    except Exception:  # HTML trop cassé : on garde ce qui a été lu
        pass
    doc = arbre.racine
    page = {"titre": "", "h1": "", "h2": [], "canonique": "", "noindex": False, "liens": [], "blocs": [],
            "site_nom": "", "lang": ""}
    for t in tous(doc, {"title"}):
        page["titre"] = texte_de(t)
        break
    for m in tous(doc, {"meta", "link", "html"}):
        a = m.attrs
        if m.tag == "html":
            page["lang"] = a.get("lang", "")[:2].lower()
        elif m.tag == "meta" and a.get("name", "").lower() in ("robots", "googlebot") and "noindex" in a.get("content", "").lower():
            page["noindex"] = True
        elif m.tag == "meta" and a.get("property", "") == "og:site_name":
            page["site_nom"] = a.get("content", "")
        elif m.tag == "link" and "canonical" in a.get("rel", "").lower().split() and a.get("href"):
            page["canonique"] = normaliser(urllib.parse.urljoin(url, a["href"].strip()))
    for h in tous(doc, {"h1"}):
        page["h1"] = texte_de(h)
        break
    marquer_a_lire(doc)
    principaux = [n for n in tous(doc, {"main", "div", "section", "article"})
                  if n.tag == "main" or n.attrs.get("role", "").lower() == "main"]
    a_principal = bool(principaux)
    contient_main = set()
    for n in principaux:
        x = n.parent
        while x is not None:
            contient_main.add(id(x))
            x = x.parent

    etat = {"section": "", "blocs": [], "liens": []}

    def ouvrir_bloc(tag, zone):
        b = Bloc(tag, etat["section"], zone)
        etat["blocs"].append(b)
        return b

    def marche(n, zone, bloc, lien, principal):
        for c in n.enfants:
            if isinstance(c, str):
                if bloc is not None:
                    bloc.morceaux.append((c, lien is not None))
                if lien is not None:
                    lien["morceaux"].append(c)
                continue
            tag = c.tag
            if tag in IGNORES:
                continue
            dans_p = principal or tag == "main" or c.attrs.get("role", "").lower() == "main"
            z = zone
            if z is None:
                z = raison_zone(c, dans_p)
                if z is None and a_principal and not dans_p and id(c) not in contient_main:
                    z = "hors du contenu principal"
            if tag == "br":
                if bloc is not None:
                    bloc.morceaux.append((" ", lien is not None))
                continue
            if tag == "img":
                alt = c.attrs.get("alt", "")
                if lien is not None:
                    lien["bloc_interne"] = True
                    if alt:
                        lien["alt"].append(alt)
                continue
            nouveau_lien = lien
            if tag == "a" and c.attrs.get("href") is not None and lien is None:
                nouveau_lien = {"href": c.attrs.get("href", ""), "morceaux": [], "alt": [], "zone": z,
                                "bloc": bloc, "bloc_interne": False, "rel": c.attrs.get("rel", "")}
                etat["liens"].append(nouveau_lien)
            elif lien is not None and tag in DANS_LIEN_BLOC:
                lien["bloc_interne"] = True
            b = bloc
            if tag in BLOCS:
                # Un conteneur de <main> (div#app, body) n'est pas du texte : seul <main> l'est.
                b = ouvrir_bloc(tag, "conteneur" if (z is None and id(c) in contient_main) else z)
            marche(c, z, b, nouveau_lien, dans_p)
            if b is not bloc:
                b.fermer()
                if b.titre and z is None and b.texte:
                    if tag in ("h2", "h3"):
                        etat["section"] = b.texte
                    if tag == "h2":
                        page["h2"].append(b.texte)
                if bloc is not None and b.texte:
                    bloc.morceaux.append((" ", False))

    racine_bloc = ouvrir_bloc("#doc", "conteneur" if a_principal else None)
    marche(doc, None, racine_bloc, None, False)
    racine_bloc.fermer()

    # Les liens : texte, bloc ou navigation.
    for l in etat["liens"]:
        ancre = re.sub(r"\s+", " ", "".join(l["morceaux"])).strip() or " ".join(l["alt"]).strip()
        b = l["bloc"]
        if l["zone"] is not None:
            genre, raison = "navigation", l["zone"]
        elif l["bloc_interne"] or b is None or b.titre:
            genre, raison = "bloc", "titre cliquable" if (b is not None and b.titre) else "carte ou image"
        else:
            reste = b.texte
            for a_, z_ in sorted(b.spans, reverse=True):
                reste = reste[:a_] + " " + reste[z_:]
            if len([m for m in mots(reste) if len(m) >= 2]) >= MOTS_AUTOUR:
                genre, raison = "texte", ""
            else:
                genre, raison = "bloc", "lien seul (liste, bouton)"
        page["liens"].append({"href": l["href"], "ancre": ancre, "genre": genre, "raison": raison,
                              "bloc": b, "rel": l["rel"]})
    # Le texte principal, dans l'ordre.
    pos = 0
    for b in etat["blocs"]:
        if b.zone is None and b.texte:
            b.offset = pos
            pos += len(b.texte) + 1
            page["blocs"].append(b)
    page["mots"] = sum(len(mots(b.texte)) for b in page["blocs"] if not b.titre)
    return page


# --------------------------------------------------------------------------- le site

PAGES_SERVICE = re.compile(
    r"(mentions|legal|l[eé]gal|confidentialit|privacy|cookie|terms|conditions|\btos\b|cgu|cgv|rgpd|gdpr|imprint|"
    r"impressum|disclaimer|contact|login|connexion|signin|sign-in|signup|inscription|account|compte|panier|cart|"
    r"checkout|merci|thank|404|plan-du-site|sitemap|unsubscribe|desinscription)", re.I)


def dossier_site(racine, host):
    nu = host.removeprefix("www.")
    for c in (host, nu, "www." + nu):
        if os.path.isdir(os.path.join(racine, c)):
            return os.path.join(racine, c)
    return os.path.join(racine, nu)


def lire_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ecrire_csv(path, entete, lignes):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(entete)
        w.writerows(lignes)


def gsc(site_dir):
    """Impressions par page sur les 28 derniers jours et état d'indexation, si search-console a tourné."""
    impr, index, info = {}, {}, ""
    p = os.path.join(site_dir, "donnees", "pages_jours.csv")
    if os.path.exists(p):
        try:
            rows = lire_csv(p)
            if rows:
                fin = max(r["date"] for r in rows)
                debut = (dt.date.fromisoformat(fin) - dt.timedelta(days=27)).isoformat()
                for r in rows:
                    if r["date"] >= debut:
                        u = normaliser(r["page"])
                        impr[u] = impr.get(u, 0) + int(float(r.get("impressions") or 0))
                info = f"impressions Search Console du {debut} au {fin}"
        except (OSError, KeyError, ValueError):
            impr = {}
    p = os.path.join(site_dir, "donnees", "index.csv")
    if os.path.exists(p):
        try:
            for r in lire_csv(p):
                index[normaliser(r["url"])] = r.get("couverture", "")
        except (OSError, KeyError):
            index = {}
    return impr, index, info


def avec_ou_sans_slash(d, u):
    if u in d:
        return d[u]
    alt = u[:-1] if u.endswith("/") and len(urllib.parse.urlsplit(u).path) > 1 else u + "/"
    return d.get(alt)


def seo_audit(site_dir):
    """Réutilise le crawl de la skill `seo-audit` (pages.csv de moins de 2 jours) : statuts et redirections."""
    p = os.path.join(site_dir, "seo-audit", "pages.csv")
    if not os.path.exists(p) or time.time() - os.path.getmtime(p) > FRAIS_JOURS * 86400:
        return {}
    out = {}
    try:
        for r in lire_csv(p):
            u = r.get("url") or r.get("page") or ""
            if not u:
                continue
            code = r.get("statut") or r.get("code") or r.get("status") or ""
            finale = r.get("url_finale") or r.get("finale") or r.get("redirection") or r.get("final_url") or u
            try:
                code = int(float(code))
            except ValueError:
                continue
            out[normaliser(u)] = {"code": code, "finale": normaliser(finale)}
    except (OSError, csv.Error):
        return {}
    return out


def explorer(base_url, graines, maxi, deja):
    """Télécharge les pages par vagues, en parallèle, dans un ordre fixe. Rend {url demandée: résultat}."""
    res = {}
    file_ = list(dict.fromkeys(graines))
    vus = set(file_)
    base = hote_nu(base_url)

    def une(u):
        if not autorise(u):
            return u, {"code": -1, "finale": u, "erreur": "interdit par robots.txt", "html": None}
        r = lire_url(u)
        time.sleep(PAUSE)
        page_html = None
        if r["code"] == 200 and "html" in r["type"].lower():
            page_html = decoder(r["corps"], r["charset"])
        return u, {"code": r["code"], "finale": normaliser(r["finale"]), "erreur": r["erreur"],
                   "html": page_html, "type": r["type"], "xrobots": r["xrobots"]}

    debut = time.time()
    with ThreadPoolExecutor(FILS) as ex:
        while file_ and len(res) < maxi:
            vague = file_[: maxi - len(res)]
            file_ = file_[len(vague):]
            for u, r in ex.map(une, vague):
                res[u] = r
                if r["html"]:
                    r["page"] = lire_page(r["html"], r["finale"])
                    r["html"] = None
            nouveaux = defaultdict(set)
            for u in vague:
                p = res[u].get("page")
                if not p:
                    continue
                for l in p["liens"]:
                    cible = resoudre_href(l["href"], res[u]["finale"], base)
                    if cible:
                        c = sans_query(cible)
                        if c not in vus and c not in deja:
                            nouveaux[c].add(u)
            # Les URL hors sitemap les plus liées d'abord (le plafond --max coupe les moins liées).
            for c in sorted(nouveaux, key=lambda c: (-len(nouveaux[c]), c)):
                vus.add(c)
                file_.append(c)
            dire(f"  {len(res)} pages lues ({time.time() - debut:.0f} s)")
    return res, file_


def resoudre_href(href, page_url, base):
    href = (href or "").strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "sms:", "whatsapp:")):
        return None
    try:
        u = normaliser(urllib.parse.urljoin(page_url, href))
    except ValueError:
        return None
    p = urllib.parse.urlsplit(u)
    if p.scheme not in ("http", "https") or hote_nu(u) != base:
        return None
    if EXT_FICHIERS.search(p.path):
        return None
    return u


# --------------------------------------------------------------------------- les termes d'une page

SEP_TITRE = re.compile(r"\s+[|—–·•:]\s+|\s+-\s+|\s*::\s*")


def nettoyer_titres(pages):
    """Retire le suffixe de marque répété (« … | MonSite ») des titles."""
    fins = Counter()
    for p in pages.values():
        parts = SEP_TITRE.split(p["titre"])
        if len(parts) > 1:
            fins[norme_ancre(parts[-1])] += 1
    marque = {f for f, n in fins.items() if f and n >= max(2, 0.3 * len(pages))}
    for p in pages.values():
        parts = SEP_TITRE.split(p["titre"])
        if len(parts) > 1 and norme_ancre(parts[-1]) in marque:
            parts = parts[:-1]
        p["titre_net"] = " — ".join(parts).strip()
    return marque


def morceaux_titre(t):
    """Les morceaux d'un titre où une expression peut vivre (« Paris & Lyon » n'en est pas une)."""
    return [m for m in re.split(r"[:;,!?()«»\"“”|—–·…&+/]+|\s-\s|\.\s|\s(?:and|et|or|ou|vs\.?)\s", t, flags=re.I)
            if m.strip()]


def significatif(m, original=""):
    n = sans_accents(m)
    if n in STOP or ANNEES.match(n) or n.isdigit():
        return False
    if len(n) >= 4:
        return True
    return bool(original) and original.isupper() and len(original) >= 2 and original.isalpha()


def termes_page(p, url, marque_mots):
    """Les termes qui désignent une page : ses mots rares, ses expressions de 2 à 4 mots, son slug."""
    simples, expressions = {}, {}
    for source in (p.get("h1", ""), p.get("titre_net", "")):
        for morceau in morceaux_titre(source):
            orig = mots(morceau)
            for i, m in enumerate(orig):
                if significatif(m, m) and sans_accents(m) not in marque_mots:
                    simples.setdefault(racine_mot(m), sans_accents(m))
            for n in (4, 3, 2):
                for i in range(len(orig) - n + 1):
                    seq = orig[i:i + n]
                    if not (significatif(seq[0], seq[0]) and significatif(seq[-1], seq[-1])):
                        continue
                    if all(sans_accents(x) in marque_mots for x in seq):
                        continue
                    cle = " ".join(racine_mot(x) for x in seq)
                    expressions.setdefault(cle, [sans_accents(x) for x in seq])
    seg = [s for s in urllib.parse.unquote(urllib.parse.urlsplit(url).path).split("/") if s]
    slug = set()  # le slug d'un seul mot (/crm, /docker) : ce mot désigne la page
    if seg:
        un = [x for x in re.split(r"[-_]+", seg[-1].rsplit(".", 1)[0]) if x and not ANNEES.match(x)]
        if len(un) == 1:
            slug = {racine_mot(un[0])}
        dernier = re.split(r"[-_]+", seg[-1].rsplit(".", 1)[0])
        dernier = [d for d in dernier if d and not ANNEES.match(d)]
        if len(dernier) == 1 and len(dernier[0]) >= 3 and sans_accents(dernier[0]) not in STOP:
            simples.setdefault(racine_mot(dernier[0]), sans_accents(dernier[0]))
        elif 2 <= len(dernier) <= 4 and significatif(dernier[0], dernier[0].upper() if len(dernier[0]) <= 3 else dernier[0]) \
                and significatif(dernier[-1], dernier[-1].upper() if len(dernier[-1]) <= 3 else dernier[-1]):
            expressions.setdefault(" ".join(racine_mot(x) for x in dernier), [sans_accents(x) for x in dernier])
    return simples, expressions, slug


def motif(mots_):
    parts = []
    for m in mots_:
        m = re.escape(m)
        if len(m) >= 4 and m[-1] in "sx" and not m.endswith("ss"):
            parts.append(m[:-1] + "[sx]?")
        elif len(m) >= 4:
            parts.append(m + "[sx]?")
        else:
            parts.append(m)
    return re.compile(r"(?<![\w])" + r"[\s\-'’]+".join(parts) + r"(?![\w])")


# --------------------------------------------------------------------------- propositions

def bornes_phrase(texte, a, b):
    debut = 0
    for m in re.finditer(r"[.!?…][»\"”')\]]*\s+", texte[:a]):
        debut = m.end()
    fin = len(texte)
    m = re.search(r"[.!?…](?=[»\"”')\]]*(?:\s|$))", texte[b:])
    if m:
        fin = b + m.end()
    return debut, fin


def phrase_autour(texte, a, b):
    debut, fin = bornes_phrase(texte, a, b)
    ph = texte[debut:fin].strip()
    a2, b2 = a - debut, b - debut
    if len(ph) > 300:
        g = max(0, a2 - 130)
        d = min(len(ph), b2 + 130)
        while g > 0 and ph[g - 1] != " ":
            g -= 1
        while d < len(ph) and ph[d] != " ":
            d += 1
        ph = ("… " if g > 0 else "") + ph[g:d].strip() + (" …" if d < len(ph) else "")
    return ph


def etendre_ancre(texte, a, b, vocab, spans):
    """Élargit une ancre d'un mot aux mots voisins du titre de la cible (4 mots au plus)."""
    toks = [(m.start(), m.end(), m.group()) for m in re.finditer(r"[^\W_]+", texte)]
    idx = [i for i, t in enumerate(toks) if t[0] >= a and t[1] <= b]
    if not idx:
        return a, b
    i0, i1 = idx[0], idx[-1]

    def libre(x, y):
        return not any(s < y and x < e for s, e in spans)

    while i1 - i0 < 3:
        moved = False
        if i0 > 0:
            s, e, w = toks[i0 - 1]
            entre = texte[e:toks[i0][0]]
            if entre.strip() in ("", "-") and racine_mot(w) in vocab and libre(s, e):
                i0 -= 1
                moved = True
        if i1 - i0 < 3 and i1 + 1 < len(toks):
            s, e, w = toks[i1 + 1]
            entre = texte[toks[i1][1]:s]
            if entre.strip() in ("", "-") and racine_mot(w) in vocab and libre(s, e):
                i1 += 1
                moved = True
        if not moved:
            break
    while i0 < i1 and sans_accents(toks[i0][2]) in STOP:
        i0 += 1
    while i1 > i0 and sans_accents(toks[i1][2]) in STOP:
        i1 -= 1
    return toks[i0][0], toks[i1][1]


def extrait(texte, a, b):
    toks = [(m.start(), m.end()) for m in re.finditer(r"\S+", texte)]
    avant = [t for t in toks if t[1] <= a][-MOTS_AUTOUR:]
    apres = [t for t in toks if t[0] >= b][:MOTS_AUTOUR]
    g = avant[0][0] if avant else a
    d = apres[-1][1] if apres else b
    return texte[g:d]


def preparer_source(page):
    """Le texte d'une page mis à plat une fois pour toutes : la recherche d'un terme y est un seul passage."""
    blocs = page["blocs"]
    plat, debuts = [], []
    pos = 0
    for b in blocs:
        debuts.append(pos)
        plat.append(sans_accents(b.texte))
        pos += len(b.texte) + 1
    compte = Counter(racine_mot(m) for t in plat for m in mots(t))
    for t in (page.get("titre", ""), page.get("h1", "")):
        compte.update(racine_mot(m) for m in mots(t))
    # Nom propre ou nom commun : combien de fois le mot est écrit avec une majuscule au milieu d'une phrase.
    milieu, majuscule = Counter(), Counter()
    for b in blocs:
        if b.titre:
            continue
        for m in re.finditer(r"[^\W_]+", b.texte):
            avant = b.texte[:m.start()].rstrip(" «\"“'(")
            if not avant or avant[-1] in ".!?:…•-–—\n":
                continue
            r = racine_mot(m.group())
            milieu[r] += 1
            if m.group()[0].isupper():
                majuscule[r] += 1
    return {"plat": "\n".join(plat), "debuts": debuts, "vocab": set(compte), "compte": compte,
            "total": sum(compte.values()), "sections": {}, "milieu": milieu, "majuscule": majuscule}


def nom_propre(prep, racine):
    return prep["milieu"][racine] >= 2 and prep["majuscule"][racine] >= 0.6 * prep["milieu"][racine]


def autre_entite(texte, a, z, vocab):
    """« Google » dans « Google Cloud » : un mot seul collé à un autre nom propre désigne autre chose."""
    apres = re.match(r"[ \-]+([^\W_]+)", texte[z:])
    if apres and apres.group(1)[0].isupper() and racine_mot(apres.group(1)) not in vocab:
        return True
    avant = re.search(r"([^\W_]+)[ \-]+$", texte[:a])
    if avant and avant.group(1)[0].isupper() and racine_mot(avant.group(1)) not in vocab:
        debut = texte[:avant.start()].rstrip(" «\"“'(")
        if debut and debut[-1] not in ".!?:…•-–—":
            return True
    return False


def chercher_mention(blocs, prep, motifs, vocab=frozenset()):
    """La mention à lier : dans une section qui porte sur le sujet si possible, sinon la première ;
    une expression passe avant un mot seul. Jamais dans un lien ni dans un titre."""
    import bisect
    meilleure = None
    for nmots, specif, pat, terme, requis, propre_, _commun in motifs:
        if not requis <= prep["vocab"]:
            continue
        premiere = False
        for m in pat.finditer(prep["plat"]):
            i = bisect.bisect_right(prep["debuts"], m.start()) - 1
            b = blocs[i]
            a, z = m.start() - prep["debuts"][i], m.end() - prep["debuts"][i]
            if b.titre or z > len(b.texte) or any(s < z and a < e for s, e in b.spans):
                continue
            if nmots == 1 and propre_ and not b.texte[a].isupper():
                continue  # « docker » en minuscule n'est pas Docker
            if autre_entite(b.texte, a, z, vocab):
                continue  # « Paris Tourism Office » n'est pas la page Tourism
            d_, f_ = bornes_phrase(b.texte, a, z)
            if len(mots(b.texte[d_:f_])) < 5:
                continue  # « Loading map… », une cellule de tableau : pas une phrase où poser un lien
            cle = (b.section, id(motifs))
            if cle not in prep["sections"]:
                sec = sans_accents(b.section)
                prep["sections"][cle] = bool(b.section) and any(x[2].search(sec) for x in motifs)
            section_ok = prep["sections"][cle]
            if not section_ok and premiere:
                continue  # la première mention est déjà retenue ; on ne cherche plus qu'une section sur le sujet
            cand = (0 if section_ok else 1, -min(nmots, 2), b.offset + a, i, a, z, nmots, specif, terme, section_ok)
            if meilleure is None or cand < meilleure:
                meilleure = cand
            premiere = True
            if section_ok:
                break
    return meilleure


def proposer(noeuds, graphe_contenu, cibles, base, impr, existants, liens_ancres):
    """Pour chaque cible : les sources qui la mentionnent sans la lier."""
    pages = {u: n for u, n in noeuds.items() if n["page"] is not None}
    marque_mots = set()
    for n in pages.values():
        for m in mots(n["page"].get("site_nom", "")):
            marque_mots.add(sans_accents(m))
    marque_mots |= {sans_accents(m) for m in mots(base.split(".")[0])}
    # Les termes de chaque page, et combien de pages partagent chaque terme.
    termes = {u: termes_page(n["page"], u, marque_mots) for u, n in pages.items() if n["indexable"]}
    df_s, df_e = Counter(), Counter()
    for s, e, _ in termes.values():
        df_s.update(s.keys())
        df_e.update(e.keys())
    preps = {u: preparer_source(n["page"]) for u, n in pages.items() if n["indexable"] and not n["service"]}
    site_c = Counter()
    for pr in preps.values():
        site_c.update(pr["compte"])
    site_total = sum(site_c.values()) or 1

    # Proximité de deux pages : leur vocabulaire commun (tf-idf, cosinus de 0 à 1).
    n_docs = len(preps)
    df_mots = Counter()
    for pr in preps.values():
        df_mots.update(k for k in pr["compte"] if len(k) >= 3 and k not in STOP and not k.isdigit())
    vecteurs = {}
    for u, pr in preps.items():
        v = {k: (1 + math.log(c)) * math.log(n_docs / df_mots[k]) for k, c in pr["compte"].items()
             if df_mots.get(k) and df_mots[k] < n_docs}
        vecteurs[u] = (v, math.sqrt(sum(x * x for x in v.values())) or 1.0)

    def proximite(a, b):
        (va, na), (vb, nb) = vecteurs[a], vecteurs[b]
        if len(va) > len(vb):
            va, vb = vb, va
        return sum(x * vb.get(k, 0.0) for k, x in va.items()) / (na * nb)

    def ratio(u, racine):
        """Combien de fois ce mot est plus fréquent sur la page u que sur l'ensemble du site."""
        pr = preps[u]
        return ((pr["compte"][racine] + 0.5) / (pr["total"] or 1)) / ((site_c[racine] + 0.5) / site_total)
    longueur = {u: (n["page"]["blocs"][-1].offset + len(n["page"]["blocs"][-1].texte)) if n["page"]["blocs"] else 1
                for u, n in pages.items()}
    sources = sorted(u for u, n in pages.items() if n["indexable"] and not n["service"])
    out = []
    for cible in cibles:
        if cible not in termes or cible not in preps:
            continue
        s, e, slug = termes[cible]
        motifs, communs = [], set()
        # Un terme ne désigne la cible que s'il y est nettement plus fréquent qu'ailleurs sur le site :
        # « Docker » sur la page Docker, pas « même » ni « chacun ».
        for cle, ms in e.items():
            rs = [ratio(cible, racine_mot(x)) for x in ms if significatif(x, x.upper() if len(x) <= 3 else x)]
            if df_e[cle] <= 3 and rs and max(rs) >= RATIO_EXPRESSION:
                motifs.append((len(ms), max(rs), motif(ms), " ".join(ms),
                               {racine_mot(x) for x in ms if len(x) >= 4}, False, False))
        for cle, m in s.items():
            # Un mot seul : celui d'un slug d'un mot (/crm, /docker) ou un nom propre de la page (Docker, Lisbonne),
            # jamais un mot courant du titre (« façon », « même », « chacun ») : trop de faux amis.
            r_ = ratio(cible, cle)
            propre = nom_propre(preps[cible], cle)
            if df_s[cle] <= 2 and r_ >= RATIO_MOT and preps[cible]["compte"][cle] >= 3 and (cle in slug or propre):
                motifs.append((1, r_, motif([m]), m, {racine_mot(m)} if len(m) >= 4 else set(),
                               propre and cle not in slug, not propre))
                if not propre:
                    communs.add(m)
        if not motifs:
            continue
        vocab = set(s.keys()) | {racine_mot(x) for ms in e.values() for x in ms}
        cands = []
        for src in sources:
            if src == cible or cible in graphe_contenu.get(src, ()):
                continue
            n = pages[src]
            prox = proximite(src, cible)
            # Un mot courant seul n'est un bon lien qu'entre deux pages proches : sinon c'est un faux ami.
            ms_src = motifs if prox >= PROXIMITE_MOT else [x for x in motifs if not x[6]]
            if not ms_src:
                continue
            mention = chercher_mention(n["page"]["blocs"], preps[src], ms_src, vocab)
            if mention is None:
                continue
            _, _, gpos, i, a, z, nmots, specif, terme, section_ok = mention
            b = n["page"]["blocs"][i]
            if nmots == 1:
                a, z = etendre_ancre(b.texte, a, z, vocab, b.spans)
            ancre = b.texte[a:z]
            if norme_ancre(ancre) in GENERIQUES:
                continue
            autres = liens_ancres.get(norme_ancre(ancre), set()) - {cible}
            frac = gpos / max(1, longueur[src])
            score = 2.0 if nmots >= 2 else (-1.5 if terme in communs else 0.0)
            score += min(3.0, math.log2(specif))
            score += 2 if section_ok else 0
            score += 2 if frac <= 0.25 else (1 if frac <= 0.5 else 0)
            score += min(3.0, 10 * prox)
            im = avec_ou_sans_slash(impr, src) or 0
            score += min(2.0, math.log10(1 + im)) if impr else 0
            raison = []
            raison.append(f"« {terme} » (" + ("expression du titre" if nmots >= 2 else
                                              "mot courant, à vérifier" if terme in communs else "nom propre du titre")
                          + f"), {specif:.0f} fois plus fréquent sur la cible qu'ailleurs")
            if section_ok:
                raison.append(f"dans la section « {b.section[:60]} »")
            raison.append(f"à {frac * 100:.0f} % de la page")
            raison.append(f"proximité des deux pages {prox:.2f}".replace(".", ","))
            if impr:
                raison.append(f"{nombre(im)} impressions sur 28 j")
            if autres:
                raison.append("ancre déjà utilisée vers " + ", ".join(court(x, base) for x in sorted(autres)[:2]))
                score -= 1
            cands.append({"source": src, "cible": cible, "phrase": phrase_autour(b.texte, a, z), "ancre": ancre,
                          "score": round(score, 1), "terme": terme, "section": b.section if section_ok else "",
                          "extrait": extrait(b.texte, a, z), "raison": ", ".join(raison)})
        out += cands
    # Une même phrase ne porte qu'un lien : si elle sert deux cibles (« life in Paris »), la mieux notée la garde.
    meilleur = {}
    for c in sorted(out, key=lambda c: (-c["score"], c["cible"])):
        meilleur.setdefault((c["source"], norme_ancre(c["ancre"]), c["phrase"]), c)
    gardes = set(map(id, meilleur.values()))
    par_cible = defaultdict(list)
    for c in out:
        if id(c) in gardes:
            par_cible[c["cible"]].append(c)
    out = []
    for cible in cibles:
        cs = sorted(par_cible.get(cible, []), key=lambda c: (-c["score"], c["source"]))
        out += cs[:MAX_PAR_CIBLE]
    for c in out:
        c["statut"] = existants.get((c["source"], c["cible"]), "")
    return out


# --------------------------------------------------------------------------- graphe et rapport

def bfs(depart, voisins):
    prof = {depart: 0}
    q = deque([depart])
    while q:
        u = q.popleft()
        for v in sorted(voisins.get(u, ())):
            if v not in prof:
                prof[v] = prof[u] + 1
                q.append(v)
    return prof


def analyser(site, base_url, res, sitemap, impr, index, audit):
    base = hote_nu(base_url)
    # Où mène chaque URL demandée (redirections, canonique).
    vers = {}
    for u, r in res.items():
        vers[u] = r
    for u, r in audit.items():
        vers.setdefault(u, {"code": r["code"], "finale": r["finale"], "page": None, "erreur": ""})

    noeuds = {}
    for u, r in sorted(res.items()):
        if r.get("page") is None or r["code"] != 200:
            continue
        f = r["finale"]
        if f in noeuds:
            continue
        p = r["page"]
        noindex = p["noindex"] or "noindex" in (r.get("xrobots") or "").lower()
        can = p["canonique"]
        can_ailleurs = bool(can) and sans_query(can) != sans_query(f) and can.rstrip("/") != f.rstrip("/")
        chemin = urllib.parse.urlsplit(f).path
        noeuds[f] = {"page": p, "noindex": noindex, "canonique": can if can_ailleurs else "",
                     "sitemap": f in sitemap or u in sitemap, "accueil": chemin in ("", "/"),
                     "service": bool(PAGES_SERVICE.search(chemin)) and chemin not in ("", "/"),
                     "indexable": not noindex and not can_ailleurs}

    def destination(cible):
        """URL demandée -> (nœud ou None, problèmes)."""
        pbs = []
        if urllib.parse.urlsplit(cible).query:
            pbs.append("paramètres")
        c = sans_query(cible)
        r = vers.get(cible) or vers.get(c)
        if r is None:
            return (c if c in noeuds else None), pbs + ([] if c in noeuds else ["non vérifié"]), None
        if r["code"] == -1:
            return None, pbs + ["interdit par robots.txt"], r
        if r["code"] == 0:
            return None, pbs + ["injoignable"], r
        if r["code"] >= 400:
            return None, pbs + [f"cassé ({r['code']})"], r
        fin = r["finale"]
        if sans_query(fin) != c:
            pbs.append("redirigé")
        n = noeuds.get(fin) or noeuds.get(sans_query(fin))
        if n is None:
            return None, pbs + ["fichier"], r
        node = fin if fin in noeuds else sans_query(fin)
        if n["noindex"]:
            pbs.append("noindex")
        if n["canonique"]:
            pbs.append("non canonique")
            if n["canonique"] in noeuds:
                node = n["canonique"]
        return node, pbs, r

    # Les liens, page par page.
    aretes = []
    for src, n in sorted(noeuds.items()):
        for l in n["page"]["liens"]:
            cible = resoudre_href(l["href"], src, base)
            if not cible:
                continue
            node, pbs, _ = destination(cible)
            if node == src:
                continue
            aretes.append({"source": src, "cible_demandee": cible, "cible": node, "genre": l["genre"],
                           "raison": l["raison"], "ancre": l["ancre"], "problemes": pbs, "nofollow": "nofollow" in l["rel"]})
    # Gabarit : un lien (même cible, même ancre) présent sur la moitié des pages ou plus est de la navigation.
    n_pages = len(noeuds)
    seuil_gabarit = max(4, math.ceil(0.5 * n_pages))
    # (On ne compte que les liens hors menu : un lien de phrase qui reprend l'ancre du pied de page reste un lien de phrase.)
    freq = Counter()
    for (cible, ancre), srcs in _grouper([a for a in aretes if a["genre"] != "navigation"]).items():
        freq[(cible, ancre)] = len(srcs)
    for a in aretes:
        if a["genre"] != "navigation" and freq[(a["cible_demandee"], norme_ancre(a["ancre"]))] >= seuil_gabarit:
            a["genre"], a["raison"] = "navigation", f"répété sur {freq[(a['cible_demandee'], norme_ancre(a['ancre']))]} pages"
    # Les blocs de texte répétés partout (bio d'auteur, bandeau) ne servent pas aux propositions.
    freq_bloc = Counter()
    for n in noeuds.values():
        for h in {hashlib.md5(b.texte.encode()).hexdigest() for b in n["page"]["blocs"] if len(b.texte) >= 20}:
            freq_bloc[h] += 1
    for n in noeuds.values():
        n["page"]["blocs"] = [b for b in n["page"]["blocs"] if len(b.texte) < 20 or
                              freq_bloc[hashlib.md5(b.texte.encode()).hexdigest()] < seuil_gabarit]

    entrants = {u: {"texte": set(), "bloc": set(), "navigation": set()} for u in noeuds}
    sortants = {u: {"texte": set(), "bloc": set(), "navigation": set()} for u in noeuds}
    for a in aretes:
        if a["cible"] in noeuds:
            entrants[a["cible"]][a["genre"]].add(a["source"])
            sortants[a["source"]][a["genre"]].add(a["cible"])
    tous_liens = {u: s["texte"] | s["bloc"] | s["navigation"] for u, s in sortants.items()}
    contenu = {u: s["texte"] | s["bloc"] for u, s in sortants.items()}
    accueil = next((u for u, n in noeuds.items() if n["accueil"]), None)
    if accueil is None:
        accueil = normaliser(base_url)
    prof_tous = bfs(accueil, tous_liens) if accueil in noeuds else {}
    prof_contenu = bfs(accueil, contenu) if accueil in noeuds else {}
    n_liens_texte = Counter(a["cible"] for a in aretes if a["genre"] == "texte")
    for u, n in noeuds.items():
        n.update({"e_texte": len(entrants[u]["texte"]), "e_bloc": len(entrants[u]["bloc"] - entrants[u]["texte"]),
                  "e_nav": len(entrants[u]["navigation"] - entrants[u]["texte"] - entrants[u]["bloc"]),
                  "s_texte": len(sortants[u]["texte"]), "s_bloc": len(sortants[u]["bloc"] - sortants[u]["texte"]),
                  "s_nav": len(sortants[u]["navigation"]), "prof": prof_tous.get(u), "prof_contenu": prof_contenu.get(u),
                  "impr": avec_ou_sans_slash(impr, u), "couverture": avec_ou_sans_slash(index, u) or "",
                  "liens_texte_entrants": n_liens_texte[u]})
    return noeuds, aretes, entrants, contenu, accueil, seuil_gabarit


def _grouper(aretes):
    g = defaultdict(set)
    for a in aretes:
        g[(a["cible_demandee"], norme_ancre(a["ancre"]))].add(a["source"])
    return g


def generer(site, base_url, site_dir, res, sitemap, sitemaps_lus, impr, index, info_gsc, audit, min_e, maxi,
            reste, duree):
    base = hote_nu(base_url)
    noeuds, aretes, entrants, contenu, accueil, seuil_gabarit = analyser(site, base_url, res, sitemap, impr, index, audit)
    if not noeuds:
        raise Panne("Aucune page HTML lisible : le site refuse peut-être les robots, ou ses pages sont vides sans JavaScript.")
    out_dir = os.path.join(site_dir, "internal-links")
    os.makedirs(out_dir, exist_ok=True)
    C = lambda u: court(u, base)  # noqa: E731

    # Pages à suivre : celles du sitemap, indexables, hors accueil et pages de service.
    suivies = sorted((u for u, n in noeuds.items() if n["indexable"] and not n["service"] and not n["accueil"]
                      and (n["sitemap"] or not sitemap)),
                     key=lambda u: (noeuds[u]["e_texte"], -(noeuds[u]["impr"] or 0), u))
    orphelines = [u for u in suivies if noeuds[u]["e_texte"] == 0]
    sous_seuil = [u for u in suivies if 0 < noeuds[u]["e_texte"] < min_e]
    aucune = [u for u in orphelines if noeuds[u]["e_bloc"] == 0 and noeuds[u]["e_nav"] == 0]
    que_menu = [u for u in orphelines if noeuds[u]["e_bloc"] == 0 and noeuds[u]["e_nav"] > 0]
    que_cartes = [u for u in orphelines if noeuds[u]["e_bloc"] > 0]
    puits = sorted((u for u in suivies if noeuds[u]["e_texte"] >= min_e and noeuds[u]["s_texte"] == 0),
                   key=lambda u: (-noeuds[u]["e_texte"], u))
    lignes_contenu = [a for a in aretes if a["genre"] in ("texte", "bloc")]
    n_texte = sum(1 for a in aretes if a["genre"] == "texte" and a["cible"] in noeuds)
    n_pages = len(noeuds)
    mediane_e = sorted(noeuds[u]["e_texte"] for u in suivies)[len(suivies) // 2] if suivies else 0
    mediane_s = sorted(len(contenu[u]) for u in noeuds)[n_pages // 2]
    hubs = sorted((u for u in noeuds if len(contenu[u]) >= max(8, 2 * mediane_s) and noeuds[u]["indexable"]
                   and not noeuds[u]["accueil"]), key=lambda u: (-len(contenu[u]), u))
    sans_retour = []
    for h in hubs:
        for s in sorted(contenu[h]):
            n = noeuds.get(s)
            if n and n["indexable"] and not n["service"] and not n["accueil"] and h not in contenu.get(s, ()):
                sans_retour.append((h, s))
    # D'abord les vrais satellites : les pages rangées sous l'URL du hub (/guides/ -> /guides/xxx).
    sous = lambda h, s: urllib.parse.urlsplit(s).path.startswith(urllib.parse.urlsplit(h).path.rstrip("/") + "/")  # noqa: E731
    sans_retour.sort(key=lambda hs: (not sous(*hs), hubs.index(hs[0]), hs[1]))
    n_sous = sum(1 for hs in sans_retour if sous(*hs))
    # Ancres.
    generiques = [a for a in lignes_contenu if norme_ancre(a["ancre"]) in GENERIQUES or
                  re.match(r"^(cliquez|clique|click)\b", norme_ancre(a["ancre"]))]
    par_ancre = defaultdict(lambda: defaultdict(set))
    for a in lignes_contenu:
        k = norme_ancre(a["ancre"])
        if len(k) >= 3 and k not in GENERIQUES and a["cible"]:
            par_ancre[k][a["cible"]].add(a["source"])
    ambigues = sorted(((k, v) for k, v in par_ancre.items() if len(v) >= 2), key=lambda kv: (-len(kv[1]), kv[0]))
    liens_ancres = {k: set(v) for k, v in par_ancre.items()}
    # Liens à corriger.
    a_corriger = defaultdict(lambda: {"sources": set(), "genres": Counter(), "problemes": None, "finale": ""})
    for a in aretes:
        pbs = [p for p in a["problemes"] if p not in ("non vérifié", "fichier")]
        if not pbs:
            continue
        k = a["cible_demandee"]
        a_corriger[k]["sources"].add(a["source"])
        a_corriger[k]["genres"][a["genre"]] += 1
        a_corriger[k]["problemes"] = pbs
        r = res.get(k) or res.get(sans_query(k))
        if r and "redirigé" in pbs:
            a_corriger[k]["finale"] = r["finale"]
        if "non canonique" in pbs and a["cible"]:
            a_corriger[k]["finale"] = a["cible"]
    casses = [k for k, v in a_corriger.items() if any(p.startswith("cassé") or p == "injoignable" for p in v["problemes"])]
    non_verifies = sorted({a["cible_demandee"] for a in aretes if "non vérifié" in a["problemes"]})

    # Propositions.
    old = {}
    prop_path = os.path.join(out_dir, "propositions.csv")
    anciens = []
    if os.path.exists(prop_path):
        try:
            anciens = lire_csv(prop_path)
            old = {(r["source"], r["cible"]): r.get("statut", "") for r in anciens}
        except (OSError, KeyError, csv.Error):
            anciens, old = [], {}
    cibles = [u for u in suivies if noeuds[u]["e_texte"] < min_e]
    props = proposer(noeuds, contenu, cibles, base, impr, old, liens_ancres)
    deja = {(p["source"], p["cible"]) for p in props}
    poses = []
    for r in anciens:
        k = (r.get("source", ""), r.get("cible", ""))
        if k in deja or not r.get("cible"):
            continue
        if r["cible"] in contenu.get(r["source"], ()):
            r = dict(r)
            if not r.get("statut", "").startswith("posé"):
                r["statut"] = f"posé (vu en ligne le {dt.date.today().isoformat()})"
            poses.append(r)
        elif r.get("statut", "").startswith(("écarté", "ecarte")):
            poses.append(r)
    cibles_avec = list(dict.fromkeys(p["cible"] for p in props))

    # ---------- CSV
    cols_p = ["source", "cible", "phrase", "ancre", "score", "statut", "terme", "section", "extrait", "raison"]
    ecrire_csv(prop_path, cols_p, [[p.get(c, "") for c in cols_p] for p in props] +
               [[r.get(c, "") for c in cols_p] for r in poses])
    ecrire_csv(os.path.join(out_dir, "pages.csv"),
               ["url", "dans_sitemap", "indexable", "type", "entrants_texte", "entrants_blocs", "entrants_nav",
                "liens_texte_entrants", "sortants_texte", "sortants_blocs", "sortants_nav", "profondeur",
                "profondeur_contenu", "mots", "title", "h1", "impressions_28j", "couverture", "canonique"],
               [[u, "oui" if n["sitemap"] else "non", "oui" if n["indexable"] else "non",
                 "accueil" if n["accueil"] else ("service" if n["service"] else "page"), n["e_texte"], n["e_bloc"],
                 n["e_nav"], n["liens_texte_entrants"], n["s_texte"], n["s_bloc"], n["s_nav"],
                 "" if n["prof"] is None else n["prof"], "" if n["prof_contenu"] is None else n["prof_contenu"],
                 n["page"]["mots"], n["page"]["titre"], n["page"]["h1"], "" if n["impr"] is None else n["impr"],
                 n["couverture"], n["canonique"]] for u, n in sorted(noeuds.items())])
    ecrire_csv(os.path.join(out_dir, "graphe.csv"),
               ["source", "cible", "cible_demandee", "type", "raison", "ancre", "problemes", "nofollow"],
               [[a["source"], a["cible"] or "", a["cible_demandee"], a["genre"], a["raison"], a["ancre"],
                 " ; ".join(a["problemes"]), "oui" if a["nofollow"] else ""]
                for a in sorted(aretes, key=lambda a: (a["source"], a["cible_demandee"], a["genre"], a["ancre"]))])

    # ---------- MAILLAGE.md
    L = []
    w = L.append
    sans_texte = [u for u, n in noeuds.items() if n["page"]["mots"] < 50]
    w(f"# Maillage interne de {base}")
    w("")
    w(f"Lu le {dt.date.today().isoformat()} · {n_pages} pages lues"
      + (f" (sitemap : {len(sitemap)} URL, {', '.join(sitemaps_lus)})" if sitemap else " (pas de sitemap trouvé : exploré depuis l'accueil)")
      + f" · seuil : {min_e} liens dans le texte par page"
      + (f" · {info_gsc}" if info_gsc else " · Search Console non branchée"))
    if reste:
        w("")
        w(f"> Plafond atteint : {maxi} pages lues, {len(reste)} URL internes laissées de côté. "
          f"Relance avec `--max {maxi + len(reste) + 20}` pour tout lire.")
    if len(sans_texte) > 0.5 * n_pages:
        w("")
        w(f"> Attention : {len(sans_texte)} pages sur {n_pages} ont moins de 50 mots lisibles dans leur HTML. "
          "Le site affiche sans doute son texte en JavaScript : ce rapport ne voit que le HTML servi, comme un robot pressé.")
    w("")
    w("## En bref")
    w("")
    w("| | |")
    w("|---|---|")
    w(f"| Pages lues | {n_pages} (dont {len(suivies)} pages à mailler : indexables, hors accueil et pages de service) |")
    w(f"| Liens internes dans le texte | {n_texte} ; une page à mailler en reçoit {mediane_e} en médiane (de pages différentes) |")
    w(f"| Liens de navigation (menu, pied de page, répétés) | {sum(1 for a in aretes if a['genre'] == 'navigation')} |")
    w(f"| Liens en bloc (cartes, listes, boutons) | {sum(1 for a in aretes if a['genre'] == 'bloc')} |")
    w(f"| Orphelines (0 lien dans le texte) | {len(orphelines)} sur {len(suivies)} ({pct(len(orphelines), len(suivies))}) |")
    w(f"| Sous le seuil (1 à {min_e - 1} liens dans le texte) | {len(sous_seuil)} |")
    w(f"| Au seuil ou plus ({min_e} et plus) | {len(suivies) - len(orphelines) - len(sous_seuil)} |")
    w(f"| Liens cassés | {len(casses)} URL |")
    w(f"| Liens à corriger (paramètres, redirigés, non canoniques, noindex) | {len(a_corriger) - len(casses)} URL |")
    w(f"| Ancres génériques (« ici », « lire la suite ») | {len(generiques)} |")
    w(f"| Ancres identiques vers des pages différentes | {len(ambigues)} |")
    w(f"| Propositions | {len(props)} pour {len(cibles_avec)} pages |")
    w("")
    w("<!-- CLAUDE: le constat en deux ou trois phrases, chiffres à l'appui : où en est le maillage, la page qui "
      "y perd le plus (impressions, indexation), et ce qu'on fait d'abord. -->")
    w("")
    w("Trois sortes de liens internes :")
    w("")
    w("- **dans le texte** : au milieu d'une phrase de l'article. C'est le lien qui compte ici : Google le lit "
      "comme un vote, avec le contexte de la phrase autour.")
    w("- **en bloc** : une carte, une liste de liens, un bouton, un titre cliquable. Il fait passer le robot, "
      "sans phrase pour dire de quoi parle la page liée.")
    w("- **de navigation** : menu, en-tête, pied de page, fil d'Ariane, sommaire, « à lire aussi », ou un même "
      f"lien répété sur {seuil_gabarit} pages ou plus. Toutes les pages le reçoivent pareil : il ne distingue rien.")
    w("")

    def table_pages(urls, titre_col=True):
        w("| Page | Dans le texte | En bloc | Menu seul | Profondeur | Impressions 28 j | Index |")
        w("|---|---:|---:|---:|---:|---:|---|")
        for u in urls[:LIGNES_TABLE]:
            n = noeuds[u]
            w(f"| `{cellule(C(u), 60)}` {cellule(n['page']['h1'] or n['page']['titre'], 50) if titre_col else ''} | "
              f"{n['e_texte']} | {n['e_bloc']} | {n['e_nav']} | {'' if n['prof'] is None else n['prof']} | "
              f"{'' if n['impr'] is None else nombre(n['impr'])} | {cellule(n['couverture'], 30)} |")
        if len(urls) > LIGNES_TABLE:
            w(f"| … et {len(urls) - LIGNES_TABLE} autres dans `pages.csv` | | | | | | |")
        w("")

    w("## Orphelines : aucun lien dans le texte")
    w("")
    if orphelines:
        w(f"{len(orphelines)} pages ne reçoivent aucun lien depuis une phrase : {len(que_cartes)} sont atteintes "
          f"par des cartes ou des listes, {len(que_menu)} par le menu ou le pied de page seulement, "
          f"{len(aucune)} par aucun lien du tout (Google ne les trouve que par le sitemap).")
        w("")
        table_pages(orphelines)
    else:
        w("Aucune : chaque page reçoit au moins un lien dans le texte.")
        w("")
    w(f"## Sous le seuil : 1 à {min_e - 1} liens dans le texte")
    w("")
    if sous_seuil:
        table_pages(sous_seuil)
    else:
        w("Aucune.")
        w("")
    w("## Puits : beaucoup de liens reçus, aucun donné")
    w("")
    if puits:
        w(f"Ces pages reçoivent {min_e} liens dans le texte ou plus, mais n'en donnent aucun : "
          "le lecteur (et le robot) s'arrête là.")
        w("")
        w("| Page | Reçus dans le texte | Donnés dans le texte |")
        w("|---|---:|---:|")
        for u in puits[:LIGNES_TABLE]:
            w(f"| `{cellule(C(u), 70)}` | {noeuds[u]['e_texte']} | 0 |")
        w("")
    else:
        w("Aucune.")
        w("")
    w("## Hubs et liens sans retour")
    w("")
    if hubs:
        w(f"Les hubs : les pages (hors accueil) qui donnent le plus de liens dans leur contenu (texte et blocs, "
          f"{max(8, 2 * mediane_s)} pages liées ou plus ; la page médiane en lie {mediane_s}). Un satellite renvoie "
          "vers son hub dans une phrase : c'est ce qui dit à Google que le hub est la page principale du sujet.")
        w("")
        w("| Hub | Pages liées (contenu) | dont dans le texte | Sans lien retour |")
        w("|---|---:|---:|---:|")
        for h in hubs[:15]:
            w(f"| `{cellule(C(h), 60)}` | {len(contenu[h])} | {noeuds[h]['s_texte']} | "
              f"{sum(1 for x, _ in sans_retour if x == h)} |")
        w("")
        if sans_retour:
            w(f"{len(sans_retour)} pages liées par un hub ne le lient pas en retour dans leur contenu "
              f"(le fil d'Ariane et le menu ne comptent pas), dont {n_sous} rangées sous l'URL du hub, "
              "ses vrais satellites. Les premières :")
            w("")
            for h, s in sans_retour[:15]:
                w(f"- `{C(s)}` ne renvoie pas vers `{C(h)}`")
            if len(sans_retour) > 15:
                w(f"- … et {len(sans_retour) - 15} autres")
            w("")
    else:
        w(f"Pas de hub : aucune page (hors accueil) ne lie {max(8, 2 * mediane_s)} pages ou plus depuis son contenu.")
        w("")
    w("## Ancres")
    w("")
    if generiques:
        w(f"{len(generiques)} liens ont une ancre générique : elle ne dit rien de la page liée.")
        w("")
        w("| Page | Ancre | Vers |")
        w("|---|---|---|")
        for a in sorted(generiques, key=lambda a: (a["source"], a["ancre"]))[:LIGNES_TABLE]:
            w(f"| `{cellule(C(a['source']), 50)}` | « {cellule(a['ancre'], 30)} » | `{cellule(C(a['cible_demandee']), 50)}` |")
        w("")
    else:
        w("Aucune ancre générique (« ici », « cliquez », « lire la suite »).")
        w("")
    if ambigues:
        w(f"{len(ambigues)} ancres identiques mènent à des pages différentes : Google ne sait plus laquelle "
          "des deux est « la » page de ce sujet.")
        w("")
        w("| Ancre | Pages visées |")
        w("|---|---|")
        for k, v in ambigues[:LIGNES_TABLE]:
            w(f"| « {cellule(k, 40)} » | " + " · ".join(f"`{cellule(C(c), 45)}` ({len(s)} pages)"
                                                       for c, s in sorted(v.items())[:4]) + " |")
        w("")
    w("## Liens à corriger")
    w("")
    if a_corriger:
        w("| Lien vers | Problème | Pages qui le font | Où | Mène à |")
        w("|---|---|---:|---|---|")
        for k, v in sorted(a_corriger.items(), key=lambda kv: (not any(p.startswith("cassé") for p in kv[1]["problemes"]),
                                                                 -len(kv[1]["sources"]), kv[0]))[:LIGNES_TABLE]:
            ou = ", ".join(f"{g} {n}" for g, n in sorted(v["genres"].items()))
            w(f"| `{cellule(C(k), 60)}` | {', '.join(v['problemes'])} | {len(v['sources'])} | {ou} | "
              f"{('`' + cellule(C(v['finale']), 50) + '`') if v['finale'] else ''} |")
        if len(a_corriger) > LIGNES_TABLE:
            w(f"| … et {len(a_corriger) - LIGNES_TABLE} autres dans `graphe.csv` (colonne problemes) | | | | |")
        w("")
        w("Un lien redirigé ou à paramètres se corrige en visant l'URL finale, sans paramètre : un saut de moins "
          "pour le robot, et le vote va droit à la bonne page.")
        w("")
    else:
        w("Aucun lien interne cassé, redirigé, à paramètres ou vers une page noindex.")
        w("")
    if non_verifies:
        w(f"{len(non_verifies)} URL internes liées n'ont pas été vérifiées (au-delà du plafond `--max`).")
        w("")
    w("## Profondeur depuis l'accueil")
    w("")
    if accueil in noeuds:
        cpt = Counter(noeuds[u]["prof"] for u in suivies)
        cpt_c = Counter(noeuds[u]["prof_contenu"] for u in suivies)
        w("Le nombre de clics pour atteindre chaque page depuis l'accueil, avec tous les liens, puis sans le menu ni "
          "le pied de page (seulement les liens du contenu).")
        w("")
        w("| Clics | Tous les liens | Sans le menu |")
        w("|---|---:|---:|")
        for k in (1, 2, 3):
            w(f"| {k} | {cpt.get(k, 0)} | {cpt_c.get(k, 0)} |")
        w(f"| 4 ou plus | {sum(v for k, v in cpt.items() if k is not None and k >= 4)} | "
          f"{sum(v for k, v in cpt_c.items() if k is not None and k >= 4)} |")
        w(f"| jamais atteinte | {cpt.get(None, 0)} | {cpt_c.get(None, 0)} |")
        w("")
        loin = [u for u in suivies if noeuds[u]["prof"] is None or noeuds[u]["prof"] > 3]
        if loin:
            w("Au-delà de 3 clics même avec le menu : " + ", ".join(f"`{C(u)}`" for u in loin[:15])
              + (f" et {len(loin) - 15} autres" if len(loin) > 15 else "") + ".")
            w("")
    else:
        w("L'accueil n'a pas pu être lu : profondeur non calculée.")
        w("")
    w("## Les propositions")
    w("")
    if props:
        w(f"Pour chaque page sous le seuil (orphelines d'abord), les pages qui parlent déjà de son sujet sans la lier : "
          f"la première mention d'un mot ou d'une expression de son titre, dans une phrase, hors lien et hors titre. "
          f"{MAX_PAR_CIBLE} au plus par page, les mieux placées d'abord. Le score monte quand la mention est dans une "
          "section qui porte sur le sujet, tôt dans la page, avec une expression plutôt qu'un mot seul"
          + (", et sur une page qui a des impressions." if impr else "."))
        w("")
        w("<!-- CLAUDE: relis chaque proposition. Garde celles où le lien aide le lecteur à cet endroit de la phrase, "
          "écarte les faux amis (le mot est là mais ne parle pas du sujet de la page), ajuste l'ancre si elle sonne mal. "
          "Note ton choix dans la colonne statut de propositions.csv (à poser, écarté). -->")
        w("")
        for cible in cibles_avec[:CIBLES_RAPPORT]:
            n = noeuds[cible]
            ps = [p for p in props if p["cible"] == cible]
            w(f"### → `{C(cible)}` · {n['e_texte']} lien(s) dans le texte"
              + (f" · {nombre(n['impr'])} impressions" if n["impr"] is not None else "")
              + (f" · {n['couverture']}" if n["couverture"] else ""))
            w("")
            w(f"Titre : « {cellule(n['page']['h1'] or n['page']['titre'], 120)} »")
            w("")
            for p in ps:
                w(f"- Dans `{C(p['source'])}`, phrase « {cellule(p['phrase'])} », ancre « **{cellule(p['ancre'])}** » "
                  f"→ `{C(cible)}` (score {p['score']} : {p['raison']})" + (f" · statut : {p['statut']}" if p["statut"] else ""))
            w("")
        if len(cibles_avec) > CIBLES_RAPPORT:
            w(f"… et {len(cibles_avec) - CIBLES_RAPPORT} autres pages cibles dans `propositions.csv`.")
            w("")
        sans_prop = [u for u in cibles if u not in set(cibles_avec)]
        if sans_prop:
            w(f"{len(sans_prop)} pages sous le seuil n'ont trouvé aucune mention ailleurs sur le site : "
              + ", ".join(f"`{C(u)}`" for u in sans_prop[:12]) + (" …" if len(sans_prop) > 12 else "")
              + ". Pour elles, il faut écrire la phrase qui amène le lien, ou se demander si la page a sa place.")
            w("")
            w("<!-- CLAUDE: pour ces pages, propose où une phrase nouvelle aurait du sens (quelle page, quelle section), "
              "ou dis franchement qu'elle est hors sujet sur ce site. -->")
            w("")
    else:
        w("Aucune proposition : " + ("toutes les pages ont au moins le seuil de liens dans le texte."
                                     if not cibles else "aucune page ne mentionne les pages sous le seuil."))
        w("")
    if poses:
        w(f"Déjà posés ou écartés lors d'un passage précédent : {len(poses)} (dans `propositions.csv`).")
        w("")
    w("## Ce qu'on fait maintenant")
    w("")
    w("<!-- CLAUDE: les trois actions dans l'ordre (poser les liens retenus, corriger les liens cassés ou redirigés, "
      "renvoyer les hubs vers leurs satellites et retour), chacune avec son chiffre ; puis le rappel : relancer le "
      "script après la mise en ligne, une ligne de journal par page qui a reçu des liens (--noter). -->")
    w("")
    w("---")
    w(f"Fichiers : `propositions.csv` (une ligne par lien à poser, colonne statut), `pages.csv` (une ligne par page), "
      f"`graphe.csv` (un lien par ligne, avec son type et ses problèmes).")
    texte = "\n".join(L) + "\n"
    md = os.path.join(out_dir, "MAILLAGE.md")
    if os.path.exists(md):
        ancien = open(md, encoding="utf-8").read()
        if "<!-- CLAUDE:" not in ancien:  # Claude y avait écrit : on garde l'ancienne version à côté
            os.replace(md, os.path.join(out_dir, f"MAILLAGE-{dt.datetime.now().strftime('%Y-%m-%d-%H%M')}.md"))
    with open(md, "w", encoding="utf-8") as f:
        f.write(texte)

    # ---------- résumé imprimé
    dire("")
    dire(f"PAGES       {n_pages} lues, {len(suivies)} à mailler · {n_texte} liens dans le texte "
         f"(médiane reçue par page : {mediane_e})")
    dire(f"ORPHELINES  {len(orphelines)} sans lien dans le texte (cartes seules : {len(que_cartes)}, menu seul : "
         f"{len(que_menu)}, aucun lien : {len(aucune)}) · sous le seuil de {min_e} : {len(sous_seuil)}")
    dire(f"À CORRIGER  {len(casses)} cassés · {len(a_corriger) - len(casses)} redirigés, à paramètres ou noindex · "
         f"{len(generiques)} ancres génériques · {len(ambigues)} ancres ambiguës")
    dire(f"STRUCTURE   {len(hubs)} hubs, {len(sans_retour)} liens sans retour · {len(puits)} puits")
    dire(f"PROPOSÉS    {len(props)} liens pour {len(cibles_avec)} pages · {len(poses)} déjà posés ou écartés")
    dire(f"RAPPORT     {md}")
    return md


# --------------------------------------------------------------------------- journal

def est_indexee(couverture):
    c = couverture.lower().replace("non indexée", "").replace("not indexed", "")
    return "indexée" in c or "indexed" in c


def noter(site_dir, urls, en_ligne, base):
    path = os.path.join(site_dir, "journal.csv")
    os.makedirs(site_dir, exist_ok=True)
    lignes = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            lignes = list(csv.DictReader(f))
    _, index, _ = gsc(site_dir)
    props = []
    pp = os.path.join(site_dir, "internal-links", "propositions.csv")
    if os.path.exists(pp):
        props = lire_csv(pp)
    nouvelles = []
    for u in urls:
        u = normaliser(u if "//" in u else f"https://{base}/{u.lstrip('/')}")
        sources = sorted({court(p["source"], base) for p in props if p.get("cible") == u
                          and p.get("statut", "").startswith(("posé", "à poser", "a poser"))})
        couv = avec_ou_sans_slash(index, u) or ""
        non_indexee = bool(couv) and not est_indexee(couv)
        ajust = f"Liens internes vers {court(u, base)}" + (f" depuis {', '.join(sources[:6])}" if sources else "")
        if any(l.get("url") == u and l.get("en_ligne") == en_ligne and l.get("ajustement", "").startswith("Liens internes")
               for l in lignes):
            dire(f"  déjà noté : {u} le {en_ligne}")
            continue
        recents = [l for l in lignes if l.get("url") == u and l.get("en_ligne", "")[:10] >= (
            dt.date.fromisoformat(en_ligne[:10]) - dt.timedelta(days=28)).isoformat()]
        if recents:
            dire(f"  ! {u} a déjà un changement noté il y a moins de 28 jours : les deux effets ne se sépareront pas.")
        attendu = ("Sort de « explorée, non indexée »" if non_indexee and "explor" in couv.lower()
                   else "Indexée" if non_indexee else "Plus d'impressions sur la page")
        nouvelles.append({"en_ligne": en_ligne, "ajustement": ajust, "url": u,
                          "attendu_index": "indexée" if non_indexee else "", "requete": "", "attendu": attendu,
                          "relire_le": "", "statut": "", "constat": "", "constat_le": ""})
    if not nouvelles:
        return
    entete = JOURNAL_COLS
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            entete = next(csv.reader(f), None) or JOURNAL_COLS
    neuf = not os.path.exists(path) or os.path.getsize(path) == 0
    if not neuf:
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            manque_fin = f.read(1) not in (b"\n", b"\r")
        if manque_fin:
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n")
    with open(path, "a", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=entete, extrasaction="ignore")
        if neuf:
            wr.writeheader()
        for n in nouvelles:
            wr.writerow(n)
            dire(f"  noté : {n['ajustement']} (en ligne le {en_ligne}, relecture dans 21 jours)")
    dire(f"JOURNAL     {path}")


# --------------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", help="monsite.com ou https://monsite.com/")
    ap.add_argument("--dossier", help="dossier racine des données (défaut ./seo)")
    ap.add_argument("--max", type=int, default=300, help="pages lues au plus (défaut 300)")
    ap.add_argument("--min-entrants", type=int, default=3, help="liens dans le texte attendus par page (défaut 3)")
    ap.add_argument("--noter", nargs="+", metavar="URL", help="note dans journal.csv les pages qui viennent de recevoir des liens")
    ap.add_argument("--en-ligne", help="date de mise en ligne pour --noter (défaut aujourd'hui)")
    a = ap.parse_args(argv)

    saisie = a.site.strip()
    p = urllib.parse.urlsplit(saisie if "//" in saisie else "https://" + saisie)
    host = (p.hostname or "").lower()
    if not host or "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host):
        raise Panne(f"« {a.site} » n'est pas un nom de site. Exemple : monsite.com")
    racine = os.path.abspath(os.path.expanduser(a.dossier or "seo"))
    site_dir = dossier_site(racine, host)

    if a.noter:
        en_ligne = a.en_ligne or dt.date.today().isoformat()
        try:
            dt.date.fromisoformat(en_ligne[:10])
        except ValueError:
            raise Panne(f"--en-ligne {en_ligne} : la date s'écrit 2026-11-03.")
        noter(site_dir, a.noter, en_ligne, host.removeprefix("www."))
        return

    if a.max < 1 or a.min_entrants < 1:
        raise Panne("--max et --min-entrants sont des nombres positifs.")
    t0 = time.time()
    depart = f"{p.scheme or 'https'}://{host}/"
    dire(f"Site {host} -> {site_dir}")
    r = lire_url(depart)
    if r["code"] == 0:
        raise Panne(f"{depart} ne répond pas ({r['erreur']}). Vérifie l'adresse et ta connexion.")
    base_url = normaliser(r["finale"]) if r["code"] < 400 else depart
    robots = charger_robots(base_url)
    if not autorise(base_url):
        raise Panne(f"robots.txt de {host} interdit la lecture de l'accueil aux robots : le script s'arrête là.")
    sitemap, lus = trouver_sitemap(base_url, robots)
    base = hote_nu(base_url)
    sitemap_int = [normaliser(u) for u in sitemap if hote_nu(u) == base]
    if sitemap:
        dire(f"  sitemap : {len(sitemap_int)} URL ({', '.join(lus)})")
    else:
        dire("  pas de sitemap trouvé : exploration depuis l'accueil")
    audit = seo_audit(site_dir)
    if audit:
        dire(f"  crawl seo-audit de moins de {FRAIS_JOURS} jours réutilisé pour {len(audit)} statuts")
    graines = [base_url] + sitemap_int
    res, reste = explorer(base_url, graines, a.max, set())
    impr, index, info = gsc(site_dir)
    if not impr:
        dire("  Search Console non branchée : le score des propositions ne tient pas compte des impressions. "
             "Installe la skill `search-console` et lance-la une fois sur ce site pour l'ajouter.")
    generer(host, base_url, site_dir, res, set(sitemap_int), lus, impr, index, info, audit, a.min_entrants, a.max,
            reste, time.time() - t0)
    dire(f"Terminé en {time.time() - t0:.0f} s.")


if __name__ == "__main__":
    try:
        main()
    except Panne as e:
        sys.exit("ERREUR : " + str(e))
    except KeyboardInterrupt:
        sys.exit("Interrompu.")
