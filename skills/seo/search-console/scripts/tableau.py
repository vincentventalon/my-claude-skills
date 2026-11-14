#!/usr/bin/env python3
"""Rend le tableau de bord : une page HTML autonome (hors ligne, téléphone, SVG inline).

Usage : python3 tableau.py <dossier du site> [--resume "deux ou trois phrases"]
Lit <dossier>/analyse.json (et <dossier>/resume.txt s'il existe), écrit <dossier>/tableau-de-bord.html.
"""
import argparse
import datetime as dt
import html
import json
import math
import os
import urllib.parse

MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)"]


def e(x):
    return html.escape("" if x is None else str(x))


def d(s):
    return dt.date.fromisoformat(s[:10])


def jour(s):
    x = d(s)
    return f"{x.day} {MOIS[x.month - 1]}"


def jm(s):
    x = d(s)
    return f"{x.day:02d}/{x.month:02d}"


def n(x, signe=False, dec=0):
    if x is None:
        return "n/a"
    if dec:
        s = f"{x:+.{dec}f}" if signe else f"{x:.{dec}f}"
        return s.replace(".", ",").replace("-", "−")
    s = f"{int(round(x)):+,}" if signe else f"{int(round(x)):,}"
    return s.replace(",", " ").replace("-", "−")


def court(url):
    p = urllib.parse.urlparse(url)
    return (p.path or "/") + (("?" + p.query) if p.query else "")


def pill(verdict):
    v = verdict or ""
    if v.startswith("hausse") or v.startswith("amélioration") or v in ("tenu", "hausse", "indexée") or v.startswith("requête vue"):
        cls, ico = "good", "▲"
    elif v.startswith("baisse") or v.startswith("régression") or v in ("pas tenu", "baisse"):
        cls, ico = "bad", "▼"
    elif v.startswith("pas de régression"):
        cls, ico = "ok", "●"
    else:
        cls, ico = "muted", "○"
    return f'<span class="pill pill-{cls}"><span aria-hidden="true">{ico}</span> {e(v)}</span>'


# ---------- graphes ----------

def barres_empilees(semaines, groupes, metrique_idx, reperes, hauteur=220):
    """Deux SVG du même graphe : large (écran) et étroit (téléphone), l'un ou l'autre selon la largeur."""
    if not semaines:
        return '<p class="note">Pas encore de semaine complète.</p>'
    large = _barres(semaines, groupes, metrique_idx, reperes, 640, hauteur, "wide")
    etroit = _barres(semaines[-10:], groupes, metrique_idx, reperes, 340, 210, "narrow")
    leg = "".join(f'<span><i style="background:{SERIES[i] if g != "autres" else "var(--s-autres)"}"></i>{e(g)}</span>'
                  for i, g in enumerate(groupes)) if len(groupes) > 1 else ""
    return f'<div class="legend">{leg}<span><i class="dash"></i>mise en ligne (journal)</span></div>' + large + etroit


def _barres(semaines, groupes, metrique_idx, reperes, W, hauteur, cls):
    H, ml, mr, mt, mb = hauteur, 40, 6, 12, 26
    tot = [sum(s[g][metrique_idx] for g in groupes) for s in semaines]
    vmax = max(tot + [1])
    pas = 10 ** math.floor(math.log10(vmax)) if vmax >= 10 else 1
    for m in (1, 2, 2.5, 5, 10):
        if vmax / (pas * m) <= 5:
            pas *= m
            break
    top = math.ceil(vmax / pas) * pas
    bw = (W - ml - mr) / len(semaines)
    y = lambda v: mt + (H - mt - mb) * (1 - v / top)
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" class="{cls}" role="img" aria-label="Barres par semaine">']
    v = 0
    while v <= top + 1e-9:
        out.append(f'<line x1="{ml}" x2="{W - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                   f'<text x="{ml - 6}" y="{y(v) + 4:.1f}" class="ax" text-anchor="end">{n(v)}</text>')
        v += pas
    for i, s in enumerate(semaines):
        x = ml + i * bw + 2
        base = 0
        tip = [f"Semaine du {jour(s['semaine'])}"]
        for gi, g in enumerate(groupes):
            val = s[g][metrique_idx]
            if val <= 0:
                continue
            y1, y0 = y(base + val), y(base)
            col = SERIES[gi] if g != "autres" else "var(--s-autres)"
            out.append(f'<rect x="{x:.1f}" y="{y1:.1f}" width="{bw - 4:.1f}" height="{max(0, y0 - y1 - 1):.1f}" '
                       f'fill="{col}" rx="1.5"/>')
            base += val
            tip.append(f"{g} : {n(val)}")
        tip.append(f"total : {n(base)}")
        out.append(f'<rect x="{x - 2:.1f}" y="{mt}" width="{bw:.1f}" height="{H - mt - mb}" class="hit" '
                   f'data-tip="{e(" · ".join(tip))}"/>')
        if (len(semaines) - 1 - i) % max(1, round(len(semaines) / (6 if W > 400 else 4))) == 0:
            out.append(f'<text x="{x + (bw - 4) / 2:.1f}" y="{H - 8}" class="ax" text-anchor="middle">{jm(s["semaine"])}</text>')
    debut = d(semaines[0]["semaine"])
    fin = d(semaines[-1]["semaine"]) + dt.timedelta(days=7)
    for date, lib in reperes:
        x0 = d(date)
        if not (debut <= x0 < fin):
            continue
        xr = ml + (x0 - debut).days / 7 * bw
        out.append(f'<line x1="{xr:.1f}" x2="{xr:.1f}" y1="{mt}" y2="{H - mb}" class="repere"/>'
                   f'<rect x="{xr - 6:.1f}" y="{mt}" width="12" height="{H - mt - mb}" class="hit" data-tip="{e(jm(date) + " : " + lib)}"/>')
    out.append("</svg>")
    return "".join(out)


def intervalle(val, lo, hi, ref, span, fmt):
    """Petit graphe : point + intervalle à 95 % autour d'une ligne de référence."""
    W, H = 150, 22
    a, b = ref - span, ref + span
    x = lambda v: 6 + (W - 12) * (min(max(v, a), b) - a) / (b - a)
    touche = lo <= ref <= hi
    col = "var(--muted)" if touche else "var(--fg)"
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" class="ci" role="img" '
            f'aria-label="{e(fmt(val))}, intervalle {e(fmt(lo))} à {e(fmt(hi))}">'
            f'<line x1="{x(ref):.1f}" x2="{x(ref):.1f}" y1="2" y2="{H - 2}" class="ref"/>'
            f'<line x1="{x(lo):.1f}" x2="{x(hi):.1f}" y1="{H / 2}" y2="{H / 2}" stroke="{col}" stroke-width="2"/>'
            f'<circle cx="{x(val):.1f}" cy="{H / 2}" r="4" fill="{col}" stroke="var(--panel)" stroke-width="2"/></svg>')


# ---------- blocs ----------

def carte_kpi(titre, t, sous=None):
    if t is None:
        return ""
    return (f'<div class="card kpi"><div class="kpi-label">{e(titre)}</div>'
            f'<div class="kpi-value">{n(t["apres"])}</div>'
            f'<div class="kpi-sub"><b>{n(t["ecart"], True)}</b> contre {n(t["avant"])} avant · seuil ±{n(t["seuil"])}</div>'
            f'<div class="kpi-sub">{pill(t["verdict"])}</div>'
            + (f'<div class="kpi-note">{e(sous)}</div>' if sous else "") + "</div>")


def carte_simple(titre, valeur, sous, note=None):
    return (f'<div class="card kpi"><div class="kpi-label">{e(titre)}</div><div class="kpi-value">{valeur}</div>'
            f'<div class="kpi-sub">{sous}</div>' + (f'<div class="kpi-note">{e(note)}</div>' if note else "") + "</div>")


def table(entetes, lignes, classes=None, id_=None):
    classes = classes or [""] * len(entetes)
    th = "".join(f'<th class="{c}"><button type="button">{e(h)}</button></th>' for h, c in zip(entetes, classes))
    trs = "".join("<tr>" + "".join(f'<td class="{c}">{v}</td>' for v, c in zip(l, classes)) + "</tr>" for l in lignes)
    return f'<div class="tablebox"><table class="sortable"{f" id={chr(34)}{id_}{chr(34)}" if id_ else ""}><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def section(id_, titre, corps, note=None, ouvert=True):
    return (f'<section class="card" id="{id_}"><h2>{e(titre)}</h2>'
            + (f'<p class="note">{note}</p>' if note else "") + corps + "</section>")


def rendre(A, resume):
    reg = A["regime"]
    K = A["kpis"]
    neuf = reg == "neuf"
    dom = A["site"].replace("sc-domain:", "")
    reperes = [(s["en_ligne"], s["ajustement"]) for s in A.get("suivi", []) if s.get("en_ligne")]
    k_txt = "1,96 × √(avant + après)" if A["k"] == 1 else "1,96 × √(2,5 × (avant + après))"
    w1, w0 = A["w1"], A["w0"]
    if not resume:
        resume = {"etabli": "Site établi : les écarts se lisent au seuil de Poisson. Chaque chiffre porte son seuil ; ce qui ne le dépasse pas est du bruit.",
                  "petit": "Petit site : seuil élargi pour la surdispersion, aucune lecture à la semaine sur les clics.",
                  "neuf": "Site neuf : à ce volume, les comparaisons de clics et d'impressions ne sont pas lisibles. Ce qui se lit tout de suite, c'est l'indexation : quelles pages Google connaît, lesquelles il garde."}[reg]

    parts = [f'<header class="head"><h1>SEO de {e(dom)}</h1><p class="take">{e(resume)}</p>'
             f'<p class="asof">Google Search Console, données finales jusqu\'au {jour(A["dernier_jour"])} {d(A["dernier_jour"]).year} · '
             f'28 jours du {jm(w1[0])} au {jm(w1[1])} contre {jm(w0[0])} → {jm(w0[1])} · généré le {jour(A["genere_le"])}</p></header>']

    # Les quatre chiffres.
    ix = A["indexation"]
    cartes = [carte_kpi(f"Clics, 28 jours ({jm(w1[0])} → {jm(w1[1])})", K["clics_28j"])]
    if neuf:
        cartes.append(carte_kpi("Impressions, 28 jours", K["impressions_28j"]))
        cartes.append(carte_simple("Pages inspectées indexées", f'{ix["indexees"]}<small>/{ix["inspectees"]}</small>',
                                   f'{ix["urls_sitemap"]} URL dans le sitemap',
                                   "Un fait oui/non, lisible tout de suite."))
        cartes.append(carte_simple("Pages du sitemap vues dans Google", f'{ix["sitemap_vues"]}<small>/{ix["urls_sitemap"]}</small>',
                                   "au moins une impression sur 28 jours"))
    else:
        s = K.get("clics_semaine")
        if s:
            cartes.append(carte_kpi(f"Clics, semaine du {jm(s['semaine'])}", s,
                                    "Une semaine hors du seuil ne fait pas une tendance : relis la suivante avant d'agir."))
        cartes.append(carte_kpi("Impressions, 28 jours", K["impressions_28j"]))
        pq = A["pages_qui_bougent"]
        cartes.append(carte_simple("Pages qui bougent vraiment (|z| > 3)",
                                   f'<span class="good">{pq["hausses"]}</span> <small>en hausse</small> · <span class="bad">{pq["baisses"]}</span> <small>en baisse</small>',
                                   f'sur {pq["testees"]} pages à 10 clics ou plus'))
    parts.append('<section class="kpis">' + "".join(cartes) + "</section>")
    if A.get("alerte_appareils"):
        parts.append(f'<p class="alerte" role="note"><b>Attention</b> · {e(A["alerte_appareils"])}</p>')

    # Clics (ou impressions) par semaine.
    hg = A.get("hebdo_groupes")
    idx_m = 1 if neuf else 0
    if hg and hg["semaines"] and not neuf:
        graphe = barres_empilees(hg["semaines"], hg["groupes"], idx_m, reperes)
        note = ("Semaines du lundi au dimanche, la semaine en cours est exclue. Somme des pages : Google compte un peu autrement que le total du site. "
                + ("« pages neuves » : vues pour la première fois depuis le " + jm(w0[0]) + ". Leur montée peut cacher une baisse du stock." if any(g == "pages neuves" for g in hg["groupes"]) else "")
                + (" Groupes par défaut ; pour tes propres groupes (un cluster, un type de page), remplis groupes.csv." if A.get("groupes_auto") else ""))
    else:
        sem = [{"semaine": h["semaine"], "total": [h["clics"], h["impressions"]]} for h in A["hebdo"]]
        graphe = barres_empilees(sem, ["total"], idx_m, reperes)
        note = "Semaines du lundi au dimanche, la semaine en cours est exclue." + (" Impressions plutôt que clics : à ce volume, les clics ne montrent rien." if neuf else "")
    parts.append(section("semaines", "Impressions par semaine" if neuf else "Clics par semaine", f'<div class="chart">{graphe}</div>', e(note)))

    blocs = []

    # Pages qui bougent.
    if not neuf and A["pages_testees"]:
        rows = sorted(A["pages_testees"], key=lambda v: (v["lecture"] == "bruit", -abs(v["z"])))
        ligne = lambda v: [f'<span class="url">{e(court(v["page"]))}</span>', e(v["groupe"]), n(v["clics_avant"]), n(v["clics_apres"]),
                           n(v["ecart"], True), n(v["z"], True, 1), pill(v["lecture"]) if v["lecture"] != "bruit" else '<span class="muted">bruit</span>',
                           n(v["position_apres"], False, 1) if v["position_apres"] else "n/a"]
        ent = ["Page", "Groupe", "Avant", "Après", "Écart", "z", "Lecture", "Position"]
        cls = ["", "", "num", "num", "num", "num", "", "num"]
        bougent = [v for v in rows if v["lecture"] != "bruit"]
        bruit = [v for v in rows if v["lecture"] == "bruit"]
        corps = table(ent, [ligne(v) for v in bougent], cls) if bougent else "<p>Aucune page ne sort du bruit.</p>"
        if bruit:
            corps += (f'<details><summary>Les {len(bruit)} autres pages testées (bruit)</summary>'
                      + table(ent, [ligne(v) for v in bruit], cls) + "</details>")
        extra = ""
        if A["pages_apparues"]:
            extra += "<h3>Pages apparues sur la fenêtre</h3><ul class=\"liste\">" + "".join(
                f'<li><span class="url">{e(court(v["page"]))}</span> · {n(v["imp_apres"])} impressions, {n(v["clics_apres"])} clics, vue le {jm(v["premiere"])}</li>'
                for v in A["pages_apparues"]) + "</ul>"
        if A["pages_disparues"]:
            extra += "<h3>Pages disparues (0 impression sur la fenêtre)</h3><ul class=\"liste\">" + "".join(
                f'<li><span class="url">{e(court(v["page"]))}</span> · {n(v["imp_avant"])} impressions avant</li>' for v in A["pages_disparues"]) + "</ul>"
        blocs.append(section("pages", "Pages, 28 jours contre 28 jours", corps + extra,
                             f"Écart de clics par page, z = écart / √(avant + après). Avec {len(rows)} pages testées, quelques dépassements de 1,96 arrivent par hasard : seule une page à |z| au-delà de 3 compte. "
                             "La position moyenne d'une page dépend des requêtes du moment : elle sert de repère, pas de preuve."))

    # Demande ou classement.
    tests = [t for t in A.get("demande", []) if "ratio" in t]
    if tests:
        span = max(3, math.ceil(max(max(abs(t["position_bas"]), abs(t["position_haut"])) for t in tests) + 0.5))
        lignes = []
        for t in tests:
            lignes.append(
                f'<div class="dem"><div class="dem-seg"><b>{e(t["segment"])}</b> <small class="muted">{n(t["requetes"])} requêtes, '
                f'{round(100 * (t["survie_impressions"] or 0))} % des impressions gardées</small></div>'
                f'<div class="dem-ci"><span class="muted small">Impressions par requête</span><span class="civ">×{n(t["ratio"], False, 2)} '
                + intervalle(t["ratio"], t["ratio_bas"], t["ratio_haut"], 1, 0.6, lambda v: f"×{v:.2f}")
                + f'<small class="muted">{n(t["ratio_bas"], False, 2)} à {n(t["ratio_haut"], False, 2)}</small></span></div>'
                f'<div class="dem-ci"><span class="muted small">Écart de position</span><span class="civ">{n(t["ecart_position"], True, 1)} '
                + intervalle(t["ecart_position"], t["position_bas"], t["position_haut"], 0, span, lambda v: f"{v:+.1f}")
                + f'<small class="muted">{n(t["position_bas"], True, 1)} à {n(t["position_haut"], True, 1)}</small></span></div>'
                f'<div class="dem-v">{pill(t["verdict"])}</div></div>')
        sa = A.get("saison", {})
        saison = (f" Il y a un an, sur les mêmes semaines, les impressions avaient fait ×{n(sa['ratio_impressions'], False, 2)}."
                  if sa.get("lisible") and sa.get("ratio_impressions") else " L'an dernier n'a pas assez de volume pour comparer la saison.")
        blocs.append(section("demande", "Demande ou classement ?",
                             '<div class="dems">' + "".join(lignes) + "</div>",
                             "Mêmes requêtes sur les deux fenêtres (au moins " + str(tests[0]["seuil_impressions"]) + " impressions avant). "
                             "Impressions qui baissent à position stable : la demande baisse (saison, pays). Position qui recule (nombre plus grand) : le classement. "
                             "Un intervalle qui ne touche pas la ligne de référence est détectable. Le test ne voit que les requêtes visibles, biaisées vers les grosses."
                             + e(saison)))

    # Pays et appareils.
    if not neuf and A.get("pays"):
        lignes = [[e(l["pays"].upper()), n(l["clics"]["avant"]), n(l["clics"]["apres"]), n(l["clics"]["ecart"], True),
                   "±" + n(l["clics"]["seuil"]), pill(l["clics"]["verdict"]), n(l["impressions"]["relatif"] * 100 if l["impressions"]["relatif"] is not None else None, True) + " %"]
                  for l in A["pays"]]
        app = ""
        if A.get("appareils"):
            app = "<h3>Appareils</h3>" + table(["Appareil", "Clics avant", "Clics après", "Écart", "Lecture", "Impressions"], [
                [e(l["appareil"].lower()), n(l["clics"]["avant"]), n(l["clics"]["apres"]), n(l["clics"]["ecart"], True),
                 pill(l["clics"]["verdict"]), n(l["impressions"]["relatif"] * 100 if l["impressions"]["relatif"] is not None else None, True) + " %"]
                for l in A["appareils"]], ["", "num", "num", "num", "", "num"])
        blocs.append(section("pays", "Par pays et par appareil", table(["Pays", "Clics avant", "Clics après", "Écart", "Seuil", "Lecture", "Impressions"],
                                                                        lignes, ["", "num", "num", "num", "num", "", "num"]) + app,
                             "Au niveau du site, ces chiffres sont complets. Croisés avec une page, l'API les tronque : ne les lis pas page par page."))

    # Chevauchements.
    if A.get("chevauchements"):
        lignes = [[e(c["requete"]), n(c["impressions"]),
                   "<br>".join(f'<span class="url">{e(court(p["page"]))}</span> <small class="muted">{n(p["impressions"])} impr., pos. {n(p["position"], False, 1)}</small>'
                               for p in c["pages"])] for c in A["chevauchements"]]
        blocs.append(section("chevauchements", "Requêtes servies par plusieurs pages",
                             table(["Requête", "Impressions", "Pages (20 % des impressions ou plus)"], lignes, ["", "num", ""]),
                             f"{A['chevauchements_total']} requêtes en tout. C'est un constat de structure, pas un coût mesuré : "
                             "deux pages sur la même intention se corrigent pour des raisons d'architecture, sans prétendre que ça coûte des clics."))

    # Suivi des changements.
    if A.get("suivi"):
        cartes = []
        for s in A["suivi"]:
            lect = ""
            for nom, l in s.get("lectures", {}).items():
                cible = f"requête « {s['requete']} »" if nom == "requete" else "pages visées"
                pos_txt = (f", position {n(l['position_avant'], False, 1)} → {n(l['position_apres'], False, 1)}"
                           if l.get("position_avant") and l.get("position_apres") else "")
                lect += (f'<li>{e(cible)} : {l["metrique"]} {n(l["avant"])} → {n(l["apres"])} sur {l["jours"]} j de chaque côté, '
                         f'écart {n(l["ecart"], True)}, seuil ±{n(l["seuil"])}{pos_txt}</li>')
            info = ""
            if s.get("indexation"):
                info += f"<li>Indexation : {e(s['indexation'])}</li>"
            if s.get("requete_vue"):
                info += f"<li>Requête {e(s['requete_vue'])}</li>"
            if s.get("empile_sur"):
                info += f'<li class="bad">Empilé sur : {e(" ; ".join(s["empile_sur"]))}. La lecture mélange les deux changements.</li>'
            cible = (s.get("requete") and f"requête « {s['requete']} »") or s.get("url") or "site"
            cartes.append(
                f'<article class="suivi"><div class="suivi-top"><span class="date">{jm(s["en_ligne"]) if s.get("en_ligne") else "?"} · J+{s.get("j", "?")}</span>{pill(s.get("etat"))}</div>'
                f'<h3>{e(s.get("ajustement"))}</h3><p class="muted small">{e(cible)} · attendu : {e(s.get("attendu") or s.get("attendu_index") or "n/a")} · relire le {jm(s["relire_le"]) if s.get("relire_le") else "?"}</p>'
                f'<ul class="liste">{lect}{info}</ul>'
                + (f'<p class="constat"><b>Constat{(" du " + jm(s["constat_le"])) if s.get("constat_le") else ""}</b> · {e(s["constat"])}</p>' if s.get("constat") else "")
                + "</article>")
        blocs.append(section("suivi", "Suivi des changements", '<div class="suivis">' + "".join(cartes) + "</div>",
                             "Une ligne de journal.csv par changement mis en ligne. On lit la requête ou la page visée, pas le total. "
                             "Verdict au plus tôt trois semaines après la mise en ligne : amélioration détectable, pas de régression détectable, régression détectable (revenir en arrière) ou indécidable."))

    # Indexation.
    nonidx = ix["non_indexees"]
    if neuf:
        lignes = [[f'<span class="url">{e(court(p["page"]))}</span>', n(p["imp_apres"]), n(p["clics_apres"]),
                   pill("indexée") if p["verdict"] == "PASS" else f'<span class="bad">{e(p["couverture"])}</span>',
                   e(jm(p["dernier_crawl"]) if p["dernier_crawl"] else "n/a"), "oui" if p["dans_sitemap"] else "non"] for p in A.get("pages_index", [])]
        corps = table(["Page", "Impr. 28 j", "Clics", "Indexation", "Dernier crawl", "Sitemap"], lignes, ["", "num", "num", "", "num", ""])
        blocs.insert(0, section("indexation", "Indexation : ce qui se lit à ce volume", corps,
                                "Inspection d'URL du jour. Une page recrawlée après un changement et dans l'état voulu, c'est un fait, pas une tendance. "
                                "« Explorée, non indexée » : Google l'a vue et ne la garde pas (liens entrants, contenu trop proche d'une autre page). "
                                "« Détectée, non explorée » : il ne l'a pas encore lue."))
    elif ix["inspectees"] or ix["hors_sitemap_total"]:
        corps = ""
        if nonidx:
            corps += table(["Page", "État", "Dernier crawl"], [[f'<span class="url">{e(court(r["url"]))}</span>', e(r["couverture"] or r["verdict"]),
                                                               e(r["dernier_crawl"][:10] or "jamais")] for r in nonidx], ["", "", "num"])
        else:
            corps += '<p>Toutes les pages inspectées sont indexées.</p>'
        if ix["hors_sitemap_total"]:
            corps += (f"<h3>Vues dans Google mais absentes du sitemap ({ix['hors_sitemap_total']})</h3><ul class=\"liste\">"
                      + "".join(f'<li><span class="url">{e(court(p))}</span></li>' for p in ix["hors_sitemap_vues"]) + "</ul>"
                      "<p class=\"note\">Souvent d'anciennes URL redirigées que Google sert encore quelques semaines : rien à faire si la redirection répond bien.</p>")
        blocs.append(section("indexation", "Indexation",
                             corps, f"{ix['inspectees']} pages inspectées : celles du journal et celles du sitemap sans aucune impression sur 28 jours. "
                                    f"Sitemap : {ix['urls_sitemap']} URL, dont {ix['sitemap_vues']} vues dans Google sur la fenêtre."))

    if neuf and A.get("requetes_top"):
        lignes = [[e(q["requete"]), n(q["impressions"]), n(q["clics"]), n(q["position"], False, 1)] for q in A["requetes_top"]]
        blocs.append(section("requetes", "Requêtes visibles, 28 jours", table(["Requête", "Impressions", "Clics", "Position"], lignes, ["", "num", "num", "num"]),
                             "Google cache les requêtes rares. Une requête qui apparaît est un fait ; sa position sur quelques impressions ne dit rien de ce que la page tiendrait sur plus."))

    # Calendrier.
    cal = "".join(f'<tr{" class=late" if c["en_retard"] else ""}><td class="num">{jm(c["date"])}</td><td>{e(c["quoi"])}'
                  f'{" <b>(en retard)</b>" if c["en_retard"] else ""}</td></tr>' for c in A["calendrier"])
    blocs.append(section("calendrier", "Calendrier de relecture", f'<div class="tablebox"><table class="cal"><tbody>{cal}</tbody></table></div>',
                         "Rien ne se relit avant sa date : plus tôt, la fenêtre est trop courte pour trancher."))

    parts += blocs

    cov = A.get("couverture") or {}
    methode = [
        f"<p><b>Le seuil du bruit.</b> Deux périodes de même durée, avant et après. L'écart compte seulement s'il dépasse {k_txt}. "
        + ("C'est l'intervalle à 95 % d'un comptage de Poisson." if A["k"] == 1 else "C'est l'intervalle à 95 % d'un comptage de Poisson, élargi parce qu'un petit site varie plus que le hasard pur.")
        + " Sous le seuil : non détectable. Ce n'est pas une version prudente de « ça monte », c'est un verdict.</p>",
        "<p><b>Les dates.</b> Search Console a deux à trois jours de retard : seules les données finales comptent, la semaine en cours est exclue.</p>",
        "<p><b>Position et CTR.</b> La position moyenne bouge dès que le mélange de requêtes change, sans que rien ne change dans Google : on ne la compare que sur un panier fixe de requêtes (le test demande ou classement). "
        "Le CTR ne se lit jamais à la semaine sur un petit site.</p>",
    ]
    if cov.get("part") is not None:
        methode.append(f"<p><b>Requêtes visibles.</b> Google ne montre que {round(100 * cov['part'])} % des impressions en dimension requête (les requêtes rares sont masquées). "
                       "Toute lecture par requête porte sur cette part, biaisée vers les grosses requêtes.</p>")
    if A.get("manque"):
        methode.append("<p><b>Ce qui manque (export manuel).</b> " + e(" ; ".join(A["manque"])) + "</p>")
    methode.append("<p><b>Rafraîchir.</b> Dans Claude Code, dis « rafraîchis le dashboard ». Pour suivre un changement, ajoute une ligne à <code>journal.csv</code>.</p>")
    parts.append(section("methode", "Comment lire ces chiffres", "".join(methode)))

    corps = "\n".join(parts)
    return PAGE.replace("{{TITRE}}", e(f"SEO de {dom}")).replace("{{CORPS}}", corps)


PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITRE}}</title>
<style>
:root {
  color-scheme: light;
  --bg: #f6f5f1; --panel: #fcfcfb; --fg: #0b0b0b; --muted: #5d5c58; --line: #e2e0d9;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --s5: #6250d6; --s-autres: #b9b7af;
  --good: #0a7d0a; --bad: #c22f2f; --good-bg: #e3f3e1; --bad-bg: #f9e1e0; --ok-bg: #e8eef8; --muted-bg: #efeee9;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #121211; --panel: #1a1a19; --fg: #f0efec; --muted: #a9a89f; --line: #34342f;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #9085e9; --s-autres: #5a5954;
    --good: #4cc44c; --bad: #ef7373; --good-bg: #1d3320; --bad-bg: #3a1e1e; --ok-bg: #1f2a3a; --muted-bg: #262624;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #121211; --panel: #1a1a19; --fg: #f0efec; --muted: #a9a89f; --line: #34342f;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #9085e9; --s-autres: #5a5954;
  --good: #4cc44c; --bad: #ef7373; --good-bg: #1d3320; --bad-bg: #3a1e1e; --ok-bg: #1f2a3a; --muted-bg: #262624;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1080px; margin: 0 auto; padding: 20px 16px 48px; }
h1 { font-size: 26px; margin: 0 0 8px; letter-spacing: -0.01em; }
h2 { font-size: 17px; margin: 0 0 6px; }
h3 { font-size: 14px; margin: 16px 0 6px; }
.take { font-size: 16px; max-width: 70ch; margin: 0 0 6px; }
.asof, .note, .muted, .kpi-note { color: var(--muted); }
.asof { font-size: 13px; margin: 0; }
.note { font-size: 13px; margin: 0 0 10px; max-width: 80ch; }
.small, small { font-size: 12px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin-top: 14px; min-width: 0; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 16px; }
.kpis .card { margin-top: 0; }
.kpi-label { font-size: 13px; color: var(--muted); }
.kpi-value { font: 600 30px/1.2 ui-serif, Georgia, serif; margin: 4px 0; font-variant-numeric: tabular-nums; }
.kpi-value small { font-size: 16px; color: var(--muted); }
.kpi-sub { font-size: 13px; margin-top: 4px; }
.kpi-note { font-size: 12px; margin-top: 6px; }
.good { color: var(--good); } .bad { color: var(--bad); }
.pill { display: inline-block; padding: 1px 8px; border-radius: 99px; font-size: 12px; line-height: 1.6; background: var(--muted-bg); color: var(--fg); }
.pill-good { background: var(--good-bg); color: var(--good); }
.pill-bad { background: var(--bad-bg); color: var(--bad); }
.pill-ok { background: var(--ok-bg); }
.alerte { background: var(--bad-bg); border-radius: 10px; padding: 10px 14px; margin: 14px 0 0; font-size: 14px; }
.chart { position: relative; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 12px; color: var(--muted); margin: 4px 0 6px; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
.legend i.dash { width: 0; height: 12px; border-left: 2px dashed var(--muted); border-radius: 0; }
svg .grid { stroke: var(--line); stroke-width: 1; }
svg .ax { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
svg .repere { stroke: var(--muted); stroke-width: 1.5; stroke-dasharray: 4 3; }
svg .hit { fill: transparent; cursor: default; }
svg .hit:hover { fill: var(--fg); fill-opacity: 0.05; }
svg.ci { vertical-align: middle; flex: none; }
.civ { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.dem { display: grid; grid-template-columns: minmax(150px, 1.2fr) 1fr 1fr minmax(150px, 1fr); gap: 4px 16px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--line); }
.dem-ci { display: flex; flex-direction: column; gap: 0; }
@media (max-width: 760px) { .dem { grid-template-columns: 1fr; } }
details { margin-top: 8px; } summary { cursor: pointer; font-size: 13px; color: var(--muted); }
svg.ci .ref { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 2 2; }
.tablebox { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-weight: 600; color: var(--muted); white-space: nowrap; }
th button { all: unset; cursor: pointer; }
th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.url { word-break: break-all; }
td .url { display: inline-block; min-width: 11em; }
table.cal td:first-child { width: 4.5em; }
tr.late td { color: var(--bad); }
.liste { margin: 6px 0; padding-left: 18px; font-size: 13px; }
.liste li { margin: 2px 0; }
.suivis { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.suivi { border: 1px solid var(--line); border-radius: 10px; padding: 12px; min-width: 0; }
.suivi h3 { margin: 6px 0 2px; }
.suivi-top { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; align-items: center; }
.date { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.constat { font-size: 13px; background: var(--muted-bg); border-radius: 8px; padding: 8px 10px; margin: 8px 0 0; }
code { font-size: 12px; background: var(--muted-bg); padding: 1px 4px; border-radius: 4px; }
#tip { position: fixed; pointer-events: none; background: var(--fg); color: var(--bg); font-size: 12px; padding: 6px 8px; border-radius: 6px; max-width: 260px; display: none; z-index: 9; }
svg.narrow { display: none; }
@media (max-width: 560px) { svg.wide { display: none; } svg.narrow { display: block; } }
@media (max-width: 520px) { h1 { font-size: 22px; } .kpi-value { font-size: 26px; } .card { padding: 12px; } }
</style>
</head>
<body>
<main>
{{CORPS}}
</main>
<div id="tip" role="tooltip"></div>
<script>
(function () {
  var tip = document.getElementById('tip');
  function show(ev, t) {
    tip.textContent = t; tip.style.display = 'block';
    var x = (ev.touches ? ev.touches[0].clientX : ev.clientX), y = (ev.touches ? ev.touches[0].clientY : ev.clientY);
    var w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, x - w / 2)) + 'px';
    tip.style.top = (y - h - 12 < 8 ? y + 16 : y - h - 12) + 'px';
  }
  document.querySelectorAll('[data-tip]').forEach(function (el) {
    el.addEventListener('mousemove', function (ev) { show(ev, el.getAttribute('data-tip')); });
    el.addEventListener('touchstart', function (ev) { show(ev, el.getAttribute('data-tip')); }, { passive: true });
    el.addEventListener('mouseleave', function () { tip.style.display = 'none'; });
  });
  document.addEventListener('touchend', function () { setTimeout(function () { tip.style.display = 'none'; }, 1500); });
  document.querySelectorAll('table.sortable').forEach(function (t) {
    t.querySelectorAll('th').forEach(function (th, i) {
      th.addEventListener('click', function () {
        var tb = t.tBodies[0], rows = Array.prototype.slice.call(tb.rows), asc = th.dataset.asc !== '1';
        th.dataset.asc = asc ? '1' : '0';
        var val = function (r) { var s = r.cells[i].textContent.replace(/[\\s\\u202f%×]/g, '').replace('−', '-').replace(',', '.'); var v = parseFloat(s); return isNaN(v) ? r.cells[i].textContent : v; };
        rows.sort(function (a, b) { var x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1); });
        rows.forEach(function (r) { tb.appendChild(r); });
      });
    });
  });
})();
</script>
</body>
</html>
"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("dossier")
    ap.add_argument("--resume", help="deux ou trois phrases en tête de page (sinon resume.txt)")
    a = ap.parse_args(argv)
    dossier = os.path.abspath(os.path.expanduser(a.dossier))
    with open(os.path.join(dossier, "analyse.json"), encoding="utf-8") as f:
        A = json.load(f)
    resume = a.resume
    rp = os.path.join(dossier, "resume.txt")
    if resume:
        with open(rp, "w", encoding="utf-8") as f:
            f.write(resume.strip() + "\n")
    elif os.path.exists(rp):
        # Un résumé écrit pour une autre fenêtre ne doit pas survivre au rafraîchissement.
        if os.path.getmtime(rp) >= os.path.getmtime(os.path.join(dossier, "analyse.json")) - 5:
            resume = open(rp, encoding="utf-8").read().strip()
    out = os.path.join(dossier, "tableau-de-bord.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(rendre(A, resume))
    print("TABLEAU : " + out)
    return out


if __name__ == "__main__":
    main()
