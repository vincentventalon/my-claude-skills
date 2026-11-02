#!/usr/bin/env python3
"""setup.py — l'installation du montage vidéo (la skill edit) : diagnostic, configuration, installations.

    python3 setup.py                     # le diagnostic : une ligne par point, n'écrit rien
    python3 setup.py --json              # le même, pour Claude
    python3 setup.py --ecris --moteur whisper --langue fr --sortie ~/Videos/edited \\
                     --sous-titres oui --remotion non
                                         # écrit ~/.config/video-editing/config.json (fusionné avec
                                         # l'existant) et crée le dossier de sortie
    pbpaste | python3 setup.py --cle-elevenlabs-stdin
                                         # la clé ElevenLabs, lue sur l'entrée standard, écrite dans
                                         # ~/.config/video-editing/env (mode 600), jamais affichée
    python3 setup.py --installe --a-blanc    # macOS : les `brew install` qui manquent, affichés
    python3 setup.py --installe              # ... et lancés
    python3 setup.py --modele            # télécharge le modèle whisper maintenant (sinon : au premier montage)
    python3 setup.py --simule machine.json   # le diagnostic d'une machine simulée (banc/test_setup.py)

Ce qu'il regarde : Python (3.10 ou plus), ffmpeg + ffprobe et libass (les sous-titres incrustés),
whisper-cli et son modèle, la clé ElevenLabs, Node (pour Remotion), le dossier de sortie,
config.json. Une ligne par point : ok, MANQUE (le montage ne peut pas tourner), à faire (setup ou
le premier montage s'en charge), option (pas besoin avec les choix faits), attention.

Le contrat, partagé avec la skill de montage :
  ~/.config/video-editing/config.json, toutes les clés facultatives :
    {"stt": "whisper" | "elevenlabs", "whisper_model": "large-v3-turbo", "ffmpeg": "/chemin/ffmpeg",
     "lang": "fr", "output_dir": "~/Videos/edited", "subtitles": true, "remotion": true}
  la clé ElevenLabs seulement dans ELEVENLABS_API_KEY (l'environnement) ou dans
  ~/.config/video-editing/env (mode 600, des lignes KEY=valeur). Jamais dans config.json.

Bibliothèque standard seulement. Tourne dès Python 3.8, pour pouvoir dire qu'il faut 3.10.
Exit : 0 prêt, 1 il manque quelque chose, 2 refusé (mauvaise option, clé illisible, simulation).
"""
from __future__ import annotations

import argparse
import datetime
import getpass
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

for _s in (sys.stdout, sys.stderr):          # les accents sur la console Windows
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(errors="replace")

ICI = Path(__file__).resolve().parent
MONTAGE = ICI.parent.parent / "edit"                   # skills/edit, à côté de skills/setup

CONFIG_DIR = "~/.config/video-editing"
CONFIG = CONFIG_DIR + "/config.json"
ENV = CONFIG_DIR + "/env"
CLES = ("stt", "whisper_model", "ffmpeg", "lang", "output_dir", "subtitles", "remotion")
MOTEURS = ("whisper", "elevenlabs")

# Comme la skill de montage (scripts/stt.py, scripts/settings.py) : les mêmes dossiers, le même ordre.
MODELES_DIRS = ("~/.cache/whisper-cpp", "~/.local/share/whisper-cpp/models")   # le premier reçoit les téléchargements
FFMPEG_CANDIDATS = ("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg", "/usr/local/opt/ffmpeg-full/bin/ffmpeg")
MODELES_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
MODELES = {"large-v3-turbo": 1_624_555_275, "large-v3-turbo-q5_0": 574_041_195,
           "small": 487_601_967, "base": 147_951_465}   # octets, à 1 % près : de quoi voir un fichier tronqué
MODELE_DEFAUT = "large-v3-turbo"

PYTHON_MIN = (3, 10)
NODE_MIN = 18
SORTIE_DEFAUT = "~/Videos/edited"
HOMEBREW = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
WHISPER_RELEASES = "https://github.com/ggml-org/whisper.cpp/releases"


# --------------------------------------------------------------------------- la machine, interrogée

class Sonde:
    """Tout ce que le diagnostic demande à la machine passe par ici : le banc la simule."""

    def __init__(self, home: str | None = None, env: dict | None = None):
        self.env = dict(os.environ if env is None else env)
        self.home = Path(home) if home else Path.home()

    def systeme(self) -> str:                 # Darwin, Linux, Windows
        return platform.system()

    def machine(self) -> str:
        return platform.machine()

    def version_os(self) -> str:
        return platform.mac_ver()[0] if self.systeme() == "Darwin" else platform.release()

    def python(self) -> tuple:
        return tuple(sys.version_info[:3])

    def which(self, nom: str) -> str | None:
        return shutil.which(nom, path=self.env.get("PATH", os.defpath))

    def lance(self, argv: list, timeout: int = 20) -> tuple:
        try:
            r = subprocess.run(argv, capture_output=True, text=True, errors="replace",
                               timeout=timeout, env=self.env)
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except (OSError, subprocess.SubprocessError) as e:
            return 127, str(e)

    def chemin(self, p) -> Path:
        p = str(p)
        if p == "~":
            return self.home
        if p.startswith("~/") or p.startswith("~\\"):
            return self.home / p[2:]
        return Path(p)

    def existe(self, p) -> bool:
        return self.chemin(p).exists()

    def est_dossier(self, p) -> bool:
        return self.chemin(p).is_dir()

    def taille(self, p) -> int | None:
        try:
            return self.chemin(p).stat().st_size
        except OSError:
            return None

    def mode(self, p) -> int | None:
        try:
            return stat.S_IMODE(self.chemin(p).stat().st_mode)
        except OSError:
            return None

    def lit(self, p) -> str | None:
        try:
            return self.chemin(p).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def ecrivable(self, p) -> bool:
        """Le dossier existe et s'écrit, ou son plus proche parent existant s'écrit."""
        q = self.chemin(p)
        while not q.exists() and q.parent != q:
            q = q.parent
        return q.is_dir() and os.access(str(q), os.W_OK)

    def montage_present(self) -> bool:
        return (MONTAGE / "SKILL.md").exists()

    def remotion_installe(self) -> bool:
        return (MONTAGE / "remotion" / "node_modules").is_dir()


class SondeSimulee(Sonde):
    """Une machine décrite en JSON (banc/machines/*.json). Rien n'y est lancé ni installé.

    Avec "disque": true, ce qui n'est pas simulé est lu sur le vrai disque sous `home` (un dossier
    temporaire) : c'est ainsi que le banc vérifie ce que --ecris écrit."""

    def __init__(self, m: dict, home: str | None = None):
        super().__init__(home=home or m.get("home", "/Users/toi"), env=m.get("env", {}))
        self.m = m
        self.disque = bool(m.get("disque"))
        c = lambda k: str(self.chemin(k))
        self.ffmpegs = {c(k): v for k, v in m.get("ffmpeg", {}).items()}
        self.fichiers = {c(k): v for k, v in m.get("fichiers", {}).items()}
        for exe, spec in self.ffmpegs.items():
            self.fichiers.setdefault(exe, 1)
            if spec.get("ffprobe", True):
                p = Path(exe)
                self.fichiers.setdefault(str(p.with_name("ffprobe" + p.suffix)), 1)
        self.whichs = {k: (c(v) if v else None) for k, v in m.get("which", {}).items()}
        for v in self.whichs.values():
            if v:
                self.fichiers.setdefault(v, 1)
        self.dossiers = {c(k) for k in m.get("dossiers", [])}
        self.contenus = {c(k): v for k, v in m.get("contenus", {}).items()}
        if "config" in m:
            self.contenus[c(CONFIG)] = json.dumps(m["config"])
        if "env_fichier" in m:
            self.contenus[c(ENV)] = m["env_fichier"]
        self.modes = {c(ENV): m.get("env_mode", 0o600)}

    def systeme(self):
        return self.m.get("systeme", "Darwin")

    def machine(self):
        return self.m.get("machine", "arm64")

    def version_os(self):
        return self.m.get("version_os", "")

    def python(self):
        return tuple(int(x) for x in str(self.m.get("python", "3.12.0")).split("."))

    def which(self, nom):
        return self.whichs.get(nom)

    def lance(self, argv, timeout=20):
        exe = str(argv[0])
        if exe in self.ffmpegs:
            spec = self.ffmpegs[exe]
            if "-filters" in argv:
                lignes = [" T. drawtext          V->V       Draw text on top of video frames."]
                if spec.get("zscale", spec.get("libass")):
                    lignes.append(" .S zscale            V->V       Apply resizing, colorspace and bit depth conversion.")
                if spec.get("libass"):
                    lignes += [" .. ass               V->V       Render ASS subtitles onto input video using the libass library.",
                               " .. subtitles         V->V       Render text subtitles onto input video using the libass library."]
                return 0, "Filters:\n" + "\n".join(lignes) + "\n"
            return 0, f"ffmpeg version {spec.get('version', '7.1')} Copyright (c) 2000-2026 the FFmpeg developers\n"
        if Path(exe).name.startswith("node") and exe in self.fichiers:
            return 0, str(self.m.get("node", "v22.11.0")) + "\n"
        return 127, f"{exe}: introuvable (machine simulée)"

    def _reel(self, p) -> Path | None:
        if not self.disque:
            return None
        q = self.chemin(p)
        try:
            q.relative_to(self.home)
        except ValueError:
            return None
        return q

    def existe(self, p):
        s = str(self.chemin(p))
        if s in self.fichiers or s in self.contenus or s in self.dossiers:
            return True
        q = self._reel(p)
        return bool(q and q.exists())

    def est_dossier(self, p):
        if str(self.chemin(p)) in self.dossiers:
            return True
        q = self._reel(p)
        return bool(q and q.is_dir())

    def taille(self, p):
        s = str(self.chemin(p))
        if s in self.fichiers:
            return self.fichiers[s]
        q = self._reel(p)
        return q.stat().st_size if q and q.is_file() else None

    def mode(self, p):
        q = self._reel(p)
        if q and q.exists():
            return stat.S_IMODE(q.stat().st_mode)
        return self.modes.get(str(self.chemin(p)))

    def lit(self, p):
        q = self._reel(p)
        if q and q.is_file():
            return q.read_text(encoding="utf-8")
        return self.contenus.get(str(self.chemin(p)))

    def ecrivable(self, p):
        q = self._reel(p)
        if q is not None:
            return super().ecrivable(p)
        return str(self.chemin(p)) not in {str(self.chemin(x)) for x in self.m.get("non_ecrivables", [])}

    def montage_present(self):
        return not self.m.get("montage_absent")

    def remotion_installe(self):
        return bool(self.m.get("remotion_installe"))


# --------------------------------------------------------------------------- un constat

@dataclass
class Constat:
    cle: str
    titre: str
    etat: str                 # ok | manque | a_faire | option | attention
    detail: str
    corrige: list = field(default_factory=list)   # les commandes qui réparent ; "# ..." = une explication
    bloque: bool = False      # vrai : le montage ne peut pas tourner tant que ce n'est pas réglé


@dataclass
class Contexte:
    systeme: str
    brew: str | None
    py: str                   # la commande Python à écrire dans les corrections
    script: str               # ce script, tel qu'on le tape
    cfg: dict
    cfg_etat: str             # absente | ok | illisible
    cfg_erreur: str = ""

    @property
    def stt(self) -> str | None:
        v = self.cfg.get("stt")
        return v if v in MOTEURS else None

    @property
    def moteur(self) -> str:            # sans choix, le montage transcrit avec whisper (gratuit, sans clé)
        return self.stt or "whisper"

    @property
    def sous_titres(self) -> bool:
        return self.cfg.get("subtitles") is not False

    @property
    def remotion(self) -> bool:             # le montage l'essaie par défaut, et s'en passe sans Node
        return self.cfg.get("remotion") is not False

    @property
    def modele(self) -> str:
        return str(self.cfg.get("whisper_model") or MODELE_DEFAUT)

    @property
    def sortie(self) -> str:
        return str(self.cfg.get("output_dir") or SORTIE_DEFAUT)


def montre(s: Sonde, p) -> str:
    """Un chemin lisible : le dossier personnel écrit ~."""
    t = str(p)
    h = str(s.home)
    if t == h:
        return "~"
    for sep in ("/", "\\"):
        if t.startswith(h + sep):
            return "~" + sep + t[len(h) + 1:]
    return t


def cite(p: str) -> str:
    return f'"{p}"' if re.search(r"\s", p) else p


def go(octets) -> str:
    """1 624 555 275 -> « 1,6 Go » ; 574 041 195 -> « 0,57 Go »."""
    if octets >= 1e9:
        return f"{octets / 1e9:.1f}".replace(".", ",") + " Go"
    return f"{octets / 1e9:.2f}".replace(".", ",") + " Go"


def vers(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


# --------------------------------------------------------------------------- les fichiers du contrat

def lire_config(s: Sonde) -> tuple:
    texte = s.lit(CONFIG)
    if texte is None:
        return {}, "absente", ""
    try:
        cfg = json.loads(texte)
    except ValueError as e:
        return {}, "illisible", str(e)
    if not isinstance(cfg, dict):
        return {}, "illisible", "ce n'est pas un objet JSON"
    return cfg, "ok", ""


def lire_env(texte: str | None) -> dict:
    out = {}
    for ligne in (texte or "").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        k, v = ligne.split("=", 1)
        k = k.strip()
        if k.startswith("export "):
            k = k[7:].strip()
        out[k] = v.strip().strip('"').strip("'")
    return out


def homebrew(s: Sonde) -> str | None:
    if s.systeme() != "Darwin":
        return None
    b = s.which("brew")
    if b:
        return str(Path(b).parent.parent)
    for d in ("/opt/homebrew", "/usr/local"):
        if s.existe(d + "/bin/brew"):
            return d
    return None


def contexte(s: Sonde) -> Contexte:
    cfg, etat, err = lire_config(s)
    systeme = s.systeme()
    py = "python" if systeme == "Windows" else "python3"
    if s.python() < PYTHON_MIN:
        for n in ("python3.13", "python3.12", "python3.11", "python3.10"):
            if s.which(n):
                py = n
                break
    script = cite(montre(s, ICI / "setup.py"))
    return Contexte(systeme, homebrew(s), py, script, cfg, etat, err)


# --------------------------------------------------------------------------- les vérifications

def verifie_systeme(s: Sonde, c: Contexte) -> Constat:
    nom = {"Darwin": "macOS", "Linux": "Linux", "Windows": "Windows"}.get(c.systeme, c.systeme)
    v = s.version_os()
    return Constat("systeme", "Système", "ok", f"{nom} {v} ({s.machine()})".replace("  ", " "))


def verifie_python(s: Sonde, c: Contexte) -> Constat:
    v = s.python()
    texte = ".".join(str(x) for x in v)
    if v >= PYTHON_MIN:
        return Constat("python", "Python", "ok", texte)
    if c.py != "python3" and c.py != "python":
        return Constat("python", "Python", "manque",
                       f"{texte} : il faut 3.10 ou plus ; {c.py} est déjà installé",
                       [f"# lance ce script et le montage avec {c.py} au lieu de python3"], bloque=True)
    fix = {"Darwin": "brew install python", "Windows": "winget install Python.Python.3.12"}.get(
        c.systeme, "sudo apt install python3   # Ubuntu 22.04 et plus : 3.10 ou plus")
    return Constat("python", "Python", "manque", f"{texte} : il faut 3.10 ou plus", [fix], bloque=True)


def lis_ffmpeg(s: Sonde, exe: str) -> dict | None:
    if not s.existe(exe):
        return None
    code, out = s.lance([exe, "-hide_banner", "-version"])
    if code != 0:
        return None
    m = re.search(r"ffmpeg version (\S+)", out)
    _, filtres = s.lance([exe, "-hide_banner", "-filters"])
    noms = set()
    for ligne in filtres.splitlines():
        p = ligne.split()
        if len(p) >= 3 and re.fullmatch(r"[.A-Z|]{2,3}", p[0]):
            noms.add(p[1])
    p = Path(exe)
    ffprobe = p.with_name("ffprobe" + p.suffix)
    return {"chemin": exe, "version": m.group(1) if m else "?",
            "libass": "ass" in noms and "subtitles" in noms, "zscale": "zscale" in noms,
            "ffprobe": s.existe(ffprobe) or bool(s.which("ffprobe"))}


def installe_ffmpeg(c: Contexte) -> list:
    if c.systeme == "Darwin":
        return ["brew install ffmpeg-full" if c.sous_titres else "brew install ffmpeg"]
    if c.systeme == "Windows":
        return ["winget install Gyan.FFmpeg   # ou : choco install ffmpeg-full ; puis rouvre le terminal"]
    return ["sudo apt install ffmpeg   # Fedora : sudo dnf install ffmpeg"]


def ffprobe_de(s: Sonde, exe: str) -> bool:
    p = Path(exe)
    return s.existe(p.with_name(p.name.replace("ffmpeg", "ffprobe"))) or bool(s.env.get("FFPROBE")) \
        or bool(s.which("ffprobe"))


def auto_ffmpeg(s: Sonde) -> tuple:
    """Ce que le montage prend quand config.json ne dit rien (settings.find_ffmpeg) : le premier
    ffmpeg qui a libass, sinon le premier trouvé. Rend (celui-là, tout ce qui a été vu)."""
    vus, deja = [], set()
    for p in (s.env.get("FFMPEG"),) + FFMPEG_CANDIDATS + (s.which("ffmpeg"),):
        if not p or p in deja:
            continue
        deja.add(p)
        i = lis_ffmpeg(s, p)
        if i:
            i["ffprobe"] = ffprobe_de(s, p)
            vus.append(i)
    avec = [i for i in vus if i["libass"]]
    return (avec or vus or [None])[0], vus


def convient(i: dict | None, sous_titres: bool) -> bool:
    return bool(i) and i["ffprobe"] and (i["libass"] or not sous_titres)


def sans_zscale(s: Sonde, c: Contexte, i: dict, det: str) -> Constat:
    """Un ffmpeg qui convient : ok, ou attention s'il n'a pas zscale (le HDR de l'iPhone)."""
    if i.get("zscale", True):
        return Constat("ffmpeg", "ffmpeg", "ok", det)
    fix = (["brew install ffmpeg-full   # a zscale et libass, s'installe à côté"] if c.systeme == "Darwin"
           else ["# un ffmpeg compilé avec libzimg (zscale) : celui de ta distribution ou de gyan.dev l'a d'ordinaire"])
    return Constat("ffmpeg", "ffmpeg", "attention",
                   det + " ; sans zscale : une vidéo iPhone en HDR sortira délavée", fix)


def verifie_ffmpeg(s: Sonde, c: Contexte) -> Constat:
    ecris = [f"{c.py} {c.script} --ecris"]
    cfg_ff = c.cfg.get("ffmpeg")
    auto, vus = auto_ffmpeg(s)
    libass = lambda i: "avec libass (sous-titres)" if i["libass"] else "sans libass : pas de sous-titres incrustés, tu n'en veux pas"
    if cfg_ff:                                          # le montage prend celui-là, tel quel
        i = lis_ffmpeg(s, str(s.chemin(cfg_ff)))
        if i:
            i["ffprobe"] = ffprobe_de(s, i["chemin"])
        if convient(i, c.sous_titres):
            return sans_zscale(s, c, i, f"{i['version']}, {libass(i)} — {cfg_ff} (config.json)")
        pourquoi = "introuvable" if not i else ("sans ffprobe à côté" if not i["ffprobe"] else "sans libass")
        if convient(auto, c.sous_titres):
            return Constat("ffmpeg", "ffmpeg", "a_faire",
                           f"config.json pointe {cfg_ff} ({pourquoi}) ; --ecris retire la ligne, "
                           f"le montage prendra {montre(s, auto['chemin'])}", ecris, bloque=True)
        return Constat("ffmpeg", "ffmpeg", "manque", f"config.json pointe {cfg_ff} ({pourquoi})",
                       installe_ffmpeg(c) + ["# puis : " + ecris[0]], bloque=True)
    if not auto:
        return Constat("ffmpeg", "ffmpeg", "manque", "introuvable", installe_ffmpeg(c), bloque=True)
    if convient(auto, c.sous_titres):
        hors_path = "" if auto["chemin"] == s.which("ffmpeg") else " (hors du PATH : le montage le trouve tout seul)"
        return sans_zscale(s, c, auto, f"{auto['version']}, {libass(auto)} — {montre(s, auto['chemin'])}{hors_path}")
    if not auto["ffprobe"]:
        return Constat("ffmpeg", "ffmpeg", "manque", f"{auto['version']} sans ffprobe ({montre(s, auto['chemin'])})",
                       installe_ffmpeg(c), bloque=True)
    pourquoi = ("# la formule ffmpeg de Homebrew est compilée sans libass ; ffmpeg-full l'a, s'installe à côté, "
                "et le montage le trouve tout seul" if c.systeme == "Darwin" else "# le ffmpeg de ta distribution a libass")
    return Constat("ffmpeg", "ffmpeg", "manque",
                   f"{auto['version']} sans libass : la vidéo sortirait sans sous-titres incrustés (le .srt reste écrit) "
                   f"— {montre(s, auto['chemin'])}",
                   installe_ffmpeg(c) + [pourquoi, "# ou bien : pas de sous-titres incrustés (--sous-titres non)"],
                   bloque=True)


def cherche_whisper(s: Sonde, c: Contexte) -> str | None:
    w = s.which("whisper-cli") or s.which("whisper-cpp")
    if not w and c.brew and s.existe(f"{c.brew}/bin/whisper-cli"):
        w = f"{c.brew}/bin/whisper-cli"
    return w


def verifie_whisper(s: Sonde, c: Contexte) -> Constat:
    w = cherche_whisper(s, c)
    if w:
        return Constat("whisper", "whisper-cli", "ok", montre(s, w))
    if c.moteur != "whisper":
        return Constat("whisper", "whisper-cli", "option", "absent (pas besoin avec ElevenLabs)")
    if c.systeme == "Darwin":
        fix = ["brew install whisper-cpp"]
    elif c.systeme == "Windows":
        fix = [f"# télécharge whisper-bin-x64.zip sur {WHISPER_RELEASES} (dernière version), "
               "dézippe-le et ajoute ce dossier au PATH, puis rouvre le terminal"]
    else:
        fix = ["sudo apt install build-essential cmake git",
               "git clone https://github.com/ggml-org/whisper.cpp && cmake -S whisper.cpp -B whisper.cpp/build "
               "-DBUILD_SHARED_LIBS=OFF && cmake --build whisper.cpp/build -j --config Release && "
               "sudo cp whisper.cpp/build/bin/whisper-cli /usr/local/bin/"]
    return Constat("whisper", "whisper-cli", "manque", "introuvable (whisper.cpp)", fix, bloque=True)


def cherche_modele(s: Sonde, nom: str) -> tuple:
    """Comme stt.find_model : un chemin donné, sinon ggml-<nom>.bin dans un des dossiers connus.
    Rend (le fichier, sa taille, s'il est complet, si le nom était un chemin)."""
    if s.existe(nom) and not s.est_dossier(nom):
        p = s.chemin(nom)
        t = s.taille(p)
        return p, t, bool(t), True
    if "/" in nom or "\\" in nom or nom.endswith(".bin"):
        return s.chemin(nom), None, False, True
    attendu = MODELES.get(nom)
    for d in MODELES_DIRS:
        p = s.chemin(f"{d}/ggml-{nom}.bin")
        t = s.taille(p)
        if t:
            return p, t, (not attendu or t >= 0.99 * attendu), False
    return s.chemin(f"{MODELES_DIRS[0]}/ggml-{nom}.bin"), None, False, False


def verifie_modele(s: Sonde, c: Contexte) -> Constat:
    nom = c.modele
    if c.moteur != "whisper":
        return Constat("modele", "Modèle whisper", "option", "pas besoin avec ElevenLabs")
    p, t, complet, chemin = cherche_modele(s, nom)
    telecharge = [f"{c.py} {c.script} --modele"]
    if chemin:
        if t:
            return Constat("modele", "Modèle whisper", "ok", f"{montre(s, p)} ({go(t)})")
        return Constat("modele", "Modèle whisper", "manque", f"config.json : whisper_model pointe {nom}, introuvable",
                       [f"{c.py} {c.script} --ecris --modele {MODELE_DEFAUT}"], bloque=True)
    taille = go(MODELES[nom]) if nom in MODELES else "taille inconnue"
    if t and not complet:
        return Constat("modele", "Modèle whisper", "manque",
                       f"{montre(s, p)} incomplet ({go(t)} sur {taille}) : à retélécharger",
                       [f"# efface {montre(s, p)}, puis :"] + telecharge, bloque=True)
    if t:
        return Constat("modele", "Modèle whisper", "ok", f"{nom} ({go(t)}) dans {montre(s, p.parent)}")
    det = f"{nom} absent ({taille}) : il se télécharge tout seul au premier montage, ou maintenant"
    if s.existe(str(p) + ".part"):
        det += " (un téléchargement interrompu traîne : --modele recommence)"
    return Constat("modele", "Modèle whisper", "a_faire", det, telecharge)


def commande_cle(c: Contexte) -> list:
    lit = {"Darwin": "pbpaste", "Windows": "Get-Clipboard"}.get(c.systeme, "xclip -selection clipboard -o")
    out = ["# copie ta clé (elevenlabs.io), ne la colle pas dans la conversation, puis :",
           f"{lit} | {c.py} {c.script} --cle-elevenlabs-stdin"]
    if c.systeme == "Linux":
        out.append("# sous Wayland : wl-paste au lieu de xclip")
    return out


def verifie_elevenlabs(s: Sonde, c: Contexte) -> Constat:
    dans_env = bool(s.env.get("ELEVENLABS_API_KEY", "").strip())
    dans_fichier = bool(lire_env(s.lit(ENV)).get("ELEVENLABS_API_KEY", "").strip())
    utile = c.moteur == "elevenlabs"
    if dans_env or dans_fichier:
        ou = "dans la variable ELEVENLABS_API_KEY" if dans_env else f"dans {ENV}"
        if dans_fichier and c.systeme != "Windows":
            m = s.mode(ENV)
            if m is not None and m & 0o077:
                return Constat("elevenlabs", "Clé ElevenLabs", "attention",
                               f"présente {ou}, mais le fichier est lisible par d'autres comptes ({oct(m)[2:]})",
                               [f"chmod 600 {ENV}"])
        if utile:
            return Constat("elevenlabs", "Clé ElevenLabs", "ok", f"présente {ou}")
        return Constat("elevenlabs", "Clé ElevenLabs", "option", f"présente {ou} ; le moteur choisi est whisper")
    if utile:
        return Constat("elevenlabs", "Clé ElevenLabs", "manque", "pas de clé (le moteur choisi est ElevenLabs)",
                       commande_cle(c), bloque=True)
    return Constat("elevenlabs", "Clé ElevenLabs", "option", "pas de clé (pas besoin avec whisper)")


def verifie_node(s: Sonde, c: Contexte) -> Constat:
    n = s.which("node")
    v = None
    if n:
        code, out = s.lance([n, "-v"])
        m = re.search(r"v?(\d+\.\d+\.\d+)", out) if code == 0 else None
        v = m.group(1) if m else None
    fix = {"Darwin": ["brew install node"], "Windows": ["winget install OpenJS.NodeJS.LTS   # puis rouvre le terminal"]}.get(
        c.systeme, ["sudo apt install nodejs npm   # node -v doit dire 18 ou plus, sinon : https://nodejs.org"])
    sans = "le titre et le carton de fin sont dessinés par ffmpeg, la vidéo sort quand même"
    if v and vers(v)[0] >= NODE_MIN:
        if not c.remotion:
            return Constat("node", "Node (Remotion)", "option", f"v{v} présent ; Remotion : non")
        det = f"v{v}"
        if not s.remotion_installe():
            det += " ; Remotion s'installe tout seul au premier rendu (npm install, une fois)"
        return Constat("node", "Node (Remotion)", "ok", det)
    if not c.remotion:
        quoi = f"v{v}, trop vieux" if v else "absent"
        return Constat("node", "Node (Remotion)", "option", f"{quoi} (pas besoin sans Remotion)")
    quoi = f"v{v} : Remotion veut Node {NODE_MIN} ou plus" if v else "absent"
    return Constat("node", "Node (Remotion)", "attention", f"{quoi} ; {sans}",
                   fix + ["# ou bien : pas de Remotion (--remotion non), et cette ligne se tait"])


def verifie_sortie(s: Sonde, c: Contexte) -> Constat:
    d = c.sortie
    if s.est_dossier(d):
        if s.ecrivable(d):
            return Constat("sortie", "Dossier de sortie", "ok", d)
        return Constat("sortie", "Dossier de sortie", "manque", f"{d} : pas le droit d'y écrire",
                       [f"# choisis un autre dossier : {c.py} {c.script} --ecris --sortie <dossier>"], bloque=True)
    if s.existe(d):
        return Constat("sortie", "Dossier de sortie", "manque", f"{d} est un fichier, pas un dossier",
                       [f"{c.py} {c.script} --ecris --sortie <dossier>"], bloque=True)
    if s.ecrivable(d):
        return Constat("sortie", "Dossier de sortie", "a_faire", f"{d} n'existe pas encore : --ecris le crée")
    return Constat("sortie", "Dossier de sortie", "manque", f"{d} : impossible à créer (pas le droit d'écrire)",
                   [f"# choisis un autre dossier : {c.py} {c.script} --ecris --sortie <dossier>"], bloque=True)


def resume_config(cfg: dict) -> str:
    morceaux = []
    if cfg.get("stt"):
        morceaux.append({"whisper": "whisper", "elevenlabs": "ElevenLabs"}.get(cfg["stt"], cfg["stt"]))
    if cfg.get("lang"):
        morceaux.append(str(cfg["lang"]))
    if cfg.get("output_dir"):
        morceaux.append(str(cfg["output_dir"]))
    if "subtitles" in cfg:
        morceaux.append("sous-titres " + ("oui" if cfg["subtitles"] else "non"))
    if "remotion" in cfg:
        morceaux.append("Remotion " + ("oui" if cfg["remotion"] else "non"))
    return " · ".join(morceaux) or "vide"


def erreurs_config(cfg: dict) -> list:
    e = []
    if "stt" in cfg and cfg["stt"] not in MOTEURS:
        e.append(f"stt = {cfg['stt']!r} (whisper ou elevenlabs)")
    for k in ("subtitles", "remotion"):
        if k in cfg and not isinstance(cfg[k], bool):
            e.append(f"{k} = {cfg[k]!r} (true ou false)")
    if "lang" in cfg and not (isinstance(cfg["lang"], str) and re.fullmatch(r"[a-z]{2,3}|auto", cfg["lang"])):
        e.append(f"lang = {cfg['lang']!r} (un code de langue : fr, en, es...)")
    for k in cfg:
        if re.search(r"key|cle|secret|token", k, re.I):
            e.append(f"{k} : une clé n'a rien à faire dans config.json (--ecris la déplace dans env)")
    return e


def verifie_config(s: Sonde, c: Contexte) -> Constat:
    ecris = f"{c.py} {c.script} --ecris"
    if c.cfg_etat == "absente":
        return Constat("config", "Configuration", "a_faire",
                       f"{CONFIG} pas encore écrite : la skill setup pose ses questions, puis --ecris")
    if c.cfg_etat == "illisible":
        return Constat("config", "Configuration", "manque", f"{CONFIG} illisible ({c.cfg_erreur})",
                       [ecris + "   # la réécrit ; l'ancienne est gardée en .bak"], bloque=True)
    e = erreurs_config(c.cfg)
    if e:
        return Constat("config", "Configuration", "manque", f"{CONFIG} : " + " ; ".join(e),
                       [ecris + " --moteur ... --sous-titres oui|non --remotion oui|non"], bloque=True)
    return Constat("config", "Configuration", "ok", resume_config(c.cfg))


def verifie_montage(s: Sonde, c: Contexte) -> Constat | None:
    if s.montage_present():
        return None
    return Constat("montage", "Skill de montage", "manque",
                   f"la skill edit n'est pas à côté de setup ({montre(s, MONTAGE)})",
                   ["# installe toutes les skills du dépôt : npx skills add vincentventalon/my-claude-skills -a claude-code"],
                   bloque=True)


def verifie_homebrew(c: Contexte, constats: list) -> Constat | None:
    if c.systeme != "Darwin":
        return None
    if c.brew:
        return Constat("homebrew", "Homebrew", "ok", c.brew)
    besoin = any(x.startswith("brew ") for k in constats if k.bloque for x in k.corrige)
    return Constat("homebrew", "Homebrew", "manque" if besoin else "option",
                   "absent : les commandes brew ci-dessous le demandent d'abord" if besoin else "absent (rien à installer avec)",
                   [HOMEBREW + "   # à lancer toi-même : il demande ton mot de passe"] if besoin else [], bloque=besoin)


@dataclass
class Diagnostic:
    contexte: Contexte
    constats: list

    @property
    def pret(self) -> bool:
        return not any(k.bloque for k in self.constats)

    def plan_brew(self) -> list:
        cmds = []
        for k in self.constats:
            if k.bloque:
                cmds += [x for x in k.corrige if x.startswith("brew ")]
        return list(dict.fromkeys(cmds))


def diagnostic(s: Sonde) -> Diagnostic:
    c = contexte(s)
    k = [verifie_systeme(s, c), verifie_python(s, c), verifie_ffmpeg(s, c), verifie_whisper(s, c),
         verifie_modele(s, c), verifie_elevenlabs(s, c), verifie_node(s, c), verifie_sortie(s, c),
         verifie_config(s, c)]
    m = verifie_montage(s, c)
    if m:
        k.append(m)
    h = verifie_homebrew(c, k)
    if h:
        k.insert(1, h)
    return Diagnostic(c, k)


# --------------------------------------------------------------------------- la sortie

LIBELLE = {"ok": "ok", "manque": "MANQUE", "a_faire": "à faire", "option": "option", "attention": "attention"}


def texte(d: Diagnostic) -> str:
    L = ["montage vidéo — diagnostic d'installation", ""]
    for k in d.constats:
        L.append(f"  {LIBELLE[k.etat]:<10} {k.titre:<18} {k.detail}")
        if k.etat != "ok":
            for x in k.corrige:
                L.append(f"  {'':<10} {'':<18}   {x if x.startswith('#') else '$ ' + x}")
    c = d.contexte
    bloquants = [k.titre for k in d.constats if k.bloque]
    L.append("")
    if not bloquants:
        L.append("Prêt pour le montage.")
    else:
        L.append(f"Il manque : {', '.join(bloquants)}. Les commandes ci-dessus réparent.")
        if c.systeme == "Darwin" and d.plan_brew():
            L.append(f"Sur macOS, `{c.py} {c.script} --installe` lance les installations Homebrew (il les affiche d'abord).")
    return "\n".join(L) + "\n"


def en_json(d: Diagnostic, s: Sonde, faits: list) -> str:
    c = d.contexte
    out = {"pret": d.pret, "systeme": c.systeme, "config_fichier": montre(s, s.chemin(CONFIG)),
           "env_fichier": montre(s, s.chemin(ENV)), "config": c.cfg, "config_etat": c.cfg_etat,
           "choix": {"stt": c.stt, "moteur_effectif": c.moteur, "subtitles": c.sous_titres,
                     "remotion": c.remotion, "whisper_model": c.modele, "output_dir": c.sortie},
           "a_installer_brew": d.plan_brew() if c.systeme == "Darwin" else [],
           "faits": faits, "constats": [asdict(k) for k in d.constats]}
    return json.dumps(out, ensure_ascii=False, indent=1)


# --------------------------------------------------------------------------- l'écriture

def oui_non(v: str) -> bool:
    v = v.strip().lower()
    if v in ("oui", "o", "yes", "y", "true", "1"):
        return True
    if v in ("non", "n", "no", "false", "0"):
        return False
    raise argparse.ArgumentTypeError("oui ou non")


def moteur(v: str) -> str:
    v = v.strip().lower()
    v = {"scribe": "elevenlabs", "eleven": "elevenlabs", "elevenlabs-scribe": "elevenlabs", "whisper.cpp": "whisper"}.get(v, v)
    if v not in MOTEURS:
        raise argparse.ArgumentTypeError("whisper ou elevenlabs")
    return v


def langue(v: str) -> str:
    v = v.strip().lower()
    if not re.fullmatch(r"[a-z]{2,3}|auto", v):
        raise argparse.ArgumentTypeError("un code de langue : fr, en, es, de...")
    return v


def tilde(s: Sonde, d: str) -> str:
    """Le dossier tel qu'on l'écrit dans config.json : ~/... quand il est sous le dossier personnel."""
    d = d.strip()
    if d.startswith("~"):
        return d.replace("\\", "/")
    p = Path(os.path.abspath(str(s.chemin(d))))
    try:
        return "~/" + p.relative_to(s.home).as_posix()
    except ValueError:
        return str(p)


def ecrit_atomique(chemin: Path, contenu: str, mode: int | None = None) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    if mode is not None:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenu)
        os.chmod(str(tmp), mode)
    else:
        tmp.write_text(contenu, encoding="utf-8")
    os.replace(str(tmp), str(chemin))
    if mode is not None:
        os.chmod(str(chemin), mode)


def ecrit_cle(s: Sonde, cle: str) -> str:
    p = s.chemin(ENV)
    lignes = [l for l in (s.lit(ENV) or "").splitlines()
              if not re.match(r"\s*(export\s+)?ELEVENLABS_API_KEY\s*=", l)]
    lignes.append(f"ELEVENLABS_API_KEY={cle}")
    ecrit_atomique(p, "\n".join(lignes) + "\n", 0o600)
    return f"clé ElevenLabs enregistrée dans {montre(s, p)} (mode 600)"


def ecris(s: Sonde, a: argparse.Namespace) -> list:
    """Écrit config.json (fusionné avec l'existant) et crée le dossier de sortie. Rend ce qui a été fait."""
    faits = []
    p = s.chemin(CONFIG)
    cfg, etat, _ = lire_config(s)
    if etat == "illisible":
        bak = p.with_name(f"config.json.bak-{datetime.date.today().isoformat()}")
        shutil.copyfile(str(p), str(bak))
        faits.append(f"config.json illisible gardée en {montre(s, bak)}")
    avant = dict(cfg)
    for k in list(cfg):                                 # une clé n'a rien à faire ici : vers env
        if re.search(r"key|cle|secret|token", k, re.I):
            v = cfg.pop(k)
            if isinstance(v, str) and v.strip() and "ELEVENLABS" in k.upper():
                faits.append(ecrit_cle(s, v.strip()))
            faits.append(f"config.json : {k} retirée")
    if a.moteur:
        cfg["stt"] = a.moteur
    if a.langue:
        cfg["lang"] = a.langue
    if a.sortie:
        cfg["output_dir"] = tilde(s, a.sortie)
    if a.sous_titres is not None:
        cfg["subtitles"] = a.sous_titres
    if a.remotion is not None:
        cfg["remotion"] = a.remotion
    if a.modele:
        cfg["whisper_model"] = a.modele
    c = Contexte(s.systeme(), homebrew(s), "", "", cfg, "ok")
    if cfg.get("ffmpeg"):                               # une ligne ffmpeg qui ne convient pas part, si le
        i = lis_ffmpeg(s, str(s.chemin(cfg["ffmpeg"])))  # montage en trouve un bon tout seul
        if i:
            i["ffprobe"] = ffprobe_de(s, i["chemin"])
        auto, _ = auto_ffmpeg(s)
        if not convient(i, c.sous_titres) and convient(auto, c.sous_titres):
            faits.append(f"config.json : ffmpeg {cfg.pop('ffmpeg')} retiré (le montage prendra {montre(s, auto['chemin'])})")
    if c.moteur == "whisper" and "whisper_model" not in cfg:
        cfg["whisper_model"] = MODELE_DEFAUT
    ordre = {k: i for i, k in enumerate(CLES)}
    cfg = dict(sorted(cfg.items(), key=lambda kv: ordre.get(kv[0], len(CLES))))
    if cfg != avant or etat != "ok":
        ecrit_atomique(p, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
        changes = [k for k in cfg if avant.get(k) != cfg[k]] + [k for k in avant if k not in cfg]
        faits.append(f"{montre(s, p)} écrit" + (f" ({', '.join(changes)})" if changes else ""))
    d = s.chemin(cfg.get("output_dir") or SORTIE_DEFAUT)
    if not d.is_dir():
        d.mkdir(parents=True, exist_ok=True)
        faits.append(f"dossier de sortie créé : {montre(s, d)}")
    env = s.chemin(ENV)
    if env.exists() and s.systeme() != "Windows":
        m = stat.S_IMODE(env.stat().st_mode)
        if m & 0o077:
            os.chmod(str(env), 0o600)
            faits.append(f"{montre(s, env)} remis en mode 600")
    return faits


def lit_cle(entree) -> str:
    if entree is None:
        entree = sys.stdin
    if hasattr(entree, "isatty") and entree.isatty():
        cle = getpass.getpass("Colle ta clé ElevenLabs (rien ne s'affiche), puis Entrée : ")
    else:
        cle = entree.read()
    cle = (cle or "").strip().strip('"').strip("'")
    if not cle:
        raise ValueError("rien reçu sur l'entrée : copie d'abord la clé, puis relance la commande")
    if re.search(r"\s", cle) or not cle.isascii() or not cle.isprintable():
        raise ValueError("ce qui a été reçu n'a pas la forme d'une clé (des espaces ou plusieurs lignes) : "
                         "recopie la clé seule")
    if len(cle) < 20:
        raise ValueError("trop court pour une clé ElevenLabs : recopie-la en entier")
    return cle


def telecharge_modele(s: Sonde, nom: str) -> int:
    if "/" in nom or "\\" in nom or nom.endswith(".bin"):
        print(f"setup : {nom} est un chemin, pas un nom de modèle à télécharger", file=sys.stderr)
        return 2
    deja, t, complet, _ = cherche_modele(s, nom)
    if t and complet:
        print(f"déjà là : {montre(s, deja)} ({go(t)})")
        return 0
    dest = s.chemin(f"{MODELES_DIRS[0]}/ggml-{nom}.bin")
    attendu = MODELES.get(nom)
    url = MODELES_URL + f"ggml-{nom}.bin"
    print(f"téléchargement de ggml-{nom}.bin ({go(attendu) if attendu else 'taille inconnue'}) vers {montre(s, dest.parent)}")
    print(f"  depuis {url}", flush=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    vu = [-1]

    def avance(n, b, total):
        if total > 0:
            pc = min(100, int(n * b * 100 / total))
            if pc >= vu[0] + 5:
                vu[0] = pc
                print(f"  {pc:3d} %  ({n * b / 1e9:.2f} / {total / 1e9:.2f} Go)", flush=True)

    try:
        urllib.request.urlretrieve(url, str(tmp), avance)
    except (OSError, ValueError) as e:
        print(f"setup : le téléchargement a échoué ({e}). Relance la même commande pour recommencer.", file=sys.stderr)
        return 1
    os.replace(str(tmp), str(dest))
    print(f"fait : {montre(s, dest)} ({go(dest.stat().st_size)})")
    return 0


def installe(s: Sonde, d: Diagnostic, a_blanc: bool) -> tuple:
    """macOS + Homebrew : lance les `brew install` qui manquent. Rend (code, ce qui a été fait)."""
    c = d.contexte
    if c.systeme != "Darwin":
        print("setup : --installe ne lance rien hors de macOS. Les commandes de ta machine sont dans le diagnostic :")
        for k in d.constats:
            if k.bloque:
                for x in k.corrige:
                    print(f"  {x if x.startswith('#') else '$ ' + x}")
        return 2, []
    plan = d.plan_brew()
    if not plan:
        print("Rien à installer avec Homebrew.")
        return 0, []
    if not c.brew:
        print("Homebrew n'est pas installé. Lance d'abord toi-même (il demande ton mot de passe) :")
        print(f"  $ {HOMEBREW}")
        print("puis relance --installe.")
        return 2, []
    print("Je vais lancer, dans l'ordre :")
    for x in plan:
        print(f"  $ {x}")
    if a_blanc:
        print("(à blanc : rien n'est lancé)")
        return 0, []
    faits = []
    brew = f"{c.brew}/bin/brew"
    for x in plan:
        argv = [brew] + x.split("#")[0].split()[1:]
        print(f"\n$ {x}", flush=True)
        if subprocess.run(argv).returncode != 0:
            print(f"setup : la commande a échoué, on s'arrête là : {x}", file=sys.stderr)
            return 1, faits
        faits.append(x)
    return 0, faits


# --------------------------------------------------------------------------- l'entrée

def main(argv: list | None = None, sonde: Sonde | None = None, entree=None) -> int:
    ap = argparse.ArgumentParser(
        prog="setup.py",
        description="Installation du montage vidéo : diagnostic (par défaut), configuration, installations.")
    ap.add_argument("--diagnostic", action="store_true", help="le diagnostic (l'action par défaut)")
    ap.add_argument("--json", action="store_true", help="la sortie pour Claude")
    ap.add_argument("--ecris", action="store_true", help="écrit config.json avec les choix ci-dessous et crée le dossier de sortie")
    ap.add_argument("--moteur", type=moteur, help="transcription : whisper ou elevenlabs")
    ap.add_argument("--langue", type=langue, help="la langue parlée dans les vidéos : fr, en, es...")
    ap.add_argument("--sortie", help=f"le dossier des vidéos montées (défaut : {SORTIE_DEFAUT})")
    ap.add_argument("--sous-titres", dest="sous_titres", type=oui_non, help="sous-titres incrustés : oui ou non")
    ap.add_argument("--remotion", type=oui_non, help="finition Remotion (Node) : oui ou non")
    ap.add_argument("--modele", nargs="?", const="", default=None, metavar="NOM",
                    help="seul : télécharge le modèle whisper maintenant ; avec --ecris : le modèle à utiliser "
                         "(large-v3-turbo, large-v3-turbo-q5_0, small)")
    ap.add_argument("--cle-elevenlabs-stdin", action="store_true",
                    help=f"lit la clé ElevenLabs sur l'entrée standard et l'écrit dans {ENV} (mode 600)")
    ap.add_argument("--installe", action="store_true", help="macOS : lance les brew install qui manquent")
    ap.add_argument("--a-blanc", action="store_true", help="avec --installe : affiche sans rien lancer")
    ap.add_argument("--simule", metavar="MACHINE.json", help="le diagnostic d'une machine simulée (rien n'est écrit)")
    a = ap.parse_args(argv)

    if a.simule:
        m = json.loads(Path(a.simule).read_text(encoding="utf-8"))
        sonde = SondeSimulee(m)
    sonde = sonde or Sonde()
    ecrit_qqch = a.ecris or a.cle_elevenlabs_stdin or (a.installe and not a.a_blanc) or (a.modele is not None and not a.ecris)
    if isinstance(sonde, SondeSimulee) and not sonde.disque and ecrit_qqch:
        print("setup : machine simulée, rien n'est écrit ni installé (seul le diagnostic tourne)", file=sys.stderr)
        return 2
    if (a.moteur or a.langue or a.sortie or a.sous_titres is not None or a.remotion is not None) and not a.ecris:
        print("setup : --moteur, --langue, --sortie, --sous-titres et --remotion vont avec --ecris", file=sys.stderr)
        return 2

    faits = []
    if a.cle_elevenlabs_stdin:
        try:
            cle = lit_cle(entree)
        except ValueError as e:
            print(f"setup : {e}. Rien n'a été écrit.", file=sys.stderr)
            return 2
        faits.append(ecrit_cle(sonde, cle))
        del cle
    if a.modele is not None and not a.ecris:
        nom = a.modele or contexte(sonde).modele
        code = telecharge_modele(sonde, nom)
        if code:
            return code
    if a.installe:
        code, f = installe(sonde, diagnostic(sonde), a.a_blanc)
        faits += f
        if code or a.a_blanc:
            return code
        if f and lire_config(sonde)[1] != "absente":     # ffmpeg-full posé à côté : config.json le dit
            faits += ecris(sonde, argparse.Namespace(moteur=None, langue=None, sortie=None, sous_titres=None,
                                                     remotion=None, modele=None))
    if a.ecris:
        faits += ecris(sonde, a)

    d = diagnostic(sonde)
    if a.json:
        print(en_json(d, sonde, faits))
    else:
        for f in faits:
            print(f"fait : {f}")
        if faits:
            print()
        sys.stdout.write(texte(d))
    return 0 if d.pret else 1


if __name__ == "__main__":
    sys.exit(main())
