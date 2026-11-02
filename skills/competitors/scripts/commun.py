"""Ce que pages.py et site.py partagent : téléchargement poli, dossiers du lecteur, mots.

Bibliothèque standard seulement (Python 3.10+). Rien à lancer ici.
"""
import gzip
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib

UA = "skill-competitors/1"  # un nom de robot honnête ; « Mozilla (compatible…) » se fait bloquer plus souvent
LANGUES = "fr-FR,fr;q=0.9,en;q=0.8"


class Panne(Exception):
    """Erreur lisible par un humain, sans trace Python."""


def racine(arg=None):
    """Dossier des données : --dossier, sinon ./seo du dossier courant (le même que search-console)."""
    return os.path.abspath(os.path.expanduser(arg or os.environ.get("GSC_DOSSIER") or "seo"))


def hote(saisie):
    """« https://www.monsite.com/x » ou « monsite.com » -> « monsite.com » (sans www.)."""
    s = saisie.strip()
    h = (urllib.parse.urlparse(s if "//" in s else "https://" + s).hostname or s).lower()
    return h[4:] if h.startswith("www.") else h


def meme_site(h1, h2):
    """Même site si même hôte, ou l'un est un sous-domaine de l'autre (blog.monsite.com)."""
    a, b = hote(h1), hote(h2)
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def slugifier(s, maxi=60):
    s = re.sub(r"[^a-z0-9]+", "-", sans_accents(s.lower())).strip("-")
    return (s[:maxi].rstrip("-")) or "page"


def telecharger(url, timeout=15, max_octets=8_000_000, accept="text/html,application/xhtml+xml,*/*;q=0.8"):
    """Une requête GET. Ne lève jamais : rend un dict avec ok, statut, url_finale, octets, ms, texte, erreur."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": LANGUES,
                                               "Accept-Encoding": "gzip"})
    t0 = time.monotonic()
    out = {"url": url, "ok": False, "statut": None, "url_finale": url, "octets": 0, "ms": None, "texte": "",
           "type": "", "erreur": ""}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            brut = r.read(max_octets + 1)
            out["ms"] = round((time.monotonic() - t0) * 1000)
            out["statut"], out["url_finale"] = r.status, r.geturl()
            enc = (r.headers.get("Content-Encoding") or "").lower()
            out["type"] = r.headers.get("Content-Type") or ""
            out["last_modified"] = r.headers.get("Last-Modified") or ""
    except urllib.error.HTTPError as e:
        out["statut"], out["ms"] = e.code, round((time.monotonic() - t0) * 1000)
        out["erreur"] = {403: "refusée (403) : le site bloque les scripts", 401: "refusée (401)",
                         404: "introuvable (404)", 410: "supprimée (410)", 429: "trop de requêtes (429)",
                         451: "indisponible ici (451)"}.get(e.code, f"le serveur répond en erreur (HTTP {e.code})"
                                                           if e.code >= 500 else f"erreur HTTP {e.code}")
        return out
    except (urllib.error.URLError, socket.timeout, TimeoutError, ssl.SSLError, ConnectionError,
            http.client.HTTPException, OSError, ValueError) as e:
        raison = getattr(e, "reason", e)
        txt = str(raison)
        if isinstance(raison, (socket.timeout, TimeoutError)) or "timed out" in txt:
            out["erreur"] = f"pas de réponse en {timeout} s"
        elif "CERTIFICATE" in txt.upper():
            out["erreur"] = "certificat HTTPS refusé"
        elif "Name or service not known" in txt or "nodename nor servname" in txt or "getaddrinfo" in txt:
            out["erreur"] = "domaine introuvable"
        else:
            out["erreur"] = "réseau : " + txt[:120]
        return out
    if len(brut) > max_octets:
        brut = brut[:max_octets]
        out["tronque"] = True
    try:
        if "gzip" in enc or brut[:2] == b"\x1f\x8b":
            brut = gzip.decompress(brut)
        elif "deflate" in enc:
            brut = zlib.decompress(brut)
    except (OSError, zlib.error, EOFError):
        pass
    out["octets"] = len(brut)
    out["texte"] = decoder(brut, out["type"])
    out["ok"] = True
    return out


def decoder(brut, content_type=""):
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    enc = m.group(1) if m else None
    if not enc:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", brut[:4096], re.I)
        enc = m.group(1).decode("ascii", "replace") if m else "utf-8"
    try:
        return brut.decode(enc, "replace")
    except LookupError:
        return brut.decode("utf-8", "replace")


def date_iso(s):
    """« 2026-03-01T10:00:00+01:00 » -> « 2026-03-01 » ; rien de reconnaissable -> « »."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def ecrire_rapport(chemin, md):
    """Écrit le rapport. Un rapport différent déjà là (relu, complété par Claude) est gardé à côté, jamais écrasé.
    Rend le nom de la copie gardée, ou « »."""
    garde = ""
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8") as f:
            ancien = f.read()
        if ancien != md:
            quand = time.strftime("%Y-%m-%d-%H%M", time.localtime(os.path.getmtime(chemin)))
            base, ext = os.path.splitext(chemin)
            garde = f"{base}-avant-{quand}{ext}"
            os.replace(chemin, garde)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(md)
    return os.path.basename(garde)


def cle(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def lire_cache(chemin, jour):
    """Le cache ne vaut que pour le jour même : deux lancements le même jour donnent le même rapport."""
    try:
        with open(chemin, encoding="utf-8") as f:
            d = json.load(f)
        return d if d.get("jour") == jour else None
    except (OSError, ValueError):
        return None


def ecrire_cache(chemin, d):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


# --- les mots ---------------------------------------------------------------

_VIDES = """
a about above after again against all also am an and any are as at be because been before being below between
both but by can could did do does doing down during each few for from further get got had has have having he her
here hers him his how i if in into is it its just like make many may me more most much my no nor not now of off on
once one only or other our ours out over own per same she should so some such than that the their them then there
these they this those through to too two under until up use using very via vs versus was we were what when where
which while who whom why will with would you your yours
au aux avec ce ces cet cette ca c chez comme comment d dans de des du elle elles en entre est et etre eux fait faire
faut il ils j je l la le les leur leurs lui m ma mais me meme mes moi moins mon n ne nos notre nous on ou par pas
peut plus pour pourquoi qu quand que quel quelle quelles quels qui quoi s sa sans se ses si son sont sur t ta te tes
toi ton tous tout toute toutes tres tu un une vers vos votre vous y avant apres depuis bien
dun dune lun lune quest cest quil quils quelle nest jai sest ny aujourd hui
"""
# Mots de deux lettres qui portent un sujet (les autres mots de moins de trois lettres sont écartés).
COURTS = {"ia", "ai", "ui", "ux", "js", "ts", "go", "os", "bi", "qa", "rh", "hr", "3d", "vr", "ml", "pc", "tv"}
# Élisions collées dans les slugs : « l'IA » devient « lia ».
ELISIONS = {"lia": "ia", "dia": "ia", "lai": "ai"}
_GENERIQUES = """
guide guides complete ultimate best top tip tips way ways thing things everything need know step steps easy simple
new updated update review reviews introduction intro conclusion summary overview final thoughts faq faqs question
questions answer answers table contents read list article blog post page home index html htm php aspx asp www com
meilleur meilleurs meilleure meilleures complet ultime astuce astuces conseil conseils savoir etape etapes sommaire
resume bonus liste nouveau nouvelle partie chapitre part en fr why what
"""


def racine_mot(m):
    """Racine grossière, la même des deux côtés : pluriels et e final (loyers = loyer, taxes = taxe = tax)."""
    if len(m) > 4 and m.endswith("ies"):
        return m[:-3] + "y"
    if len(m) > 4 and m.endswith("es") and m[-3] in "sxzh":
        m = m[:-2]
    elif len(m) > 3 and m[-1] in "sx" and not m.endswith(("ss", "us", "is")):
        m = m[:-1]
    if len(m) >= 4 and m.endswith("e"):
        m = m[:-1]
    return m


VIDES = set(_VIDES.split())
GENERIQUES = {racine_mot(m) for m in _GENERIQUES.split()}
MOT = re.compile(r"[a-z0-9]+")


def mots_bruts(texte):
    return MOT.findall(sans_accents(texte.lower()).replace("’", "'"))


def formes(texte, ignores=()):
    """Les mots qui portent un sujet, en couples (racine, mot tel qu'écrit) : sans mots vides fr/en, sans
    mots génériques (guide, best, conseils…), sans chiffres. La racine sert à comparer, le mot à afficher."""
    out = []
    for m in mots_bruts(texte):
        m = ELISIONS.get(m, m)
        if m in COURTS:
            if m not in ignores:
                out.append((m, m))
            continue
        if m in VIDES or len(m) < 3 or m.isdigit():
            continue
        r = racine_mot(m)
        if r in GENERIQUES or r in ignores or len(r) < 3:
            continue
        out.append((r, m))
    return out


def jetons(texte, ignores=()):
    return [r for r, _ in formes(texte, ignores)]


def langue_des_mots(mots):
    """« fr », « en » ou « ? » d'après les mots vides les plus courants (sur des slugs ou un texte)."""
    fr = sum(m in {"de", "la", "le", "les", "des", "du", "en", "et", "pour", "un", "une", "comment", "sur"} for m in mots)
    en = sum(m in {"the", "of", "to", "and", "for", "in", "how", "your", "with", "is", "on", "what"} for m in mots)
    if fr + en < 5:
        return "?"
    return "fr" if fr > 1.5 * en else "en" if en > 1.5 * fr else "?"
