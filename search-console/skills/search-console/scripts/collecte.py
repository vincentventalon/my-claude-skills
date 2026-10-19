#!/usr/bin/env python3
"""Récupère les données Search Console d'un site dans <dossier>/<domaine>/donnees/.

Usage : python3 collecte.py monsite.com [--dossier ./seo] [--sans-inspection]

Ne juge rien : analyse.py calcule, tableau.py rend la page.
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsc_api as g  # noqa: E402

JOURNAL_COLS = ["en_ligne", "ajustement", "url", "attendu_index", "requete", "attendu", "relire_le", "statut",
                "constat", "constat_le"]
GROUPES_COLS = ["motif", "groupe"]


def iso(d):
    return d.isoformat()


def ecrire(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def lignes(rows, n_keys):
    return [r["keys"][:n_keys] + [int(r["clicks"]), int(r["impressions"]), round(r["position"], 2)] for r in rows]


def lire_journal(site_dir):
    path = os.path.join(site_dir, "journal.csv")
    if not os.path.exists(path):
        ecrire(path, JOURNAL_COLS, [])
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        h = next(rd, None) or JOURNAL_COLS
        out = []
        for n, row in enumerate(rd, 2):
            if not any(c.strip() for c in row):
                continue
            if len(row) != len(h):
                raise g.Panne(f"{path}, ligne {n} : {len(row)} colonnes au lieu de {len(h)}. "
                              "Mets entre guillemets tout champ qui contient une virgule.")
            out.append(dict(zip(h, row)))
        return out


def urls_sitemap(url, vus=None, profondeur=0):
    vus = vus if vus is not None else set()
    if url in vus or profondeur > 2:
        return []
    vus.add(url)
    req = urllib.request.Request(url, headers={"User-Agent": "skill-search-console/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        import gzip
        raw = gzip.decompress(raw)
    xml = raw.decode("utf-8", "replace")
    locs = [l.strip() for l in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml)]
    if "<sitemapindex" in xml:
        return [u for sub in locs for u in urls_sitemap(sub, vus, profondeur + 1)]
    return locs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", help="monsite.com, https://monsite.com/ ou sc-domain:monsite.com")
    ap.add_argument("--dossier", help="dossier racine des données (défaut ./seo)")
    ap.add_argument("--sans-inspection", action="store_true", help="ne pas appeler l'inspection d'URL")
    ap.add_argument("--inspection-max", type=int, default=150, help="nombre max d'URL inspectées (quota : 2 000/jour)")
    a = ap.parse_args(argv)

    root = g.racine(a.dossier)
    site = g.resoudre_site(a.site)
    site_dir = os.path.join(root, g.nom_dossier(site))
    out = os.path.join(site_dir, "donnees")
    os.makedirs(out, exist_ok=True)
    journal = lire_journal(site_dir)
    if not os.path.exists(os.path.join(site_dir, "groupes.csv")):
        ecrire(os.path.join(site_dir, "groupes.csv"), GROUPES_COLS, [])
    print(f"Propriété {site} -> {site_dir}")

    today = dt.date.today()
    # Totaux par jour sur 16 mois, données finales : le dernier jour rendu est le dernier jour complet.
    rows, _ = g.recherche(site, iso(today - dt.timedelta(days=490)), iso(today), ["date"], data_state="final")
    if not rows:
        raise g.Panne(f"{site} ne renvoie aucune donnée de recherche (site trop neuf, ou propriété vide).")
    jours = lignes(rows, 1)
    ecrire(os.path.join(out, "jours.csv"), ["date", "clics", "impressions", "position"], jours)
    L = dt.date.fromisoformat(max(r[0] for r in jours))
    # Les jours provisoires (dataState all), pour information seulement.
    prov, meta = g.recherche(site, iso(L + dt.timedelta(days=1)), iso(today), ["date"], data_state="all")
    ecrire(os.path.join(out, "jours_provisoires.csv"), ["date", "clics", "impressions", "position"], lignes(prov, 1))

    w1 = (L - dt.timedelta(days=27), L)
    w0 = (L - dt.timedelta(days=55), L - dt.timedelta(days=28))
    debut_pages = L - dt.timedelta(days=17 * 7 - 1)
    print(f"  dernier jour complet : {L} · fenêtre {w1[0]} → {w1[1]} contre {w0[0]} → {w0[1]}")

    rows, _ = g.recherche(site, iso(debut_pages), iso(L), ["date", "page"], data_state="final")
    ecrire(os.path.join(out, "pages_jours.csv"), ["date", "page", "clics", "impressions", "position"], lignes(rows, 2))
    print(f"  pages par jour : {len(rows)} lignes")

    for nom, (d, f) in (("w1", w1), ("w0", w0)):
        for dims, fichier, cols in ((["query"], "requetes", ["requete"]),
                                    (["query", "page"], "requetes_pages", ["requete", "page"]),
                                    (["query", "country"], "requetes_pays", ["requete", "pays"]),
                                    (["query", "device"], "requetes_appareils", ["requete", "appareil"]),
                                    (["country"], "pays", ["pays"]),
                                    (["device"], "appareils", ["appareil"])):
            rows, _ = g.recherche(site, iso(d), iso(f), dims, data_state="final")
            ecrire(os.path.join(out, f"{fichier}_{nom}.csv"), cols + ["clics", "impressions", "position"],
                   lignes(rows, len(dims)))
    print("  requêtes, pays et appareils : ok")

    # Les requêtes du journal, jour par jour (un filtre exact par requête).
    suivi = []
    for q in sorted({e.get("requete", "").strip() for e in journal if e.get("requete", "").strip()}):
        rows, _ = g.recherche(site, iso(debut_pages), iso(L), ["date"], data_state="final",
                              filtres=[{"dimension": "query", "operator": "equals", "expression": q}])
        suivi += [[q] + r for r in lignes(rows, 1)]
    ecrire(os.path.join(out, "suivi_requetes.csv"), ["requete", "date", "clics", "impressions", "position"], suivi)

    # Sitemaps déclarés dans Search Console, et leurs URL.
    sm_urls, sm_info = [], []
    try:
        for s in g.sitemaps(site):
            sm_info.append({"path": s.get("path"), "lastDownloaded": s.get("lastDownloaded"),
                            "errors": s.get("errors"), "warnings": s.get("warnings"),
                            "submitted": sum(int(c.get("submitted", 0)) for c in s.get("contents", []))})
            try:
                sm_urls += urls_sitemap(s["path"])
            except Exception as e:  # un sitemap illisible ne bloque pas le reste
                sm_info[-1]["lecture"] = f"illisible : {e}"
    except g.Panne as e:
        sm_info.append({"erreur": str(e)})
    sm_urls = list(dict.fromkeys(sm_urls))

    meta = {"site": site, "collecte_le": dt.datetime.now().isoformat(timespec="seconds"), "source": "api",
            "dernier_jour": iso(L), "w1": [iso(w1[0]), iso(w1[1])], "w0": [iso(w0[0]), iso(w0[1])],
            "debut_pages": iso(debut_pages), "sitemaps": sm_info, "urls_sitemap": len(sm_urls)}

    inspection = []
    if not a.sans_inspection:
        cibles = {}
        for e in journal:
            for u in e.get("url", "").split():
                if u.endswith("*"):
                    for s in sm_urls:
                        if s.startswith(u[:-1]):
                            cibles.setdefault(s, "journal")
                else:
                    cibles.setdefault(u, "journal")
        clics_w1 = sum(int(r[1]) for r in jours if w1[0].isoformat() <= r[0])
        vues = set()
        with open(os.path.join(out, "pages_jours.csv"), newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["date"] >= iso(w1[0]) and int(r["impressions"]) > 0:
                    vues.add(r["page"])
        for s in sm_urls:
            # Site établi : seulement les pages du sitemap sans aucune impression sur 28 j.
            if clics_w1 < 200 or s not in vues:
                cibles.setdefault(s, "sitemap")
        cibles = dict(list(cibles.items())[:a.inspection_max])
        print(f"  inspection d'URL : {len(cibles)} pages…")
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        def une(item):
            u, pourquoi = item
            try:
                ir = g.inspecter(site, u)
            except g.Panne as e:
                ir = {"verdict": "ERREUR", "coverageState": str(e).splitlines()[0][:160]}
            return [u, pourquoi, "oui" if u in sm_urls else "non", ir.get("verdict", ""), ir.get("coverageState", ""),
                    ir.get("lastCrawlTime", ""), ir.get("googleCanonical", ""), ir.get("userCanonical", ""), now]

        with ThreadPoolExecutor(4) as ex:
            inspection = list(ex.map(une, cibles.items()))
        erreurs = [r for r in inspection if r[3] == "ERREUR"]
        if erreurs:
            print(f"  ! {len(erreurs)} inspection(s) en échec, ex. : {erreurs[0][4]}")
    ecrire(os.path.join(out, "index.csv"), ["url", "pourquoi", "dans_sitemap", "verdict", "couverture", "dernier_crawl",
                                            "canonique_google", "canonique_declaree", "inspecte_le"], inspection)
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "sitemap_urls.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sm_urls))
    g.retenir(root)
    print("Collecte terminée.")
    return site_dir


if __name__ == "__main__":
    try:
        main()
    except g.Panne as e:
        sys.exit("ERREUR : " + str(e))
