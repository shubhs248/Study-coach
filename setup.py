"""
One-time setup: detect your hardware and pick a model profile.

Run:
    python setup.py            # detect + interactively choose
    python setup.py --auto     # detect + accept the recommendation, no prompts
    python setup.py --profile mid   # force a specific profile

It writes your choice to a local `.env` file that the app reads automatically,
so you never have to remember model names. Re-run it any time to change.
"""

from __future__ import annotations

import argparse
import ctypes
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()
ENV_PATH = Path(__file__).resolve().parent / ".env"

# Hardware profiles: bigger profile = better answers, needs more horsepower.
PROFILES = {
    "light": {
        "label": "Light - CPU only / no GPU (8-16 GB RAM)",
        "chat": "llama3.2:3b",
        "embed": "nomic-embed-text",
        "note": "Fast on any laptop. ~2.5 GB download.",
    },
    "mid": {
        "label": "Mid - 16-32 GB RAM, or a modest GPU",
        "chat": "llama3.1:8b",
        "embed": "nomic-embed-text",
        "note": "Better answers, comfortable with some GPU or lots of RAM. ~5 GB.",
    },
    "strong": {
        "label": "Strong - good GPU / 32 GB+ RAM",
        "chat": "qwen2.5:14b",
        "embed": "nomic-embed-text",
        "note": "Best quality. Best with a dedicated GPU. ~9 GB.",
    },
}


def total_ram_gb() -> float | None:
    """Best-effort total RAM in GB, cross-platform, no external deps."""
    system = platform.system()
    try:
        if system == "Windows":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return round(stat.ullTotalPhys / (1024**3), 1)
        if system == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            return round(int(out.strip()) / (1024**3), 1)
        if system == "Linux":
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024**2), 1)
    except Exception:
        return None
    return None


def detect_gpu() -> tuple[bool, str]:
    """Return (has_gpu, description). Covers NVIDIA, Apple Silicon, AMD ROCm."""
    # NVIDIA
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if out:
                return True, f"NVIDIA GPU: {out.splitlines()[0]}"
        except Exception:
            pass

    # Apple Silicon (Metal acceleration is used by Ollama automatically)
    if platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"}:
        return True, "Apple Silicon GPU (Metal)"

    # AMD ROCm
    if shutil.which("rocminfo"):
        return True, "AMD GPU (ROCm)"

    return False, "No dedicated GPU detected (CPU only)"


def recommend(has_gpu: bool, ram_gb: float | None) -> str:
    """Pick a sensible default profile from detected hardware."""
    ram = ram_gb or 0
    if has_gpu and ram >= 32:
        return "strong"
    if has_gpu or ram >= 16:
        return "mid"
    return "light"


def write_env(profile_key: str) -> None:
    p = PROFILES[profile_key]
    content = (
        "# Written by setup.py - your DevOps Study Coach hardware profile.\n"
        "# Edit or delete this file, or re-run `python setup.py`, to change.\n"
        f"COACH_PROFILE={profile_key}\n"
        f"COACH_CHAT_MODEL={p['chat']}\n"
        f"COACH_EMBED_MODEL={p['embed']}\n"
    )
    ENV_PATH.write_text(content, encoding="utf-8")


def show_detection(has_gpu: bool, gpu_desc: str, ram_gb: float | None, rec: str) -> None:
    table = Table(show_header=False, box=None)
    table.add_row("GPU", gpu_desc)
    table.add_row("RAM", f"{ram_gb} GB" if ram_gb else "unknown")
    table.add_row("OS", f"{platform.system()} {platform.machine()}")
    table.add_row("Recommended", f"[bold green]{rec}[/] - {PROFILES[rec]['label']}")
    console.print(Panel(table, title="Detected hardware", border_style="cyan"))


def choose_interactively(rec: str) -> str:
    table = Table(title="Available profiles")
    table.add_column("Key", style="bold")
    table.add_column("Profile")
    table.add_column("Chat model", style="cyan")
    table.add_column("Notes", style="dim")
    for key, p in PROFILES.items():
        marker = " (recommended)" if key == rec else ""
        table.add_row(key + marker, p["label"], p["chat"], p["note"])
    console.print(table)

    choice = Prompt.ask(
        "Pick a profile",
        choices=list(PROFILES.keys()),
        default=rec,
    )
    return choice


def main() -> None:
    parser = argparse.ArgumentParser(description="Pick a hardware profile for the coach.")
    parser.add_argument("--auto", action="store_true", help="accept the recommendation")
    parser.add_argument("--profile", choices=list(PROFILES.keys()), help="force a profile")
    args = parser.parse_args()

    has_gpu, gpu_desc = detect_gpu()
    ram_gb = total_ram_gb()
    rec = recommend(has_gpu, ram_gb)

    show_detection(has_gpu, gpu_desc, ram_gb, rec)

    if args.profile:
        chosen = args.profile
    elif args.auto:
        chosen = rec
    else:
        chosen = choose_interactively(rec)

    write_env(chosen)
    p = PROFILES[chosen]

    console.print(
        Panel.fit(
            f"[bold green]Saved profile: {chosen}[/]\n"
            f"chat model:  [cyan]{p['chat']}[/]\n"
            f"embed model: [cyan]{p['embed']}[/]\n"
            f"written to:  {ENV_PATH}\n\n"
            "Next steps:\n"
            f"  1. ollama pull {p['chat']}\n"
            f"  2. ollama pull {p['embed']}\n"
            "  3. python ingest.py\n"
            "  4. python coach.py",
            border_style="green",
        )
    )

    if has_gpu is False and chosen != "light":
        console.print(
            "[yellow]Heads up:[/] no GPU was detected but you chose a heavier "
            "profile. Answers may be slow. You can re-run `python setup.py` anytime."
        )


if __name__ == "__main__":
    main()
