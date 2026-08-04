"""
data.py — THE ONLY FILE THAT TOUCHES YOUR REAL DATA.

Every other module (vault.py, tools.py, main.py) only ever sees a Vault
object built from a list of folder paths. This is the single place that
decides *which* folders those are, and it decides that from ULTRON_DEMO.

ULTRON_DEMO=1 (default)  -> data/demo/  (generated fixtures, safe to record)
ULTRON_DEMO=0            -> your real folders, listed in ULTRON_FOLDERS

You have to opt IN to your real life. If you don't set ULTRON_DEMO=0
explicitly, you get the demo.
"""

import os
from pathlib import Path

from vault import Vault

AGENT_DIR = Path(__file__).resolve().parent
ULTRON_ROOT = AGENT_DIR.parent
DEMO_DIR = ULTRON_ROOT / "data" / "demo"

_vault_singleton: Vault | None = None


def is_demo_mode() -> bool:
    return os.environ.get("ULTRON_DEMO", "1").strip() != "0"


def _real_folders() -> list[str]:
    raw = os.environ.get("ULTRON_FOLDERS", "")
    folders = [f.strip() for f in raw.split(",") if f.strip()]
    return folders


def configured_roots() -> list[str]:
    if is_demo_mode():
        return [str(DEMO_DIR)]
    folders = _real_folders()
    if not folders:
        # Never silently fall back to demo data here — an empty real vault
        # is loud and obvious; pretending to be real while showing demo
        # fixtures would violate "never invent".
        print("ULTRON_DEMO=0 but ULTRON_FOLDERS is empty — set it in .env, "
              "comma-separated, e.g. ULTRON_FOLDERS=/Users/me/Documents/Clients,/Users/me/Notes")
    return folders


def get_vault(force_reload: bool = False) -> Vault:
    global _vault_singleton
    if _vault_singleton is None or force_reload:
        _vault_singleton = Vault(configured_roots())
    return _vault_singleton


def mode_label() -> str:
    return "demo" if is_demo_mode() else "live"
