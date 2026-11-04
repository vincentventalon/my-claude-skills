#!/usr/bin/env python3
"""Ta page contre celles qui tiennent la première page de Google sur une requête, mesurées côte à côte.

Usage :
  python3 pages.py --requete "cout de la vie a lisbonne" --mienne https://monsite.com/cout-de-la-vie \\
      https://concurrent1.com/page https://concurrent2.com/article ...
  python3 pages.py --requete "..." --site monsite.com URL...     (tu n'as pas encore de page sur le sujet)

Passe les URL concurrentes dans l'ordre de la page de résultats : la première est la position 1.
Une page refuse le script ? Ouvre-la dans ton navigateur, enregistre-la (Ctrl+S, « page web, HTML
uniquement »), puis ajoute --html URL=fichier.html (répétable).

Mesure chaque page (bibliothèque standard, html.parser) : title et sa longueur, description, H1,
H2 et H3, mots du texte principal (sans menu, en-tête, pied de page ni barre latérale), images,
tableaux, listes, vidéos, FAQ (schema FAQPage ou titres en question), types JSON-LD, dates
déclarées, liens internes et externes du texte, auteur, mots de la requête dans le title, le H1 et
les 100 premiers mots, temps de réponse, taille du HTML, langue. Puis ce que les concurrents ont
et que ta page n'a pas. Si la skill `read-my-search-console` est installée à côté et branchée : la position
de tes pages sur cette requête.

Écrit ./seo/<site>/competitors/<requete>.md (le rapport, marqueurs <!-- CLAUDE: --> à remplir),
<requete>.json (toutes les mesures), et tient serp.csv (les URL notées, requête par requête).
Les pages lues restent en cache le jour même (competitors/.cache/) : relancer le même jour ne
retélécharge rien et redonne le même rapport ; --rafraichir pour relire.
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import statistics
import sys
import urllib.parse
from html.parser import HTMLParser

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(errors="replace")

ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
import commun as c  # noqa: E402

sys.path.insert(0, os.path.join(ici, "..", "..", "read-my-search-console", "scripts"))
try:
    import gsc_api as g  # noqa: E402
except ImportError:
    g = None  # la skill marche sans, en disant ce qu'elle n'a pas pu faire

MAX_URLS = 15

# --- un arbre HTML minimal -------------------------------------------------------

VIDES_HTML = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
              "track", "wbr"}
BLOCS = {"address", "article", "aside", "blockquote", "br", "caption", "dd", "details", "div", "dl", "dt",
         "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr",
         "li", "main", "nav", "ol", "p", "pre", "section", "summary", "table", "tbody", "td", "th", "thead", "tr",
         "ul"}
FERME_P = BLOCS - {"br", "li", "dd", "dt", "td", "th", "tr", "tbody", "thead", "caption", "summary", "figcaption"}
SANS_TEXTE = {"script", "style", "noscript", "template", "svg", "button", "select", "textarea", "option", "iframe",
              "video", "audio", "canvas", "object", "head", "title"}
TOUJOURS_EXCLUS = {"script", "style", "noscript", "template", "svg", "head", "nav", "aside", "footer", "dialog"}
ROLES_EXCLUS = {"navigation", "banner", "contentinfo", "complementary", "search", "dialog", "menu", "menubar"}
CLASSES_CONTIENT = ("cookie", "consent", "gdpr", "sidebar", "breadcrumb", "related", "share", "sharing",
                    "comment", "newsletter", "subscribe", "advert", "popup", "modal", "author-box", "authorbox")
CLASSES_PREFIXES = ("widget", "toc", "ez-toc", "table-of-contents", "navbar", "menu", "site-header", "site-footer",
                    "footer", "social", "post-navigation", "nav-")
CLASSE_SIMPLE = re.compile(r"[a-z][a-z0-9_-]*")
IDS_EXCLUS = {"header", "masthead", "nav", "navigation", "secondary", "colophon", "sidebar", "comments", "respond",
              "toc", "breadcrumb", "breadcrumbs", "related", "share", "cookie-notice", "footer"}
CONTENEURS_CLASSES = {"div", "section", "ul", "ol", "span", "form", "aside"}
TYPES_DECOR = {"ListItem", "EntryPoint", "SearchAction", "ReadAction", "PropertyValueSpecification", "ImageObject",
               "Question", "Answer", "WebPageElement", "SiteNavigationElement", "PostalAddress", "ContactPoint",
               "GeoCoordinates", "Language", "WPHeader", "WPFooter", "WPSideBar", "Thing"}
TYPES_ARTICLE = {"Article", "BlogPosting", "NewsArticle", "TechArticle", "Report", "HowTo", "Recipe", "WebPage",
                 "FAQPage", "Guide", "ScholarlyArticle", "AnalysisNewsArticle", "LiveBlogPosting", "MedicalWebPage"}
TITRE_DECOR = re.compile(
    r"^((related|more|recent|popular|latest|similar|other) (articles?|posts?|blogs?|stories|reads|guides?)|"
    r"you (may|might) also|quick links|useful links|get in touch|contact us|share( this)?|follow us|subscribe|"
    r"newsletter|leave a (comment|reply)|comments?|.*pin it!?|back to .*|table of contents|in this article|"
    r"sommaire|au sommaire|articles? (similaires|li[ée]s|r[ée]cents)|[àa] lire aussi|lire aussi|partager.*|"
    r"commentaires?|laisser un commentaire|abonne[sz]?-(toi|vous).*|inscri(s|vez)-(toi|vous).*|"
    r"sur le m[êe]me (sujet|th[èe]me)|nos (derniers )?articles|about the author|[àa] propos de l'auteur)[.!:?]*$",
    re.I)
FAQ_TITRE = re.compile(r"\bfaqs?\b|questions? (fr[ée]quentes|courantes)|frequently asked|vos questions|"
                       r"common questions|people also ask", re.I)


class Noeud:
    __slots__ = ("tag", "attrs", "enfants", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.enfants, self.parent = tag, attrs, [], parent


class Arbre(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.doc = Noeud("#doc", {}, None)
        self.pile = [self.doc]

    def _ajoute(self, tag, attrs):
        haut = self.pile[-1]
        if len(self.pile) > 1 and ((haut.tag == "p" and tag in FERME_P) or
                                   (tag == haut.tag and tag in ("li", "dt", "dd", "tr", "td", "th", "option", "p"))):
            self.pile.pop()
        n = Noeud(tag, {k.lower(): (v or "") for k, v in attrs}, self.pile[-1])
        self.pile[-1].enfants.append(n)
        return n

    def handle_starttag(self, tag, attrs):
        n = self._ajoute(tag, attrs)
        if tag not in VIDES_HTML:
            self.pile.append(n)

    def handle_startendtag(self, tag, attrs):
        self._ajoute(tag, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self.pile) - 1, 0, -1):
            if self.pile[i].tag == tag:
                del self.pile[i:]
                return

    def handle_data(self, data):
        self.pile[-1].enfants.append(data)


def noeuds(racine, sauter=None):
    """Tous les éléments sous racine, dans l'ordre du document, sans descendre dans ceux que sauter refuse."""
    pile = [racine]
    while pile:
        n = pile.pop()
        if isinstance(n, str):
            continue
        if n is not racine and sauter and sauter(n):
            continue
        yield n
        pile.extend(reversed(n.enfants))


def texte(racine, sauter=None):
    morceaux, pile = [], [racine]
    while pile:
        n = pile.pop()
        if n is None:
            morceaux.append(" ")
            continue
        if isinstance(n, str):
            morceaux.append(n)
            continue
        if n is not racine and ((sauter and sauter(n)) or n.tag in SANS_TEXTE):
            continue
        if n.tag in BLOCS:
            morceaux.append(" ")
            pile.append(None)
        pile.extend(reversed(n.enfants))
    return re.sub(r"\s+", " ", "".join(morceaux)).strip()


def dans(n, tag):
    p = n.parent
    while p is not None:
        if p.tag == tag:
            return True
        p = p.parent
    return False


def exclusion(contexte, proteges=frozenset()):
    """Ce qui n'est pas le texte de la page : menus, en-tête, pied, barre latérale, bandeau cookies, partage.
    Un élément qui contient le H1 (proteges) n'est jamais écarté sur sa seule classe."""
    def exclu(n):
        t = n.tag
        if t in TOUJOURS_EXCLUS or (t == "header" and contexte == "body"):
            return True
        a = n.attrs
        if a.get("role", "").lower() in ROLES_EXCLUS or "hidden" in a or a.get("aria-hidden") == "true":
            return True
        if re.search(r"display\s*:\s*none", a.get("style", ""), re.I):
            return True
        if t in CONTENEURS_CLASSES and id(n) not in proteges:
            if a.get("id", "").lower() in IDS_EXCLUS:
                return True
            for k in a.get("class", "").lower().split():
                if not CLASSE_SIMPLE.fullmatch(k):  # classes utilitaires (Tailwind…) : rien à en tirer
                    continue
                if k.startswith(CLASSES_PREFIXES) or any(x in k for x in CLASSES_CONTIENT):
                    return True
        return False
    return exclu


def nb_mots(t):
    return len(re.findall(r"[^\W_]+", t))


def court(s, n=110):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


# --- la mesure d'une page ----------------------------------------------------------

def jsonld(doc):
    objets, illisibles = [], 0
    for n in noeuds(doc):
        if n.tag != "script" or "ld+json" not in n.attrs.get("type", "").lower():
            continue
        brut = "".join(x for x in n.enfants if isinstance(x, str)).strip()
        brut = re.sub(r"^\s*<!--|-->\s*$", "", brut)
        for essai in (brut, re.sub(r",\s*([}\]])", r"\1", brut)):
            try:
                data = json.loads(essai, strict=False)
                break
            except ValueError:
                data = None
        if data is None:
            illisibles += 1
            continue
        pile = [data]
        while pile:
            o = pile.pop()
            if isinstance(o, list):
                pile.extend(reversed(o))
            elif isinstance(o, dict):
                objets.append(o)
                pile.extend(reversed([v for v in o.values() if isinstance(v, (dict, list))]))
    return objets, illisibles


def types_de(o):
    t = o.get("@type", [])
    return {x.split("/")[-1] for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}


def nom_auteur(a, par_id):
    if isinstance(a, list):
        noms = [nom_auteur(x, par_id) for x in a]
        return ", ".join(x for x in noms if x)[:80]
    if isinstance(a, str):
        return a.strip()
    if isinstance(a, dict):
        if not a.get("name") and a.get("@id") in par_id:
            a = par_id[a["@id"]]
        n = a.get("name", "")
        return n.strip() if isinstance(n, str) else ""
    return ""


def mesurer(html, url, q_jetons):
    arbre = Arbre()
    try:
        arbre.feed(html)
        arbre.close()
    except Exception:  # un HTML très cassé : on garde ce qui a été lu
        pass
    doc = arbre.doc
    tout = list(noeuds(doc))
    m = {}
    racine_html = next((n for n in tout if n.tag == "html"), None)
    metas = {}
    for n in tout:
        if n.tag == "meta":
            k = (n.attrs.get("name") or n.attrs.get("property") or n.attrs.get("itemprop")
                 or n.attrs.get("http-equiv") or "").lower()
            if k and k not in metas:
                metas[k] = n.attrs.get("content", "").strip()
    m["langue"] = (racine_html.attrs.get("lang", "") if racine_html else "") or metas.get("og:locale", "") \
        or metas.get("content-language", "")
    t = next((n for n in tout if n.tag == "title" and not dans(n, "svg")), None)
    m["title"] = re.sub(r"\s+", " ", "".join(x for x in t.enfants if isinstance(x, str))).strip() if t else ""
    m["description"] = metas.get("description", "")
    morceaux_t = re.split(r"\s+[|\-–—:]{1,2}\s+", m["title"])
    m["marque"] = metas.get("og:site_name", "") + " " + (morceaux_t[-1] if len(morceaux_t) > 1
                                                          and len(morceaux_t[-1]) <= 40 else "")
    m["canonique"] = next((n.attrs.get("href", "") for n in tout if n.tag == "link"
                           and "canonical" in n.attrs.get("rel", "").lower().split()), "")
    m["noindex"] = "noindex" in metas.get("robots", "").lower()

    objets, m["jsonld_illisibles"] = jsonld(doc)
    par_id = {o["@id"]: o for o in objets if isinstance(o.get("@id"), str)}
    types = set()
    for o in objets:
        types |= types_de(o)
    for n in tout:
        if n.attrs.get("itemtype"):
            types |= {x.rstrip("/").split("/")[-1] for x in n.attrs["itemtype"].split()}
    m["types_jsonld"] = sorted(x for x in types - TYPES_DECOR if x)
    articles = [o for o in objets if types_de(o) & TYPES_ARTICLE] + objets

    def premier(cle_):
        for o in articles:
            v = o.get(cle_)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    faq = [o for o in objets if "FAQPage" in types_de(o)]
    faq_schema = 0
    for o in faq:
        e = o.get("mainEntity", [])
        faq_schema += len(e) if isinstance(e, list) else 1

    # le texte principal
    corps = next((n for n in tout if n.tag == "body"), doc)
    h1_noeud = next((n for n in tout if n.tag == "h1" and not dans(n, "svg") and dans(n, "body")), None)
    proteges = set()
    p_ = h1_noeud
    while p_ is not None:
        proteges.add(id(p_))
        p_ = p_.parent
    proteges = frozenset(proteges)
    ex_body = exclusion("body", proteges)
    total = nb_mots(texte(corps, ex_body))
    conteneur, ctx = corps, "body"
    mains = [n for n in noeuds(corps, ex_body) if n.tag == "main" or n.attrs.get("role", "").lower() == "main"]
    if mains:
        best = max(mains, key=lambda n: nb_mots(texte(n, exclusion("main", proteges))))
        if nb_mots(texte(best, exclusion("main", proteges))) >= 0.25 * total:
            conteneur, ctx = best, "main"
    if ctx == "body":
        arts = [n for n in noeuds(corps, ex_body) if n.tag == "article"]
        if arts:
            best = max(arts, key=lambda n: nb_mots(texte(n, exclusion("article", proteges))))
            if nb_mots(texte(best, exclusion("article", proteges))) >= 0.3 * total:
                conteneur, ctx = best, "article"
    ex = exclusion(ctx, proteges)
    etiquette = "<" + ctx + ">"
    # Affinage : le plus petit élément qui porte 85 % du texte en paragraphes (écarte les articles liés,
    # les formulaires et les encarts restés dans le conteneur).
    couvert, profondeur, par_id_n, total_p = {}, {}, {}, 0
    for n in noeuds(conteneur, ex):
        if n.tag == "p":
            k = nb_mots(texte(n, ex))
            if k >= 12:
                total_p += k
                a_, d_ = n.parent, 0
                chaine = []
                while a_ is not None and a_ is not conteneur.parent:
                    chaine.append(a_)
                    a_ = a_.parent
                for prof, a_ in enumerate(reversed(chaine)):
                    couvert[id(a_)] = couvert.get(id(a_), 0) + k
                    profondeur[id(a_)] = prof
                    par_id_n[id(a_)] = a_
    if total_p >= 150:
        assez = [i for i, k in couvert.items() if k >= 0.85 * total_p]
        if assez:
            fin_ = par_id_n[max(assez, key=lambda i: profondeur[i])]
            if fin_ is not conteneur and fin_.tag not in ("p", "li", "blockquote"):
                conteneur = fin_
                cls = fin_.attrs.get("class", "").split()
                etiquette += " > <" + fin_.tag + ("." + cls[0] if cls else "") + ">"
    m["compte_dans"] = etiquette
    corps_txt = texte(conteneur, ex)
    m["mots"] = nb_mots(corps_txt)
    debut = " ".join(re.findall(r"[^\W_]+", corps_txt)[:100])
    m["mots_page_entiere"] = nb_mots(texte(corps, None))
    elems = list(noeuds(conteneur, ex))

    m["h1"] = [court(texte(n), 160) for n in tout if n.tag == "h1" and not dans(n, "svg")]
    m["titres"], m["titres_decor"] = [], []
    for n in elems:
        if n.tag in ("h2", "h3", "h4") and texte(n).strip():
            tt = court(texte(n), 160)
            (m["titres_decor"] if TITRE_DECOR.match(tt.strip()) else m["titres"]).append([int(n.tag[1]), tt])
    m["h2"] = sum(1 for x in m["titres"] if x[0] == 2)
    m["h3"] = sum(1 for x in m["titres"] if x[0] == 3)
    m["images"] = sum(1 for n in elems if n.tag == "img")
    m["images_sans_alt"] = sum(1 for n in elems if n.tag == "img" and not n.attrs.get("alt", "").strip())
    m["tableaux"] = sum(1 for n in elems if n.tag == "table")
    m["listes"] = sum(1 for n in elems if n.tag in ("ul", "ol"))
    m["videos"] = sum(1 for n in elems if n.tag == "video" or (n.tag == "iframe" and re.search(
        r"youtube|youtu\.be|vimeo|dailymotion|wistia|loom", n.attrs.get("src", "") + n.attrs.get("data-src", ""))))

    questions = [texte(n) for n in elems if n.tag in ("h2", "h3", "h4", "h5", "summary", "dt")
                 and texte(n).strip().endswith("?")]
    bloc_faq = any(FAQ_TITRE.search(x[1]) for x in m["titres"])
    if faq_schema:
        m["faq"] = f"oui (schema FAQPage, {faq_schema} q.)"
    elif bloc_faq:
        m["faq"] = f"oui (section FAQ, {len(questions)} q.)"
    elif len(questions) >= 3:
        m["faq"] = f"oui ({len(questions)} titres en question)"
    else:
        m["faq"] = "non" if not questions else f"non ({len(questions)} titre(s) en question)"
    m["faq_oui"] = m["faq"].startswith("oui")
    m["questions"] = [court(q, 140) for q in questions[:30]]

    # les liens du texte
    internes, externes, domaines = set(), set(), {}
    for n in elems:
        if n.tag != "a":
            continue
        h = n.attrs.get("href", "").strip()
        if not h or h.startswith(("#", "javascript:", "mailto:", "tel:", "sms:", "data:")):
            continue
        cible = urllib.parse.urldefrag(urllib.parse.urljoin(url, h))[0]
        pu = urllib.parse.urlparse(cible)
        hc = pu.hostname or ""
        if pu.scheme not in ("http", "https") or not hc:
            continue
        if c.meme_site(hc, url):
            internes.add(cible.rstrip("/"))
        else:
            externes.add(cible)
            d = c.hote(hc)
            domaines[d] = domaines.get(d, 0) + 1
    m["liens_internes"], m["liens_externes"] = len(internes), len(externes)
    m["domaines_cites"] = sorted(domaines, key=lambda d: (-domaines[d], d))[:10]

    # les dates
    def meta_date(*cles):
        for k in cles:
            if metas.get(k):
                return metas[k]
        return ""

    def itemprop(nom):
        for n in tout:
            if n.attrs.get("itemprop") == nom:
                return n.attrs.get("datetime") or n.attrs.get("content") or texte(n)
        return ""

    pub = [(premier("datePublished"), "schema"), (meta_date("article:published_time", "og:published_time",
           "date", "publish-date", "pubdate", "dc.date.issued", "dc.date"), "meta"), (itemprop("datePublished"),
           "microdata")]
    mod = [(premier("dateModified"), "schema"), (meta_date("article:modified_time", "og:updated_time",
           "last-modified", "dc.date.modified"), "meta"), (itemprop("dateModified"), "microdata")]
    temps = next((n.attrs.get("datetime", "") for n in elems if n.tag == "time" and n.attrs.get("datetime")), "")
    pub.append((temps, "<time>"))
    m["publiee"], m["publiee_source"] = next(((c.date_iso(v), s) for v, s in pub if c.date_iso(v)), ("", ""))
    m["modifiee"], m["modifiee_source"] = next(((c.date_iso(v), s) for v, s in mod if c.date_iso(v)), ("", ""))

    # l'auteur
    auteur, source = "", ""
    for o in articles:
        if o.get("author"):
            auteur, source = nom_auteur(o["author"], par_id), "schema"
            if auteur:
                break
    if not auteur and metas.get("author"):
        auteur, source = metas["author"], "meta"
    if not auteur:
        for n in tout:
            rel = n.attrs.get("rel", "").lower().split()
            cls = n.attrs.get("class", "").lower().split()
            if (n.tag == "a" and "author" in rel) or n.attrs.get("itemprop") == "author" or \
                    any(k.startswith(("author", "byline", "post-author", "entry-author")) for k in cls):
                v = court(texte(n), 80)
                if 2 < len(v) <= 70:
                    auteur, source = v, "page"
                    break
    m["auteur"], m["auteur_source"] = court(auteur, 70), source

    # la requête
    def part(s):
        if not q_jetons:
            return None
        js = set(c.jetons(s))
        return sum(1 for q in q_jetons if q in js)
    m["req_title"], m["req_h1"], m["req_debut"] = part(m["title"]), part(" ".join(m["h1"])), part(debut)
    m["jetons_titres"] = sorted({j for x in m["titres"] for j in c.jetons(x[1])})
    m["formes"] = {}
    for x in m["titres"]:
        for r, f in c.formes(x[1]):
            m["formes"].setdefault(r, f)
    m["jetons_texte"] = {}
    for j in c.jetons(corps_txt):
        m["jetons_texte"][j] = m["jetons_texte"].get(j, 0) + 1
    return m


# --- lecture des pages -------------------------------------------------------------

def lire(url, cache_dir, jour, rafraichir, fichier=None):
    if fichier:
        try:
            with open(os.path.expanduser(fichier), "rb") as f:
                brut = f.read()
        except OSError as e:
            return {"url": url, "ok": False, "erreur": f"fichier illisible ({e.strerror})", "source": "fichier"}
        return {"url": url, "ok": True, "statut": 200, "url_finale": url, "octets": len(brut), "ms": None,
                "texte": c.decoder(brut), "source": "fichier"}
    chemin = os.path.join(cache_dir, c.cle(url) + ".json")
    if not rafraichir:
        d = c.lire_cache(chemin, jour)
        if d:
            return d
    d = c.telecharger(url)
    d["jour"], d["source"] = jour, "web"
    if d["ok"] and not re.search(r"html|xml|^$", d.get("type", ""), re.I):
        d["ok"], d["erreur"] = False, "pas une page HTML (" + d["type"].split(";")[0] + ")"
    c.ecrire_cache(chemin, d)
    return d


def search_console(dossier, site, requete):
    """Tes pages sur cette requête dans Search Console, 28 jours. Ne plante jamais."""
    if g is None:
        return {"etat": "absente", "message": "Search Console non lue : installe la skill `read-my-search-console` à côté "
                "de celle-ci et suis son guide pour avoir la position de tes pages sur cette requête."}
    mots = [x for x in re.findall(r"[^\W_]+", requete.lower()) if c.sans_accents(x) not in c.VIDES][:6]
    if not mots:
        return {"etat": "absente", "message": "Pas de mot à chercher dans Search Console."}
    fin = dt.date.today() - dt.timedelta(days=3)
    debut = fin - dt.timedelta(days=27)
    try:
        g.racine(dossier)
        prop = g.resoudre_site(site)
        rows, _ = g.recherche(prop, debut.isoformat(), fin.isoformat(), ["query", "page"], data_state="final",
                              filtres=[{"dimension": "query", "operator": "contains", "expression": x} for x in mots])
    except g.Panne as e:
        return {"etat": "panne", "message": "Search Console non branchée (" + str(e).splitlines()[0][:160]
                + ") : installe la skill `read-my-search-console` et suis son guide."}
    except Exception as e:  # noqa: BLE001 - une panne de la skill voisine ne bloque pas le rapport
        return {"etat": "panne", "message": f"Search Console illisible ({type(e).__name__}) : rapport sans elle."}
    pages, requetes = {}, {}
    for r in rows:
        q, p = r["keys"]
        p = p.split("#")[0]
        for d, k in ((pages, p), (requetes, q)):
            e = d.setdefault(k, [0, 0, 0.0])
            e[0] += int(r["clicks"])
            e[1] += int(r["impressions"])
            e[2] += r["position"] * r["impressions"]
    fmt = lambda d: [[k, v[0], v[1], round(v[2] / v[1], 1) if v[1] else None]  # noqa: E731
                     for k, v in sorted(d.items(), key=lambda kv: (-kv[1][1], kv[0]))]
    return {"etat": "ok", "propriete": prop, "debut": debut.isoformat(), "fin": fin.isoformat(), "mots": mots,
            "pages": fmt(pages), "requetes": fmt(requetes)}


# --- le rapport --------------------------------------------------------------------

def nombre(x):
    return "—" if x is None else f"{x:,}".replace(",", " ")


def ctr(cl, im):
    return "—" if im < 10 else f"{100 * cl / im:.2f} %".replace(".", ",")


def virgule(x):
    return "—" if x is None else f"{x:.1f}".replace(".", ",")


def med(vals):
    v = [x for x in vals if isinstance(x, (int, float))]
    return statistics.median(v) if v else None


def cellule(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def ecarts(moi, autres, q_jetons, ignores):
    """Les sujets que les concurrents titrent et que tes titres n'ont pas, et les sections entières absentes."""
    mes = set(moi["jetons_titres"]) | {j for h in moi["h1"] for j in c.jetons(h)} if moi else set()
    ign = set(q_jetons) | ignores
    par_mot = {}
    sections = []
    for i, a in autres:
        vus = set()
        absentes = []
        for niv, titre in a["titres"]:
            if niv > 3:
                continue
            js = [j for j in c.jetons(titre) if j not in ign]
            for j in js:
                if j not in mes and j not in vus:
                    vus.add(j)
                    par_mot.setdefault(j, []).append((i, titre))
            if js and not any(j in mes for j in js):
                absentes.append((titre, js))
        sections.append((i, absentes))
    mots = sorted(par_mot.items(), key=lambda kv: (-len(kv[1]), (moi or {}).get("jetons_texte", {}).get(kv[0], 0),
                                                   kv[0]))
    return mots, sections


def rapport(requete, site, lignes, moi_idx, sc, jour):
    ok = [(i, l) for i, l in enumerate(lignes) if l["m"]]
    moi = lignes[moi_idx]["m"] if moi_idx is not None and lignes[moi_idx]["m"] else None
    autres = [(i, l["m"]) for i, l in ok if i != moi_idx]
    n = len(autres)
    q_jetons = sorted(set(c.jetons(requete))) if requete else []
    ignores = {j for l in lignes for j in c.jetons(c.hote(l["url"]).split(".")[0])}
    ignores |= {j for i, l in ok if i != moi_idx for j in c.jetons(l["m"]["marque"])}
    L = []
    w = L.append
    titre = f"« {requete} »" if requete else "la page"
    w(f"# Concurrents sur {titre}")
    w("")
    w(f"Mesuré le {jour} par `pages.py` pour {site}. Pages concurrentes dans l'ordre donné (#1 = la première "
      f"passée, la position notée dans la recherche). {n} concurrente(s) lue(s) sur "
      f"{len(lignes) - (1 if moi_idx is not None else 0)}.")
    w("")
    w("<!-- CLAUDE: d'où viennent ces URL (outil de recherche, date, pays) et le verdict en deux phrases : ce que "
      "Google accepte sur cette requête et ce qui manque à ta page, chaque fait avec son chiffre du tableau. -->")
    w("")
    w("## Les pages")
    w("")
    noms = []
    for i, l in enumerate(lignes):
        etiq = "toi" if i == moi_idx else f"#{l['pos']}"
        noms.append(f"{etiq} {c.hote(l['url'])}")
        etat = "" if l["m"] else f" : **non lue, {l['erreur']}**"
        w(f"- **{etiq}** {l['url']}{etat}")
    w("")
    if not autres:
        w("Aucune page concurrente lue : rien à comparer. Voir « Pages non lues » plus bas.")
    cols = ([moi_idx] if moi_idx is not None else []) + [i for i, _ in autres]
    entete = ["", "ta page"] if moi_idx is not None else [""]
    entete += ["médiane concurrents"] + [noms[i] for i, _ in autres]
    w("| " + " | ".join(cellule(x) for x in entete) + " |")
    w("|" + "---|" * len(entete))

    def ligne(lib, f, mediane="num"):
        vals = {i: f(lignes[i]["m"]) if lignes[i]["m"] else "—" for i in cols}
        cells = [lib]
        if moi_idx is not None:
            cells.append(vals[moi_idx])
        if mediane == "num":
            mm = med([vals[i] for i, _ in autres])
            cells.append(nombre(round(mm)) if mm is not None else "—")
        elif mediane == "oui":
            cells.append(f"{sum(1 for i, _ in autres if str(vals[i]).startswith('oui'))}/{n} oui")
        elif mediane == "date":
            ds = sorted(vals[i] for i, _ in autres if vals[i] and vals[i] != "—")
            cells.append(ds[len(ds) // 2] if ds else "—")
        else:
            cells.append("")
        cells += [vals[i] for i, _ in autres]
        w("| " + " | ".join(cellule(nombre(x) if isinstance(x, int) else x if x != "" else "—") for x in cells) + " |")

    ligne("title (caractères)", lambda m: len(m["title"]))
    ligne("description (caractères)", lambda m: len(m["description"]))
    ligne("H1", lambda m: len(m["h1"]))
    ligne("H2", lambda m: m["h2"])
    ligne("H3", lambda m: m["h3"])
    ligne("mots du texte principal", lambda m: m["mots"])
    ligne("images", lambda m: m["images"])
    ligne("tableaux", lambda m: m["tableaux"])
    ligne("listes", lambda m: m["listes"])
    ligne("vidéos intégrées", lambda m: m["videos"])
    ligne("FAQ", lambda m: m["faq"], "oui")
    ligne("types JSON-LD", lambda m: ", ".join(m["types_jsonld"]) or "aucun", None)
    ligne("publiée le", lambda m: m["publiee"] or "non déclarée", "date")
    ligne("modifiée le", lambda m: m["modifiee"] or "non déclarée", "date")
    ligne("liens internes (texte)", lambda m: m["liens_internes"])
    ligne("liens externes (texte)", lambda m: m["liens_externes"])
    ligne("auteur", lambda m: f"oui : {m['auteur']}" if m["auteur"] else "non trouvé", "oui")
    if q_jetons:
        k = len(q_jetons)
        ligne(f"mots de la requête dans le title (/{k})", lambda m: m["req_title"])
        ligne(f"… dans le H1 (/{k})", lambda m: m["req_h1"])
        ligne(f"… dans les 100 premiers mots (/{k})", lambda m: m["req_debut"])
    ligne("temps de réponse (ms, une mesure)", lambda m: m["_ms"] if m["_ms"] is not None else "—")
    ligne("taille du HTML (Ko)", lambda m: round(m["_octets"] / 1024))
    ligne("langue déclarée", lambda m: m["langue"] or "non déclarée", None)
    ligne("mots comptés dans", lambda m: m["compte_dans"], None)
    w("")
    if q_jetons:
        w(f"Mots de la requête comptés : {', '.join(q_jetons)} (sans les mots vides, au singulier). ")
    w("Le temps de réponse est une seule mesure depuis ta connexion : un ordre de grandeur, pas un classement.")
    w("")
    w("<!-- CLAUDE: ce que Google accepte sur cette requête, lu dans le tableau : le format qui domine (guide, "
      "liste, outil, page commerciale), la longueur médiane, FAQ ou pas, tableaux ou pas, la fraîcheur. Des "
      "faits avec leur n (« 4/5 ont un tableau »), jamais « il faut plus de mots pour ranker ». -->")
    w("")
    w("## Titles et H1")
    w("")
    for i in cols:
        mm = lignes[i]["m"]
        etiq = "toi" if i == moi_idx else noms[i]
        w(f"- **{etiq}** : {cellule(mm['title']) or '(pas de title)'}  ")
        w(f"  H1 : {cellule(' / '.join(mm['h1'])) or '(pas de H1)'}  ")
        w(f"  description : {cellule(court(mm['description'], 160)) or '(aucune)'}")
    w("")

    if sc:
        w("## Search Console : tes pages sur cette requête")
        w("")
        if sc["etat"] != "ok":
            w(sc["message"])
        else:
            tot_i = sum(p[2] for p in sc["pages"])
            w(f"{sc['propriete']}, du {sc['debut']} au {sc['fin']} (28 jours, données finales), requêtes qui "
              f"contiennent : {', '.join(sc['mots'])}. {len(sc['requetes'])} requête(s), {nombre(tot_i)} "
              f"impressions, {nombre(sum(p[1] for p in sc['pages']))} clics.")
            w("")
            if not sc["pages"]:
                w("Aucune impression : Google ne montre encore aucune de tes pages sur ces mots. Ce n'est pas "
                  "« zéro demande » : Search Console ne voit que là où le site apparaît déjà.")
            else:
                w("| ta page | clics | impressions | CTR | position moyenne |")
                w("|---|---|---|---|---|")
                for p, cl, im, pos in sc["pages"][:8]:
                    w(f"| {cellule(p)} | {nombre(cl)} | {nombre(im)} | {ctr(cl, im)} | {virgule(pos) if im >= 10 else 'bruit (< 10 impr.)'} |")
                w("")
                w("| requête | clics | impressions | CTR | position moyenne |")
                w("|---|---|---|---|---|")
                for q, cl, im, pos in sc["requetes"][:8]:
                    w(f"| {cellule(q)} | {nombre(cl)} | {nombre(im)} | {ctr(cl, im)} | {virgule(pos) if im >= 10 else 'bruit (< 10 impr.)'} |")
                w("")
                pl = [p for p in sc["pages"] if p[2] >= 10]
                if len(pl) >= 2:
                    w(f"{len(pl)} de tes pages ont 10 impressions ou plus sur ces mots : un constat de "
                      "structure (une requête, plusieurs pages), à lire avec la skill `read-my-search-console` avant de "
                      "parler de cannibalisation.")
        w("")

    if autres:
        mots, sections = ecarts(moi, autres, q_jetons, ignores)
        w("## Ce qu'ils ont et que ta page n'a pas")
        w("")
        if moi is None:
            w("Tu n'as pas encore de page : tout ce qui suit est à couvrir. Les chiffres te donnent le format "
              "attendu, pas un plan à recopier.")
            w("")
        else:
            faits = []
            k_faq = sum(1 for _, a in autres if a["faq_oui"])
            if not moi["faq_oui"] and k_faq:
                faits.append(f"**FAQ** : {k_faq}/{n} concurrents en ont une, ta page non ({moi['faq']}).")
            k_tab = sum(1 for _, a in autres if a["tableaux"])
            if not moi["tableaux"] and k_tab:
                faits.append(f"**Tableau** : {k_tab}/{n} ont au moins un tableau, ta page aucun.")
            mm = med([a["mots"] for _, a in autres])
            plus = sum(1 for _, a in autres if a["mots"] > moi["mots"])
            if plus:
                faits.append(f"**Longueur** : {plus}/{n} ont plus de mots que toi (médiane {nombre(round(mm))}, "
                             f"toi {nombre(moi['mots'])}). Un indice de ce que Google accepte ici, pas une cause.")
            for cle_, lib in (("images", "images"), ("videos", "vidéos intégrées"), ("listes", "listes")):
                k = sum(1 for _, a in autres if a[cle_] > moi[cle_])
                if k * 2 > n:
                    faits.append(f"**{lib.capitalize()}** : {k}/{n} en ont plus que toi (médiane "
                                 f"{nombre(round(med([a[cle_] for _, a in autres])))}, toi {moi[cle_]}).")
            ma_date = moi["modifiee"] or moi["publiee"]
            dates = [(a["modifiee"] or a["publiee"], i) for i, a in autres if a["modifiee"] or a["publiee"]]
            if not ma_date and dates:
                faits.append(f"**Date** : ta page ne déclare aucune date ; {len(dates)}/{n} en déclarent une "
                             f"(la plus récente : {max(dates)[0]}).")
            elif ma_date:
                recentes = [d for d, _ in dates if d > ma_date]
                if recentes:
                    faits.append(f"**Date** : {len(recentes)}/{n} sont datées plus récemment que la tienne "
                                 f"({ma_date}) ; la plus récente : {max(recentes)}.")
            schemas = {}
            for _, a in autres:
                for t in a["types_jsonld"]:
                    if t not in moi["types_jsonld"]:
                        schemas[t] = schemas.get(t, 0) + 1
            schemas = {t: k for t, k in schemas.items() if k >= 2}
            if schemas:
                faits.append("**Schema déclaré par 2 concurrents ou plus, pas chez toi** : " + ", ".join(
                    f"{t} ({k}/{n})" for t, k in sorted(schemas.items(), key=lambda kv: (-kv[1], kv[0]))[:6]) + ".")
            k_aut = sum(1 for _, a in autres if a["auteur"])
            if not moi["auteur"] and k_aut:
                faits.append(f"**Auteur** : {k_aut}/{n} affichent ou déclarent un auteur, ta page non.")
            k_src = sum(1 for _, a in autres if a["liens_externes"] > moi["liens_externes"])
            if k_src * 2 > n:
                faits.append(f"**Sources** : {k_src}/{n} citent plus de sites que toi (liens externes du texte : "
                             f"médiane {nombre(round(med([a['liens_externes'] for _, a in autres])))}, toi "
                             f"{moi['liens_externes']}).")
            if not faits:
                faits.append("Rien de mesurable ne manque à ta page par rapport à eux (FAQ, tableau, longueur, "
                             "date, schema, auteur). L'écart, s'il existe, est dans l'angle : lis-les.")
            for f in faits:
                w("- " + f)
            w("")
            enplus = []
            if moi["faq_oui"] and sum(1 for _, a in autres if a["faq_oui"]) * 2 < n:
                enplus.append("une FAQ")
            if moi["tableaux"] and sum(1 for _, a in autres if a["tableaux"]) * 2 < n:
                enplus.append("un tableau")
            if moi["mots"] > (mm or 0):
                enplus.append(f"plus de mots que la médiane ({nombre(moi['mots'])})")
            if enplus:
                w("Ce que ta page a et que la plupart n'ont pas : " + ", ".join(enplus) + ".")
                w("")
        w("### Les sujets qu'ils titrent et pas toi")
        w("")
        if moi is not None:
            w("Un mot compte quand il est dans un H2 ou un H3 d'un concurrent et dans aucun de tes titres (H1 à "
              "H4). « Dans ton texte » : combien de fois il apparaît quand même dans ta page.")
        else:
            w("Un mot compte quand il est dans un H2 ou un H3 d'un concurrent.")
        w("")
        seuil = max(2, -(-n // 3)) if n >= 3 else 1
        retenus = [(j, v) for j, v in mots if len(v) >= seuil][:25]
        if retenus:
            w("| mot | concurrents qui le titrent | exemples de titres" + (" | dans ton texte |" if moi else " |"))
            w("|---|---|---|" + ("---|" if moi else ""))
            formes = {}
            for _, a in autres:
                for r, f in a["formes"].items():
                    formes.setdefault(r, f)
            for j, v in retenus:
                ex = " · ".join(f"{noms[i].split(' ')[0]} {court(t, 60)}" for i, t in v[:3])
                cel = f"| {formes.get(j, j)} | {len(v)}/{n} | {cellule(ex)} |"
                if moi:
                    cel += f" {moi['jetons_texte'].get(j, 0)} |"
                w(cel)
        else:
            w(f"Aucun mot titré par {seuil} concurrents ou plus qui manque à tes titres.")
        w("")
        w("### Leurs sections, page par page")
        w("")
        for (i, a), (_, absentes) in zip(autres, sections):
            w(f"**{noms[i]}** : {a['h2']} H2, {a['h3']} H3, {nombre(a['mots'])} mots, FAQ {a['faq']}.")
            w("")
            h2 = [t for niv, t in a["titres"] if niv == 2] or [t for niv, t in a["titres"] if niv == 3]
            for t in h2[:30]:
                marque = " ← absent de tes titres" if moi and any(t == x for x, _ in absentes) else ""
                w(f"- {cellule(t)}{marque}")
            if len(h2) > 30:
                w(f"- … et {len(h2) - 30} autres (dans le JSON)")
            if not h2:
                w("- (aucun H2 ni H3 dans le texte principal)")
            if a["domaines_cites"]:
                w(f"\n  Sites cités dans le texte : {', '.join(a['domaines_cites'][:8])}.")
            w("")
        w("<!-- CLAUDE: lis en entier les 3 pages les plus proches de l'intention (pas les 10), et écris pour "
          "chacune son angle en une ligne : à qui elle parle, ce qu'elle promet, ce qui la rend crédible "
          "(chiffres, expérience, sources). -->")
        w("")
        w("## L'angle et le plan")
        w("")
        w("<!-- CLAUDE: l'angle qui manque à toutes ces pages, ce que toi seul peux apporter (expérience vécue, "
          "chiffres à toi, une FAQ sourcée), puis le plan de ta page : les sujets du tableau ci-dessus à couvrir "
          "avec tes mots, jamais la structure d'un concurrent recopiée. Si un concurrent a un site entier sur ce "
          "sujet et toi une page, dis que c'est un hub à construire (voir site.py). -->")
        w("")

    rates = [(i, l) for i, l in enumerate(lignes) if not l["m"]]
    if rates:
        w("## Pages non lues")
        w("")
        for i, l in rates:
            w(f"- {l['url']} : {l['erreur']}")
        w("")
        w("Un site qui refuse un script n'est pas un site qui a disparu de Google. Ouvre la page dans ton "
          "navigateur, enregistre-la (« page web, HTML uniquement ») et relance avec "
          "`--html URL=fichier.html`, ou retire-la du tableau en le disant.")
        w("")
    w("## Ce que ce rapport ne mesure pas")
    w("")
    w("Les liens qui pointent vers ces pages (backlinks), l'autorité de leur domaine, les clics qu'elles "
      "reçoivent, ce que Google lit du texte rendu en JavaScript. Une page refusée ou rendue côté navigateur peut "
      "compter moins de mots qu'elle n'en affiche. « Non trouvé » veut dire « pas dans le code lu », pas « absent "
      "de la page ».")
    w("")
    return "\n".join(L)


def maj_serp(chemin, requete, lignes, moi_idx, jour):
    entete = ["requete", "position", "url", "domaine", "note_le"]
    gardees = []
    if os.path.exists(chemin):
        with open(chemin, newline="", encoding="utf-8") as f:
            gardees = [r for r in csv.DictReader(f) if r.get("requete") != requete]
    for i, l in enumerate(lignes):
        if i != moi_idx:
            gardees.append({"requete": requete, "position": str(l["pos"]), "url": l["url"],
                            "domaine": c.hote(l["url"]), "note_le": jour})
    gardees.sort(key=lambda r: (r["requete"], int(r["position"] or 0)))
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=entete, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(gardees)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*", help="les URL concurrentes, dans l'ordre de la page de résultats")
    ap.add_argument("--mienne", help="l'URL de ta page sur ce sujet")
    ap.add_argument("--site", help="ton site (monsite.com), si tu n'as pas encore de page sur ce sujet")
    ap.add_argument("--requete", help="la requête visée, telle qu'on la tape dans Google")
    ap.add_argument("--dossier", help="dossier racine des données (défaut ./seo)")
    ap.add_argument("--html", action="append", default=[], metavar="URL=FICHIER",
                    help="une page enregistrée depuis ton navigateur, pour un site qui refuse le script")
    ap.add_argument("--rafraichir", action="store_true", help="relire les pages même si elles sont en cache")
    ap.add_argument("--sans-search-console", action="store_true", help="ne pas appeler Search Console")
    a = ap.parse_args(argv)

    if not a.mienne and not a.site:
        raise c.Panne("Dis quel est ton site : --mienne https://monsite.com/ta-page, ou --site monsite.com si tu "
                      "n'as pas encore de page sur ce sujet.")
    fichiers = {}
    for x in a.html:
        if "=" not in x:
            raise c.Panne(f"--html attend URL=fichier.html, pas « {x} ».")
        u, f = x.split("=", 1)
        fichiers[u.strip()] = f.strip()
    urls = list(dict.fromkeys(u.strip() for u in a.urls + list(fichiers) if u.strip()))
    if a.mienne:
        urls = [u for u in urls if u.rstrip("/") != a.mienne.rstrip("/")]
    if not urls:
        raise c.Panne("Aucune URL concurrente. Passe les 5 à 10 URL de la première page de Google, dans l'ordre.")
    if len(urls) > MAX_URLS:
        print(f"  {len(urls)} URL : je garde les {MAX_URLS} premières (au-delà, la première page est finie).")
        urls = urls[:MAX_URLS]
    for u in urls + ([a.mienne] if a.mienne else []):
        if not re.match(r"https?://", u):
            raise c.Panne(f"« {u} » n'est pas une URL complète (elle doit commencer par https://).")

    site = c.hote(a.site or a.mienne)
    jour = dt.date.today().isoformat()
    root = c.racine(a.dossier)
    dossier = os.path.join(root, site, "competitors")
    cache_dir = os.path.join(dossier, ".cache")
    os.makedirs(dossier, exist_ok=True)
    slug = c.slugifier(a.requete) if a.requete else c.slugifier(
        urllib.parse.urlparse(a.mienne).path.strip("/").split("/")[-1] if a.mienne else "comparaison")
    q_jetons = sorted(set(c.jetons(a.requete))) if a.requete else []

    entrees = ([(a.mienne, None)] if a.mienne else []) + [(u, p) for p, u in enumerate(urls, 1)]
    moi_idx = 0 if a.mienne else None
    lignes = []
    print(f"{site} : {len(urls)} page(s) concurrente(s){' + la tienne' if a.mienne else ''} -> {dossier}")
    for u, pos in entrees:
        d = lire(u, cache_dir, jour, a.rafraichir, fichiers.get(u))
        l = {"url": u, "pos": pos, "m": None, "erreur": d.get("erreur", "")}
        if d.get("ok"):
            m = mesurer(d["texte"], d.get("url_finale") or u, q_jetons)
            m["_ms"], m["_octets"], m["_statut"] = d.get("ms"), d.get("octets", 0), d.get("statut")
            m["_url_finale"], m["_source"] = d.get("url_finale"), d.get("source")
            if m["mots"] < 80 and m["mots_page_entiere"] < 150:
                l["erreur"] = (f"page presque vide pour un script ({m['mots_page_entiere']} mots) : rendue en "
                               "JavaScript, ou une page de vérification anti-robot")
            else:
                l["m"] = m
        lignes.append(l)
        etat = f"{l['m']['mots']} mots" if l["m"] else l["erreur"]
        print(f"  {'toi' if pos is None else '#' + str(pos):>4} {u[:90]} : {etat}")

    sc = None
    if a.requete and not a.sans_search_console:
        sc = search_console(a.dossier, site, a.requete)
        print("  Search Console : " + ("ok" if sc["etat"] == "ok" else sc["message"]))

    md = rapport(a.requete, site, lignes, moi_idx, sc, jour)
    chemin_md = os.path.join(dossier, slug + ".md")
    garde = c.ecrire_rapport(chemin_md, md)
    if garde:
        print(f"  l'ancien rapport est gardé : {garde}")
    detail = {"requete": a.requete, "site": site, "mesure_le": jour, "search_console": sc,
              "pages": [{"url": l["url"], "position": l["pos"], "erreur": l["erreur"] if not l["m"] else "",
                         "mesures": l["m"]} for l in lignes]}
    with open(os.path.join(dossier, slug + ".json"), "w", encoding="utf-8") as f:
        json.dump(detail, f, ensure_ascii=False, indent=1, sort_keys=True)
    if a.requete:
        maj_serp(os.path.join(dossier, "serp.csv"), a.requete, lignes, moi_idx, jour)
    lues = sum(1 for l in lignes if l["m"])
    print(f"RAPPORT {chemin_md}")
    print(f"  {lues}/{len(lignes)} page(s) lue(s) ; marqueurs à remplir : {md.count('<!-- CLAUDE:')}")
    return chemin_md


if __name__ == "__main__":
    try:
        main()
    except c.Panne as e:
        sys.exit("ERREUR : " + str(e))
