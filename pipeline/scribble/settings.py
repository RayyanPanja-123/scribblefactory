"""library/settings.json: machine-level options. A missing file or key means its default; unknown keys are ignored.

render_workers: "auto" (recommended for this PC) or 1..MAX_WORKERS parallel Chromium processes per render.
force_software_gl: render with SwiftShader (software WebGL) instead of the GPU, for debugging.
socials: {youtube, instagram, facebook} handles shown on every part's closing "Follow for more" screen (finish);
  an empty one is left off the screen.
brand_tags: hashtags every caption carries (the Gemini caption writer adds them to the story's own).
caption_model: the free Gemini model captions try first (FREE_GEMINI).
gemini_key: the Gemini API key for captions; read only by gemini_key(), never by load(), so it never reaches the browser.
"""
import ctypes
import json
import os
import sys
from pathlib import Path

SOCIALS = ("youtube", "instagram", "facebook")
# free-tier Gemini text models (Pro has no free quota), probed 2026-11-19. The chosen one goes first; when it is busy
# (503), out of quota (429) or gone (404) the captions fall through the rest in this order.
FREE_GEMINI = ("gemini-flash-latest", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
               "gemini-3-flash-preview", "gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
DEFAULTS = {"render_workers": "auto", "force_software_gl": False, "socials": dict.fromkeys(SOCIALS, ""), "brand_tags": "",
            "caption_model": FREE_GEMINI[0]}
MAX_WORKERS = 16
MAX_AUTO = 8
GB_PER_WORKER = 1.5  # one Chromium with its page and frames in flight, plus headroom
WEAK_GPU = ("intel(r) uhd", "intel(r) hd", "intel(r) iris", "swiftshader", "llvmpipe", "microsoft basic")
WEAK_GPU_WORKERS = 2  # an integrated or software GPU is the bottleneck: more browsers only queue on it


def path(library: Path) -> Path:
    return Path(library) / "settings.json"


def load(library: Path) -> dict:
    try:
        s = json.loads(path(library).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    s = s if isinstance(s, dict) else {}
    out = {k: s.get(k, v) for k, v in DEFAULTS.items()}
    so = out["socials"] if isinstance(out["socials"], dict) else {}
    out["socials"] = {k: str(so.get(k) or "").strip() for k in SOCIALS}
    out["brand_tags"] = str(out["brand_tags"] or "").strip()
    if out["caption_model"] not in FREE_GEMINI:
        out["caption_model"] = FREE_GEMINI[0]
    return out


def ram_gb() -> float | None:
    try:
        if sys.platform == "win32":
            class Mem(ctypes.Structure):  # MEMORYSTATUSEX
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + \
                           [(n, ctypes.c_ulonglong) for n in ("total", "avail", "tpage", "apage", "tvirt", "avirt", "aext")]
            m = Mem(length=ctypes.sizeof(Mem))
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return None
            return m.total / 2**30
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except (AttributeError, OSError, ValueError):
        return None


def last_gpu(library: Path) -> str | None:
    """the GPU the newest rendered chunk used (render info written per chunk), or None before any render"""
    chunks = Path(library).glob("*/*/frames/chunks/c???.json")  # chunk records, not cNNN.info.json
    for f in sorted(chunks, key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            r = json.loads(f.read_text(encoding="utf-8")).get("renderer")
        except (OSError, ValueError, AttributeError):
            continue
        if not isinstance(r, dict):
            continue
        return "SwiftShader (software)" if r.get("renderer") == "swiftshader" else r.get("gpu_name")
    return None


def recommend(threads: int, ram: float | None, gpu: str | None) -> int:
    """half the CPU threads (about one per core), capped by RAM, by MAX_AUTO, and to 2 on an integrated GPU or before
    any render has shown which GPU this PC has (the first render reports it; Auto then raises on a strong one)"""
    n = min(MAX_AUTO, threads // 2)
    if ram:
        n = min(n, int(ram / GB_PER_WORKER))
    if not gpu or any(w in gpu.lower() for w in WEAK_GPU):
        n = min(n, WEAK_GPU_WORKERS)
    return max(1, n)


def machine(library: Path) -> dict:
    threads, ram, gpu = os.cpu_count() or 2, ram_gb(), last_gpu(library)
    return {"cpu_threads": threads, "ram_gb": round(ram, 1) if ram else None, "gpu": gpu,
            "recommended_workers": recommend(threads, ram, gpu)}


def render_workers(library: Path) -> int:
    w = load(library)["render_workers"]
    if type(w) is int and 1 <= w <= MAX_WORKERS:
        return w
    return recommend(os.cpu_count() or 2, ram_gb(), last_gpu(library))


def gemini_key(library: Path) -> str:
    try:
        s = json.loads(path(library).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(s.get("gemini_key") or "").strip() if isinstance(s, dict) else ""


def software_gl(library: Path) -> bool:
    return load(library)["force_software_gl"] is True
