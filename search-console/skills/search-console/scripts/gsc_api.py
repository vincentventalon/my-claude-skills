"""Accès à l'API Google Search Console, sans dépendance (Python 3.8+, stdlib).

Authentification : le jeton gcloud ADC
  gcloud auth application-default login \
    --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/webmasters.readonly
Projet de quota (en-tête X-Goog-User-Project), lu dans cet ordre :
  1. la variable d'environnement GSC_QUOTA_PROJECT
  2. le fichier ./seo/config.json du dossier de travail : {"projet_google_cloud": "mon-projet"}
  3. le quota_project_id du fichier ADC (gcloud auth application-default set-quota-project)

Les données, le journal et le tableau de bord vivent dans ./seo/ (dossier de travail du lecteur),
jamais dans le dossier de la skill : une mise à jour du plugin le remplace.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

RACINE = None  # dossier des données, fixé par racine()
MEMOIRE = os.path.join(os.path.expanduser("~"), ".config", "search-console", "dossiers.txt")
API = "https://searchconsole.googleapis.com"
SCOPES = "https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/webmasters.readonly"
LOGIN = f"gcloud auth application-default login --scopes={SCOPES}"


class Panne(Exception):
    """Erreur lisible par un humain, sans trace Python."""


def racine(arg=None):
    """Dossier des données : --dossier, sinon $GSC_DOSSIER, sinon ./seo du dossier courant."""
    global RACINE
    RACINE = os.path.abspath(os.path.expanduser(arg or os.environ.get("GSC_DOSSIER") or "seo"))
    return RACINE


def retenir(dossier):
    """Garde la liste des dossiers déjà utilisés, pour « rafraîchis le dashboard » lancé d'ailleurs."""
    try:
        os.makedirs(os.path.dirname(MEMOIRE), exist_ok=True)
        vus = [l.strip() for l in open(MEMOIRE, encoding="utf-8")] if os.path.exists(MEMOIRE) else []
        vus = [dossier] + [v for v in vus if v and v != dossier]
        with open(MEMOIRE, "w", encoding="utf-8") as f:
            f.write("\n".join(vus[:20]) + "\n")
    except OSError:
        pass


def dossiers_connus():
    try:
        return [l.strip() for l in open(MEMOIRE, encoding="utf-8") if l.strip() and os.path.isdir(l.strip())]
    except OSError:
        return []


def config():
    path = os.path.join(RACINE or racine(), "config.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except ValueError as e:
            raise Panne(f"config.json illisible ({e}). Il doit ressembler à : {{\"projet_google_cloud\": \"mon-projet\"}}")
    return {}


def quota_project():
    p = os.environ.get("GSC_QUOTA_PROJECT") or config().get("projet_google_cloud")
    if p:
        return p.strip()
    adc = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
    if os.name == "nt":
        adc = os.path.join(os.environ.get("APPDATA", ""), "gcloud", "application_default_credentials.json")
    try:
        with open(adc) as f:
            p = json.load(f).get("quota_project_id")
            if p:
                return p
    except (OSError, ValueError):
        pass
    raise Panne(
        "Pas de projet Google Cloud pour le quota.\n"
        "Google exige l'en-tête X-Goog-User-Project sur chaque appel, sinon il répond 403 « requires a quota project ».\n"
        "Donne l'id de ton projet d'une de ces trois façons :\n"
        "  export GSC_QUOTA_PROJECT=mon-projet\n"
        f"  ou crée {os.path.join(RACINE or racine(), 'config.json')} avec {{\"projet_google_cloud\": \"mon-projet\"}}\n"
        "  ou gcloud auth application-default set-quota-project mon-projet"
    )


_TOKEN = None


def token():
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not gcloud:
        raise Panne("gcloud introuvable. Installe le Google Cloud CLI (https://cloud.google.com/sdk/docs/install), puis :\n  " + LOGIN)
    r = subprocess.run([gcloud, "auth", "application-default", "print-access-token"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise Panne("Pas de jeton d'accès Google (session absente ou expirée). Lance :\n  " + LOGIN + "\n(détail gcloud : " + r.stderr.strip()[:200] + ")")
    _TOKEN = r.stdout.strip()
    return _TOKEN


def _explique(code, msg, site=None):
    m = msg.lower()
    if "quota project" in m:
        return ("403 : Google veut un projet de quota. Vérifie l'id du projet (" + quota_project() + ") : il doit exister et tu dois y avoir accès.\n"
                "Rappel : chaque appel porte l'en-tête X-Goog-User-Project.")
    if "has not been used" in m or "is disabled" in m or "service_disabled" in m:
        return ("403 : l'API Google Search Console n'est pas activée sur le projet " + quota_project() + ". Active-la :\n"
                "  gcloud services enable searchconsole.googleapis.com --project " + quota_project() + "\n"
                "puis attends deux minutes.")
    if "insufficient authentication scopes" in m or "scope" in m and code == 403:
        return "403 : ta session gcloud n'a pas le droit de lire Search Console (scope manquant). Relance :\n  " + LOGIN
    if "sufficient permission for site" in m or "not a verified" in m:
        return f"403 : ton compte Google n'a pas accès à la propriété {site}.\n" + _proprietes_connues()
    if "project" in m and ("not found" in m or "deleted" in m):
        return ("Le projet Google Cloud « " + quota_project() + " » n'existe pas, ou ton compte n'y a pas accès.\n"
                "Donne l'id du projet (pas son nom) : gcloud projects list")
    if code == 401:
        return "401 : jeton refusé (session expirée ?). Relance :\n  " + LOGIN
    if "user_project_denied" in m or "serviceusage" in m:
        return ("403 : ton compte n'a pas le droit d'utiliser le projet " + quota_project() + " comme projet de quota.\n"
                "Il faut le rôle « Service Usage Consumer » sur ce projet, ou choisis un projet dont tu es propriétaire.")
    return f"{code} : {msg[:400]}"


def _proprietes_connues():
    try:
        sites = lister_sites()
    except Panne:
        return "Impossible de lister tes propriétés."
    if not sites:
        return "Ton compte ne voit aucune propriété Search Console. Connecte-toi avec le compte qui possède le site."
    return "Propriétés visibles avec ce compte :\n" + "\n".join("  " + s for s in sites)


def appel(method, path, body=None, site=None, essais=4):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    for i in range(essais):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + token(),
            "X-Goog-User-Project": quota_project(),
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            try:
                msg = json.loads(txt)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                msg = txt
            if (e.code == 429 or e.code >= 500) and i < essais - 1:
                time.sleep(3 * (i + 1) ** 2)
                continue
            raise Panne(_explique(e.code, msg, site))
        except urllib.error.URLError as e:
            if i < essais - 1:
                time.sleep(3 * (i + 1))
                continue
            raise Panne(f"Réseau : impossible de joindre l'API Google ({e.reason}).")
    raise Panne("API Google injoignable après plusieurs essais.")


def lister_sites():
    r = appel("GET", "/webmasters/v3/sites")
    return sorted(s["siteUrl"] for s in r.get("siteEntry", []))


def resoudre_site(saisie):
    """« monsite.com », « https://monsite.com/ » ou « sc-domain:monsite.com » -> propriété existante."""
    s = saisie.strip()
    if s.startswith("sc-domain:"):
        dom = s[len("sc-domain:"):]
    else:
        dom = urllib.parse.urlparse(s if "//" in s else "https://" + s).hostname or s
    dom = dom.lower().strip("/")
    nu = dom[4:] if dom.startswith("www.") else dom
    sites = lister_sites()
    candidats = ["sc-domain:" + nu, "https://" + dom + "/", "https://www." + nu + "/", "https://" + nu + "/",
                 "http://" + dom + "/", "http://www." + nu + "/", "http://" + nu + "/"]
    if s in sites:
        return s
    for c in candidats:
        if c in sites:
            if not c.startswith("sc-domain:"):
                print(f"  (pas de propriété Domaine sc-domain:{nu}, j'utilise la propriété {c} : "
                      "elle ne voit que ce préfixe d'URL)", file=sys.stderr)
            return c
    raise Panne(f"Propriété introuvable pour « {saisie} ».\n" + _proprietes_connues()
                + "\nCrée une propriété de type Domaine dans Search Console, ou passe le nom exact ci-dessus.")


def nom_dossier(site):
    if site.startswith("sc-domain:"):
        return site[len("sc-domain:"):]
    return (urllib.parse.urlparse(site).hostname or site).replace(":", "_")


def chemin(site):
    return urllib.parse.quote(site, safe="")


def recherche(site, debut, fin, dimensions=(), filtres=None, data_state="all", type_recherche="web"):
    """Toutes les lignes de Search Analytics (pagination par 25 000)."""
    lignes, start, meta = [], 0, {}
    while True:
        body = {"startDate": debut, "endDate": fin, "dimensions": list(dimensions), "type": type_recherche,
                "dataState": data_state, "rowLimit": 25000, "startRow": start}
        if filtres:
            body["dimensionFilterGroups"] = [{"filters": filtres}]
        r = appel("POST", f"/webmasters/v3/sites/{chemin(site)}/searchAnalytics/query", body, site=site)
        meta = r.get("metadata", meta)
        got = r.get("rows", [])
        lignes += got
        if len(got) < 25000:
            return lignes, meta
        start += 25000


def inspecter(site, url):
    r = appel("POST", "/v1/urlInspection/index:inspect",
              {"inspectionUrl": url, "siteUrl": site, "languageCode": "fr-FR"}, site=site, essais=3)
    return r.get("inspectionResult", {}).get("indexStatusResult", {})


def sitemaps(site):
    return appel("GET", f"/webmasters/v3/sites/{chemin(site)}/sitemaps", site=site).get("sitemap", [])
