#!/usr/bin/env python3
"""Le banc de setup.py : des machines simulées (machines/*.json) et l'écriture dans un dossier jetable.

    python3 banc/test_setup.py          # tout ; rien n'est installé, rien ne part sur le réseau

Chaque machine dit ce qu'elle attend (`attendu`) : l'état de chaque point, des morceaux de texte qui
doivent apparaître (`contient`) ou jamais (`jamais` : une commande d'un autre système, la clé), les
`brew install` que --installe lancerait, et `pret_comptes` (yt-dlp prêt pour audit et outliers). Pour voir le diagnostic d'une machine :
    python3 scripts/setup.py --simule banc/machines/mac-vide.json
"""
import contextlib
import copy
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
SCRIPT = ICI.parent / "scripts" / "setup.py"
sys.path.insert(0, str(SCRIPT.parent))
import setup  # noqa: E402

echecs = []


def verifie(cond, quoi):
    if not cond:
        echecs.append(quoi)
        print(f"    ÉCHEC  {quoi}")


def lance(argv, sonde=None, entree=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = setup.main(argv, sonde=sonde, entree=entree)
    return code, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------- 1. les machines simulées

for f in sorted((ICI / "machines").glob("*.json")):
    m = json.loads(f.read_text(encoding="utf-8"))
    att = m["attendu"]
    print(f"{f.name} : {m['nom']}")
    d = setup.diagnostic(setup.SondeSimulee(m))
    sortie = setup.texte(d)
    js = setup.en_json(d, setup.SondeSimulee(m), [])
    etats = {k.cle: k.etat for k in d.constats}
    verifie(d.pret == att["pret"], f"{f.name} : prêt = {d.pret}, attendu {att['pret']}")
    if "pret_comptes" in att:
        verifie(json.loads(js)["pret_comptes"] == att["pret_comptes"],
                f"{f.name} : pret_comptes = {d.pret_comptes}, attendu {att['pret_comptes']}")
    for cle, etat in att.get("etats", {}).items():
        verifie(etats.get(cle) == etat, f"{f.name} : {cle} = {etats.get(cle)}, attendu {etat}")
    for t in att.get("contient", []):
        verifie(t in sortie, f"{f.name} : « {t} » absent du diagnostic")
    for t in att.get("jamais", []):
        verifie(t not in sortie and t not in js, f"{f.name} : « {t} » ne doit jamais apparaître")
    if "brew" in att:
        verifie(d.plan_brew() == att["brew"], f"{f.name} : plan brew {d.plan_brew()}, attendu {att['brew']}")
    # chaque point dit quoi faire quand il bloque
    for k in d.constats:
        if k.bloque:
            verifie(k.corrige, f"{f.name} : {k.cle} bloque sans dire comment réparer")

# la ligne de commande, de bout en bout, sur une machine simulée
r = subprocess.run([sys.executable, str(SCRIPT), "--simule", str(ICI / "machines" / "mac-vide.json")],
                   capture_output=True, text=True, encoding="utf-8")
verifie(r.returncode == 1 and "MANQUE" in r.stdout, f"--simule mac-vide : code {r.returncode}")
r = subprocess.run([sys.executable, str(SCRIPT), "--diagnostic", "--json", "--simule",
                    str(ICI / "machines" / "mac-sans-sous-titres.json")], capture_output=True, text=True, encoding="utf-8")
verifie(r.returncode == 0 and json.loads(r.stdout)["pret"] is True, f"--simule --json mac-sans-sous-titres : {r.returncode}")
r = subprocess.run([sys.executable, str(SCRIPT), "--simule", str(ICI / "machines" / "mac-vide.json"), "--ecris"],
                   capture_output=True, text=True, encoding="utf-8")
verifie(r.returncode == 2 and "rien n'est écrit" in r.stderr, "--simule --ecris doit refuser")

print("--installe --a-blanc")
vide = json.loads((ICI / "machines" / "mac-vide.json").read_text(encoding="utf-8"))
code, out, _ = lance(["--installe", "--a-blanc"], setup.SondeSimulee(vide))
verifie(code == 2 and "Homebrew n'est pas installé" in out, f"sans Homebrew : code {code}")
sans = json.loads((ICI / "machines" / "mac-ffmpeg-sans-libass.json").read_text(encoding="utf-8"))
code, out, _ = lance(["--installe", "--a-blanc"], setup.SondeSimulee(sans))
verifie(code == 0 and "$ brew install ffmpeg-full" in out and "à blanc" in out, f"plan à blanc : code {code}")
lin = json.loads((ICI / "machines" / "linux.json").read_text(encoding="utf-8"))
code, out, _ = lance(["--installe", "--a-blanc"], setup.SondeSimulee(lin))
verifie(code == 2 and "ne lance rien sous Linux" in out and "cmake" in out, f"Linux : code {code}")

print("Windows : whisper.cpp qui ne démarre pas, whisper.cpp absent (--installe le télécharge)")
win = json.loads((ICI / "machines" / "windows-apres-winget.json").read_text(encoding="utf-8"))
m = copy.deepcopy(win)
m["whisper_code"] = 3221225781                       # 0xC0000135 : MSVCP140.dll introuvable
d = setup.diagnostic(setup.SondeSimulee(m))
k = next(k for k in d.constats if k.cle == "whisper")
verifie(k.etat == "manque" and k.bloque and any("Microsoft.VCRedist.2015+.x64" in x for x in k.corrige),
        f"whisper sans sa DLL : {k.etat} {k.corrige}")
m = copy.deepcopy(win)
del m["fichiers"]["~/AppData/Local/whisper.cpp/Release/whisper-cli.exe"]
d = setup.diagnostic(setup.SondeSimulee(m))
k = next(k for k in d.constats if k.cle == "whisper")
verifie(k.etat == "manque" and k.corrige[0].startswith("py ") and k.corrige[0].split("#")[0].strip().endswith("--installe"),
        f"whisper absent : {k.corrige}")
verifie(d.whisper_a_telecharger and "télécharge whisper.cpp" in setup.texte(d), "Windows : --installe pas proposé")
code, out, _ = lance(["--installe", "--a-blanc"], setup.SondeSimulee(m))
verifie(code == 0 and "Je vais télécharger whisper.cpp" in out and "à blanc" in out, f"Windows à blanc : code {code}\n{out}")

print("yt-dlp : audit et outliers en ont besoin, le montage jamais")
pret = json.loads((ICI / "machines" / "mac-pret-elevenlabs.json").read_text(encoding="utf-8"))
code, out, _ = lance(["--installe", "--a-blanc"], setup.SondeSimulee(pret))
verifie(code == 0 and "$ brew install yt-dlp" in out, f"Mac prêt sans yt-dlp, --installe à blanc : code {code}\n{out}")
m = copy.deepcopy(pret)
m["lecteurs"] = []                                    # setup et edit seuls, sans audit ni outliers
d = setup.diagnostic(setup.SondeSimulee(m))
k = next(k for k in d.constats if k.cle == "ytdlp")
verifie(k.etat == "option" and not d.plan_brew(), f"sans audit ni outliers : {k.etat} {d.plan_brew()}")
m = copy.deepcopy(pret)
del m["which"]["brew"]                                # pas de Homebrew : yt-dlp seul le demande, sans bloquer
d = setup.diagnostic(setup.SondeSimulee(m))
k = next(k for k in d.constats if k.cle == "homebrew")
verifie(k.etat == "a_faire" and not k.bloque and d.pret and k.corrige, f"Homebrew pour yt-dlp seul : {k.etat} {k.bloque}")
full = json.loads((ICI / "machines" / "mac-ffmpeg-full-a-cote.json").read_text(encoding="utf-8"))
m = copy.deepcopy(full)
m["ytdlp_code"] = 1                                   # un yt-dlp cassé (son Python a changé)
d = setup.diagnostic(setup.SondeSimulee(m))
k = next(k for k in d.constats if k.cle == "ytdlp")
verifie(k.etat == "a_faire" and d.pret and not d.pret_comptes and d.plan_brew() == ["brew reinstall yt-dlp"],
        f"yt-dlp qui ne démarre pas : {k.etat} {d.plan_brew()}")
m = copy.deepcopy(lin)
m["fichiers"] = {"~/.local/bin/yt-dlp": 1}            # pipx l'a posé, ~/.local/bin pas encore dans le PATH
d = setup.diagnostic(setup.SondeSimulee(m))
k = next(k for k in d.constats if k.cle == "ytdlp")
verifie(k.etat == "attention" and k.corrige[0] == "pipx ensurepath", f"Linux, pipx hors du PATH : {k.etat} {k.corrige}")
winv = json.loads((ICI / "machines" / "windows.json").read_text(encoding="utf-8"))
code, out, _ = lance(["--installe", "--a-blanc"], setup.SondeSimulee(winv))
verifie(code == 2 and "$ winget install yt-dlp.yt-dlp -e --accept-package-agreements" in out,
        f"Windows : yt-dlp dans les commandes à lancer à part : code {code}\n{out}")
code, out, _ = lance(["--installe", "--a-blanc"], setup.SondeSimulee(lin))
verifie("$ pipx install yt-dlp" in out, f"Linux : yt-dlp dans les commandes : {out}")


# --------------------------------------------------------------------------- 2. l'écriture, dans un dossier jetable

def machine_disque(nom, sans_config=True):
    m = copy.deepcopy(json.loads((ICI / "machines" / nom).read_text(encoding="utf-8")))
    m["disque"] = True
    if sans_config:
        m.pop("config", None)
    m.pop("env_fichier", None)
    m["dossiers"] = []
    return m


CLE = "sk_banc_0123456789abcdef0123456789abcdef"

with tempfile.TemporaryDirectory() as home:
    print("--ecris : ffmpeg-full à côté, modèle rangé dans ~/.local/share")
    s = setup.SondeSimulee(machine_disque("mac-ffmpeg-full-a-cote.json"), home=home)
    code, out, err = lance(["--ecris", "--moteur", "whisper", "--langue", "FR", "--sortie", "~/Videos/edited",
                            "--sous-titres", "oui", "--remotion", "non"], s)
    cfg = json.loads((Path(home) / ".config/video-editing/config.json").read_text(encoding="utf-8"))
    verifie(set(cfg) <= set(setup.CLES), f"clés hors contrat : {set(cfg) - set(setup.CLES)}")
    verifie(cfg.get("stt") == "whisper" and cfg.get("lang") == "fr", f"stt/lang : {cfg}")
    verifie(cfg.get("output_dir") == "~/Videos/edited", f"output_dir : {cfg.get('output_dir')}")
    verifie(cfg.get("subtitles") is True and cfg.get("remotion") is False, f"booléens : {cfg}")
    verifie("ffmpeg" not in cfg, f"le montage trouve ffmpeg-full tout seul, pas de ligne : {cfg.get('ffmpeg')}")
    verifie(cfg.get("whisper_model") == "large-v3-turbo", f"whisper_model : {cfg.get('whisper_model')}")
    verifie((Path(home) / "Videos/edited").is_dir(), "dossier de sortie pas créé")
    verifie(code == 0 and "Prêt pour le montage" in out, f"après --ecris : code {code}\n{out}{err}")

    print("--ecris : un second passage ne change que ce qu'on lui donne")
    code, out, _ = lance(["--ecris", "--sous-titres", "non"], s)
    cfg2 = json.loads((Path(home) / ".config/video-editing/config.json").read_text(encoding="utf-8"))
    verifie(cfg2.get("lang") == "fr" and cfg2.get("stt") == "whisper", f"fusion : {cfg2}")
    verifie(cfg2.get("subtitles") is False, "subtitles pas mis à jour")
    verifie(set(cfg2) == set(cfg), f"rien d'autre ne bouge : {cfg2}")
    code, out, _ = lance(["--ecris", "--sortie", str(Path(home) / "Movies" / "montages")], s)
    cfg3 = json.loads((Path(home) / ".config/video-editing/config.json").read_text(encoding="utf-8"))
    verifie(cfg3.get("output_dir") == "~/Movies/montages", f"chemin absolu ramené à ~ : {cfg3.get('output_dir')}")

    print("--cle-elevenlabs-stdin : la clé va dans env (600), jamais ailleurs")
    code, out, err = lance(["--cle-elevenlabs-stdin", "--ecris", "--moteur", "elevenlabs", "--json"], s,
                           entree=io.StringIO(CLE + "\n"))
    env = Path(home) / ".config/video-editing/env"
    verifie(env.read_text(encoding="utf-8") == f"ELEVENLABS_API_KEY={CLE}\n", "env : contenu")
    if os.name != "nt":
        verifie(stat.S_IMODE(env.stat().st_mode) == 0o600, f"env : mode {oct(stat.S_IMODE(env.stat().st_mode))}")
    conf_txt = (Path(home) / ".config/video-editing/config.json").read_text(encoding="utf-8")
    verifie(CLE not in conf_txt and CLE not in out and CLE not in err, "la clé a fuité (config, sortie)")
    verifie(json.loads(out)["pret"] is True, "ElevenLabs avec sa clé : pas prêt")
    verifie(json.loads(conf_txt).get("stt") == "elevenlabs", "stt pas passé à elevenlabs")

    print("une clé illisible n'écrase rien")
    for mauvaise in ("", "deux mots", "court", "ligne1\nligne2"):
        code, out, err = lance(["--cle-elevenlabs-stdin"], s, entree=io.StringIO(mauvaise))
        verifie(code == 2 and "Rien n'a été écrit" in err, f"clé {mauvaise!r} : code {code}")
    verifie(env.read_text(encoding="utf-8") == f"ELEVENLABS_API_KEY={CLE}\n", "env modifié par une mauvaise clé")

    print("une clé posée dans config.json part dans env")
    p = Path(home) / ".config/video-editing/config.json"
    c = json.loads(p.read_text(encoding="utf-8"))
    c["elevenlabs_api_key"] = CLE + "x"
    p.write_text(json.dumps(c), encoding="utf-8")
    code, out, err = lance(["--diagnostic"], s)
    verifie("n'a rien à faire dans config.json" in out, "clé dans config.json pas signalée")
    code, out, err = lance(["--ecris"], s)
    verifie("elevenlabs_api_key" not in p.read_text(encoding="utf-8"), "clé restée dans config.json")
    verifie(f"ELEVENLABS_API_KEY={CLE}x" in env.read_text(encoding="utf-8"), "clé pas déplacée dans env")
    verifie(CLE not in out and CLE not in err, "la clé a fuité à l'affichage")

    print("un env lisible par tous est signalé puis remis en 600")
    if os.name != "nt":
        os.chmod(str(env), 0o644)
        code, out, _ = lance([], s)
        verifie("lisible par d'autres comptes" in out, "mode 644 pas signalé")
        lance(["--ecris"], s)
        verifie(stat.S_IMODE(env.stat().st_mode) == 0o600, "env pas remis en 600")

    print("une config illisible est gardée en .bak puis réécrite")
    p.write_text("{pas du json", encoding="utf-8")
    code, out, _ = lance([], s)
    verifie(code == 1 and "illisible" in out, f"config illisible : code {code}")
    code, out, _ = lance(["--ecris", "--moteur", "whisper"], s)
    verifie(json.loads(p.read_text(encoding="utf-8")).get("stt") == "whisper", "config pas réécrite")
    verifie(any(x.name.startswith("config.json.bak-") for x in p.parent.iterdir()), "pas de .bak")

with tempfile.TemporaryDirectory() as home:
    print("--ecris retire une ligne ffmpeg périmée, garde une ligne qui marche")
    m = machine_disque("mac-config-perimee.json", sans_config=False)
    s = setup.SondeSimulee(m, home=home)
    cfgp = Path(home) / ".config/video-editing/config.json"
    cfgp.parent.mkdir(parents=True)
    cfgp.write_text(json.dumps(m["config"]), encoding="utf-8")
    code, out, _ = lance(["--ecris"], s)
    c = json.loads(cfgp.read_text(encoding="utf-8"))
    verifie("ffmpeg" not in c and c.get("lang") == "fr", f"ligne périmée : {c}")
    verifie("ffmpeg /usr/local/bin/ffmpeg-ancien retiré" in out, "le retrait n'est pas dit")
    c["ffmpeg"] = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
    cfgp.write_text(json.dumps(c), encoding="utf-8")
    lance(["--ecris", "--langue", "en"], s)
    c = json.loads(cfgp.read_text(encoding="utf-8"))
    verifie(c.get("ffmpeg") == "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg" and c.get("lang") == "en", f"ligne qui marche : {c}")

with tempfile.TemporaryDirectory() as home:
    print("--installe sans config : n'écrit pas de config.json")
    m = machine_disque("mac-ffmpeg-sans-libass.json")
    code, out, _ = lance(["--installe", "--a-blanc"], setup.SondeSimulee(m, home=home))
    verifie(not (Path(home) / ".config/video-editing/config.json").exists(), "config.json écrite par --installe --a-blanc")

print()
if echecs:
    print(f"{len(echecs)} échec(s)")
    sys.exit(1)
print("banc vert")
