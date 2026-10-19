#!/usr/bin/env python3
"""Une commande : récupère, analyse, rend le tableau de bord.

  python3 rapport.py monsite.com            premier compte rendu (crée ./seo/monsite.com/)
  python3 rapport.py                        rafraîchit tous les sites de ./seo/
                                            (ou du dernier dossier ./seo utilisé, si on est ailleurs)
Options : --dossier ./seo · --sans-inspection · --resume "texte" (refait juste la page)
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import gsc_api as g  # noqa: E402
import tableau  # noqa: E402


def sites_du_dossier(root):
    return sorted(os.path.dirname(os.path.dirname(p)) for p in glob.glob(os.path.join(root, "*", "donnees", "meta.json")))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sites", nargs="*", help="un ou plusieurs sites ; rien = rafraîchir ceux déjà suivis")
    ap.add_argument("--dossier", help="dossier des données (défaut ./seo)")
    ap.add_argument("--sans-inspection", action="store_true")
    ap.add_argument("--resume", help="texte d'en-tête : refait seulement la page, sans rappeler l'API")
    a = ap.parse_args()
    root = g.racine(a.dossier)

    if a.resume:
        cibles = [os.path.join(root, g.nom_dossier(s if s.startswith("sc-domain:") or "//" in s else "sc-domain:" + s.lower()))
                  for s in a.sites] or sites_du_dossier(root)
        if len(cibles) != 1:
            sys.exit("--resume vise un seul site : précise lequel.")
        tableau.main([cibles[0], "--resume", a.resume])
        return

    sites = list(a.sites)
    if not sites:
        dossiers = sites_du_dossier(root)
        if not dossiers and not a.dossier:
            for autre in g.dossiers_connus():
                if sites_du_dossier(autre):
                    root = g.racine(autre)
                    dossiers = sites_du_dossier(root)
                    print(f"Pas de dossier seo/ ici : je rafraîchis {root} (le dernier utilisé).")
                    break
        if not dossiers:
            sys.exit("Aucun site suivi pour l'instant. Donne le site : python3 rapport.py monsite.com")
        for dsite in dossiers:
            with open(os.path.join(dsite, "donnees", "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
            sites.append(meta["site"])

    import collecte
    for s in sites:
        args = [s, "--dossier", root] + (["--sans-inspection"] if a.sans_inspection else [])
        dossier = collecte.main(args)
        print()
        analyse.main(dossier)
        print()
        tableau.main([dossier])
        print()


if __name__ == "__main__":
    try:
        main()
    except g.Panne as e:
        sys.exit("ERREUR : " + str(e))
