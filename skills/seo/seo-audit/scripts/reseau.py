"""Le réseau de l'audit : des requêtes polies qui gardent la chaîne de redirections.

Bibliothèque standard seulement. Rien ne lève d'exception : une page qui refuse, un serveur
muet ou un certificat faux donnent un résultat avec `statut` 0 et une `erreur` lisible.
"""
import http.client
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; skill-seo-audit/1; +https://github.com/vincentventalon/my-claude-skills)"
TIMEOUT = 15
MAX_OCTETS = 3_000_000
DELAI = 0.25          # pause après chaque requête, par fil
REDIRECTIONS = (301, 302, 303, 307, 308)
ENTETES = ("content-type", "content-length", "x-robots-tag", "strict-transport-security", "cache-control",
           "last-modified", "location", "link", "content-encoding")


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_SansRedirection)


def _raison(e):
    r = getattr(e, "reason", e)
    txt = str(r)
    if isinstance(r, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in txt:
        return "certificat HTTPS refusé (" + txt[:120] + ")"
    if isinstance(r, socket.gaierror) or "nodename nor servname" in txt or "Name or service not known" in txt \
            or "getaddrinfo" in txt:
        return "domaine introuvable (DNS)"
    if isinstance(r, (socket.timeout, TimeoutError)) or "timed out" in txt:
        return f"pas de réponse en {TIMEOUT} s"
    if "refused" in txt.lower():
        return "connexion refusée"
    return txt[:160] or e.__class__.__name__


def en_ascii(url):
    """Une URL avec accents ou espaces, encodée comme le ferait un navigateur."""
    try:
        p = urllib.parse.urlsplit(url)
        hote = p.hostname.encode("idna").decode("ascii") if p.hostname else ""
        netloc = hote + (f":{p.port}" if p.port else "")
    except (ValueError, UnicodeError):
        return url
    garde = "/:@!$&'()*+,;=%~-._"
    return urllib.parse.urlunsplit((p.scheme, netloc, urllib.parse.quote(p.path, safe=garde),
                                    urllib.parse.quote(p.query, safe=garde + "?"), ""))


def requete(url, methode="GET", lire=True, max_octets=MAX_OCTETS):
    """Une requête, sans suivre de redirection."""
    t0 = time.monotonic()
    corps = b""
    try:
        req = urllib.request.Request(en_ascii(url), method=methode, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr,en;q=0.8",
        })
        try:
            r = _OPENER.open(req, timeout=TIMEOUT)
            code = r.status
        except urllib.error.HTTPError as e:
            r, code = e, e.code
        ttfb = time.monotonic() - t0
        entetes = {k: r.headers.get(k) for k in ENTETES if r.headers.get(k) is not None}
        if lire and methode != "HEAD":
            try:
                corps = r.read(max_octets)
            except (http.client.IncompleteRead, OSError, ValueError) as e:
                corps = getattr(e, "partial", b"") or b""
        try:
            r.close()
        except Exception:
            pass
        return {"url": url, "statut": code, "entetes": entetes, "corps": corps, "ttfb_ms": round(ttfb * 1000),
                "total_ms": round((time.monotonic() - t0) * 1000), "erreur": ""}
    except Exception as e:  # réseau, SSL, réponse illisible : jamais d'arrêt
        return {"url": url, "statut": 0, "entetes": {}, "corps": b"", "ttfb_ms": None,
                "total_ms": round((time.monotonic() - t0) * 1000), "erreur": _raison(e)}
    finally:
        time.sleep(DELAI)


def suivre(url, methode="GET", lire=True, sauts=10):
    """Suit les redirections une à une. `chaine` = [[url, code], ...] avant la réponse finale."""
    chaine, vus = [], set()
    cur = url
    for _ in range(sauts + 1):
        r = requete(cur, methode, lire)
        if methode == "HEAD" and r["statut"] in (403, 404, 405, 410, 501):  # certains serveurs refusent HEAD
            r = requete(cur, "GET", lire=False)
        if r["statut"] in REDIRECTIONS and r["entetes"].get("location"):
            chaine.append([cur, r["statut"]])
            nxt = urllib.parse.urljoin(cur, r["entetes"]["location"].strip())
            if nxt in vus or nxt == cur:
                r["erreur"] = "boucle de redirections"
                break
            vus.add(cur)
            cur = nxt
            continue
        break
    else:
        r["erreur"] = f"plus de {sauts} redirections"
    r["chaine"] = chaine
    r["url_finale"] = cur
    r["url"] = url
    return r


def texte(r):
    """Le corps décodé : charset de l'en-tête, sinon <meta charset>, sinon UTF-8 tolérant."""
    corps = r.get("corps") or b""
    ct = r["entetes"].get("content-type", "")
    m = re.search(r"charset=([\w-]+)", ct, re.I) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", corps[:4000], re.I)
    enc = m.group(1) if m else "utf-8"
    if isinstance(enc, bytes):
        enc = enc.decode("ascii", "replace")
    try:
        return corps.decode(enc, "replace")
    except LookupError:
        return corps.decode("utf-8", "replace")


# --- robots.txt (RFC 9309 : groupes, Allow/Disallow, * et $, la règle la plus longue gagne) ---

def lire_robots(contenu):
    groupes, sitemaps = [], []
    agent_precedent = False
    for ligne in contenu.splitlines():
        ligne = ligne.split("#", 1)[0].strip()
        if ":" not in ligne:
            continue
        cle, val = (x.strip() for x in ligne.split(":", 1))
        cle = cle.lower()
        if cle == "user-agent":
            if not agent_precedent:
                groupes.append({"agents": [], "regles": []})
            groupes[-1]["agents"].append(val.lower())
            agent_precedent = True
            continue
        agent_precedent = False
        if cle in ("allow", "disallow") and groupes:
            groupes[-1]["regles"].append((cle == "allow", val))
        elif cle == "sitemap" and val:
            sitemaps.append(val)
    return groupes, sitemaps


def regles_pour(groupes, agent="googlebot"):
    """Les règles qui s'appliquent à Googlebot : son groupe s'il en a un, sinon celui de *."""
    propres = [r for g in groupes if agent in g["agents"] for r in g["regles"]]
    if any(agent in g["agents"] for g in groupes):
        return propres
    return [r for g in groupes if "*" in g["agents"] for r in g["regles"]]


def autorise(regles, url):
    p = urllib.parse.urlsplit(url)
    chemin = (p.path or "/") + ("?" + p.query if p.query else "")
    meilleure = None
    for permis, motif in regles:
        if not motif:
            continue
        rx = "^" + re.escape(motif).replace(r"\*", ".*")
        if rx.endswith(r"\$"):
            rx = rx[:-2] + "$"
        if re.match(rx, chemin) or re.match(rx, urllib.parse.unquote(chemin)):
            if meilleure is None or len(motif) > meilleure[0] or (len(motif) == meilleure[0] and permis):
                meilleure = (len(motif), permis, motif)
    if meilleure is None:
        return True, ""
    return meilleure[1], meilleure[2]
