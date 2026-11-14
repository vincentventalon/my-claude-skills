"""Les constats de l'audit et le rapport AUDIT.md (appelé par audit.py).

Chaque constat : une priorité (1 indexation, 2 maillage dans le texte, 3 fondamentaux, 4 balises),
le fait, la preuve (URL et chiffres, tous posés ici), une correction proposée et un marqueur
<!-- CLAUDE: --> pour le jugement. Ce qui passe va dans « 5. Ce qui va bien », avec son chiffre.
"""
import csv
import datetime as dt
import re
import statistics
import urllib.parse
from collections import Counter

import lecture as lec
import reseau as net

TITLE_MAX, TITLE_MIN, DESC_MAX, DESC_MIN = 60, 20, 160, 50
IMAGE_LOURDE, TTFB_LENT, MOTS_VIDE, CACHE_MIN = 200_000, 800, 100, 7 * 86400
LCP_BON, CLS_BON, TBT_BON = 2500, 0.1, 200
LEGALE = re.compile(r"(mentions|legal|confidential|privacy|cgu|cgv|terms|/tos/?$|cookie|conditions|rgpd|gdpr|"
                    r"impressum|disclaimer|politique)", re.I)
HREFLANG = re.compile(r"^(x-default|[a-z]{2,3}(-[a-z]{4})?(-([a-z]{2}|\d{3}))?)$", re.I)
PRIORITES = {
    1: "Indexation : Google peut-il lire et garder tes pages ?",
    2: "Maillage dans le texte : tes pages se citent-elles ?",
    3: "Fondamentaux : redirections, HTTPS, vitesse, dates",
    4: "Balises : titles, descriptions, H1, images",
}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre"]


def hote_de(u):
    try:
        return (urllib.parse.urlsplit(u).hostname or "").lower()
    except ValueError:
        return ""


def court(u, hote):
    """`/chemin` pour une URL du site, l'URL entière sinon."""
    p = urllib.parse.urlsplit(u)
    if (p.hostname or "").lower() == hote:
        return urllib.parse.unquote(p.path or "/") + ("?" + p.query if p.query else "")
    return u


def nb(x, dec=None):
    """Un nombre à la française : virgule décimale."""
    t = f"{x:.{dec}f}" if dec is not None else f"{x:g}"
    return t.replace(".", ",")


def ko(n):
    return f"{round(n / 1000)} Ko" if n < 1_000_000 else f"{n / 1_000_000:.1f} Mo".replace(".", ",")


def pluriel(n, mot, mots=None):
    return f"{n} {mot if n == 1 else (mots or mot + 's')}"


def date_fr(iso):
    try:
        d = dt.datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.day} {MOIS[d.month - 1]} {d.year} à {d:%H:%M}"


def max_age(cc):
    m = re.search(r"max-age=(\d+)", cc or "")
    return int(m.group(1)) if m else None


def lire_journal(chemin):
    try:
        with open(chemin, newline="", encoding="utf-8") as f:
            return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]
    except (OSError, csv.Error):
        return []


# --- les constats ---------------------------------------------------------------

def analyser(A, pages, R, entrants, sortants, interne):
    ent_t, ent_b, ent_n = entrants
    sor_t, sor_b = sortants
    C, OK = [], []
    hote, accueil = A["site"], A["accueil"]
    hotes = {hote, hote[4:] if hote.startswith("www.") else "www." + hote}

    def c(prio, cle, titre, fait, preuves, correction, claude, rang=50):
        """rang : l'ordre dans la priorité (0 d'abord) ; à rang égal, l'ordre d'écriture."""
        C.append({"priorite": prio, "cle": cle, "titre": titre, "fait": fait, "preuves": preuves[:12],
                  "preuves_total": len(preuves), "correction": correction, "claude": claude, "rang": rang})

    def k(u):
        return "`" + court(u, hote) + "`"

    rows = {p["url"]: p for p in A["pages"]}
    sitemap = A["sitemap"]
    sm = [e["url"] for e in sitemap]
    sm_set = set(sm)
    insp = {i["url"]: i for i in A["gsc"]["inspections"]}

    def noindex(u):
        return rows.get(u, {}).get("noindex") == "oui"

    def canon(u):
        return rows.get(u, {}).get("canonique", "")

    html = sorted(pages)
    indexables = [u for u in html if not noindex(u) and (not canon(u) or canon(u) == u)]

    # ===== 1. Indexation =====
    rb = A["robots"]
    regles = [(p == "Allow", m) for p, m in rb["regles"]]
    if rb["statut"] == 0 or rb["statut"] >= 500:
        c(1, "robots-erreur", "robots.txt ne répond pas",
          f"`/robots.txt` répond {rb['statut'] or rb['erreur']}. Quand robots.txt renvoie une erreur serveur, Google "
          "met l'exploration de tout le site en pause.", [],
          "Fais répondre `/robots.txt` en 200, ou en 404 si tu n'en veux pas (Google explore alors tout).",
          "Relance l'audit dans une heure : si c'est passager, dis-le sans alarmer.", rang=0)
    elif rb["statut"] == 404:
        OK.append("Pas de robots.txt (404) : Google explore tout le site, c'est permis.")
    elif rb["statut"] == 200 and rb["html"]:
        c(1, "robots-html", "robots.txt renvoie une page HTML",
          "`/robots.txt` répond 200 avec une page web au lieu d'un fichier texte : Google n'y trouve aucune règle et "
          "aucun sitemap.", [], "Sers un vrai fichier texte à `/robots.txt` (souvent une route attrape-tout du site "
          "qui passe devant).", "Si le code du site est dans le dossier courant, trouve la route qui intercepte.")
    if rb["tout_bloque"]:
        c(1, "robots-tout", "robots.txt interdit tout le site à Google",
          "La règle `Disallow: /` s'applique à Googlebot : aucune page ne peut être explorée.", [],
          "Retire `Disallow: /` (souvent un reste de la préproduction).",
          "Presque toujours un oubli de mise en ligne : confirme avec l'utilisateur, c'est la correction n° 1.", rang=0)
    elif regles:
        bloq = []
        for u in sm:
            permis, motif = net.autorise(regles, u)
            if not permis and interne(u):
                bloq.append(f"{k(u)} : bloquée par `Disallow: {motif}`")
        if bloq:
            c(1, "robots-bloque", f"robots.txt bloque {pluriel(len(bloq), 'page')} du sitemap",
              "Le sitemap présente ces pages à Google, robots.txt lui interdit de les lire : il ne peut ni les "
              "explorer, ni voir leur contenu.", bloq,
              "Retire la règle qui les bloque, ou retire ces pages du sitemap si elles doivent rester fermées. Pour "
              "garder une page hors de Google, c'est `noindex`, pas robots.txt (Google doit pouvoir lire la page pour "
              "voir le `noindex`).", "Volontaire ou pas ? Une règle large (`/blog`, `/*?`) attrape souvent plus que prévu.")
        ass = [x["url"] for x in A["assets"] if interne(x["url"]) and not net.autorise(regles, x["url"])[0]]
        if ass:
            c(1, "robots-assets", f"robots.txt bloque {pluriel(len(ass), 'fichier')} CSS ou JavaScript",
              "Google a besoin du CSS et du JavaScript pour voir la page comme un visiteur.", [k(u) for u in ass],
              "Retire les règles `Disallow` qui touchent les dossiers de CSS et JS.", "")
        if sm and not any("Disallow" in x[0] for x in []) and not bloq:
            OK.append(f"robots.txt n'interdit aucune des {len(sm)} URL du sitemap.")
    elif rb["statut"] == 200:
        OK.append("robots.txt n'a aucune règle d'interdiction : tout est ouvert.")
    if rb["statut"] == 200 and not rb["html"] and sitemap and not rb["sitemaps"]:
        trouve = next((f["url"] for f in A["sitemap_fichiers"] if f["statut"] == 200), "")
        c(1, "robots-sans-sitemap", "robots.txt ne donne pas l'adresse du sitemap",
          "Le sitemap existe, mais robots.txt ne le cite pas : Google et les autres moteurs le trouvent moins vite.",
          [], f"Ajoute une ligne à robots.txt : `Sitemap: {trouve}`.",
          "Sans urgence si le sitemap est déjà déclaré dans Search Console.")

    fich = A["sitemap_fichiers"]
    if not sitemap:
        essais = ", ".join(f"`{court(f['url'], hote)}` ({f['statut'] or f['erreur']}"
                           f"{', page HTML' if f['genre'] == 'html' else ''})" for f in fich) or "aucun"
        c(1, "sitemap-absent", "Pas de sitemap lisible",
          f"Aucun sitemap n'a donné d'URL. Adresses essayées : {essais}.", [],
          "Publie un sitemap XML (la plupart des CMS et frameworks le font en un réglage ou un module), cite-le dans "
          "robots.txt (`Sitemap: https://…/sitemap.xml`) et déclare-le dans Search Console (Sitemaps).",
          "Sur un site neuf, c'est la première correction : sans sitemap ni liens, Google trouve les pages au hasard.",
          rang=0)
    else:
        mauvais = [f for f in fich if f["statut"] != 200 or f["genre"] in ("html", "illisible")]
        if mauvais:
            c(1, "sitemap-illisible", f"{pluriel(len(mauvais), 'fichier')} sitemap illisible(s)",
              "Un sitemap qui répond une erreur ou une page HTML est ignoré par Google, sans alerte visible.",
              [f"`{court(f['url'], hote)}` : {f['statut'] or f['erreur']}"
               f"{', page HTML au lieu de XML' if f['genre'] == 'html' else ''}"
               f"{', contenu illisible' if f['genre'] == 'illisible' else ''}" for f in mauvais],
              "Fais répondre chaque sitemap en XML (en-tête `Content-Type: application/xml`), ou retire-le de "
              "robots.txt et de Search Console.", "")
        dehors = [e for e in sitemap if hote_de(e["url"]) != hote]
        if dehors:
            c(1, "sitemap-hors", f"{pluriel(len(dehors), 'URL', 'URL')} du sitemap hors de {hote}",
              f"Le site répond sur `{hote}`, mais le sitemap liste des URL d'un autre hôte ou en http : Google ne "
              "les prend pas pour ce site, ou suit une redirection à chaque fois.", [f"`{e['loc']}`" for e in dehors],
              f"Écris toutes les URL du sitemap en `https://{hote}/…`, exactement comme l'URL finale des pages.", "")
        if A["sitemap_doublons"]:
            c(1, "sitemap-doublons", f"{pluriel(len(A['sitemap_doublons']), 'URL', 'URL')} en double dans le sitemap",
              "La même URL apparaît plusieurs fois.", [f"`{u}`" for u in A["sitemap_doublons"]],
              "Dédoublonne la génération du sitemap.", "Sans gravité, mais souvent le signe de deux sources de pages.")
        redir, err = [], []
        for u in sm:
            r = R.get(u)
            if not r:
                continue
            if r["chaine"]:
                redir.append(f"{k(u)} → {k(r['url_finale'])} ({r['chaine'][0][1]})")
            elif r["statut"] != 200:
                err.append(f"{k(u)} : {r['statut'] or r['erreur']}")
        if err:
            c(1, "sitemap-erreurs", f"{pluriel(len(err), 'URL', 'URL')} du sitemap en erreur",
              "Le sitemap présente à Google des pages qui n'existent pas (ou plus).", err,
              "Retire-les du sitemap ; si la page a été déplacée, redirige l'ancienne URL (301) vers la nouvelle.",
              "Un 0 (pas de réponse) ou un 5xx peut être passager : relance avant de corriger.")
        if redir:
            c(1, "sitemap-redirections", f"{pluriel(len(redir), 'URL', 'URL')} du sitemap redirigent",
              "Un sitemap ne doit lister que des URL finales : chaque redirection envoie un signal contradictoire "
              "(« cette URL » puis « non, celle-là »).", redir,
              "Remplace chaque URL par sa destination finale dans le sitemap.",
              "Souvent un slash final ou http/https : une seule règle dans le générateur corrige tout.")
        ni_sm = [u for u in sm if noindex(u)]
        can_sm = [f"{k(u)} → canonique {k(canon(u))}" for u in sm if canon(u) and canon(u) != u and not noindex(u)]
        if can_sm:
            c(1, "sitemap-canoniques", f"{pluriel(len(can_sm), 'URL', 'URL')} du sitemap déclarent une autre page comme canonique",
              "Le sitemap dit « indexe celle-ci », la page dit « c'est l'autre qui compte » : le sitemap ne doit lister "
              "que les URL canoniques.", can_sm,
              "Mets dans le sitemap l'URL que la canonique désigne (ou corrige la canonique si c'est elle qui a tort).", "")
        lues = [u for u in sm if u in R]
        if lues and not err and not redir and not ni_sm and not can_sm and not dehors:
            OK.append(f"Les {len(lues)} URL lues du sitemap répondent 200, sans redirection, indexables et canoniques.")
        absentes = [u for u in indexables if u not in sm_set and interne(u)]
        if absentes:
            c(1, "sitemap-incomplet", f"{pluriel(len(absentes), 'page')} trouvée(s) par les liens, absente(s) du sitemap",
              "Ces pages répondent 200, sont indexables et liées depuis le site, mais le sitemap ne les liste pas.",
              [f"{k(u)} : citée dans {pluriel(len(ent_t.get(u, ())), 'phrase')}, {len(ent_b.get(u, ()))} bloc(s) de "
               f"liens, {len(ent_n.get(u, ()))} lien(s) de navigation" for u in absentes],
              "Ajoute-les au sitemap si elles doivent être dans Google ; sinon passe-les en `noindex`.",
              "Regarde ce que sont ces pages : des pages de tags ou de pagination peuvent rester hors sitemap, une vraie "
              "page de contenu non.")
    gs = A["gsc"]
    if A["propriete"] and gs.get("sitemaps") is not None and not any("sitemaps" in e for e in gs["erreurs"]):
        declares = {lec.normaliser(s["path"] or "") for s in gs["sitemaps"]}
        nos = {lec.normaliser(f["url"]) for f in fich if f["statut"] == 200}
        if sitemap and not (declares & nos):
            c(1, "gsc-sitemap", "Le sitemap n'est pas déclaré dans Search Console",
              "Search Console ne connaît aucun des sitemaps que le site publie"
              + (f" (il connaît : {', '.join('`' + s['path'] + '`' for s in gs['sitemaps'])})." if gs["sitemaps"] else "."),
              [], "Dans Search Console : Indexation > Sitemaps, colle l'adresse du sitemap, Envoyer.",
              "Sur un site neuf, c'est ce qui fait venir Google le plus vite.", rang=5)
        for s in gs["sitemaps"]:
            if s["errors"] or s["warnings"]:
                c(1, "gsc-sitemap-erreurs", "Search Console signale des erreurs dans un sitemap",
                  f"`{s['path']}` : {s['errors']} erreur(s), {s['warnings']} avertissement(s), lu le "
                  f"{(s['lastDownloaded'] or '?')[:10]}.", [], "Ouvre le rapport Sitemaps de Search Console pour le détail.", "")
        lus = [s for s in gs["sitemaps"] if s["path"] and lec.normaliser(s["path"]) in nos]
        if lus:
            OK.append("Sitemap déclaré dans Search Console : " + ", ".join(
                f"`{court(s['path'], hote)}` lu le {(s['lastDownloaded'] or 'jamais')[:10]}" for s in lus) + ".")

    ni = [u for u in sorted(rows) if rows[u]["noindex"] == "oui"]
    if ni:
        n_sm = sum(1 for u in ni if u in sm_set)
        c(1, "noindex", f"{pluriel(len(ni), 'page')} en noindex" + ("" if n_sm else ", hors sitemap"),
          "Ces pages demandent à Google de ne pas les garder." +
          (f" {n_sm} d'entre elles sont pourtant dans le sitemap : deux consignes contraires." if n_sm else
           " Aucune n'est dans le sitemap : la consigne est cohérente, reste à savoir si elle est voulue."),
          [f"{k(u)} : {'dans le sitemap' if u in sm_set else 'hors sitemap'}, "
           f"{'en-tête X-Robots-Tag' if 'noindex' in rows[u]['x_robots_tag'].lower() else 'balise meta robots'}"
           for u in ni],
          ("Si c'est voulu (pages de tags, remerciement, compte), retire-les du sitemap. Sinon, retire la balise "
           "`noindex` (ou l'en-tête `X-Robots-Tag`).") if n_sm else
          "Si c'est voulu (pages de tags, remerciement, compte), rien à faire. Sinon, retire la balise `noindex`.",
          "Volontaire ou oubli ? Une page de contenu en noindex est presque toujours un oubli (réglage du CMS, reste de "
          "préproduction) ; des pages de tags ou de pagination en noindex, c'est un choix courant. Dis lesquelles "
          "sont normales.", rang=20 if n_sm else 90)
    else:
        OK.append(f"Aucune page en noindex parmi les {len(html)} lues.")

    autres, incoh, multi = [], [], []
    for u in html:
        cu = canon(u)
        if rows.get(u, {}).get("nb_canoniques", 0) and rows[u]["nb_canoniques"] > 1:
            multi.append(f"{k(u)} : {rows[u]['nb_canoniques']} balises canonical")
        if not cu or cu == u or noindex(u):
            continue
        r = R.get(cu)
        if hote_de(cu) not in hotes:
            incoh.append(f"{k(u)} → `{cu}` (autre site)")
        elif cu.startswith("http://") and u.startswith("https://"):
            incoh.append(f"{k(u)} → `{cu}` (en http)")
        elif r and (r["chaine"] or r["statut"] != 200):
            etat = f"redirige vers {k(r['url_finale'])}" if r["chaine"] else f"répond {r['statut'] or r['erreur']}"
            incoh.append(f"{k(u)} → {k(cu)}, qui {etat}")
        elif noindex(cu):
            incoh.append(f"{k(u)} → {k(cu)}, qui est en noindex")
        else:
            autres.append(f"{k(u)} → {k(cu)}")
    if incoh:
        c(1, "canonique-incoherente", f"{pluriel(len(incoh), 'canonique')} incohérente(s)",
          "La canonique désigne une URL qui redirige, répond une erreur, est en noindex ou sur un autre hôte : Google "
          "ignore alors la consigne et choisit seul.", incoh,
          "Fais pointer chaque canonique vers l'URL finale, en 200, indexable (souvent la page elle-même).",
          "Souvent le slash final ou http : une règle du gabarit corrige toutes les pages.")
    if autres:
        c(1, "canonique-autre", f"{pluriel(len(autres), 'page')} désignent une autre page comme canonique",
          "Ces pages disent à Google « ne me garde pas, garde l'autre ».", autres,
          "Si les deux pages sont différentes, mets une canonique vers elle-même sur chacune.",
          "Volontaire (deux versions d'un même contenu) ou erreur de gabarit (toutes les pages vers l'accueil) ?")
    if multi:
        c(1, "canonique-multiple", f"{pluriel(len(multi), 'page')} avec plusieurs balises canonical",
          "Deux canoniques sur une page : Google les ignore toutes.", multi,
          "Garde une seule balise `<link rel=\"canonical\">` (souvent un plugin SEO et le thème qui en posent chacun une).", "")
    if not incoh and not autres and not multi and html:
        n_can = sum(1 for u in html if canon(u))
        if n_can:
            OK.append(f"Canoniques cohérentes : {n_can} pages sur {len(html)} en déclarent une, toutes vers elles-mêmes.")

    hl_pages = [u for u in html if rows[u]["hreflang"]]
    if hl_pages:
        pb = []
        for u in hl_pages:
            couples = [x.split("=", 1) for x in rows[u]["hreflang"].split()]
            cibles = {lec.normaliser(h) for _, h in couples if h}
            for code, h in couples:
                if not HREFLANG.match(code):
                    pb.append(f"{k(u)} : code `{code}` invalide (ex. `fr`, `fr-FR`, `en-GB`, `x-default`)")
                r = R.get(lec.normaliser(h)) if h else None
                if r and (r["chaine"] or r["statut"] != 200):
                    pb.append(f"{k(u)} : `{code}` pointe vers {k(h)}, qui répond {r['statut'] if not r['chaine'] else 'par une redirection'}")
            if u not in cibles:
                pb.append(f"{k(u)} : ne se cite pas elle-même dans ses hreflang")
            for h in cibles:
                if h in rows and rows[h]["hreflang"] and u not in {lec.normaliser(x.split('=', 1)[1]) for x in rows[h]["hreflang"].split() if '=' in x}:
                    pb.append(f"{k(u)} → {k(h)} : pas de lien retour")
        if pb:
            c(1, "hreflang", f"{pluriel(len(pb), 'erreur')} de hreflang",
              f"{len(hl_pages)} pages déclarent des versions dans d'autres langues ; une paire sans lien retour ou "
              "vers une URL qui n'est pas en 200 est ignorée par Google.", pb,
              "Chaque version cite toutes les autres et elle-même, avec des URL finales en 200.", "")
        else:
            OK.append(f"hreflang cohérents sur {len(hl_pages)} pages (auto-référence et liens retour).")

    # Search Console
    if A["propriete"]:
        ins = [i for i in gs["inspections"] if i["categorie"] != "erreur"]
        cat = Counter(i["categorie"] for i in ins)

        def ligne_insp(i):
            et = len(ent_t.get(i["url"], ()))
            crawl = f", dernier passage {i['dernier_crawl']}" if i["dernier_crawl"] else ""
            return f"{k(i['url'])} : « {i['couverture']} »{crawl}, citée dans {pluriel(et, 'phrase')} du site"

        for cle, titre, fait, corr, claude in (
            ("explorée", "« explorée, actuellement non indexée »",
             "Google est passé sur ces pages et a choisi de ne pas les garder. C'est le seul motif du rapport Pages "
             "qui mérite qu'on creuse.",
             "Pour chacune : apporte-t-elle quelque chose que tes autres pages n'ont pas ? Si oui, donne-lui 2 ou 3 liens "
             "dans le texte depuis tes pages les plus vues et étoffe-la ; si non, fusionne-la avec la page voisine "
             "(redirection 301).",
             "Lis chaque page (mots et liens entrants dans pages.csv) : contenu mince, doublon d'une autre page, ou trop "
             "neuve ? Une page passée il y a moins de deux semaines peut encore entrer."),
            ("détectée", "« détectée, actuellement non indexée »",
             "Google connaît ces URL mais ne les a pas encore explorées.",
             "Sur un site neuf, c'est la file d'attente : ajoute des liens dans le texte vers elles depuis des pages déjà "
             "indexées, puis attends. Sur un site établi, beaucoup de « détectée » veut dire que Google juge que le site "
             "ne mérite pas plus d'exploration : moins de pages, meilleures.",
             "Site neuf ou établi ? Dis lequel, et si ces pages ont des liens dans le texte (dernier chiffre de chaque ligne)."),
            ("inconnue", "inconnues de Google",
             "Google n'a jamais vu ces URL, alors qu'elles sont dans ton sitemap ou sur ton site.",
             "Vérifie que le sitemap est déclaré dans Search Console et lu récemment ; ajoute des liens dans le texte "
             "depuis des pages indexées ; puis « Demander l'indexation » dans l'outil d'inspection de Search Console "
             "(quelques URL par jour).",
             "Regarde le nombre de liens dans le texte de chaque page : une page inconnue sans lien entrant, c'est le "
             "maillage qu'il faut corriger d'abord."),
        ):
            liste = [i for i in ins if i["categorie"] == cle]
            if liste:
                c(1, "gsc-" + cle, f"{pluriel(len(liste), 'page')} {titre}", fait, [ligne_insp(i) for i in liste], corr,
                  claude, rang=10)
        dif = []
        for i in ins:
            gc, uc = i["canonique_google"], i["canonique_declaree"]
            if gc and uc and lec.normaliser(gc) != lec.normaliser(uc):
                dif.append(f"{k(i['url'])} : tu déclares {k(uc)}, Google garde {k(gc)}")
        if dif:
            c(1, "gsc-canonique", f"Google a choisi une autre canonique que la tienne sur {pluriel(len(dif), 'page')}",
              "Google n'est pas d'accord sur l'URL à garder : il indexe une autre version que celle que tu déclares.",
              dif,
              "Aligne tout sur la même URL : canonique, sitemap, liens internes. Une URL à paramètres choisie par Google "
              "(`?src=`, `?utm_`) se corrige en retirant ces paramètres des liens du site et en redirigeant (301) "
              "l'URL à paramètres vers l'URL propre si elle n'a pas d'autre usage.",
              "Le piège classique : un lien partagé avec `?src=` reçoit plus de liens que l'URL propre, et Google le "
              "prend comme canonique. Dis d'où viennent ces URL si tu le sais.", rang=15)
        reste = [i for i in ins if i["categorie"] in ("noindex", "canonique", "introuvable", "redirection", "soft 404",
                                                       "bloquée par robots.txt", "autre")
                 and i["pourquoi"] != "vue par Google, hors sitemap"]
        if reste:
            c(1, "gsc-autres", f"{pluriel(len(reste), 'page')} hors index pour un autre motif",
              "Motifs donnés par Search Console. Une page en noindex voulu, ou « autre page avec balise canonique "
              "correcte », c'est normal : Google applique ta consigne.",
              [f"{k(i['url'])} ({i['pourquoi']}) : « {i['couverture']} »" for i in reste],
              "Ne corrige que les pages que tu veux voir dans Google : une URL du sitemap qui n'est pas la canonique "
              "sort du sitemap ; une ancienne URL en 404 se redirige (301) vers la page qui la remplace.",
              "Trie : normal (consigne appliquée) ou à corriger ?", rang=60)
        a_soi = [i for i in ins if i["pourquoi"] != "vue par Google, hors sitemap"]
        n_idx = sum(1 for i in a_soi if i["categorie"] == "indexée")
        if a_soi and n_idx == len(a_soi):
            OK.append(f"Les {len(a_soi)} pages inspectées (accueil et sitemap) sont indexées par Google.")
        elif a_soi:
            OK.append(f"{n_idx} pages indexées sur {len(a_soi)} inspectées (accueil et sitemap).")
        hors = [p for p in gs["pages_google"] if hote_de(p["url"]) in hotes and p["url"] not in sm_set
                and p["url"] != accueil]
        if hors:
            def motif(p):
                u = p["url"]
                if lec.sans_suivi(u)[1]:
                    return "paramètres de suivi"
                if hote_de(u) != hote:
                    return f"autre hôte ({hote_de(u)})"
                if u.startswith("http://") and accueil.startswith("https://"):
                    return "en http"
                if "?" in u:
                    return "URL à paramètres"
                r = R.get(u)
                if r and r["chaine"]:
                    return f"redirige vers {k(r['url_finale'])}"
                if r and r["statut"] != 200:
                    return f"répond {r['statut']}"
                return "page hors sitemap"

            def google(p):
                i = insp.get(p["url"])
                return f" ; Search Console : « {i['couverture']} »" if i and i["couverture"] else ""
            normal = all(lec.sans_suivi(p["url"])[1] and insp.get(p["url"], {}).get("categorie") == "canonique"
                         for p in hors)
            c(1, "gsc-hors-sitemap", f"Google montre {pluriel(len(hors), 'URL', 'URL')} qui ne sont pas dans ton sitemap",
              f"Pages apparues dans les résultats de Google ({gs['fenetre'][0]} → {gs['fenetre'][1]}) sans être dans le "
              "sitemap.",
              [f"{k(p['url'])} : {pluriel(p['impressions'], 'impression')}, {pluriel(p['clics'], 'clic')}, {motif(p)}"
               f"{google(p)}" for p in hors],
              "Une ancienne URL : redirection 301 vers la page qui la remplace. Une URL à paramètres : canonique propre et "
              "liens internes sans paramètres (Google garde alors l'URL propre : « autre page avec balise canonique "
              "correcte », c'est le bon résultat). Une vraie page oubliée : ajoute-la au sitemap.",
              "Trie les lignes par motif et dis ce qui est normal (une URL de campagne que Google rattache à la page "
              "propre, une page de tags) et ce qui est à corriger.", rang=70 if normal else 40)

    # ===== 2. Maillage dans le texte =====
    cand = [u for u in indexables if u != accueil and interne(u)]
    legales = [u for u in cand if LEGALE.search(urllib.parse.urlsplit(u).path)]
    contenu = [u for u in cand if u not in legales]
    et = {u: len(ent_t.get(u, ())) for u in cand}
    eb = {u: len(ent_b.get(u, ())) for u in cand}
    en = {u: len(ent_n.get(u, ())) for u in cand}
    st = {u: len(sor_t.get(u, ())) for u in cand}
    sb = {u: len(sor_b.get(u, ())) for u in cand}

    def g_(u):
        i = insp.get(u)
        return f", Google : {i['categorie']}" if i else ""

    def detail(u):
        return f"{eb[u]} bloc(s) de liens, {en[u]} lien(s) de navigation{g_(u)}"

    orph = [u for u in contenu if et[u] == 0 and eb[u] == 0 and en[u] == 0]
    sans_phrase = [u for u in contenu if et[u] == 0 and (eb[u] or en[u])]
    un = [u for u in contenu if et[u] == 1]
    imp = [u for u in contenu if st[u] == 0 and sb[u] == 0]
    med = statistics.median([et[u] for u in contenu]) if contenu else 0
    if orph:
        c(2, "orphelines", f"{pluriel(len(orph), 'page')} sans aucun lien interne",
          "Aucune page lue ne pointe vers elles : Google ne les trouve que par le sitemap et ne leur donne aucun poids.",
          [f"{k(u)}{' (dans le sitemap)' if u in sm_set else ''}{g_(u)}" for u in orph],
          "Ajoute 2 ou 3 liens dans le texte depuis des pages du même sujet, avec un texte de lien qui dit de quoi parle "
          "la page.",
          "Pour chaque page, propose les 2 ou 3 pages sources les plus proches par le sujet (titres dans pages.csv) et "
          "la phrase où poser le lien. La skill `internal-links` fait ce travail en détail.")
    if sans_phrase:
        c(2, "sans-phrase", f"{pluriel(len(sans_phrase), 'page')} citée(s) dans aucune phrase du site",
          "Elles ont des liens, mais seulement dans le menu, le pied de page ou des blocs de cartes (« à lire aussi », "
          "grilles). Un lien de menu dit « cette page existe » ; un lien dans une phrase dit « cette page répond à "
          "ça », avec les mots du lien.",
          [f"{k(u)} : 0 phrase, {detail(u)}" for u in sorted(sans_phrase, key=lambda x: (eb[x] + en[x], x))],
          "Cite chacune dans le texte d'au moins 2 pages proches par le sujet, avec un texte de lien qui dit ce qu'on y "
          "trouve.",
          "Lesquelles comptent (un guide, une page outil) et lesquelles peuvent rester au menu (contact, à propos) ? "
          "Propose pour les premières la page source et la phrase.")
    if un:
        c(2, "une-phrase", f"{pluriel(len(un), 'page')} citée(s) dans une seule phrase du site",
          f"Une seule porte d'entrée depuis le texte. Pour comparer : la médiane du site est de {nb(med)} page(s) qui "
          f"citent une page dans une phrase ({len(contenu)} pages de contenu).",
          [f"{k(u)} : citée par {k(next(iter(ent_t[u])))}, {detail(u)}" for u in un],
          "Ajoute un ou deux liens dans le texte depuis les pages voisines par le sujet.",
          "Commence par les pages qui comptent (celles qui doivent ranker ou vendre).")
    if imp:
        c(2, "impasses", f"{pluriel(len(imp), 'page')} sans aucun lien vers tes autres pages dans leur contenu",
          "Le lecteur (et Google) arrive et n'a nulle part où aller ensuite, sauf le menu.",
          [f"{k(u)} : {rows[u]['mots']} mots, 0 lien interne hors navigation" for u in imp],
          "Ajoute dans le texte 2 ou 3 liens vers les pages qui prolongent le sujet.",
          "Une page outil ou une page de vente peut s'en passer : dis lesquelles.")
    if legales:
        OK.append(f"{pluriel(len(legales), 'page légale', 'pages légales')} (mentions, confidentialité…) mise(s) à part du "
                  "maillage : il est normal qu'elles ne soient liées que du pied de page.")
    if contenu and not orph and not sans_phrase:
        OK.append(f"Chacune des {len(contenu)} pages de contenu est citée dans au moins une phrase d'une autre page "
                  f"(médiane : {nb(med)}).")
    elif contenu:
        OK.append(f"Médiane : chaque page de contenu est citée dans une phrase de {nb(med)} autre(s) page(s) "
                  f"({len(contenu)} pages de contenu).")
    if A["casses"]:
        uniq = sorted({(s, cible, st_, t) for s, cible, st_, t in A["casses"]})
        c(2, "casses-internes", f"{pluriel(len({x[1] for x in uniq}), 'lien')} interne(s) cassé(s)",
          f"Liens de ton site vers des pages qui répondent une erreur ({len(uniq)} occurrences).",
          [f"{k(s)} → {k(cible)} ({st_ or 'pas de réponse'}) « {t[:60]} »" for s, cible, st_, t in uniq],
          "Corrige le lien vers la bonne URL, ou redirige l'ancienne URL (301) vers la page qui la remplace.",
          "Une cible sans réponse peut être passagère : relance avant de corriger.")
    else:
        n_int = sum(A["zones"].values())
        OK.append(f"Aucun lien interne cassé parmi {n_int} liens lus.")
    casses_ext, refus = [], []
    for u, d in A["externes"].items():
        s = d.get("statut")
        if s is None:
            continue
        if s in (404, 410) or (s == 0 and "DNS" in (d.get("erreur") or "")):
            casses_ext.append(f"`{u}` : {s or d['erreur']} ({pluriel(d['occurrences'], 'lien')})")
        elif s in (401, 403, 429, 999) or s >= 500 or s == 0:
            refus.append(u)
    if casses_ext:
        c(2, "casses-externes", f"{pluriel(len(casses_ext), 'lien')} externe(s) cassé(s)",
          f"Sur un échantillon de {A['externes_testes']} liens vers d'autres sites (les plus fréquents), ceux-ci "
          "mènent à une page disparue.", casses_ext,
          "Remplace par la nouvelle adresse de la ressource, ou retire le lien.",
          "Ouvre une ou deux de ces URL pour confirmer, puis propose la nouvelle adresse quand elle se devine."
          + (f" {len(refus)} autre(s) site(s) ont refusé la vérification (403, 429…) : ce n'est pas une panne, ne "
             "les compte pas." if refus else ""))
    elif A["externes_testes"]:
        OK.append(f"Aucun lien externe cassé sur un échantillon de {A['externes_testes']}"
                  + (f" ({len(refus)} sites ont refusé la vérification, ce n'est pas une panne)." if refus else "."))
    if A["suivi_internes"]:
        u_ = sorted({(s, cible, " ".join(p)) for s, cible, p in A["suivi_internes"]})
        c(2, "suivi-internes", f"{pluriel(len(u_), 'lien')} interne(s) avec paramètres de suivi",
          "Des liens de ton site vers ton site portent `?utm_…`, `?src=…` ou `?ref=…`. Google les suit comme des URL "
          "distinctes, et peut finir par en prendre une comme canonique.",
          [f"{k(s)} → {k(cible)}" for s, cible, _ in u_],
          "Retire les paramètres des liens internes ; garde-les pour les liens que tu partages ailleurs (réseaux, "
          "newsletter).", "")

    # ===== 3. Fondamentaux =====
    if accueil.startswith("http://"):
        c(3, "https", "Le site n'est pas servi en HTTPS",
          f"L'accueil finit sur `{accueil}`. Chrome marque le site « non sécurisé » et Google préfère HTTPS.", [],
          "Active HTTPS chez ton hébergeur (gratuit presque partout), puis redirige http vers https (301).", "")
    else:
        if A["accueil_reponse"]["hsts"]:
            OK.append("HTTPS, avec l'en-tête HSTS (le navigateur ne repasse jamais par http).")
        else:
            c(3, "hsts", "Pas d'en-tête HSTS",
              "HTTPS fonctionne, mais sans `Strict-Transport-Security` : un visiteur qui tape l'adresse en http passe par "
              "une redirection à chaque fois.", [],
              "Ajoute l'en-tête `Strict-Transport-Security: max-age=31536000` (un réglage chez la plupart des hébergeurs).",
              "Faible priorité : à faire si c'est un clic chez l'hébergeur.")
    for v, d in A["variantes"].items():
        if not d:
            continue
        vh, vs = hote_de(v), urllib.parse.urlsplit(v).scheme
        if d["statut"] == 0:
            if vh != hote and "DNS" in (d["erreur"] or ""):
                OK.append(f"`{vh}` n'existe pas : rien à rediriger.")
            elif vs == "http":
                OK.append(f"`{v}` ne répond pas ({d['erreur']}) : acceptable, les navigateurs passent en https.")
            else:
                c(3, "variante", f"`{v}` ne répond pas", f"{d['erreur']}. Un visiteur qui tape cette adresse tombe sur une erreur.",
                  [], f"Redirige `{v}` vers `{accueil}` (301), ou retire l'entrée DNS.", "")
            continue
        fin = d["finale"]
        if fin == accueil:
            if len(d["chaine"]) > 1:
                c(3, "chaine", f"`{v}` arrive à l'accueil en {len(d['chaine'])} redirections",
                  "Chaque saut coûte un aller-retour : une seule redirection suffit.",
                  [" → ".join(f"`{x[0]}` ({x[1]})" for x in d["chaine"]) + f" → `{fin}`"],
                  f"Redirige `{v}` directement vers `{accueil}`.", "")
            else:
                code = d["chaine"][0][1] if d["chaine"] else ""
                OK.append(f"`{v}` redirige vers l'accueil en une fois ({code}).")
                if code in (302, 307):
                    c(3, "redir-temporaire", f"`{v}` redirige en {code} (temporaire)",
                      "Une redirection temporaire dit à Google que l'ancienne adresse va revenir.", [],
                      "Passe-la en 301 (ou 308).", "")
        elif d["statut"] == 200 and not d["chaine"]:
            ok_can = d.get("canonique") and lec.normaliser(urllib.parse.urljoin(v, d["canonique"])).startswith(accueil.rstrip("/"))
            c(3, "doublon-site", f"`{v}` répond sans rediriger",
              "Le site existe en deux exemplaires : Google peut indexer l'un ou l'autre, et les liens se partagent."
              + (" Sa canonique pointe vers la bonne version, ce qui limite les dégâts." if ok_can else ""),
              [], f"Redirige `{v}` vers `{accueil}` (301), sur tout le site, chemin compris.", "")
        else:
            c(3, "variante", f"`{v}` finit ailleurs que sur l'accueil",
              f"Elle arrive sur `{fin}` ({d['statut'] or d['erreur']}).", [],
              f"Redirige `{v}` vers `{accueil}` (301).", "")
    ix = A["inexistante"]
    if ix.get("statut") == 200 and not ix.get("chaine"):
        c(3, "soft404", "Une page qui n'existe pas répond 200",
          f"`{court(ix['url'], hote)}` répond 200 au lieu de 404 : Google peut prendre des URL bidon pour des pages, et "
          "les signale comme « soft 404 ».", [],
          "Fais répondre 404 aux URL inconnues (la page d'erreur peut rester jolie, c'est le code qui compte).", "")
    elif ix.get("chaine") and lec.normaliser(ix.get("finale", "")) == accueil:
        c(3, "soft404", "Une page qui n'existe pas redirige vers l'accueil",
          f"`{court(ix['url'], hote)}` redirige vers l'accueil : Google traite ça comme une « soft 404 » et le visiteur ne "
          "comprend pas où il est.", [], "Fais répondre 404 aux URL inconnues, avec des liens utiles sur la page d'erreur.", "")
    elif ix.get("statut") in (404, 410):
        OK.append(f"Une URL inexistante répond bien {ix['statut']}.")
    sl = A.get("slash")
    if sl and sl.get("statut") is not None:
        if sl["statut"] == 200 and not sl["chaine"]:
            can = lec.normaliser(urllib.parse.urljoin(sl["variante"], sl["canonique"])) if sl.get("canonique") else ""
            if can == sl["exemple"]:
                OK.append(f"`{court(sl['variante'], hote)}` répond aussi, mais sa canonique pointe vers `{court(sl['exemple'], hote)}` : acceptable.")
            else:
                c(3, "slash", "Deux URL pour la même page (slash final)",
                  f"`{court(sl['exemple'], hote)}` et `{court(sl['variante'], hote)}` répondent toutes les deux 200, sans "
                  "canonique qui les départage.", [],
                  "Choisis une forme (avec ou sans slash final) et redirige l'autre en 301, sur tout le site.", "")
        elif sl["chaine"] and sl["finale"] == sl["exemple"]:
            OK.append(f"Slash final cohérent : `{court(sl['variante'], hote)}` redirige vers `{court(sl['exemple'], hote)}`.")
        elif sl["statut"] in (404, 410):
            OK.append(f"Slash final strict : `{court(sl['variante'], hote)}` répond {sl['statut']}.")
    if A["vers_redirections"]:
        u_ = sorted({(cible, fin) for _, cible, fin in A["vers_redirections"]})
        par_cible = Counter(cible for _, cible, _ in A["vers_redirections"])
        c(3, "liens-redirection", f"{pluriel(len(u_), 'lien')} interne(s) passent par une redirection",
          f"{len(A['vers_redirections'])} liens du site pointent vers une URL qui redirige.",
          [f"{k(cible)} → {k(fin)} ({pluriel(par_cible[cible], 'lien')})" for cible, fin in u_],
          "Fais pointer chaque lien directement vers l'URL finale.",
          "Sans urgence si c'est un slash final : chaque lien coûte un aller-retour de plus.")
    mixte = []
    if accueil.startswith("https://"):
        for u in html:
            n = sum(1 for im in pages[u]["page"]["images"] if im["src"].startswith("http://")) + \
                sum(1 for _, x in pages[u]["page"]["assets"] if x.startswith("http://"))
            if n:
                mixte.append(f"{k(u)} : {pluriel(n, 'ressource')} en http")
    if mixte:
        c(3, "mixte", f"{pluriel(len(mixte), 'page')} chargent des ressources en http",
          "Une page https qui charge une image ou un script en http : le navigateur la bloque ou la marque non sûre.",
          mixte, "Passe ces adresses en https.", "")
    tt = sorted((rows[u]["ttfb_ms"], u) for u in html if isinstance(rows.get(u, {}).get("ttfb_ms"), int))
    if tt:
        med_t = statistics.median(t for t, _ in tt)
        lents = [(t, u) for t, u in tt if t > TTFB_LENT]
        if lents:
            c(3, "lent", f"{pluriel(len(lents), 'page')} répondent en plus de {TTFB_LENT} ms",
              f"Temps avant le premier octet, mesuré une fois depuis cet ordinateur (médiane du site : {nb(med_t)} ms, "
              f"{len(tt)} pages).", [f"{k(u)} : {t} ms" for t, u in sorted(lents, reverse=True)],
              "Mets les pages en cache (CDN, génération statique) ; un serveur qui calcule chaque page à la demande est "
              "souvent la cause.",
              "Lent sur la moitié des pages : vrai signal. Sur une page isolée : peut-être un hasard, relance avant de conclure.")
        else:
            OK.append(f"Serveur rapide : médiane {nb(med_t)} ms avant le premier octet ({len(tt)} pages, mesuré d'ici).")
    lh = A["lighthouse"]
    lhp = [p for p in lh.get("pages", []) if "performance" in p]
    if lhp:
        mauvais = [p for p in lhp if p["lcp_ms"] > LCP_BON or p["cls"] > CLS_BON or p["tbt_ms"] > TBT_BON]
        if mauvais:
            c(3, "lighthouse", f"Lighthouse : {pluriel(len(mauvais), 'page')} au-delà des seuils sur mobile",
              f"Mesure de laboratoire sur un téléphone simulé (seuils : LCP {nb(LCP_BON / 1000)} s, CLS {nb(CLS_BON)}, TBT "
              f"{TBT_BON} ms). Ce n'est pas ce que vivent tes visiteurs (ça, c'est le rapport Core Web Vitals de "
              "Search Console), mais un écart net se retrouve chez eux.",
              [f"{k(p['url'])} : performance {p['performance']}/100, LCP {nb(p['lcp_ms'] / 1000, 1)} s, CLS {nb(p['cls'])}, "
               f"TBT {p['tbt_ms']} ms" for p in mauvais],
              "LCP lent : l'image du haut de page trop lourde ou chargée tard (pas de `loading=\"lazy\"` sur elle). CLS : "
              "donne `width` et `height` aux images. TBT : moins de JavaScript au chargement.",
              "Une mesure Lighthouse varie de 5 à 10 points d'un passage à l'autre : ne conclus que sur un écart net.")
        else:
            OK.append("Lighthouse mobile dans les seuils sur " + ", ".join(
                f"{k(p['url'])} ({p['performance']}/100, LCP {nb(p['lcp_ms'] / 1000, 1)} s)" for p in lhp) + ".")
        ech = sorted({(e, p["url"]) for p in lhp for e in p["echecs_seo"]})
        if ech:
            c(4, "lighthouse-seo", f"Lighthouse SEO : {pluriel(len(ech), 'contrôle')} en échec",
              "Contrôles SEO de base de Lighthouse qui échouent.", [f"{k(u)} : {e}" for e, u in ech],
              "Corrige chaque contrôle (le détail est dans le rapport Lighthouse de la page).", "")
    lourdes, anciennes = [], []
    for u, d in A["images"].items():
        if d.get("statut") != 200 or d.get("moderne"):
            continue
        if d.get("taille") and d["taille"] > IMAGE_LOURDE:
            lourdes.append((d["taille"], u, d["pages"]))
        if d.get("type") in ("image/jpeg", "image/png", "image/gif"):
            anciennes.append(u)
    if lourdes:
        c(3, "images-lourdes", f"{pluriel(len(lourdes), 'image')} de plus de {IMAGE_LOURDE // 1000} Ko",
          f"Sur {A['images_testees']} images vérifiées. Une image lourde ralentit l'affichage, surtout sur mobile.",
          [f"{k(u)} : {ko(t)}, sur {pluriel(n, 'page')}" for t, u, n in sorted(lourdes, key=lambda x: (-x[0], x[1]))],
          "Recompresse-les et sers-les en WebP ou AVIF, à la taille où elles s'affichent (pas plus de 2 fois la largeur "
          "affichée).", "Commence par celles de l'accueil et des pages les plus vues.")
    if len(anciennes) >= 3:
        c(3, "formats", f"{pluriel(len(anciennes), 'image')} en JPEG, PNG ou GIF sans version moderne",
          "WebP et AVIF pèsent 25 à 50 % de moins à qualité égale, et tous les navigateurs actuels les lisent.",
          [k(u) for u in sorted(anciennes)],
          "Convertis-les (ou active la conversion automatique de ton hébergeur ou de ton framework).",
          "Faible priorité si elles sont légères.")
    if A["images_testees"] and not lourdes:
        OK.append(f"Aucune image de plus de {IMAGE_LOURDE // 1000} Ko parmi {A['images_testees']} vérifiées.")
    cache_pb = []
    for x in A["assets"]:
        if not interne(x["url"]) or x.get("statut") != 200:
            continue
        cc = (x.get("cache") or "").lower()
        ma = max_age(cc)
        if not cc or "no-store" in cc or "no-cache" in cc or (ma is not None and ma < CACHE_MIN and "immutable" not in cc):
            cache_pb.append(f"{k(x['url'])} : `cache-control: {x.get('cache') or 'absent'}`")
    if cache_pb:
        c(3, "cache", f"{pluriel(len(cache_pb), 'fichier')} CSS ou JS sans cache long",
          "Le navigateur les retélécharge (ou redemande) à chaque visite.", cache_pb,
          "Donne aux fichiers versionnés (avec une empreinte dans le nom) `cache-control: public, max-age=31536000, "
          "immutable`.", "Si les noms n'ont pas d'empreinte, un cache long empêcherait les mises à jour : dis-le.")
    elif [x for x in A["assets"] if interne(x["url"])]:
        OK.append("CSS et JavaScript du site servis avec un cache long.")
    lm = [e["lastmod"] for e in sitemap]
    if sitemap:
        sans = sum(1 for x in lm if not x)
        futur = [e for e in sitemap if e["lastmod"][:10] > dt.date.today().isoformat()]
        if sans == len(lm):
            c(3, "lastmod", "Le sitemap ne donne aucune date (lastmod)",
              "Sans `lastmod`, Google ne sait pas quelles pages ont changé depuis son dernier passage.", [],
              "Fais écrire au générateur la date de dernière vraie modification de chaque page.",
              "Seulement la vraie date du contenu : une date qui change à chaque déploiement est pire que rien.")
        elif len(lm) >= 5 and len({x[:10] for x in lm if x}) == 1:
            c(3, "lastmod", f"Les {len(lm)} URL du sitemap ont la même date",
              f"Toutes en `{lm[0]}` : c'est la date de génération, pas celle des pages. Google finit par ignorer les "
              "dates de ce sitemap.", [],
              "Donne à chaque URL la date de sa dernière vraie modification.", "")
        elif futur:
            c(3, "lastmod", f"{pluriel(len(futur), 'URL', 'URL')} du sitemap datées dans le futur", "Google ignore ces dates.",
              [f"{k(e['url'])} : {e['lastmod']}" for e in futur], "Corrige la date dans le générateur.", "")
        else:
            OK.append(f"Le sitemap date ses URL ({len(lm) - sans} sur {len(lm)}, {len({x[:10] for x in lm if x})} dates différentes).")
    articles = [u for u in indexables if re.search(r"(Article|BlogPosting|NewsArticle|TechArticle)",
                                                     rows[u]["jsonld"]) and "dateModified" not in rows[u]["dates"]
                and "article:modified_time" not in rows[u]["dates"]]
    if articles:
        c(3, "dates-articles", f"{pluriel(len(articles), 'article')} sans date de mise à jour",
          "Ces pages se déclarent comme articles (JSON-LD) mais ne disent pas quand elles ont changé.",
          [k(u) for u in articles],
          "Ajoute `dateModified` au JSON-LD (et la date visible sur la page), mise à jour quand le contenu change.", "")
    sans_date = [u for u in indexables if not rows[u]["dates"] and u != accueil]
    if sans_date and len(sans_date) < len(indexables):
        c(3, "dates", f"{pluriel(len(sans_date), 'page')} sans aucune date déclarée",
          "Ni `dateModified`, ni `article:modified_time`, ni balise `<time>` dans le HTML.",
          [k(u) for u in sans_date],
          "Pour les articles et les guides : date de publication et de mise à jour, visibles et dans le JSON-LD.",
          "Utile pour les articles et les guides (Google affiche la date et préfère le frais sur les sujets qui "
          "bougent), inutile pour une page outil, de contact ou légale. Dis lesquelles en ont besoin.")
    elif sans_date:
        c(3, "dates", "Aucune page ne déclare de date",
          f"Aucune des {len(indexables)} pages n'a `dateModified`, `article:modified_time` ou `<time>`.", [],
          "Pour les articles et les guides : date de publication et de mise à jour, visibles et dans le JSON-LD.",
          "Le site a-t-il des articles ou des guides ? Si ce ne sont que des pages produit ou outil, c'est sans objet.")
    vides = [u for u in indexables if isinstance(rows[u]["mots"], int) and rows[u]["mots"] < MOTS_VIDE]
    if vides:
        c(3, "vides", f"{pluriel(len(vides), 'page')} presque vide(s) dans le HTML",
          f"Le HTML envoyé par le serveur contient moins de {MOTS_VIDE} mots. Soit la page est vraiment mince, soit son "
          "texte est ajouté par JavaScript dans le navigateur : Google finit par le lire, mais plus tard, et les robots "
          "des IA ne le lisent pas.", [f"{k(u)} : {rows[u]['mots']} mots" for u in vides],
          "Si c'est du JavaScript, fais rendre le texte côté serveur (rendu serveur ou génération statique). Si c'est "
          "mince, étoffe ou fusionne.",
          "Ouvre une de ces URL : la page affichée a-t-elle du texte ? Une page outil (calculateur, carte) peut être "
          "courte : dis-le.")

    # ===== 4. Balises =====
    idx = [u for u in indexables if interne(u)]
    t_manque = [u for u in idx if not rows[u]["title"]]
    titres = Counter(rows[u]["title"] for u in idx if rows[u]["title"])
    t_double = [u for u in idx if rows[u]["title"] and titres[rows[u]["title"]] > 1]
    t_long = [u for u in idx if rows[u]["title"] and len(rows[u]["title"]) > TITLE_MAX]
    t_court = [u for u in idx if rows[u]["title"] and len(rows[u]["title"]) < TITLE_MIN]
    if t_manque:
        c(4, "title-absent", f"{pluriel(len(t_manque), 'page')} sans title", "Google invente alors un titre.",
          [k(u) for u in t_manque], "Donne à chaque page un title qui dit ce qu'elle contient.", "")
    if t_double:
        par = {}
        for u in t_double:
            par.setdefault(rows[u]["title"], []).append(u)
        c(4, "title-double", f"{pluriel(len(t_double), 'page')} partagent leur title avec une autre",
          "Deux pages au même titre : Google ne sait pas laquelle montrer.",
          [f"« {t[:70]} » : " + ", ".join(k(u) for u in us) for t, us in sorted(par.items())],
          "Un title propre à chaque page.", "Pagination ou variantes d'une même page : dis si c'est le cas.")
    if t_long:
        c(4, "title-long", f"{pluriel(len(t_long), 'title')} de plus de {TITLE_MAX} caractères",
          "Google coupe l'affichage vers 60 caractères (la mesure exacte est en pixels) : la fin ne se voit pas.",
          [f"{k(u)} ({len(rows[u]['title'])} car.) « {rows[u]['title'][:90]} »" for u in t_long],
          "Mets les mots qui comptent au début ; la fin peut être coupée sans dommage.",
          "Ne réécris pas sur un site neuf sans requêtes qui sortent (voir SKILL.md) : signale seulement ceux dont le "
          "début ne dit pas le sujet.")
    if t_court:
        c(4, "title-court", f"{pluriel(len(t_court), 'title')} de moins de {TITLE_MIN} caractères",
          "Un title très court dit peu de chose à Google et au lecteur.",
          [f"{k(u)} « {rows[u]['title']} »" for u in t_court], "Dis de quoi parle la page, en 30 à 60 caractères.", "")
    d_manque = [u for u in idx if not rows[u]["description"]]
    descs = Counter(rows[u]["description"] for u in idx if rows[u]["description"])
    d_double = [u for u in idx if rows[u]["description"] and descs[rows[u]["description"]] > 1]
    d_long = [u for u in idx if rows[u]["description"] and len(rows[u]["description"]) > DESC_MAX]
    d_court = [u for u in idx if rows[u]["description"] and len(rows[u]["description"]) < DESC_MIN]
    if d_manque:
        c(4, "desc-absente", f"{pluriel(len(d_manque), 'page')} sans meta description",
          "Google prend alors un bout de texte de la page, pas toujours le bon.", [k(u) for u in d_manque],
          "Une phrase de 120 à 160 caractères qui donne envie de cliquer.", "")
    if d_double:
        par = {}
        for u in d_double:
            par.setdefault(rows[u]["description"], []).append(u)
        c(4, "desc-double", f"{pluriel(len(d_double), 'page')} partagent leur description avec une autre", "",
          [f"« {t[:70]}… » : " + ", ".join(k(u) for u in us) for t, us in sorted(par.items())],
          "Une description propre à chaque page.", "")
    if d_long:
        c(4, "desc-longue", f"{pluriel(len(d_long), 'description')} de plus de {DESC_MAX} caractères",
          "Coupées dans les résultats.", [f"{k(u)} ({len(rows[u]['description'])} car.)" for u in d_long],
          "Raccourcis à 160 caractères au plus, l'essentiel au début.", "Faible priorité : Google réécrit souvent les descriptions.")
    if d_court:
        c(4, "desc-courte", f"{pluriel(len(d_court), 'description')} de moins de {DESC_MIN} caractères", "",
          [f"{k(u)} « {rows[u]['description']} »" for u in d_court], "Vise 120 à 160 caractères.", "")
    h0 = [u for u in idx if rows[u]["nb_h1"] == 0]
    h2 = [u for u in idx if isinstance(rows[u]["nb_h1"], int) and rows[u]["nb_h1"] > 1]
    if h0:
        c(4, "h1-absent", f"{pluriel(len(h0), 'page')} sans H1", "Le titre visible de la page n'est pas balisé en `<h1>`.",
          [k(u) for u in h0], "Balise le titre principal de la page en `<h1>`, un seul.", "")
    if h2:
        c(4, "h1-multiple", f"{pluriel(len(h2), 'page')} avec plusieurs H1", "Plusieurs `<h1>` brouillent le sujet principal.",
          [f"{k(u)} : {rows[u]['nb_h1']} H1" for u in h2], "Garde un `<h1>`, passe les autres en `<h2>`.",
          "Faible priorité : Google s'en accommode. À corriger si c'est le gabarit (une règle, toutes les pages).")
    sans_can = [u for u in idx if not rows[u]["canonique"]]
    if sans_can:
        c(4, "canonique-absente", f"{pluriel(len(sans_can), 'page')} sans balise canonical",
          "Google choisit seul l'URL à garder quand une page est joignable de plusieurs façons (paramètres, slash).",
          [k(u) for u in sans_can], "Ajoute `<link rel=\"canonical\" href=\"URL complète de la page\">` dans le gabarit.", "")
    alt = {u: d for u, d in A["images"].items() if d["alt_absent"]}
    if alt:
        n_pages = len({u for u in html for im in pages[u]["page"]["images"] if im["alt"] is None})
        c(4, "alt", f"{pluriel(len(alt), 'image')} sans attribut alt, sur {pluriel(n_pages, 'page')}",
          "Sans `alt`, Google ne sait pas ce que montre l'image, et un lecteur d'écran non plus. (Un `alt=\"\"` vide est "
          "correct pour une image décorative : il n'est pas compté ici.)",
          [f"{k(u)} (sur {pluriel(d['pages'], 'page')})" for u, d in sorted(alt.items(), key=lambda x: (-x[1]['pages'], x[0]))],
          "Décris chaque image utile en quelques mots ; mets `alt=\"\"` aux images décoratives.", "")
    else:
        OK.append(f"Toutes les images ont un attribut alt ({len(A['images'])} images).")
    sans_lang = [u for u in idx if not rows[u]["lang"]]
    if sans_lang:
        c(4, "lang", f"{pluriel(len(sans_lang), 'page')} sans langue déclarée", "Pas d'attribut `lang` sur `<html>`.",
          [k(u) for u in sans_lang], "Ajoute `<html lang=\"fr\">` (ou la langue de la page) au gabarit.", "")
    sans_vp = [u for u in idx if rows[u]["viewport"] == "non"]
    if sans_vp:
        c(4, "viewport", f"{pluriel(len(sans_vp), 'page')} sans balise viewport",
          "Sans `<meta name=\"viewport\">`, la page s'affiche en miniature sur mobile, et Google indexe la version mobile.",
          [k(u) for u in sans_vp], "Ajoute `<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">`.", "")
    sans_og = [u for u in idx if not ("title" in rows[u]["og"].split() and "image" in rows[u]["og"].split())]
    if sans_og:
        c(4, "og", f"{pluriel(len(sans_og), 'page')} sans og:title ou og:image",
          "Sans Open Graph, un lien partagé (réseaux, messageries) s'affiche sans image ni bon titre.",
          [f"{k(u)} : a {rows[u]['og'] or 'rien'}" for u in sans_og], "Ajoute `og:title`, `og:description` et `og:image` au gabarit.",
          "Sans effet sur Google : priorité basse, sauf si le site vit des partages.")
    err_ld = [u for u in idx if rows[u]["jsonld_erreurs"]]
    if err_ld:
        c(4, "jsonld-erreur", f"{pluriel(len(err_ld), 'page')} avec un JSON-LD illisible",
          "Le bloc de données structurées n'est pas du JSON valide : Google l'ignore.", [k(u) for u in err_ld],
          "Corrige le JSON (une virgule ou un guillemet de trop, souvent) et teste-le dans le test des résultats "
          "enrichis de Google.", "")
    avec_ld = [u for u in idx if rows[u]["jsonld"]]
    if idx and not avec_ld:
        c(4, "jsonld-absent", "Aucune donnée structurée (JSON-LD)",
          "Aucune page n'a de bloc JSON-LD dans son HTML. (Un JSON-LD ajouté par JavaScript n'est pas vu ici.)", [],
          "Pose au moins `Organization` ou `Person` sur l'accueil et `Article` sur les articles. La skill schema-markup "
          "s'il y en a une, sinon le générateur de ton CMS.", "Sans urgence : ça n'aide pas à ranker, ça aide l'affichage.")
    elif avec_ld:
        types = Counter(t for u in avec_ld for t in rows[u]["jsonld"].split())
        OK.append(f"JSON-LD sur {len(avec_ld)} pages sur {len(idx)} (" + ", ".join(f"{t} {n}" for t, n in types.most_common(5)) + ").")
    tits = len(set(t_manque) | set(t_double) | set(t_long) | set(t_court))
    if idx and not tits:
        OK.append(f"Titles présents, uniques et de 20 à 60 caractères sur les {len(idx)} pages.")
    descs_pb = len(set(d_manque) | set(d_double) | set(d_long) | set(d_court))
    if idx and not descs_pb:
        OK.append(f"Meta descriptions présentes, uniques et de 50 à 160 caractères sur les {len(idx)} pages.")
    if idx and not h0 and not h2:
        OK.append(f"Un seul H1 sur chacune des {len(idx)} pages.")

    C = [x for _, x in sorted(enumerate(C), key=lambda e: (e[1]["priorite"], e[1]["rang"], e[0]))]
    ins_ok = [i for i in A["gsc"]["inspections"] if i["categorie"] != "erreur"
              and i["pourquoi"] != "vue par Google, hors sitemap"]
    resume = {
        "pages_sitemap": len(sitemap), "pages_lues": len(html),
        "hors_sitemap": len([u for u in indexables if u not in sm_set]),
        "inspectees": len(ins_ok) if A["propriete"] else None,
        "indexees": sum(1 for i in ins_ok if i["categorie"] == "indexée") if A["propriete"] else None,
        "sans_lien_texte": len(orph) + len(sans_phrase), "sans_aucun_lien": len(orph), "un_seul_lien": len(un),
        "mediane_entrants_texte": med, "pages_contenu": len(contenu),
        "casses_internes": len({x[1] for x in A["casses"]}), "casses_externes": len(casses_ext),
        "titles_a_corriger": tits, "descriptions_a_corriger": descs_pb,
        "constats": {str(p): sum(1 for x in C if x["priorite"] == p) for p in (1, 2, 3, 4)},
    }
    return C, OK, resume


# --- le rapport -----------------------------------------------------------------

LIGNES_RESUME = [
    ("pages_sitemap", "URL dans le sitemap"),
    ("pages_lues", "Pages lues (HTML en 200)"),
    ("hors_sitemap", "Pages indexables hors sitemap"),
    ("indexees", "Indexées par Google"),
    ("pages_contenu", "Pages de contenu (hors accueil, pages légales, noindex)"),
    ("sans_lien_texte", "citées dans aucune phrase du site"),
    ("sans_aucun_lien", "dont sans aucun lien interne"),
    ("un_seul_lien", "citées dans une seule phrase"),
    ("mediane_entrants_texte", "Médiane : pages qui citent une page dans une phrase"),
    ("casses_internes", "Liens internes cassés"),
    ("casses_externes", "Liens externes cassés (échantillon)"),
    ("titles_a_corriger", "Titles à revoir"),
    ("descriptions_a_corriger", "Descriptions à revoir"),
]


def _valeur(res, cle):
    if res is None:
        return ""
    if cle == "indexees":
        if res.get("inspectees") is None:
            return "non mesuré"
        return f"{res.get('indexees')} sur {res.get('inspectees')} (accueil et sitemap)"
    v = res.get(cle, "")
    return nb(v) if isinstance(v, float) else str(v)


def bloc_resume(A):
    r = A["resume"]
    gsc = (f"{r['indexees']} indexées sur {r['inspectees']} inspectées (accueil et sitemap)" if r["inspectees"] is not None
           else "Search Console non lue")
    lignes = [
        f"SITE      {A['site']} · {r['pages_lues']} pages lues · {r['pages_sitemap']} URL dans le sitemap · {A['duree_s']} s",
        f"INDEX     {gsc}",
        f"MAILLAGE  sur {r['pages_contenu']} pages de contenu : {r['sans_lien_texte']} citées dans aucune phrase "
        f"({r['sans_aucun_lien']} sans aucun lien), {r['un_seul_lien']} dans une seule ; médiane {nb(r['mediane_entrants_texte'])}",
        f"CASSÉS    {r['casses_internes']} internes, {r['casses_externes']} externes (échantillon de {A['externes_testes']})",
        f"BALISES   {r['titles_a_corriger']} titles, {r['descriptions_a_corriger']} descriptions à revoir",
        "CONSTATS  " + " · ".join(f"{p} : {n}" for p, n in r["constats"].items()),
    ]
    for x in A["constats"]:
        if x["priorite"] == 1:
            lignes.append(f"  [1] {x['titre']}")
    if A["note_gsc"]:
        lignes.append("NOTE      " + A["note_gsc"])
    if A["lighthouse"]["etat"] and A["lighthouse"]["etat"] != "ok":
        lignes.append("NOTE      " + A["lighthouse"]["etat"])
    return lignes


def markdown(A):
    L = []
    w = L.append
    r = A["resume"]
    hote = A["site"]
    lh = A["lighthouse"]
    lhp = [p for p in lh.get("pages", []) if "performance" in p]
    w(f"# Audit SEO technique : {hote}")
    w("")
    gsc = (f"Search Console : `{A['propriete']}`" if A["propriete"] else "Search Console : non lue")
    lht = f"Lighthouse : {len(lhp)} pages" if lhp else "Lighthouse : non lancé"
    w(f"{date_fr(A['date'])} · {r['pages_lues']} pages lues · {gsc} · {lht} · {A['duree_s']} s")
    w("")
    w("Ce rapport mesure, il ne modifie rien. Tous les chiffres viennent du script. Chaque `<!-- CLAUDE: … -->` "
      "est à remplacer par la lecture de Claude.")
    w("")
    w("## Résumé")
    w("")
    p = A.get("precedent")
    if p and p.get("resume"):
        w(f"| | maintenant | audit du {p['date'][:10]} |")
        w("|---|---|---|")
        for cle, lib in LIGNES_RESUME:
            w(f"| {lib} | {_valeur(r, cle)} | {_valeur(p['resume'], cle)} |")
    else:
        w("| | |")
        w("|---|---|")
        for cle, lib in LIGNES_RESUME:
            w(f"| {lib} | {_valeur(r, cle)} |")
    w("| Constats par priorité | " + " · ".join(f"{k} : {n}" for k, n in r["constats"].items()) + " |"
      + (" |" if p and p.get("resume") else ""))
    w("")
    w("<!-- CLAUDE: en trois phrases, ce qui empêche Google de lire ou de garder des pages (priorité 1), puis le "
      "maillage, puis le reste. Dis ce qu'il faut corriger d'abord, et ce qu'on laisse de côté sur ce site "
      "(SKILL.md : l'autorité, les titres sans requêtes derrière). -->")
    w("")
    lim = []
    if A["note_gsc"]:
        lim.append(A["note_gsc"])
    if A["gsc"]["erreurs"]:
        lim += ["Search Console : " + e for e in A["gsc"]["erreurs"]]
    n_err = sum(1 for i in A["gsc"]["inspections"] if i["categorie"] == "erreur")
    if n_err:
        ex = next(i["couverture"] for i in A["gsc"]["inspections"] if i["categorie"] == "erreur")
        lim.append(f"{n_err} inspection(s) d'URL en échec (ex. : {ex}).")
    if A["gsc"].get("non_inspectees"):
        lim.append(f"{A['gsc']['non_inspectees']} URL non inspectées (plafond --inspection-max {A['options']['inspection_max']}).")
    if lh["etat"] and lh["etat"] != "ok":
        lim.append(lh["etat"])
    for x in lh.get("pages", []):
        if "erreur" in x:
            lim.append(f"Lighthouse a échoué sur `{court(x['url'], hote)}` : {x['erreur']}")
    if A["pages_non_lues"]:
        lim.append(f"{A['pages_non_lues']} pages trouvées non lues (plafond --max {A['options']['max']}) : leurs liens "
                   "ne sont pas comptés.")
    refus = [x for x in A["pages"] if x["statut"] in (401, 403, 429, 503)]
    if refus:
        lim.append(f"{len(refus)} page(s) ont refusé la lecture ({', '.join(sorted({str(x['statut']) for x in refus}))}) : "
                   "un pare-feu bloque peut-être les robots. Vérifie que Googlebot, lui, passe (inspection d'URL).")
    lim.append("Seul le HTML envoyé par le serveur est lu : un texte, un lien ou un JSON-LD ajoutés par JavaScript dans "
               "le navigateur n'y sont pas.")
    w("## Ce que l'audit n'a pas pu lire")
    w("")
    for x in lim:
        w(f"- {x}")
    w("")
    for prio, titre in PRIORITES.items():
        w(f"## {prio}. {titre}")
        w("")
        liste = [x for x in A["constats"] if x["priorite"] == prio]
        if not liste:
            w("Rien à signaler.")
            w("")
            continue
        for n, x in enumerate(liste, 1):
            w(f"### {prio}.{n} {x['titre']}")
            w("")
            if x["fait"]:
                w(f"**Le fait.** {x['fait']}")
                w("")
            if x["preuves"]:
                w("**La preuve.**")
                w("")
                for pr in x["preuves"]:
                    w(f"- {pr}")
                if x["preuves_total"] > len(x["preuves"]):
                    w(f"- … et {x['preuves_total'] - len(x['preuves'])} autres (audit.json, clé `constats`)")
                w("")
            w(f"**Correction proposée.** {x['correction']}")
            w("")
            claude = x["claude"] or "volontaire ou à corriger, et la correction précise pour ce site (si son code est " \
                                    "dans le dossier courant, le fichier à changer)."
            w(f"<!-- CLAUDE: {claude} -->")
            w("")
    w("## 5. Ce qui va bien")
    w("")
    for x in A["ok"]:
        w(f"- {x}")
    w("")
    rows = [x for x in A["pages"] if x["statut"] == 200 and not x["redirections"] and x["noindex"] != "oui"
            and x["mots"] != "" and hote_de(x["url"]) == hote]
    if rows:
        w("## Annexe : le maillage page par page")
        w("")
        w("Chaque colonne compte des pages sources (une page qui cite deux fois compte une fois). « Phrase » : un lien "
          "posé dans une phrase d'une autre page. « Bloc » : un lien du contenu sans phrase autour (cartes « à lire "
          "aussi », grille d'une page hub, liste de liens). « Navigation » : menu, en-tête, pied de page, encadré "
          "`<aside>`, fil d'Ariane, ou lien répété à l'identique sur plus de la moitié des pages"
          + (f" (seuil : {A['seuil_gabarit']} pages, {A['gabarit']} liens de gabarit repérés)"
             if A.get("seuil_gabarit") else "") + ".")
        w("")
        z = A["zones"]
        w(f"Sur tout le site : {z.get('texte', 0)} liens internes dans une phrase, {z.get('bloc de liens', 0)} dans des "
          f"blocs, {z.get('navigation', 0)} de navigation.")
        w("")
        w("| page | citée dans une phrase par | en bloc par | en navigation par | ses liens en phrase | mots | Google |")
        w("|---|---|---|---|---|---|---|")
        tri = sorted(rows, key=lambda x: (x["entrants_texte"], x["entrants_blocs"], x["entrants_nav"], x["url"]))
        for x in tri[:40]:
            w(f"| `{court(x['url'], hote)}` | {x['entrants_texte']} | {x['entrants_blocs']} | {x['entrants_nav']} | "
              f"{x['sortants_texte']} | {x['mots']} | {x['gsc_categorie'] or ''} |")
        if len(tri) > 40:
            w(f"| … {len(tri) - 40} autres pages dans `pages.csv` | | | | | | |")
        w("")
    if lhp:
        w("## Annexe : Lighthouse (mobile, laboratoire)")
        w("")
        w("| page | performance | SEO | LCP | CLS | TBT |")
        w("|---|---|---|---|---|---|")
        for x in lhp:
            w(f"| `{court(x['url'], hote)}` | {x['performance']} | {x['seo']} | {nb(x['lcp_ms'] / 1000, 1)} s | "
              f"{nb(x['cls'])} | {x['tbt_ms']} ms |")
        w("")
    w("## Le journal")
    w("")
    j = A.get("journal") or []
    if j:
        w(f"Déjà noté dans `journal.csv` ({len(j)} lignes, les 5 dernières) :")
        w("")
        for e in j[-5:]:
            w(f"- {e.get('en_ligne', '')} · {e.get('ajustement', '')} · {e.get('url', '')}")
        w("")
    w("Chaque correction mise en ligne : une ligne dans `journal.csv` (date de mise en ligne, ce qui a changé, URL, "
      "`attendu_index` = `indexée` si le but est d'entrer dans Google). La skill `search-console` en mesure l'effet "
      "trois semaines après. Refais cet audit une semaine après les corrections : les pages neuves refont les mêmes "
      "fautes.")
    w("")
    w("## Fichiers")
    w("")
    w("| fichier | contenu |")
    w("|---|---|")
    w("| `AUDIT.md` | ce rapport |")
    w("| `pages.csv` | une ligne par URL lue : statut, redirections, balises, mots, liens entrants et sortants, Google |")
    w("| `liens.csv` | chaque lien : source, cible, zone (texte, `<nav>`, `<footer>`, gabarit…), texte du lien, statut |")
    w("| `audit.json` | tout ce que le script a mesuré, constats compris |")
    w("")
    return "\n".join(L)
