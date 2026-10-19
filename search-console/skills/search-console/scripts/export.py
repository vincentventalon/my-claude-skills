#!/usr/bin/env python3
"""Mode sans API : convertit l'export du rapport Performances de Search Console (zip ou dossier de CSV)
au format de collecte.py, pour qu'analyse.py et tableau.py fassent le reste.

Usage : python3 export.py export.zip --site monsite.com [--dossier ./seo]
Puis   : python3 analyse.py ./seo/monsite.com && python3 tableau.py ./seo/monsite.com
(rapport.py --export export.zip --site monsite.com enchaîne les trois)

L'export contient : les totaux par jour (Graphique/Chart), et jusqu'à 1 000 lignes de requêtes, pages,
pays et appareils. En mode « Comparer » (deux périodes), chaque tableau porte les deux périodes.
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsc_api as g  # noqa: E402

TYPES = {
    "jours": ("date",),
    "pages": ("pages les plus populaires", "top pages", "page", "pages"),
    "requetes": ("requêtes les plus fréquentes", "top queries", "requête", "requêtes", "query", "queries"),
    "pays": ("pays", "country", "countries"),
    "appareils": ("appareil", "device", "devices"),
    "filtres": ("filtre", "filter"),
}
COLS = {"pages": "page", "requetes": "requete", "pays": "pays", "appareils": "appareil"}
PAYS = {"france": "fra", "malte": "mlt", "malta": "mlt", "royaume-uni": "gbr", "united kingdom": "gbr",
        "états-unis": "usa", "united states": "usa", "allemagne": "deu", "germany": "deu", "belgique": "bel",
        "belgium": "bel", "suisse": "che", "switzerland": "che", "canada": "can", "italie": "ita", "italy": "ita",
        "espagne": "esp", "spain": "esp", "inde": "ind", "india": "ind", "pays-bas": "nld", "netherlands": "nld"}


def nombre(x):
    x = (x or "").strip().replace(" ", "").replace(" ", "").replace("%", "")
    if not x:
        return 0.0
    if x.count(",") == 1 and "." not in x:
        x = x.replace(",", ".")
    return float(x.replace(",", ""))


def lire_fichiers(chemin):
    out = {}
    if os.path.isdir(chemin):
        for nom in os.listdir(chemin):
            if nom.lower().endswith(".csv"):
                with open(os.path.join(chemin, nom), encoding="utf-8-sig") as f:
                    out[nom] = f.read()
    elif zipfile.is_zipfile(chemin):
        with zipfile.ZipFile(chemin) as z:
            for nom in z.namelist():
                if nom.lower().endswith(".csv"):
                    out[os.path.basename(nom)] = z.read(nom).decode("utf-8-sig")
    else:
        raise g.Panne(f"{chemin} : ni un zip, ni un dossier. Exporte le rapport Performances en « Télécharger CSV ».")
    if not out:
        raise g.Panne(f"Aucun CSV dans {chemin}. Choisis l'export CSV (pas Google Sheets ni Excel).")
    return out


def type_de(entete):
    h = entete[0].strip().lower()
    for t, noms in TYPES.items():
        if h in noms:
            return t
    return None


def colonnes(entete):
    """Repère les colonnes clics / impressions / position, une ou deux périodes."""
    res = {"clics": [], "impressions": [], "position": []}
    for i, h in enumerate(entete[1:], 1):
        l = h.lower()
        k = "clics" if ("clic" in l or "click" in l) else "impressions" if "impression" in l else "position" if "position" in l else None
        if k:
            prec = bool(re.search(r"précédent|precedent|previous|avant|prior", l))
            res[k].append((i, prec))
    comparaison = len(res["clics"]) >= 2

    def idx(k, prec):
        c = res[k]
        if not c:
            return None
        if len(c) == 1:
            return c[0][0]
        marques = [i for i, p in c if p == prec]
        return marques[0] if marques else (c[1][0] if prec else c[0][0])
    return comparaison, idx


def convertir(chemin, site, root):
    if not site:
        raise g.Panne("Précise le site : --site monsite.com")
    fichiers = lire_fichiers(chemin)
    tables, filtres = {}, {}
    for nom, txt in fichiers.items():
        rows = list(csv.reader(io.StringIO(txt)))
        if not rows:
            continue
        t = type_de(rows[0])
        if t == "filtres":
            filtres = {r[0]: r[1] for r in rows[1:] if len(r) >= 2}
        elif t:
            tables[t] = rows
    if "jours" not in tables:
        raise g.Panne("L'export n'a pas de tableau par date (Graphique.csv / Chart.csv). Refais l'export depuis le rapport Performances.")

    nom_site = site.replace("sc-domain:", "").replace("https://", "").replace("http://", "").strip("/")
    dossier = os.path.join(root, nom_site)
    out = os.path.join(dossier, "donnees")
    os.makedirs(out, exist_ok=True)
    for f_, cols in (("journal.csv", "en_ligne,ajustement,url,attendu_index,requete,attendu,relire_le,statut,constat,constat_le"),
                     ("groupes.csv", "motif,groupe")):
        if not os.path.exists(os.path.join(dossier, f_)):
            with open(os.path.join(dossier, f_), "w", encoding="utf-8") as fh:
                fh.write(cols + "\n")

    # Totaux par jour.
    entete = tables["jours"][0]
    comp, idx = colonnes(entete)
    jours = []
    lignes_j = [r for r in tables["jours"][1:] if r and re.match(r"\d{4}-\d{2}-\d{2}", r[0])]
    for r in lignes_j:
        jours.append([r[0], int(nombre(r[idx("clics", False)])), int(nombre(r[idx("impressions", False)])),
                      round(nombre(r[idx("position", False)]), 2) if idx("position", False) else 0])
    if comp:
        # Mode Comparer : la période précédente est sur les mêmes lignes, décalée de la durée de la période.
        n = len(lignes_j)
        for r in lignes_j:
            jd = (dt.date.fromisoformat(r[0][:10]) - dt.timedelta(days=n)).isoformat()
            jours.append([jd, int(nombre(r[idx("clics", True)])), int(nombre(r[idx("impressions", True)])),
                          round(nombre(r[idx("position", True)]), 2) if idx("position", True) else 0])
    jours.sort()
    with open(os.path.join(out, "jours.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "clics", "impressions", "position"])
        w.writerows(jours)
    L = dt.date.fromisoformat(jours[-1][0])
    w1 = (L - dt.timedelta(days=27), L)
    w0 = (L - dt.timedelta(days=55), L - dt.timedelta(days=28))

    periode = " ".join(v for k_, v in filtres.items() if k_.lower() in ("date", "dates"))
    manque = ["pas d'inspection d'URL : l'indexation ne se lit pas (rapport Pages de Search Console à regarder à la main)",
              "pas de croisement requête × page : pas de détection des requêtes servies par plusieurs pages",
              "pas de détail jour par jour par page ou par requête : le journal des changements ne se mesure pas",
              "1 000 lignes au plus par tableau"]
    tables_comp = False
    for t in ("pages", "requetes", "pays", "appareils"):
        if t not in tables:
            continue
        ent = tables[t][0]
        comp_t, idx_t = colonnes(ent)
        for suffixe, prec in (("w1", False), ("w0", True)) if comp_t else (("periode", False),):
            with open(os.path.join(out, f"{t}_{suffixe}.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([COLS[t], "clics", "impressions", "position"])
                for r in tables[t][1:]:
                    if not r or not r[0]:
                        continue
                    cle = PAYS.get(r[0].strip().lower(), r[0].strip().lower()) if t == "pays" else r[0].strip()
                    w.writerow([cle, int(nombre(r[idx_t("clics", prec)])), int(nombre(r[idx_t("impressions", prec)])),
                                round(nombre(r[idx_t("position", prec)]), 2) if idx_t("position", prec) else 0])
        tables_comp = tables_comp or comp_t
    if not tables_comp:
        manque.append("export sans comparaison : pages, requêtes et pays ne se comparent pas entre deux périodes. "
                      "Refais l'export avec « Comparer » sur les 28 derniers jours contre la période précédente")
    elif "28" not in periode:
        manque.append(f"les tableaux comparent les périodes de ton export ({periode or 'inconnues'}), pas forcément les 28 jours du haut de page")
    manque.append("totaux par jour : seulement la période exportée"
                  + (f" ({periode})" if periode else "") + ", donc pas de saison si elle fait moins de 13 mois")

    meta = {"site": "sc-domain:" + nom_site, "source": "export", "collecte_le": dt.datetime.now().isoformat(timespec="seconds"),
            "dernier_jour": L.isoformat(), "w1": [w1[0].isoformat(), w1[1].isoformat()],
            "w0": [w0[0].isoformat(), w0[1].isoformat()], "periode_export": periode, "manque": manque, "sitemaps": []}
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"Export converti : {len(jours)} jours, tableaux {', '.join(sorted(tables))} -> {dossier}")
    return dossier


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export")
    ap.add_argument("--site", required=True)
    ap.add_argument("--dossier")
    a = ap.parse_args()
    try:
        convertir(a.export, a.site, g.racine(a.dossier))
    except g.Panne as e:
        sys.exit("ERREUR : " + str(e))
