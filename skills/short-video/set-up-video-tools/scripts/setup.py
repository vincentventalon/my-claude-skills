#!/usr/bin/env python3
"""setup.py — l'installation des skills vidéo : le montage (edit), et yt-dlp pour audit et outliers.
Diagnostic, configuration, installations.

    python3 setup.py                     # le diagnostic : une ligne par point, n'écrit rien
    python3 setup.py --json              # le même, pour Claude
    python3 setup.py --ecris --moteur whisper --langue fr --sortie ~/Videos/edited \\
                     --sous-titres oui --remotion non
                                         # écrit ~/.config/video-editing/config.json (fusionné avec
                                         # l'existant) et crée le dossier de sortie
    python3 setup.py --ecris --police "Montserrat Black" --couleur jaune
                                         # la police et la couleur du mot dit : seulement les clés qui
                                         # changent, dans ~/.config/video-editing/style.json
    pbpaste | python3 setup.py --cle-elevenlabs-stdin
                                         # la clé ElevenLabs, lue sur l'entrée standard, écrite dans
                                         # ~/.config/video-editing/env (mode 600), jamais affichée
    python3 setup.py --installe --a-blanc    # ce qui manque, affiché (macOS : les `brew install`, yt-dlp
                                             # compris ; Windows : whisper.cpp, que setup télécharge
                                             # lui-même, et les commandes winget)
    python3 setup.py --installe              # ... et lancé
    python3 setup.py --modele            # télécharge le modèle whisper maintenant (sinon : au premier montage)
    python3 setup.py --simule machine.json   # le diagnostic d'une machine simulée (banc/test_setup.py)

Ce qu'il regarde : Python (3.10 ou plus), ffmpeg + ffprobe et libass (les sous-titres incrustés),
whisper-cli et son modèle, la clé ElevenLabs, Node (pour Remotion), yt-dlp (audit et outliers lisent
les comptes avec, sans connexion ; le montage s'en passe), le dossier de sortie, config.json. Une
ligne par point : ok, MANQUE (le montage ne peut pas tourner), à faire (setup ou le premier montage
s'en charge), option (pas besoin avec les choix faits), attention.

Le contrat, partagé avec la skill de montage :
  ~/.config/video-editing/config.json, toutes les clés facultatives :
    {"stt": "whisper" | "elevenlabs", "whisper_model": "large-v3-turbo", "ffmpeg": "/chemin/ffmpeg",
     "lang": "fr", "output_dir": "~/Videos/edited", "subtitles": true, "remotion": true}
  la clé ElevenLabs seulement dans ELEVENLABS_API_KEY (l'environnement) ou dans
  ~/.config/video-editing/env (mode 600, des lignes KEY=valeur). Jamais dans config.json.
  ~/.config/video-editing/style.json : ce qui change du style livré avec le montage (son style.json) ;
  setup n'y pose que la police (font, font_file) et la couleur du mot dit (captions.highlight, et
  title.highlight, split.highlight, end_card.box qui la suivent), le reste se règle à la main.

Sur Windows, `py` (le lanceur de python.org) ou `python` au lieu de `python3`.
Bibliothèque standard seulement. Tourne dès Python 3.8, pour pouvoir dire qu'il faut 3.10.
Exit : 0 prêt, 1 il manque quelque chose, 2 refusé (mauvaise option, clé illisible, simulation).
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import getpass
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

for _s in (sys.stdout, sys.stderr):          # Windows écrit en cp1252 dans un tube : Claude lirait des « � »
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ICI = Path(__file__).resolve().parent
MONTAGE = ICI.parent.parent / "edit-my-video"          # à côté de set-up-video-tools

CONFIG_DIR = "~/.config/video-editing"
CONFIG = CONFIG_DIR + "/config.json"
ENV = CONFIG_DIR + "/env"
STYLE = CONFIG_DIR + "/style.json"
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
# Windows : les versions vX.Y.Z de whisper.cpp n'ont aucun fichier ; les zips sont dans les builds bNNNN.
WHISPER_API = "https://api.github.com/repos/ggml-org/whisper.cpp/releases?per_page=20"
# Sans ces options, winget attend un « Y » au premier usage : la commande ne rend jamais la main à Claude.
WINGET = " -e --accept-package-agreements --accept-source-agreements"
# Les skills qui lisent un compte avec yt-dlp, installées à côté de setup. Sans elles, yt-dlp ne sert à rien.
LECTEURS = ("audit-my-account", "find-outliers-in-my-niche")
# Un .exe qui ne démarre pas faute de DLL (0xC0000135, 0xC0000139, 0xC000007B), signé ou non selon Python.
DLL_MANQUANTE = {3221225781, 3221225785, 3221225595, -1073741515, -1073741511, -1073741701}

# Le style : la police livrée avec le montage (edit-my-video/fonts/), les couleurs proposées.
POLICE_DEFAUT = "Inter ExtraBold"
POLICES_LIVREES = {"inter extrabold": "Inter ExtraBold", "inter": "Inter ExtraBold"}
COULEUR_DEFAUT = "#3DDC97"
COULEURS = {"menthe": "#3DDC97", "jaune": "#FFD23F", "orange": "#FF8C42", "rose": "#FF5DA2", "bleu": "#4DA3FF"}
COULEURS_EN = {"mint": "menthe", "green": "menthe", "vert": "menthe", "yellow": "jaune", "pink": "rose", "blue": "bleu"}
# Si le montage n'est pas à côté : les valeurs de son style.json qui comptent ici.
STYLE_LIVRE = {"font": POLICE_DEFAUT, "font_file": "", "captions": {"highlight": COULEUR_DEFAUT},
               "title": {"box": "#FFFFFF", "highlight": "#0F9D6B"}, "split": {"highlight": COULEUR_DEFAUT}}


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
            return self.chemin(p).read_text(encoding="utf-8-sig")   # -sig : un fichier enregistré par le Bloc-notes
        except (OSError, UnicodeDecodeError):
            return None

    def cherche(self, motif: str) -> list:
        return sorted(glob.glob(motif), reverse=True)

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

    def lecteurs_presents(self) -> list:
        return [n for n in LECTEURS if (ICI.parent.parent / n / "SKILL.md").exists()]

    def dossiers_polices(self) -> list:
        """Là où le système range les polices installées."""
        sy = self.systeme()
        if sy == "Darwin":
            return ["/System/Library/Fonts", "/Library/Fonts", str(self.home / "Library/Fonts")]
        if sy == "Windows":
            return [os.path.join(self.env.get("WINDIR", "C:/Windows"), "Fonts"),
                    str(local_appdata(self) / "Microsoft" / "Windows" / "Fonts")]
        return ["/usr/share/fonts", "/usr/local/share/fonts", str(self.home / ".local/share/fonts"),
                str(self.home / ".fonts")]


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
        if Path(exe).name.startswith("whisper") and exe in self.fichiers:
            code = int(self.m.get("whisper_code", 0))          # 3221225781 : une DLL manque (Windows)
            return code, "usage: whisper-cli [options] file0 file1 ...\n" if code == 0 else ""
        if Path(exe).name.startswith("yt-dlp") and exe in self.fichiers:
            code = int(self.m.get("ytdlp_code", 0))
            return code, str(self.m.get("ytdlp", "2026.10.22")) + "\n" if code == 0 else "ImportError\n"
        return 127, f"{exe}: introuvable (machine simulée)"

    def cherche(self, motif):
        return sorted((f for f in self.fichiers if fnmatch.fnmatchcase(f, motif)), reverse=True)

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

    def lecteurs_presents(self):                 # par défaut, audit et outliers sont là, comme après npx skills add
        return list(self.m.get("lecteurs", LECTEURS))

    def dossiers_polices(self):                  # seulement ceux de la machine simulée, sous `home`
        return [str(self.chemin(d)) for d in self.m.get("polices", [])] if self.disque else []


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
    py = "python3"
    if systeme == "Windows":       # python.org pose `py` ; `python` n'est dans le PATH que si la case a été cochée
        py = "py" if s.which("py") else "python"
    if s.python() < PYTHON_MIN:
        for n in ("python3.13", "python3.12", "python3.11", "python3.10"):
            if s.which(n):
                py = n
                break
    # Windows : le chemin entier, avec des / : « ~\... » ne se tape ni dans PowerShell (pas de ~ pour un
    # .exe) ni dans le Git Bash de Claude Code (\ y est un échappement) ; « C:/... » passe dans les deux
    script = cite((ICI / "setup.py").as_posix() if systeme == "Windows" else montre(s, ICI / "setup.py"))
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
    if c.py not in ("python3", "python", "py"):
        return Constat("python", "Python", "manque",
                       f"{texte} : il faut 3.10 ou plus ; {c.py} est déjà installé",
                       [f"# lance ce script et le montage avec {c.py} au lieu de python3"], bloque=True)
    fix = {"Darwin": "brew install python", "Windows": f"winget install Python.Python.3.12{WINGET}"}.get(
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
        return [f"winget install Gyan.FFmpeg{WINGET}   # ou : choco install ffmpeg-full ; le montage le trouve sans rouvrir le terminal"]
    return ["sudo apt install ffmpeg   # Fedora : sudo dnf install ffmpeg"]


def ffprobe_de(s: Sonde, exe: str) -> bool:
    p = Path(exe)
    return s.existe(p.with_name(p.name.replace("ffmpeg", "ffprobe"))) or bool(s.env.get("FFPROBE")) \
        or bool(s.which("ffprobe"))


def local_appdata(s: Sonde) -> Path:
    base = s.env.get("LOCALAPPDATA")
    return Path(base) if base else s.home / "AppData" / "Local"


def ffmpegs_winget(s: Sonde) -> tuple:
    """Windows : là où `winget install Gyan.FFmpeg` pose ffmpeg (settings.windows_ffmpegs) ; le montage
    le trouve là sans attendre que le terminal soit rouvert."""
    if s.systeme() != "Windows":
        return ()
    w = local_appdata(s) / "Microsoft" / "WinGet"
    return (str(w / "Links" / "ffmpeg.exe"),) + tuple(
        s.cherche(str(w / "Packages" / "Gyan.FFmpeg*" / "*" / "bin" / "ffmpeg.exe")))


def auto_ffmpeg(s: Sonde) -> tuple:
    """Ce que le montage prend quand config.json ne dit rien (settings.find_ffmpeg) : le premier
    ffmpeg qui a libass, sinon le premier trouvé. Rend (celui-là, tout ce qui a été vu)."""
    vus, deja = [], set()
    for p in (s.env.get("FFMPEG"),) + FFMPEG_CANDIDATS + (s.which("ffmpeg"),) + ffmpegs_winget(s):
        if not p or os.path.normcase(p) in deja:
            continue
        deja.add(os.path.normcase(p))
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


def dossier_whisper_windows(s: Sonde) -> Path:
    """Windows : où --installe dézippe whisper.cpp, et où le montage le cherche (settings.find_whisper)."""
    return local_appdata(s) / "whisper.cpp"


def cherche_whisper(s: Sonde, c: Contexte) -> str | None:
    w = s.which("whisper-cli") or s.which("whisper-cpp")       # whisper-cli.exe sur Windows (PATHEXT)
    if not w and c.brew and s.existe(f"{c.brew}/bin/whisper-cli"):
        w = f"{c.brew}/bin/whisper-cli"
    if not w and c.systeme == "Windows":                        # jamais main.exe : ce n'est plus qu'un avertissement
        d = dossier_whisper_windows(s)
        w = next((str(p) for p in (d / "Release" / "whisper-cli.exe", d / "whisper-cli.exe") if s.existe(p)), None)
    return w


def verifie_whisper(s: Sonde, c: Contexte) -> Constat:
    w = cherche_whisper(s, c)
    besoin = c.moteur == "whisper"
    if w:
        code, out = s.lance([w, "-h"])
        if code == 0:
            return Constat("whisper", "whisper-cli", "ok", montre(s, w))
        if c.systeme == "Windows" and code in DLL_MANQUANTE:
            arch = "arm64" if s.machine().upper() in ("ARM64", "AARCH64") else "x64"
            det = (f"{montre(s, w)} ne démarre pas : il manque le Visual C++ Redistributable de Microsoft "
                   "(MSVCP140.dll, VCOMP140.dll)")
            fix = [f"winget install Microsoft.VCRedist.2015+.{arch}{WINGET}"]
        else:
            det = f"{montre(s, w)} ne démarre pas (code {code}) {out.strip()[-160:]}".rstrip()
            fix = {"Darwin": ["brew reinstall whisper-cpp"],
                   "Windows": [f"# efface le dossier {montre(s, Path(w).parent)}, puis : {c.py} {c.script} --installe"]}.get(
                c.systeme, ["# recompile whisper.cpp (la commande de la ligne whisper-cli quand il manque)"])
        if not besoin:
            return Constat("whisper", "whisper-cli", "option", det + " (pas besoin avec ElevenLabs)")
        return Constat("whisper", "whisper-cli", "manque", det, fix, bloque=True)
    if not besoin:
        return Constat("whisper", "whisper-cli", "option", "absent (pas besoin avec ElevenLabs)")
    if c.systeme == "Darwin":
        fix = ["brew install whisper-cpp"]
    elif c.systeme == "Windows":
        fix = [f"{c.py} {c.script} --installe   # télécharge whisper.cpp (le zip officiel, GitHub) dans "
               f"{montre(s, dossier_whisper_windows(s))}, sans toucher au PATH",
               f"# ou à la main : whisper-bin-x64.zip de la dernière build bNNNN sur {WHISPER_RELEASES} "
               "(les versions vX.Y.Z n'ont pas de fichiers), dézippé, son dossier Release dans le PATH"]
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
    # Windows : par powershell, que la commande soit tapée dans PowerShell ou dans le Git Bash de Claude Code
    lit = {"Darwin": "pbpaste", "Windows": "powershell -NoProfile -Command Get-Clipboard"}.get(
        c.systeme, "xclip -selection clipboard -o")
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
    fix = {"Darwin": ["brew install node"],
           "Windows": [f"winget install OpenJS.NodeJS.LTS{WINGET}   # puis rouvre le terminal et Claude Code"]}.get(
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


def installe_ytdlp(c: Contexte) -> list:
    if c.systeme == "Darwin":
        return ["brew install yt-dlp"]
    if c.systeme == "Windows":
        return [f"winget install yt-dlp.yt-dlp{WINGET}   # puis rouvre le terminal et Claude Code"]
    return ["pipx install yt-dlp   # sans pipx : sudo apt install pipx ; le paquet apt yt-dlp est souvent trop vieux pour TikTok"]


def ytdlp_hors_path(s: Sonde, c: Contexte) -> str | None:
    """Un yt-dlp posé mais pas encore dans le PATH de ce terminal (winget, pipx, Homebrew sans ses « Next
    steps ») : audit et outliers le cherchent dans le PATH, il faut rouvrir le terminal."""
    if c.systeme == "Windows":
        w = local_appdata(s) / "Microsoft" / "WinGet"
        vus = (str(w / "Links" / "yt-dlp.exe"),) + tuple(s.cherche(str(w / "Packages" / "yt-dlp.yt-dlp*" / "yt-dlp.exe")))
    else:
        vus = ((f"{c.brew}/bin/yt-dlp",) if c.brew else ()) + (str(s.chemin("~/.local/bin/yt-dlp")),)
    return next((p for p in vus if s.existe(p)), None)


def verifie_ytdlp(s: Sonde, c: Contexte) -> Constat:
    """yt-dlp : audit et outliers lisent les comptes avec, sans connexion. Le montage s'en passe : ce point
    ne bloque jamais, mais --installe l'installe quand audit ou outliers sont là."""
    pour = "audit et outliers lisent les comptes avec, sans connexion"
    besoin = bool(s.lecteurs_presents())
    sans = "pas besoin : ni audit ni outliers à côté de setup"
    y = s.which("yt-dlp")
    if y:
        code, out = s.lance([y, "--version"])
        if code == 0:
            v = (out.strip().splitlines() or ["?"])[0]
            return Constat("ytdlp", "yt-dlp", "ok", f"{v} — {montre(s, y)} (audit, outliers)")
        det = f"{montre(s, y)} ne démarre pas (code {code})"
        if not besoin:
            return Constat("ytdlp", "yt-dlp", "option", f"{det} ({sans})")
        fix = {"Darwin": ["brew reinstall yt-dlp"], "Linux": ["pipx reinstall yt-dlp"]}.get(
            c.systeme, ["# désinstalle-le (winget uninstall yt-dlp.yt-dlp), puis :"] + installe_ytdlp(c))
        return Constat("ytdlp", "yt-dlp", "a_faire", f"{det} : {pour}", fix)
    h = ytdlp_hors_path(s, c)
    if h:
        fix = ["# ferme et rouvre le terminal et Claude Code : audit et outliers le cherchent dans le PATH"]
        if Path(h).parent == s.chemin("~/.local/bin"):            # pipx : ~/.local/bin pas encore dans le PATH
            fix.insert(0, "pipx ensurepath")
        return Constat("ytdlp", "yt-dlp", "attention" if besoin else "option",
                       f"installé ({montre(s, h)}) mais pas encore dans le PATH de ce terminal", fix)
    if not besoin:
        return Constat("ytdlp", "yt-dlp", "option", f"absent ({sans})")
    return Constat("ytdlp", "yt-dlp", "a_faire", f"absent : {pour} ; le montage s'en passe", installe_ytdlp(c))


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
                       f"{CONFIG} pas encore écrite : la skill `set-up-video-tools` pose ses questions, puis --ecris")
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
                   f"la skill `edit-my-video` n'est pas à côté de setup ({montre(s, MONTAGE)})",
                   ["# installe toutes les skills du dépôt : npx skills add vincentventalon/my-claude-skills -a claude-code"],
                   bloque=True)


def a_installer(k: Constat) -> bool:
    """Ce que --installe traite : ce qui bloque le montage, et yt-dlp pour audit et outliers (qui ne le bloque pas)."""
    return k.bloque or (k.cle == "ytdlp" and k.etat == "a_faire")


def verifie_homebrew(c: Contexte, constats: list) -> Constat | None:
    if c.systeme != "Darwin":
        return None
    if c.brew:
        return Constat("homebrew", "Homebrew", "ok", c.brew)
    brew = lambda garde: any(x.startswith("brew ") for k in constats if garde(k) for x in k.corrige)
    bloque, besoin = brew(lambda k: k.bloque), brew(a_installer)
    if not besoin:
        return Constat("homebrew", "Homebrew", "option", "absent (rien à installer avec)")
    return Constat("homebrew", "Homebrew", "manque" if bloque else "a_faire",
                   "absent : les commandes brew ci-dessous le demandent d'abord" if bloque
                   else "absent : yt-dlp (audit, outliers) s'installe avec",
                   [HOMEBREW + "   # à lancer toi-même : il demande ton mot de passe"], bloque=bloque)


@dataclass
class Diagnostic:
    contexte: Contexte
    constats: list

    @property
    def pret(self) -> bool:
        return not any(k.bloque for k in self.constats)

    @property
    def pret_comptes(self) -> bool:               # audit et outliers peuvent lire un compte
        return any(k.cle == "ytdlp" and k.etat == "ok" for k in self.constats)

    @property
    def whisper_a_telecharger(self) -> bool:      # Windows : --installe le télécharge
        return any(k.cle == "whisper" and k.bloque and any(x.split("#")[0].strip().endswith("--installe") for x in k.corrige)
                   for k in self.constats)

    def plan_brew(self) -> list:
        cmds = []
        for k in self.constats:
            if a_installer(k):
                cmds += [x for x in k.corrige if x.startswith("brew ")]
        return list(dict.fromkeys(cmds))


def diagnostic(s: Sonde) -> Diagnostic:
    c = contexte(s)
    k = [verifie_systeme(s, c), verifie_python(s, c), verifie_ffmpeg(s, c), verifie_whisper(s, c),
         verifie_modele(s, c), verifie_elevenlabs(s, c), verifie_node(s, c), verifie_ytdlp(s, c),
         verifie_sortie(s, c), verifie_config(s, c)]
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
    if c.systeme == "Windows" and d.whisper_a_telecharger:
        L.append(f"Sur Windows, `{c.py} {c.script} --installe` télécharge whisper.cpp (il le dit d'abord).")
    return "\n".join(L) + "\n"


def en_json(d: Diagnostic, s: Sonde, faits: list) -> str:
    c = d.contexte
    st = style_resolu(s)
    out = {"pret": d.pret, "pret_comptes": d.pret_comptes, "systeme": c.systeme, "config_fichier": montre(s, s.chemin(CONFIG)),
           "env_fichier": montre(s, s.chemin(ENV)), "config": c.cfg, "config_etat": c.cfg_etat,
           "choix": {"stt": c.stt, "moteur_effectif": c.moteur, "subtitles": c.sous_titres,
                     "remotion": c.remotion, "whisper_model": c.modele, "output_dir": c.sortie,
                     "police": st.get("font"), "couleur": st["captions"].get("highlight")},
           "style_fichier": montre(s, s.chemin(STYLE)),
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


# --------------------------------------------------------------------------- le style : police et couleur

def noms_police(chemin) -> list:
    """Les noms que porte un .ttf / .otf / .ttc (sa table name) : [{1: famille, 2: graisse, 4: nom complet,
    16, 17: famille et graisse typographiques}], une entrée par police du fichier. [] s'il ne se lit pas."""
    import struct
    try:
        with open(str(chemin), "rb") as f:
            tete = f.read(12)
            debuts = [0]
            if tete[:4] == b"ttcf":
                n = struct.unpack(">I", tete[8:12])[0]
                debuts = list(struct.unpack(f">{n}I", f.read(4 * n)))
            out = []
            for o in debuts:
                f.seek(o + 4)
                nt = struct.unpack(">H", f.read(2))[0]
                f.seek(o + 12)
                tables = f.read(16 * nt)
                for i in range(nt):
                    tag, _, off, _ = struct.unpack(">4sIII", tables[16 * i:16 * i + 16])
                    if tag != b"name":
                        continue
                    f.seek(off)
                    _, cnt, so = struct.unpack(">HHH", f.read(6))
                    recs = f.read(12 * cnt)
                    d = {}
                    for j in range(cnt):
                        pid, _, lid, nid, ln, oo = struct.unpack(">6H", recs[12 * j:12 * j + 12])
                        if nid not in (1, 2, 4, 16, 17) or pid not in (0, 1, 3):
                            continue
                        if nid in d and not (pid == 3 and lid == 0x409):   # l'anglais d'abord
                            continue
                        f.seek(off + so + oo)
                        brut = f.read(ln)
                        d[nid] = brut.decode("mac_roman" if pid == 1 else "utf-16-be", "replace").strip("\x00 ")
                    out.append(d)
            return out
    except (OSError, struct.error, ValueError):
        return []


def nom_de_fichier(chemin) -> str | None:
    """Le nom à écrire dans `font` pour un fichier de police : sa famille quand c'est la graisse
    normale (Impact), sinon son nom complet (Montserrat Bold), que libass et Remotion retrouvent."""
    for d in noms_police(chemin)[:1]:
        if d.get(1) and d.get(2, "Regular") in ("Regular", "Normal"):
            return d[1]
        return d.get(4) or d.get(1)
    return None


def cherche_police(s: Sonde, nom: str) -> str | None:
    """Le nom tel que la machine l'écrit, si une police installée le porte (famille ou nom complet)."""
    voulu = nom.casefold()
    for dossier in s.dossiers_polices():
        for racine, _, fichiers in os.walk(dossier):
            for f in fichiers:
                if not f.lower().endswith((".ttf", ".otf", ".ttc")):
                    continue
                for d in noms_police(os.path.join(racine, f)):
                    noms = [d.get(1), d.get(4), d.get(16)]
                    if d.get(16) and d.get(17):
                        noms.append(f"{d[16]} {d[17]}")
                    for n in noms:
                        if n and n.casefold() == voulu:
                            return n
    return None


def police(v: str) -> str:
    v = v.strip().strip('"').strip("'")
    if not v:
        raise argparse.ArgumentTypeError("Inter ExtraBold, le nom d'une police installée ou un fichier .ttf / .otf")
    return v


def couleur(v: str) -> str:
    """Un nom proposé (menthe, jaune, orange, rose, bleu ; en anglais aussi) ou un hex : #RRGGBB, #RGB."""
    n = v.strip().lower()
    n = COULEURS_EN.get(n, n)
    if n in COULEURS:
        return COULEURS[n]
    h = n.lstrip("#")
    if re.fullmatch(r"[0-9a-f]{3}", h):
        h = "".join(x * 2 for x in h)
    if not re.fullmatch(r"[0-9a-f]{6}", h):
        raise argparse.ArgumentTypeError(f"{', '.join(COULEURS)}, ou un hex (#FFD23F)")
    return "#" + h.upper()


def luminance(hexa: str) -> float:
    def canal(x):
        x = int(x, 16) / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    h = hexa.lstrip("#")
    return 0.2126 * canal(h[0:2]) + 0.7152 * canal(h[2:4]) + 0.0722 * canal(h[4:6])


def contraste(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def lisible_sur(hexa: str, fond: str, mini: float = 3.0) -> str:
    """La couleur, assombrie (même teinte) ou éclaircie juste assez pour se lire sur `fond` (3:1, du
    gros texte) : le mot en couleur du titre, posé sur son cadre blanc."""
    h = hexa.lstrip("#")
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    sombre = luminance(fond[:7]) > 0.4
    for pas in range(51):
        k = pas / 50
        c = [round(x * (1 - k)) for x in rgb] if sombre else [round(x + (255 - x) * k) for x in rgb]
        out = "#" + "".join(f"{x:02X}" for x in c)
        if contraste(out, fond[:7]) >= mini:
            return out
    return out


def style_livre() -> dict:
    try:
        return json.loads((MONTAGE / "style.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return json.loads(json.dumps(STYLE_LIVRE))


def lire_style(s: Sonde) -> tuple:
    texte = s.lit(STYLE)
    if texte is None:
        return {}, "absente"
    try:
        st = json.loads(texte)
    except ValueError:
        return {}, "illisible"
    return (st, "ok") if isinstance(st, dict) else ({}, "illisible")


def style_resolu(s: Sonde) -> dict:
    """Le style que le montage prendra : le livré, puis celui de l'utilisateur (comme finish.load_style)."""
    def fusion(base, sur):
        for k, v in sur.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                fusion(base[k], v)
            elif not isinstance(base.get(k), dict):      # une section remplacée par autre chose : ignorée
                base[k] = v
        return base
    st = fusion(json.loads(json.dumps(STYLE_LIVRE)), style_livre())
    return fusion(st, lire_style(s)[0])


def pose(perso: dict, livre: dict, chemin: tuple, valeur) -> None:
    """Met une clé du style de l'utilisateur ; None ou égale au style livré, elle part (le défaut suffit),
    et sa section avec si elle se vide."""
    if len(chemin) == 1:
        d, ref = perso, livre
    else:
        if not isinstance(perso.get(chemin[0]), dict):
            perso[chemin[0]] = {}
        d, ref = perso[chemin[0]], livre.get(chemin[0]) or {}
    cle = chemin[-1]
    if valeur is None or valeur == ref.get(cle):
        d.pop(cle, None)
    else:
        d[cle] = valeur
    if len(chemin) > 1 and not d:
        perso.pop(chemin[0])


def ecris_style(s: Sonde, a: argparse.Namespace) -> list:
    """La police et la couleur dans ~/.config/video-editing/style.json : seulement ce qui change du style
    livré, les autres clés de l'utilisateur gardées. Rend ce qui a été fait."""
    faits = []
    p = s.chemin(STYLE)
    perso, etat = lire_style(s)
    if etat == "illisible":
        bak = p.with_name(f"style.json.bak-{datetime.date.today().isoformat()}")
        shutil.copyfile(str(p), str(bak))
        faits.append(f"style.json illisible gardée en {montre(s, bak)}")
    avant = json.loads(json.dumps(perso))
    livre = style_livre()
    if a.police:
        v = a.police
        fichier = s.chemin(v) if v.lower().endswith((".ttf", ".otf")) else None
        if fichier is not None:
            nom = nom_de_fichier(fichier)
            if not fichier.is_file() or not nom:
                raise ValueError(f"{v} : fichier de police introuvable ou illisible (un .ttf ou un .otf)")
            pose(perso, livre, ("font_file",), tilde(s, str(fichier)))
            pose(perso, livre, ("font",), nom)
        else:
            nom = POLICES_LIVREES.get(v.casefold())
            if not nom:
                nom = cherche_police(s, v)
                if not nom:
                    nom = v
                    faits.append(f"police « {v} » pas trouvée parmi celles de cette machine : vérifie son nom "
                                 f"(sinon le montage en prend une autre), ou donne le fichier .ttf / .otf")
            pose(perso, livre, ("font_file",), None)       # un fichier d'avant passerait devant le nom
            pose(perso, livre, ("font",), nom)
    if a.couleur:
        c = a.couleur
        if c == COULEUR_DEFAUT:                            # la couleur de base : le style livré, tel quel
            for k in (("captions", "highlight"), ("title", "highlight"), ("split", "highlight"), ("end_card", "box")):
                pose(perso, livre, k, None)
            if perso.get("end_card", {}).get("color") == "#FFFFFF":   # le blanc qu'on avait posé nous-mêmes
                pose(perso, livre, ("end_card", "color"), None)
        else:
            pose(perso, livre, ("captions", "highlight"), c)
            pose(perso, livre, ("split", "highlight"), c)
            cadre = str(style_resolu(s)["title"].get("box") or "#FFFFFF")
            pose(perso, livre, ("title", "highlight"), lisible_sur(c, cadre))
            pose(perso, livre, ("end_card", "box"), c)         # le carton de fin est de sa couleur aussi
            texte = str((livre.get("end_card") or {}).get("color") or "#101114")   # le texte livré, pas le blanc d'un choix d'avant
            pose(perso, livre, ("end_card", "color"), "#FFFFFF" if contraste(c, texte) < 3.0 else None)
    if perso != avant or etat == "illisible":
        if perso:
            ecrit_atomique(p, json.dumps(perso, ensure_ascii=False, indent=2) + "\n")
            faits.append(f"{montre(s, p)} écrit : " + json.dumps(perso, ensure_ascii=False))
        elif p.exists():
            p.unlink()
            faits.append(f"{montre(s, p)} retiré : le style de base")
    return faits


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
    cle = (cle or "").strip().lstrip("\ufeff").strip('"').strip("'")
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


def telecharge_whisper_windows(s: Sonde) -> int:
    """whisper.cpp n'a pas de paquet winget : le zip officiel de la dernière build qui en a un (GitHub),
    vérifié (sha256 de GitHub), dézippé dans %LOCALAPPDATA%\\whisper.cpp. Pas de PATH à toucher : le
    montage le cherche là. Ses DLL restent à côté de whisper-cli.exe, dans Release."""
    arm = s.machine().upper() in ("ARM64", "AARCH64")
    nom = "whisper-bin-win-cpu-arm64.zip" if arm else "whisper-bin-x64.zip"
    dest = dossier_whisper_windows(s)
    entetes = {"Accept": "application/vnd.github+json", "User-Agent": "video-editing-setup"}
    try:
        with urllib.request.urlopen(urllib.request.Request(WHISPER_API, headers=entetes), timeout=60) as r:
            versions = json.load(r)
        rel, a = next(((v, x) for v in versions if not v.get("draft") for x in v.get("assets", [])
                       if x.get("name") == nom), (None, None))
        if not a:
            print(f"setup : aucune build de whisper.cpp n'a {nom} ({WHISPER_RELEASES})", file=sys.stderr)
            return 1
        print(f"téléchargement de {nom} ({rel['tag_name']}, {(a.get('size') or 0) / 1e6:.0f} Mo) vers {montre(s, dest)}",
              flush=True)
        with tempfile.TemporaryDirectory() as t:
            z = os.path.join(t, nom)
            urllib.request.urlretrieve(a["browser_download_url"], z)
            empreinte = str(a.get("digest") or "")
            if empreinte.startswith("sha256:"):
                with open(z, "rb") as f:
                    if hashlib.sha256(f.read()).hexdigest() != empreinte[7:]:
                        print("setup : le zip téléchargé ne correspond pas à son empreinte GitHub, rien n'est installé",
                              file=sys.stderr)
                        return 1
            with zipfile.ZipFile(z) as zf:
                noms = zf.namelist()
                if any(n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/") for n in noms):
                    print("setup : le zip contient des chemins hors de son dossier, rien n'est installé", file=sys.stderr)
                    return 1
                if dest.exists():
                    shutil.rmtree(str(dest))
                zf.extractall(str(dest))
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        print(f"setup : le téléchargement de whisper.cpp a échoué ({e}). Relance la même commande.", file=sys.stderr)
        return 1
    exe = next((p for p in (dest / "Release" / "whisper-cli.exe", dest / "whisper-cli.exe") if p.exists()), None)
    if not exe:
        print(f"setup : pas de whisper-cli.exe dans {nom} : à faire à la main ({WHISPER_RELEASES})", file=sys.stderr)
        return 1
    print(f"whisper-cli : {montre(s, exe)}")
    return 0


def installe_windows(s: Sonde, d: Diagnostic, a_blanc: bool) -> tuple:
    """Windows : setup télécharge whisper.cpp lui-même ; le reste (winget), c'est Claude qui le lance,
    avec l'accord de l'utilisateur. Rend (code, ce qui a été fait)."""
    autres = [x for k in d.constats if a_installer(k) and not (k.cle == "whisper" and d.whisper_a_telecharger)
              for x in k.corrige]
    if d.whisper_a_telecharger:
        print(f"Je vais télécharger whisper.cpp (whisper-bin-x64.zip, la dernière build de {WHISPER_RELEASES}) "
              f"dans {montre(s, dossier_whisper_windows(s))}, sans toucher au PATH.")
    if autres:
        print("À lancer à part (winget : ensuite, rouvre le terminal et Claude Code pour Python, Node et yt-dlp) :")
        for x in autres:
            print(f"  {x if x.startswith('#') else '$ ' + x}")
    if not d.whisper_a_telecharger:
        if not autres:
            print("Rien à installer.")
        return (2 if autres else 0), []
    if a_blanc:
        print("(à blanc : rien n'est lancé)")
        return 0, []
    if telecharge_whisper_windows(s):
        return 1, []
    return 0, ["whisper.cpp téléchargé dans " + montre(s, dossier_whisper_windows(s))]


def installe(s: Sonde, d: Diagnostic, a_blanc: bool) -> tuple:
    """macOS + Homebrew : lance les `brew install` qui manquent (yt-dlp compris) ; Windows : télécharge
    whisper.cpp. Rend (code, ce qui a été fait)."""
    c = d.contexte
    if c.systeme == "Windows":
        return installe_windows(s, d, a_blanc)
    if c.systeme != "Darwin":
        print("setup : --installe ne lance rien sous Linux. Les commandes de ta machine sont dans le diagnostic :")
        for k in d.constats:
            if a_installer(k):
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
        description="Installation des skills vidéo (montage, yt-dlp pour audit et outliers) : diagnostic "
                    "(par défaut), configuration, installations.")
    ap.add_argument("--diagnostic", action="store_true", help="le diagnostic (l'action par défaut)")
    ap.add_argument("--json", action="store_true", help="la sortie pour Claude")
    ap.add_argument("--ecris", action="store_true", help="écrit config.json avec les choix ci-dessous et crée le dossier de sortie")
    ap.add_argument("--moteur", type=moteur, help="transcription : whisper ou elevenlabs")
    ap.add_argument("--langue", type=langue, help="la langue parlée dans les vidéos : fr, en, es...")
    ap.add_argument("--sortie", help=f"le dossier des vidéos montées (défaut : {SORTIE_DEFAUT})")
    ap.add_argument("--sous-titres", dest="sous_titres", type=oui_non, help="sous-titres incrustés : oui ou non")
    ap.add_argument("--remotion", type=oui_non, help="finition Remotion (Node) : oui ou non")
    ap.add_argument("--police", type=police, metavar="POLICE",
                    help=f"sous-titres et titre : {POLICE_DEFAUT} (défaut), le nom d'une police installée, "
                         "ou le chemin d'un .ttf / .otf")
    ap.add_argument("--couleur", type=couleur, metavar="COULEUR",
                    help=f"le mot dit : {', '.join(COULEURS)} ({COULEUR_DEFAUT}, défaut), ou un hex #RRGGBB")
    ap.add_argument("--modele", nargs="?", const="", default=None, metavar="NOM",
                    help="seul : télécharge le modèle whisper maintenant ; avec --ecris : le modèle à utiliser "
                         "(large-v3-turbo, large-v3-turbo-q5_0, small)")
    ap.add_argument("--cle-elevenlabs-stdin", action="store_true",
                    help=f"lit la clé ElevenLabs sur l'entrée standard et l'écrit dans {ENV} (mode 600)")
    ap.add_argument("--installe", action="store_true",
                    help="macOS : lance les brew install qui manquent (yt-dlp compris) ; Windows : télécharge whisper.cpp")
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
    if (a.moteur or a.langue or a.sortie or a.sous_titres is not None or a.remotion is not None
            or a.police or a.couleur) and not a.ecris:
        print("setup : --moteur, --langue, --sortie, --sous-titres, --remotion, --police et --couleur vont avec --ecris",
              file=sys.stderr)
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
        if a.police or a.couleur:
            try:
                faits += ecris_style(sonde, a)
            except ValueError as e:
                print(f"setup : {e}. Le style n'a pas été écrit.", file=sys.stderr)
                return 2

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
