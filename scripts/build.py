#!/usr/bin/env python3
"""Build the web frontend assets (CSS and templates) without Node.js/npm.

Steps:
  1. Download each pre-built Bootswatch theme straight to static/css/{main,dark}.css.
  2. Translate Jinja2 templates for all supported languages.

The custom stylesheet (static/css/custom.css) and the JS modules are edited in
place under src/botamusique/static/ and tracked in git — they need no build step.
"""
import argparse
import json
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--no-cache", action="store_true",
    help="Ignore the download cache and re-download all theme CSS "
         "(e.g. after the Bootswatch CDN content changes for a fixed version).")
args = parser.parse_args()

root = Path(__file__).parent.parent

with open(root / "pyproject.toml", "rb") as f:
    _build_cfg = tomllib.load(f)["tool"]["botamusique"]["build"]

BOOTSWATCH_VERSION = _build_cfg["bootswatch_version"]

# Bootswatch theme → static filename swapped by the JS theme switcher.
THEMES = {
    "main": "flatly",
    "dark": "darkly",
}

pkg_dir = root / "src" / "botamusique"
cache_file = root / "tmp" / "vendor" / "build_cache.json"
static_css_dir = pkg_dir / "static" / "css"
templates_out_dir = pkg_dir / "web"

cache_file.parent.mkdir(parents=True, exist_ok=True)
static_css_dir.mkdir(parents=True, exist_ok=True)


# --- Build cache (URL-based invalidation) ---
# tmp/vendor/build_cache.json maps cache keys → last-used URL. When the
# Bootswatch version is bumped in pyproject.toml the URL changes and the
# corresponding theme is re-downloaded automatically.
_cache: dict[str, str] = {}
if cache_file.exists() and not args.no_cache:
    _cache = json.loads(cache_file.read_text(encoding="utf-8"))


def download_file(url: str, dest: Path, cache_key: str) -> None:
    """Download url to dest, skipping if the URL (and thus the version) hasn't changed."""
    if _cache.get(cache_key) == url and dest.exists():
        return
    print(f"Downloading {url} -> {dest.name} ...")
    urllib.request.urlretrieve(url, dest)
    _cache[cache_key] = url
    cache_file.write_text(json.dumps(_cache, indent=2), encoding="utf-8")


# --- CSS: each Bootswatch theme is served as-is; custom.css layers on top ---
for output_name, theme_name in THEMES.items():
    theme_url = (
        f"https://cdn.jsdelivr.net/npm/bootswatch@{BOOTSWATCH_VERSION}"
        f"/dist/{theme_name}/bootstrap.min.css"
    )
    download_file(theme_url, static_css_dir / f"{output_name}.css", f"css/{theme_name}")

# --- Templates ---
subprocess.run(
    [sys.executable, root / "scripts" / "translate_templates.py",
     "--lang-dir", pkg_dir / "lang",
     "--template-dir", pkg_dir / "web" / "templates",
     "--output-dir", templates_out_dir],
    check=True,
)
