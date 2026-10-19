#!/usr/bin/env python3
"""Sépare le signal du bruit dans les données récupérées par collecte.py.

Usage : python3 analyse.py <dossier du site>   (ex. ~/search-console/monsite.com)
Écrit <dossier>/analyse.json et imprime le résumé à lire avant toute conclusion.
"""
import csv
import datetime as dt
import fnmatch
import json
import math
import os
import random
import sys
import urllib.parse

Z95 = 1.96
SURDISPERSION = 2.5      # petit site, page seule, requête seule : la variance dépasse Poisson
SEUIL_ETABLI = 200       # clics sur 28 j à partir desquels on lit le site au seuil de Poisson pur
SEUIL_NEUF = 30          # en dessous, les clics ne disent rien : on lit l'indexation
Z_PAGES = 3              # beaucoup de pages testées : 1,96 sort par hasard, on exige 3
DELAI_VERDICT = 21       # jours minimum entre la mise en ligne et un verdict


# ---------- lecture ----------

def charge(dossier, nom):
    path = os.path.join(dossier, "donnees", nom)
    if not os.path.exists(path):
        return None
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("clics", "impressions"):
            if k in r and r[k] != "":
                r[k] = int(float(r[k]))
        if r.get("position", "") != "":
            r["position"] = float(r["position"])
        if r.get("page"):
            r["page"] = r["page"].split("#")[0]  # un lien d'ancre (#section) est la même page
    return rows


def charge_brut(dossier, nom, cols):
    path = os.path.join(dossier, nom)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if any((r.get(c) or "").strip() for c in cols)]


def d(s):
    return dt.date.fromisoformat(s[:10])


def fr(n, signe=False):
    if n is None:
        return "n/a"
    if isinstance(n, float) and not n.is_integer():
        s = f"{n:+.1f}" if signe else f"{n:.1f}"
        return s.replace(".", ",")
    s = f"{int(round(n)):+,}" if signe else f"{int(round(n)):,}"
    return s.replace(",", " ")


def jj(day):
    return day.strftime("%d/%m")


# ---------- statistiques ----------

def test_comptes(avant, apres, k=1.0):
    """Écart entre deux comptes sur deux périodes de même durée, au seuil de 95 %."""
    ecart = apres - avant
    total = avant + apres
    seuil = Z95 * math.sqrt(k * total) if total else 0
    z = ecart / math.sqrt(k * total) if total else 0
    if total == 0:
        verdict = "aucune donnée"
    elif seuil >= max(avant, apres, 1) * 0.75 and abs(ecart) <= seuil:
        verdict = "illisible à ce volume"
    elif abs(ecart) <= seuil:
        verdict = "non détectable"
    else:
        verdict = "hausse détectable" if ecart > 0 else "baisse détectable"
    return {"avant": avant, "apres": apres, "ecart": ecart, "seuil": round(seuil), "z": round(z, 2),
            "relatif": round(ecart / avant, 3) if avant else None, "verdict": verdict, "k": k}


def bootstrap(items, stat, n=600, seed=7):
    rnd = random.Random(seed)
    vals = []
    m = len(items)
    for _ in range(n):
        s = [items[rnd.randrange(m)] for _ in range(m)]
        v = stat(s)
        if v is not None:
            vals.append(v)
    vals.sort()
    if not vals:
        return None, None
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def test_demande(avant, apres, min_imp):
    """avant/apres : {cle: (impressions, position)}. Mêmes requêtes sur les deux périodes."""
    eligibles = {q: v for q, v in avant.items() if v[0] >= min_imp}
    panier = [(v[0], v[1], apres[q][0], apres[q][1]) for q, v in eligibles.items() if q in apres and apres[q][0] > 0]
    imp_elig = sum(v[0] for v in eligibles.values())
    survie = sum(p[0] for p in panier) / imp_elig if imp_elig else None
    res = {"requetes": len(panier), "eligibles": len(eligibles), "survie_impressions": round(survie, 3) if survie else None,
           "seuil_impressions": min_imp}
    if len(panier) < 20:
        res["verdict"] = f"panier trop petit ({len(panier)} requêtes)"
        return res

    # Poids = inverse de la variance du log-ratio de Poisson : une requête géante ne pèse pas tout le panier,
    # une requête à 10 impressions ne pèse presque rien.
    def poids(p):
        return p[0] * p[2] / (p[0] + p[2])

    def ratio(s):
        w = sum(poids(p) for p in s)
        return math.exp(sum(poids(p) * math.log(p[2] / p[0]) for p in s) / w) if w else None

    def dpos(s):
        w = sum(poids(p) for p in s)
        return sum(poids(p) * (p[3] - p[1]) for p in s) / w if w else None

    r, (rlo, rhi) = ratio(panier), bootstrap(panier, ratio)
    dp, (plo, phi) = dpos(panier), bootstrap(panier, dpos)
    demande = "baisse" if rhi < 1 else "hausse" if rlo > 1 else None
    classement = "recule" if plo > 0 else "progresse" if phi < 0 else None
    if classement and demande:
        v = f"le classement {classement} et les impressions sont en {demande}"
    elif classement:
        v = f"le classement {classement}"
    elif demande:
        v = f"la demande est en {demande}, à position stable"
    else:
        v = "non détectable"
    res.update({"ratio": round(r, 3), "ratio_bas": round(rlo, 3), "ratio_haut": round(rhi, 3),
                "ecart_position": round(dp, 2), "position_bas": round(plo, 2), "position_haut": round(phi, 2),
                "verdict": v})
    return res


# ---------- groupes de pages ----------

def regles_groupes(dossier):
    out = []
    for r in charge_brut(dossier, "groupes.csv", ["motif"]):
        m, gname = r["motif"].strip(), (r.get("groupe") or "").strip()
        if m and gname:
            out.append((m, gname))
    return out


def chemin(url):
    p = urllib.parse.urlparse(url)
    return p.path or "/"


def groupe_de(url, regles):
    p = chemin(url)
    for motif, nom in regles:
        cible = url if motif.startswith("http") else p
        if "*" in motif or "?" in motif:
            if fnmatch.fnmatch(cible, motif):
                return nom
        elif cible.startswith(motif):
            return nom
    return None


# ---------- analyse ----------

def somme(rows, debut, fin, k):
    return sum(r[k] for r in rows if debut <= r["date"] <= fin)


def agrege(rows, cle, filtre=None):
    """{cle: [clics, impressions, somme pos*imp]}"""
    out = {}
    for r in rows:
        if filtre and not filtre(r):
            continue
        key = cle(r)
        a = out.setdefault(key, [0, 0, 0.0])
        a[0] += r["clics"]
        a[1] += r["impressions"]
        a[2] += r.get("position", 0) * r["impressions"]
    return out


def pos(a):
    return round(a[2] / a[1], 1) if a[1] else None


def main(dossier):
    dossier = os.path.abspath(os.path.expanduser(dossier))
    with open(os.path.join(dossier, "donnees", "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    jours = charge(dossier, "jours.csv") or []
    L = d(meta["dernier_jour"])
    w1 = [d(meta["w1"][0]), d(meta["w1"][1])]
    w0 = [d(meta["w0"][0]), d(meta["w0"][1])]
    W1 = [x.isoformat() for x in w1]
    W0 = [x.isoformat() for x in w0]
    today = dt.date.today()
    A = {"site": meta["site"], "source": meta.get("source", "api"), "dernier_jour": meta["dernier_jour"],
         "w1": W1, "w0": W0, "genere_le": dt.datetime.now().isoformat(timespec="seconds"), "manque": meta.get("manque", [])}

    c1, c0 = somme(jours, *W1, "clics"), somme(jours, *W0, "clics")
    i1, i0 = somme(jours, *W1, "impressions"), somme(jours, *W0, "impressions")
    regime = "etabli" if c1 >= SEUIL_ETABLI else "petit" if c1 >= SEUIL_NEUF else "neuf"
    k = 1.0 if regime == "etabli" else SURDISPERSION
    A["regime"] = regime
    A["k"] = k

    # Semaines complètes, du lundi au dimanche.
    dimanche = L - dt.timedelta(days=(L.weekday() + 1) % 7)
    semaines = [dimanche - dt.timedelta(days=6 + 7 * i) for i in range(15, -1, -1)]
    premier_jour = min((r["date"] for r in jours), default=W1[0])
    semaines = [s for s in semaines if s.isoformat() >= premier_jour[:10] or s + dt.timedelta(days=6) >= d(premier_jour)]

    def sem(rows, lundi, cle):
        return somme(rows, lundi.isoformat(), (lundi + dt.timedelta(days=6)).isoformat(), cle)

    hebdo = [{"semaine": s.isoformat(), "clics": sem(jours, s, "clics"), "impressions": sem(jours, s, "impressions")}
             for s in semaines]
    A["hebdo"] = hebdo

    # Les quatre chiffres.
    kpis = {"clics_28j": test_comptes(c0, c1, k), "impressions_28j": test_comptes(i0, i1, k)}
    premiere_impression = min((r["date"] for r in jours if r["impressions"] > 0), default=W1[0])
    A["premiere_impression"] = premiere_impression
    if premiere_impression > W0[0]:
        for t in kpis.values():
            if t["verdict"] != "illisible à ce volume":
                t["verdict"] = "pas comparable : le site n'apparaissait pas encore au début de la fenêtre d'avant"
    if len(hebdo) >= 2:
        a, b = hebdo[-2], hebdo[-1]
        kpis["clics_semaine"] = test_comptes(a["clics"], b["clics"], k)
        kpis["clics_semaine"]["semaine"] = b["semaine"]
        kpis["clics_semaine"]["semaine_avant"] = a["semaine"]
    A["kpis"] = kpis

    # Pages.
    pj = charge(dossier, "pages_jours.csv")
    regles = regles_groupes(dossier)
    pages = {}
    if pj is not None:
        premiere = {}
        for r in pj:
            if r["impressions"] > 0 and (r["page"] not in premiere or r["date"] < premiere[r["page"]]):
                premiere[r["page"]] = r["date"]
        a1 = agrege(pj, lambda r: r["page"], lambda r: W1[0] <= r["date"] <= W1[1])
        a0 = agrege(pj, lambda r: r["page"], lambda r: W0[0] <= r["date"] <= W0[1])
        debut_donnees = meta.get("debut_pages", W0[0])
    else:
        premiere = {}
        p1, p0 = charge(dossier, "pages_w1.csv") or [], charge(dossier, "pages_w0.csv") or []
        a1 = agrege(p1, lambda r: r["page"])
        a0 = agrege(p0, lambda r: r["page"])
        debut_donnees = None
    for p in set(a1) | set(a0) | set(premiere):
        x1, x0 = a1.get(p, [0, 0, 0]), a0.get(p, [0, 0, 0])
        pages[p] = {"page": p, "clics_avant": x0[0], "clics_apres": x1[0], "imp_avant": x0[1], "imp_apres": x1[1],
                    "position_apres": pos(x1), "position_avant": pos(x0), "premiere": premiere.get(p)}

    def groupe(p):
        if regime != "neuf" and debut_donnees and premiere.get(p, "") >= W0[0] and premiere.get(p, "") > debut_donnees:
            return "pages neuves"
        return groupe_de(p, regles) or ("stock" if not regles else "autres")

    for p, v in pages.items():
        v["groupe"] = groupe(p)

    mouvements = []
    if regime != "neuf":
        for v in pages.values():
            if max(v["clics_avant"], v["clics_apres"]) >= 10:
                t = test_comptes(v["clics_avant"], v["clics_apres"], 1.0 if regime == "etabli" else k)
                v["ecart"], v["z"] = t["ecart"], t["z"]
                v["lecture"] = "hausse" if t["z"] > Z_PAGES else "baisse" if t["z"] < -Z_PAGES else "bruit"
                mouvements.append(v)
        mouvements.sort(key=lambda v: v["z"])
    A["pages_testees"] = mouvements
    A["pages_qui_bougent"] = {"hausses": sum(v["lecture"] == "hausse" for v in mouvements),
                              "baisses": sum(v["lecture"] == "baisse" for v in mouvements),
                              "testees": len(mouvements)}
    A["pages_apparues"] = sorted([v for v in pages.values() if v["premiere"] and v["premiere"] >= W1[0]
                                  and debut_donnees and v["premiere"] > debut_donnees],
                                 key=lambda v: -v["imp_apres"])[:15]
    A["pages_disparues"] = sorted([v for v in pages.values() if v["imp_avant"] >= 30 and v["imp_apres"] == 0],
                                  key=lambda v: -v["imp_avant"])[:15]

    # Clics par semaine et par groupe (données par page).
    if pj is not None:
        top = sorted({v["groupe"] for v in pages.values()},
                     key=lambda g_: -sum(v["clics_apres"] + v["clics_avant"] for v in pages.values() if v["groupe"] == g_))
        garder = top[:4] if len(top) > 5 else top
        par_groupe = {}
        for r in pj:
            g_ = pages.get(r["page"], {}).get("groupe", "autres")
            g_ = g_ if g_ in garder else "autres"
            par_groupe.setdefault(g_, {})
            lundi = d(r["date"]) - dt.timedelta(days=d(r["date"]).weekday())
            par_groupe[g_][lundi.isoformat()] = par_groupe[g_].get(lundi.isoformat(), [0, 0])
            par_groupe[g_][lundi.isoformat()][0] += r["clics"]
            par_groupe[g_][lundi.isoformat()][1] += r["impressions"]
        ordre = [g_ for g_ in garder if g_ in par_groupe] + (["autres"] if "autres" in par_groupe and "autres" not in garder else [])
        A["hebdo_groupes"] = {"groupes": ordre, "semaines": [
            {"semaine": h["semaine"], **{g_: par_groupe.get(g_, {}).get(h["semaine"], [0, 0]) for g_ in ordre}}
            for h in hebdo if h["semaine"] >= (debut_donnees or "")]}
        A["groupes_auto"] = not regles

    # Couverture de la dimension requête.
    q1, q0 = charge(dossier, "requetes_w1.csv"), charge(dossier, "requetes_w0.csv")
    if q1 is not None:
        vis = sum(r["impressions"] for r in q1)
        A["couverture"] = {"impressions_visibles": vis, "part": round(vis / i1, 3) if i1 else None,
                           "clics_visibles": sum(r["clics"] for r in q1),
                           "part_clics": round(sum(r["clics"] for r in q1) / c1, 3) if c1 else None,
                           "requetes_w1": len(q1), "requetes_w0": len(q0 or [])}

    if q1 is not None:
        A["requetes_top"] = [{"requete": r["requete"], "clics": r["clics"], "impressions": r["impressions"],
                              "position": r["position"]} for r in sorted(q1, key=lambda r: -r["impressions"])[:25]]

    # Demande ou classement : mêmes requêtes sur les deux fenêtres.
    min_imp = 10 if regime == "etabli" else 3
    tests = []
    if q1 is not None and q0 is not None and regime != "neuf":
        def dico(rows, cle):
            ag = agrege(rows, cle)
            return {kk: (v[1], v[2] / v[1] if v[1] else 0) for kk, v in ag.items()}
        t = test_demande(dico(q0, lambda r: r["requete"]), dico(q1, lambda r: r["requete"]), min_imp)
        tests.append({"segment": "tout le site", **t})
        rp1, rp0 = charge(dossier, "requetes_pays_w1.csv"), charge(dossier, "requetes_pays_w0.csv")
        if rp1 and rp0:
            pays_imp = agrege(rp1, lambda r: r["pays"])
            for code in sorted(pays_imp, key=lambda c_: -pays_imp[c_][1])[:3]:
                f_ = lambda r, c_=code: r["pays"] == c_
                t = test_demande(dico([r for r in rp0 if f_(r)], lambda r: r["requete"]),
                                 dico([r for r in rp1 if f_(r)], lambda r: r["requete"]), min_imp)
                tests.append({"segment": "pays : " + code.upper(), **t})
        ra1, ra0 = charge(dossier, "requetes_appareils_w1.csv"), charge(dossier, "requetes_appareils_w0.csv")
        if ra1 and ra0:
            mob = lambda r: r["appareil"].upper() == "MOBILE"
            t = test_demande(dico([r for r in ra0 if mob(r)], lambda r: r["requete"]),
                             dico([r for r in ra1 if mob(r)], lambda r: r["requete"]), min_imp)
            tests.append({"segment": "mobile seul", **t})
        qp1, qp0 = charge(dossier, "requetes_pages_w1.csv"), charge(dossier, "requetes_pages_w0.csv")
        if qp1 and qp0 and len(pages) > 1:
            for g_ in sorted({v["groupe"] for v in pages.values()}):
                if g_ == "pages neuves":
                    continue
                membres = {p for p, v in pages.items() if v["groupe"] == g_}
                t = test_demande(dico([r for r in qp0 if r["page"] in membres], lambda r: r["requete"]),
                                 dico([r for r in qp1 if r["page"] in membres], lambda r: r["requete"]), min_imp)
                if t["requetes"] >= 20:
                    tests.append({"segment": "groupe : " + g_, **t})
    A["demande"] = tests

    # Saison : les mêmes semaines il y a un an.
    an = lambda x: (x - dt.timedelta(days=364)).isoformat()
    ca1, ca0 = somme(jours, an(w1[0]), an(w1[1]), "clics"), somme(jours, an(w0[0]), an(w0[1]), "clics")
    ia1, ia0 = somme(jours, an(w1[0]), an(w1[1]), "impressions"), somme(jours, an(w0[0]), an(w0[1]), "impressions")
    A["saison"] = {"clics_avant": ca0, "clics_apres": ca1, "imp_avant": ia0, "imp_apres": ia1,
                   "lisible": ca0 + ca1 >= 200,
                   "ratio_impressions": round(ia1 / ia0, 3) if ia0 else None}

    # Pays et appareils (niveau site : complet, contrairement à page x pays).
    for nom in ("pays", "appareils"):
        r1, r0 = charge(dossier, f"{nom}_w1.csv"), charge(dossier, f"{nom}_w0.csv")
        if r1 is None or r0 is None:
            continue
        col = "pays" if nom == "pays" else "appareil"
        x1, x0 = agrege(r1, lambda r: r[col]), agrege(r0, lambda r: r[col])
        lignes = []
        for key in sorted(set(x1) | set(x0), key=lambda kk: -(x1.get(kk, [0, 0])[1]))[:8]:
            a_, b_ = x0.get(key, [0, 0, 0]), x1.get(key, [0, 0, 0])
            lignes.append({col: key, "clics": test_comptes(a_[0], b_[0], k), "impressions": test_comptes(a_[1], b_[1], k)})
        A[nom] = lignes
    alerte = None
    for l_ in (A.get("appareils", []) if regime != "neuf" and i0 >= 1000 else []):
        if l_["appareil"].upper() == "DESKTOP":
            ti, tc = l_["impressions"], l_["clics"]
            sens_oppose = tc["verdict"].endswith("détectable") and (tc["ecart"] > 0) != (ti["ecart"] > 0)
            if ti["verdict"] in ("hausse détectable", "baisse détectable") and ti["relatif"] is not None \
                    and abs(ti["relatif"]) > 0.3 and (sens_oppose or tc["verdict"] in ("non détectable", "illisible à ce volume")):
                alerte = (f"Impressions ordinateur {fr(round(ti['relatif'] * 100), True)} % et clics ordinateur {fr(tc['ecart'], True)} : "
                          "possible trafic sans humain ou changement côté Google. Lis plutôt le mobile, et ne cite ni CTR ni position du site.")
    A["alerte_appareils"] = alerte

    # Chevauchements (cannibalisation structurelle) : une requête servie par plusieurs pages.
    qp1 = charge(dossier, "requetes_pages_w1.csv")
    chev = []
    if qp1:
        par_q = {}
        for r in qp1:
            par_q.setdefault(r["requete"], []).append(r)
        mini = 30 if regime == "etabli" else 10
        for q, rows in par_q.items():
            tot = sum(r["impressions"] for r in rows)
            if tot < mini:
                continue
            fortes = sorted([r for r in rows if r["impressions"] >= 0.2 * tot], key=lambda r: -r["impressions"])
            if len(fortes) >= 2:
                chev.append({"requete": q, "impressions": tot, "pages": [
                    {"page": r["page"], "impressions": r["impressions"], "clics": r["clics"], "position": r["position"]}
                    for r in fortes[:3]]})
        chev.sort(key=lambda c_: -c_["impressions"])
    A["chevauchements"] = chev[:12]
    A["chevauchements_total"] = len(chev)

    # Indexation.
    idx = charge(dossier, "index.csv") or []
    index_par_url = {r["url"]: r for r in idx}
    sm_urls = []
    smp = os.path.join(dossier, "donnees", "sitemap_urls.txt")
    if os.path.exists(smp):
        sm_urls = [u for u in open(smp, encoding="utf-8").read().split() if u]
    etats = {}
    for r in idx:
        etats[r["couverture"] or r["verdict"]] = etats.get(r["couverture"] or r["verdict"], 0) + 1
    vues_w1 = {p for p, v in pages.items() if v["imp_apres"] > 0}
    toutes = sorted(set(sm_urls) | vues_w1)
    A["pages_index"] = sorted([{
        "page": p, "imp_apres": pages.get(p, {}).get("imp_apres", 0), "clics_apres": pages.get(p, {}).get("clics_apres", 0),
        "position_apres": pages.get(p, {}).get("position_apres"), "premiere": pages.get(p, {}).get("premiere"),
        "dans_sitemap": p in sm_urls, "verdict": (index_par_url.get(p) or {}).get("verdict", ""),
        "couverture": (index_par_url.get(p) or {}).get("couverture", "non inspectée"),
        "dernier_crawl": ((index_par_url.get(p) or {}).get("dernier_crawl") or "")[:10]}
        for p in toutes], key=lambda x: (-x["imp_apres"], x["page"]))[:200]
    A["indexation"] = {
        "urls_sitemap": len(sm_urls), "inspectees": len(idx),
        "indexees": sum(r["verdict"] == "PASS" for r in idx),
        "etats": etats,
        "non_indexees": [r for r in idx if r["verdict"] != "PASS"][:40],
        "sitemap_vues": len([u for u in sm_urls if u in vues_w1]),
        "hors_sitemap_vues": sorted([p for p in vues_w1 if sm_urls and p not in sm_urls],
                                    key=lambda p: -pages[p]["imp_apres"])[:10],
        "hors_sitemap_total": len([p for p in vues_w1 if sm_urls and p not in sm_urls]),
        "sitemaps": meta.get("sitemaps", []),
    }

    # Journal des changements.
    journal = charge_brut(dossier, "journal.csv", ["en_ligne"])
    sq = charge(dossier, "suivi_requetes.csv") or []
    suivi = []
    for n, e in enumerate(journal):
        try:
            D = d(e["en_ligne"].strip())
        except ValueError:
            suivi.append({"ligne": n + 2, "ajustement": e.get("ajustement", ""), "etat": "date illisible"})
            continue
        J = (L - D).days
        motifs = e.get("url", "").split()
        req = (e.get("requete") or "").strip()

        def match(p):
            return any(p.startswith(m[:-1]) if m.endswith("*") else p == m for m in motifs)

        series = {}
        if req:
            for r in sq:
                if r["requete"] == req:
                    series.setdefault("requete", []).append(r)
        if motifs and pj is not None:
            series["pages"] = [r for r in pj if match(r["page"])]
        lect = {}
        nmax = min(J, 28)
        if debut_donnees:
            nmax = min(nmax, (D - d(debut_donnees)).days)
        for nom, rows in series.items():
            if nmax < 7:
                break
            av = [D - dt.timedelta(days=nmax), D - dt.timedelta(days=1)]
            ap = [D + dt.timedelta(days=1), D + dt.timedelta(days=nmax)]
            A_ = lambda w, kk: sum(r[kk] for r in rows if w[0].isoformat() <= r["date"] <= w[1].isoformat())
            cl = A_(av, "clics") + A_(ap, "clics")
            metrique = "clics" if cl >= 20 else "impressions"
            t = test_comptes(A_(av, metrique), A_(ap, metrique), SURDISPERSION)
            P = lambda w: (sum(r["position"] * r["impressions"] for r in rows if w[0].isoformat() <= r["date"] <= w[1].isoformat())
                           / max(1, A_(w, "impressions")))
            lect[nom] = {"metrique": metrique, "jours": nmax, **t,
                         "position_avant": round(P(av), 1) if A_(av, "impressions") else None,
                         "position_apres": round(P(ap), 1) if A_(ap, "impressions") else None}
        principal = lect.get("requete") or lect.get("pages")
        if J < 7 or not principal:
            verdict = f"trop tôt (J+{J})" if J < 7 else "rien à mesurer (ni page vue, ni requête vue)"
        elif J < DELAI_VERDICT:
            verdict = f"en cours (J+{J}) : verdict à partir du {jj(D + dt.timedelta(days=DELAI_VERDICT))}"
            if principal["z"] <= -Z95:
                verdict += " ; baisse déjà détectable, à surveiller"
        elif principal["z"] >= Z95:
            verdict = "amélioration détectable"
        elif principal["z"] <= -Z95:
            verdict = "régression détectable : envisage de revenir en arrière"
        elif principal["avant"] and principal["seuil"] / principal["avant"] <= 0.3:
            verdict = "pas de régression détectable"
        else:
            mde = round(100 * principal["seuil"] / principal["avant"]) if principal["avant"] else None
            verdict = "indécidable" + (f" (une baisse de moins de {mde} % passerait inaperçue)" if mde else "")
        # indexation des URL visées
        cibles = [r for u_, r in index_par_url.items() if match(u_)] if motifs else []
        recrawl = [r for r in cibles if r.get("dernier_crawl") and r["dernier_crawl"][:10] > D.isoformat()]
        idx_etat = None
        att = (e.get("attendu_index") or "").strip()
        if cibles:
            ok = [r for r in cibles if (r["verdict"] == "PASS") == (att != "hors index")] if att else []
            if att:
                idx_etat = ("tenu" if len(ok) == len(cibles) else
                            "attend un recrawl" if len(recrawl) < len(cibles) else "pas tenu")
            idx_txt = f"{len(recrawl)}/{len(cibles)} recrawlées depuis la mise en ligne"
            if att:
                idx_txt += f", {len(ok)}/{len(cibles)} dans l'état voulu ({att})"
        else:
            idx_txt = None
        vue = None
        if req and series.get("requete"):
            apres = [r for r in series["requete"] if r["date"] > D.isoformat() and r["impressions"] > 0]
            if apres:
                vue = f"vue le {jj(d(min(r['date'] for r in apres)))}, meilleure position {min(r['position'] for r in apres):.0f}"
        # changements empilés sur la même cible
        empile = []
        for m, f_ in enumerate(journal):
            if m == n:
                continue
            try:
                D2 = d(f_["en_ligne"].strip())
            except ValueError:
                continue
            meme = (req and req == (f_.get("requete") or "").strip()) or (set(motifs) & set(f_.get("url", "").split()))
            if meme and 0 <= (D - D2).days < 28:
                empile.append(f"{f_.get('ajustement', '')[:60]} ({jj(D2)})")
        relire = (e.get("relire_le") or "").strip() or (D + dt.timedelta(days=DELAI_VERDICT)).isoformat()
        etat = (e.get("statut") or "").strip() or idx_etat or verdict
        suivi.append({"ligne": n + 2, "en_ligne": D.isoformat(), "j": J, "ajustement": e.get("ajustement", ""),
                      "url": e.get("url", ""), "requete": req, "attendu": e.get("attendu", ""),
                      "attendu_index": att, "relire_le": relire, "constat": e.get("constat", ""),
                      "constat_le": e.get("constat_le", ""), "verdict": verdict, "etat": etat, "lectures": lect,
                      "indexation": idx_txt, "requete_vue": vue, "empile_sur": empile})
    A["suivi"] = suivi
    A["changements_fenetre"] = [s for s in suivi if s.get("en_ligne") and W0[0] <= s["en_ligne"] <= W1[1]]

    # Calendrier de relecture.
    cal = []
    for s in suivi:
        if not s.get("relire_le"):
            continue
        r_ = d(s["relire_le"])
        fait = s.get("constat_le") and s["constat_le"][:10] >= s["relire_le"]
        if fait:
            continue
        u0 = s["url"].split()[0] if s["url"] else ""
        cible = (s["requete"] and f"la requête « {s['requete']} »" or u0.endswith("*") and f"les pages {u0}"
                 or u0 and f"la page {chemin(u0)}" or "le site")
        cal.append({"date": r_.isoformat(), "quoi": f"Relire « {s['ajustement'][:70]} » : {cible}, pas le total",
                    "en_retard": r_ < today})
    cal.append({"date": (today + dt.timedelta(days=7)).isoformat(),
                "quoi": ("Refaire l'export Performances (mode Comparer, 28 jours) et le déposer" if A["source"] == "export"
                         else "Rafraîchir le tableau de bord : « rafraîchis le dashboard »"), "en_retard": False})
    cal.append({"date": (L + dt.timedelta(days=30)).isoformat(),
                "quoi": "Revue du mois : une nouvelle fenêtre de 28 jours complète, à comparer à celle-ci", "en_retard": False})
    nonidx = A["indexation"]["non_indexees"]
    if nonidx:
        cal.append({"date": (today + dt.timedelta(days=7)).isoformat(),
                    "quoi": f"Ré-inspecter {len(nonidx)} page(s) non indexée(s)", "en_retard": False})
    A["calendrier"] = sorted(cal, key=lambda c_: c_["date"])

    with open(os.path.join(dossier, "analyse.json"), "w", encoding="utf-8") as f:
        json.dump(A, f, ensure_ascii=False, indent=1)
    print(resume(A))
    return A


REGIMES = {"etabli": "site établi : seuil de Poisson",
           "petit": "petit site : seuil élargi ×√2,5 (surdispersion), pas de verdict hebdo sur les clics",
           "neuf": "site neuf : les clics ne disent rien à ce volume, lis l'indexation"}


def ligne_test(nom, t):
    return f"- {nom} : {fr(t['apres'])} contre {fr(t['avant'])} → {fr(t['ecart'], True)} (seuil ±{fr(t['seuil'])}) : {t['verdict']}"


def resume(A):
    w1, w0 = [d(x) for x in A["w1"]], [d(x) for x in A["w0"]]
    K = A["kpis"]
    cov = A.get("couverture") or {}
    sem = K.get("clics_semaine")
    out = [
        f"SITE        : {A['site']} ({REGIMES[A['regime']]})",
        f"FENÊTRE     : {jj(w1[0])} → {jj(w1[1])} contre {jj(w0[0])} → {jj(w0[1])} (données finales ; dernier jour complet {jj(d(A['dernier_jour']))})",
        f"VOLUME      : {fr(round(K['clics_28j']['apres'] / 4))} clics/sem, {fr(round(K['impressions_28j']['apres'] / 4))} impressions/sem"
        + (f", {fr(cov['requetes_w1'])} requêtes visibles" if cov else ""),
        f"SEUIL       : ±{fr(K['clics_28j']['seuil'])} clics sur 28 j" + (f", ±{fr(sem['seuil'])} sur une semaine" if sem else ""),
        f"COUVERTURE  : " + (f"{round(100 * cov['part'])} % des impressions visibles en dimension requête" if cov.get("part") is not None else "inconnue"),
        "CHANGEMENTS : " + ("; ".join(f"{jj(d(s['en_ligne']))} {s['ajustement'][:50]}" for s in A["changements_fenetre"])
                            or "aucun dans le journal (vérifie aussi git log / les déploiements)"),
        "",
        ligne_test("Clics 28 j", K["clics_28j"]),
    ]
    if sem:
        out.append(ligne_test(f"Clics semaine du {jj(d(sem['semaine']))}", sem))
    out.append(ligne_test("Impressions 28 j", K["impressions_28j"]))
    pq = A["pages_qui_bougent"]
    if pq["testees"]:
        out.append(f"- Pages qui bougent (|z| > {Z_PAGES}) : {pq['hausses']} en hausse, {pq['baisses']} en baisse, sur {pq['testees']} pages à 10 clics ou plus")
        for v in [v for v in A["pages_testees"] if v["lecture"] != "bruit"]:
            out.append(f"    {v['lecture']:6} {chemin(v['page'])} : {v['clics_avant']} → {v['clics_apres']} (z {fr(v['z'])})")
    if A.get("alerte_appareils"):
        out.append("- ALERTE : " + A["alerte_appareils"])
    for t in A["demande"]:
        if "ratio" in t:
            out.append(f"- Demande ou classement, {t['segment']} : impressions ×{fr(t['ratio'])} [{fr(t['ratio_bas'])} ; {fr(t['ratio_haut'])}], "
                       f"position {fr(t['ecart_position'], True)} [{fr(t['position_bas'], True)} ; {fr(t['position_haut'], True)}] "
                       f"sur {t['requetes']} requêtes ({round(100 * (t['survie_impressions'] or 0))} % des impressions gardées) : {t['verdict']}")
        else:
            out.append(f"- Demande ou classement, {t['segment']} : {t['verdict']}")
    s = A["saison"]
    if s["lisible"] and s["ratio_impressions"]:
        out.append(f"- Il y a un an, mêmes semaines : impressions ×{fr(s['ratio_impressions'])}")
    else:
        out.append("- Saison : l'an dernier n'a pas assez de volume pour comparer")
    ix = A["indexation"]
    if ix["inspectees"]:
        out.append(f"- Indexation : {ix['indexees']}/{ix['inspectees']} pages inspectées indexées ; sitemap {ix['urls_sitemap']} URL, "
                   f"{ix['sitemap_vues']} vues dans Google sur 28 j")
        for r in ix["non_indexees"][:10]:
            out.append(f"    {chemin(r['url'])} : {r['couverture'] or r['verdict']} (dernier crawl {r['dernier_crawl'][:10] or 'jamais'})")
    if A["chevauchements_total"]:
        out.append(f"- Chevauchements : {A['chevauchements_total']} requêtes servies par 2 pages ou plus (constat structurel, pas un coût mesuré)")
    for s_ in A["suivi"]:
        out.append(f"- Suivi « {s_['ajustement'][:60]} » (J+{s_.get('j', '?')}) : {s_.get('etat')}"
                   + (f" ; {s_['indexation']}" if s_.get("indexation") else "")
                   + (f" ; requête {s_['requete_vue']}" if s_.get("requete_vue") else ""))
    out.append("")
    out.append("CALENDRIER :")
    for c_ in A["calendrier"]:
        out.append(f"  {jj(d(c_['date']))}{' (en retard)' if c_['en_retard'] else ''} : {c_['quoi']}")
    if A.get("manque"):
        out.append("")
        out.append("CE QUI MANQUE (export) : " + " ; ".join(A["manque"]))
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
