"""Lecture d'une page HTML pour l'audit : balises, liens (texte ou navigation), images, dates.

Bibliothèque standard seulement (html.parser). Ne lit que le HTML envoyé par le serveur : ce
qu'un script ajoute ensuite dans le navigateur n'y est pas.

Trois zones pour un lien :
- navigation : dans <nav>, <header>, <footer> ou <aside>, dans un élément dont le rôle, la classe
  ou l'id dit navigation, menu, fil d'Ariane ou pagination, ou hors de <main> quand la page en a
  un. audit.py ajoute une règle sur tout le site : un lien identique (même cible, même texte, même
  place) sur plus de la moitié des pages est un bloc du gabarit, donc de la navigation ;
- texte : dans une phrase, c'est-à-dire dans un paragraphe, un élément de liste, une cellule ou
  une citation qui a au moins MOTS_PHRASE mots à lui autour du lien ;
- bloc de liens : le reste du contenu, des liens sans phrase autour (cartes « à lire aussi »,
  grilles d'une page hub, listes de liens nus).
"""
import json
import re
import urllib.parse
from html.parser import HTMLParser

VIDES = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
         "track", "wbr"}
CACHES = {"noscript", "template"}
ZONES = {"nav": "<nav>", "header": "<header>", "footer": "<footer>", "aside": "<aside>"}
ROLES = {"navigation": "rôle navigation", "menu": "rôle menu", "menubar": "rôle menu", "banner": "<header>",
         "contentinfo": "<footer>", "complementary": "<aside>"}
MOTS_NAV = {"nav", "navbar", "navigation", "menu", "menubar", "submenu", "breadcrumb", "breadcrumbs", "ariane",
            "pagination"}
CONTENEURS = {"p", "li", "td", "th", "dd", "dt", "blockquote", "figcaption", "caption", "summary"}
MOTS_PHRASE = 3
SUIVI = re.compile(r"^(utm_\w+|src|ref|fbclid|gclid|msclkid|mc_cid|mc_eid|igshid|_hs\w+)$", re.I)


def normaliser(url):
    """URL absolue sans fragment : schéma et hôte en minuscules, chemin vide -> /, encodage unifié."""
    try:
        p = urllib.parse.urlsplit(url.strip())
        hote = (p.hostname or "").lower()
        port = p.port
    except ValueError:
        return url.strip()
    if port and not ((p.scheme == "http" and port == 80) or (p.scheme == "https" and port == 443)):
        hote += f":{port}"
    chemin = urllib.parse.quote(urllib.parse.unquote(p.path or "/"), safe="/:@!$&'()*+,;=-._~")
    return urllib.parse.urlunsplit((p.scheme.lower(), hote, chemin, p.query, ""))


def sans_suivi(url):
    """L'URL sans ses paramètres de suivi (utm_*, src, ref, fbclid...), et la liste de ceux retirés."""
    p = urllib.parse.urlsplit(url)
    if not p.query:
        return url, []
    garde, retires = [], []
    for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True):
        (retires if SUIVI.match(k) else garde).append((k, v))
    if not retires:
        return url, []
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(garde), "")), \
        sorted({k for k, _ in retires})


def _mots_attr(a):
    return set(re.split(r"[^a-z0-9]+", (a.get("class", "") + " " + a.get("id", "")).lower()))


class Lecteur(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.base = url
        self.pile = []          # [tag, raison_nav, est_main, conteneur ou None]
        self.svg = 0
        self.cache = 0          # dans <noscript> ou <template>
        self.brut = None        # dans <script> ou <style>
        self.titres, self._titre = [], None
        self.h1, self._h1 = [], None
        self.metas, self.canoniques, self.hreflang, self.assets = [], [], [], []
        self.liens, self._a = [], None
        self.images, self._picture = [], None
        self.jsonld, self._json = [], None
        self.times = []
        self.lang = None
        self.a_main = False
        self.mots = 0
        self.mots_main = 0

    # --- contexte ---
    def _zone(self):
        for _, raison, _, _ in self.pile:
            if raison:
                return raison
        return None

    def _dans_main(self):
        return any(e[2] for e in self.pile)

    def _conteneur(self):
        for e in reversed(self.pile):
            if e[3] is not None:
                return e[3]
        return None

    def _ferme(self, entree):
        ct = entree[3]
        if ct is not None:
            for l in ct["liens"]:
                l["phrase"] = ct["mots"] >= MOTS_PHRASE

    def _abs(self, href):
        return urllib.parse.urljoin(self.base, href.strip())

    # --- balises ---
    def handle_starttag(self, tag, attrs, fermee=False):
        a = {k: (v if v is not None else "") for k, v in attrs}
        role = a.get("role", "").lower().strip()
        raison = ZONES.get(tag) or ROLES.get(role)
        if not raison and _mots_attr(a) & MOTS_NAV:
            raison = "classe menu/nav"
        est_main = tag == "main" or role == "main"
        if est_main:
            self.a_main = True
        if tag == "svg":
            self.svg += 1
        if tag in CACHES:
            self.cache += 1
        if tag not in VIDES and not fermee:
            self.pile.append([tag, raison, est_main, {"mots": 0, "liens": []} if tag in CONTENEURS else None])
        if tag in ("script", "style"):
            self.brut = tag
            if tag == "script":
                if a.get("src"):
                    self.assets.append(("js", self._abs(a["src"])))
                if "ld+json" in a.get("type", "").lower():
                    self._json = []
            return
        if self.svg or self.cache:
            return
        if tag == "html":
            self.lang = a.get("lang") or a.get("xml:lang") or None
        elif tag == "base" and a.get("href"):
            self.base = self._abs(a["href"])
        elif tag == "title":
            self._titre = []
        elif tag == "h1":
            self._h1 = []
        elif tag == "meta":
            self.metas.append(a)
        elif tag == "link":
            rel = a.get("rel", "").lower().split()
            href = a.get("href", "")
            if "canonical" in rel:
                self.canoniques.append(href.strip())
            if "alternate" in rel and a.get("hreflang"):
                self.hreflang.append((a["hreflang"].strip(), self._abs(href) if href else ""))
            if "stylesheet" in rel and href:
                self.assets.append(("css", self._abs(href)))
        elif tag == "picture":
            self._picture = []
        elif tag == "source" and self._picture is not None:
            self._picture.append((a.get("type", "") + " " + a.get("srcset", "")).lower())
        elif tag == "img":
            src = a.get("src", "")
            if not src or src.startswith("data:"):
                src = a.get("data-src") or a.get("data-lazy-src") or (a.get("srcset", "").split(" ")[0])
            moderne = bool(self._picture and any(("webp" in s or "avif" in s) for s in self._picture)) \
                or ".webp" in a.get("srcset", "").lower() or ".avif" in a.get("srcset", "").lower()
            if src and not src.startswith("data:"):
                self.images.append({"src": self._abs(src), "alt": a.get("alt") if "alt" in a else None,
                                    "moderne": moderne})
            if self._a is not None and a.get("alt"):
                self._a["alt"].append(a["alt"])
        elif tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"].strip())
        elif tag == "a":
            self._fin_lien()
            href = a.get("href")
            if href is None:
                return
            zone = self._zone() or ("classe menu/nav" if _mots_attr(a) & MOTS_NAV else None)
            self._a = {"href": href.strip(), "zone": zone, "main": self._dans_main(), "texte": [], "alt": [],
                       "label": a.get("aria-label", "") or a.get("title", ""),
                       "nofollow": "nofollow" in a.get("rel", "").lower(), "phrase": False,
                       "place": "/".join(e[0] for e in self.pile[-6:]), "conteneur": self._conteneur()}

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs, fermee=True)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            if self._json is not None:
                self.jsonld.append("".join(self._json))
                self._json = None
            self.brut = None
        elif tag == "title" and self._titre is not None:
            self.titres.append(" ".join("".join(self._titre).split()))
            self._titre = None
        elif tag == "h1" and self._h1 is not None:
            self.h1.append(" ".join("".join(self._h1).split()))
            self._h1 = None
        elif tag == "a":
            self._fin_lien()
        elif tag == "picture":
            self._picture = None
        if tag == "svg" and self.svg:
            self.svg -= 1
        if tag in CACHES and self.cache:
            self.cache -= 1
        if tag in VIDES:
            return
        for i in range(len(self.pile) - 1, -1, -1):
            if self.pile[i][0] == tag:
                for e in self.pile[i:]:
                    self._ferme(e)
                del self.pile[i:]
                break

    def handle_data(self, data):
        if self.brut:
            if self._json is not None:
                self._json.append(data)
            return
        if self.cache:
            return
        if self._titre is not None:
            self._titre.append(data)
            return
        if self.svg:
            return
        if self._h1 is not None:
            self._h1.append(data)
        n = len(data.split())
        if self._a is not None:
            self._a["texte"].append(data)
        else:
            ct = self._conteneur()
            if ct is not None:
                ct["mots"] += len(re.findall(r"\w{2,}", data))
        self.mots += n
        if self._dans_main():
            self.mots_main += n

    def _fin_lien(self):
        a, self._a = self._a, None
        if a is None:
            return
        texte = " ".join("".join(a.pop("texte")).split()) or " ".join(a.pop("alt")) or a["label"]
        a.pop("alt", None)
        a["texte"] = texte[:120]
        ct = a.pop("conteneur")
        if ct is not None:
            ct["liens"].append(a)
        self.liens.append(a)


def _types_jsonld(obj, types, dates):
    if isinstance(obj, list):
        for x in obj:
            _types_jsonld(x, types, dates)
    elif isinstance(obj, dict):
        t = obj.get("@type")
        for x in (t if isinstance(t, list) else [t] if t else []):
            if isinstance(x, str):
                types.add(x)
        for k in ("dateModified", "datePublished"):
            if isinstance(obj.get(k), str) and k not in dates:
                dates[k] = obj[k]
        for v in obj.values():
            if isinstance(v, (list, dict)):
                _types_jsonld(v, types, dates)


def lire(html, url):
    """Tout ce que l'audit veut savoir d'une page, dans un dict simple (sérialisable en JSON)."""
    lc = Lecteur(url)
    try:
        lc.feed(html)
        lc.close()
    except Exception:  # HTML cassé : on garde ce qui a été lu
        pass
    lc._fin_lien()
    for e in lc.pile:  # balises jamais fermées
        lc._ferme(e)
    meta = {}
    for m in lc.metas:
        cle = (m.get("name") or m.get("property") or m.get("http-equiv") or "").lower().strip()
        if cle and cle not in meta:
            meta[cle] = (m.get("content") or "").strip()
    robots = " ".join(meta.get(k, "") for k in ("robots", "googlebot")).lower()
    types, dates_ld, erreurs_ld = set(), {}, 0
    for bloc in lc.jsonld:
        try:
            _types_jsonld(json.loads(bloc.strip(), strict=False), types, dates_ld)
        except ValueError:
            erreurs_ld += 1
    dates = {}
    for cle in ("article:modified_time", "article:published_time", "og:updated_time"):
        if meta.get(cle):
            dates[cle] = meta[cle]
    for k, v in dates_ld.items():
        dates["JSON-LD " + k] = v
    if lc.times:
        dates["<time>"] = lc.times[0]
    liens = []
    for l in lc.liens:
        h = l["href"]
        if not h or h.startswith("#") or re.match(r"^(mailto|tel|javascript|data|sms|whatsapp):", h, re.I):
            continue
        cible = lc._abs(h)
        if not cible.lower().startswith(("http://", "https://")):
            continue
        zone = l["zone"] or ("hors <main>" if lc.a_main and not l["main"] else None)
        zone = zone or ("texte" if l["phrase"] else "bloc de liens")
        liens.append({"url": normaliser(cible), "texte": l["texte"], "zone": zone,
                      "nofollow": l["nofollow"], "place": l["place"]})
    return {
        "titres": lc.titres,
        "description": meta.get("description"),
        "robots": robots,
        "noindex": bool(re.search(r"\b(noindex|none)\b", robots)),
        "canoniques": lc.canoniques,
        "hreflang": lc.hreflang,
        "lang": lc.lang,
        "viewport": "viewport" in meta,
        "jsonld_types": sorted(types),
        "jsonld_erreurs": erreurs_ld,
        "og": {k: meta[k] for k in ("og:title", "og:description", "og:image", "og:type") if meta.get(k)},
        "h1": lc.h1,
        "images": lc.images,
        "dates": dates,
        "liens": liens,
        "assets": lc.assets,
        "a_main": lc.a_main,
        "mots": lc.mots_main if lc.a_main else lc.mots,
    }
