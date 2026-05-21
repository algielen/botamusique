#!/usr/bin/env python3
"""Build the web frontend assets (CSS and templates) without Node.js/npm.

Steps:
  1. Download pre-built Bootswatch theme CSS if not already cached.
  2. Compile web/sass/main.scss with libsass.
  3. Concatenate theme CSS + custom CSS → static/css/{main,dark}.css
  4. Translate Jinja2 templates for all supported languages.
"""
import json
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

import sass  # libsass-python

root = Path(__file__).parent.parent

with open(root / "pyproject.toml", "rb") as f:
    _build_cfg = tomllib.load(f)["tool"]["botamusique"]["build"]

BOOTSWATCH_VERSION = _build_cfg["bootswatch_version"]

THEMES = {
    "main": "flatly",
    "dark": "darkly",
}

pkg_dir = root / "src" / "botamusique"
vendor_dir = root / "tmp" / "vendor" / "css"
cache_file = root / "tmp" / "vendor" / "build_cache.json"
static_css_dir = pkg_dir / "static" / "css"
templates_out_dir = pkg_dir / "web"

vendor_dir.mkdir(parents=True, exist_ok=True)
static_css_dir.mkdir(parents=True, exist_ok=True)


# --- Build cache (URL-based invalidation) ---
# src/botamusique/static/vendor/build_cache.json maps cache keys → last-used URL.
# When a version is bumped in pyproject.toml the URL changes and the
# corresponding file(s) are re-downloaded automatically.
_cache: dict[str, str] = {}
if cache_file.exists():
    _cache = json.loads(cache_file.read_text(encoding="utf-8"))


def _save_cache() -> None:
    cache_file.write_text(json.dumps(_cache, indent=2), encoding="utf-8")


def _is_cached(key: str, url: str) -> bool:
    return _cache.get(key) == url


def _mark_cached(key: str, url: str) -> None:
    _cache[key] = url
    _save_cache()


def download_file(url: str, dest: Path, cache_key: str) -> None:
    """Download url to dest, skipping if the URL (and thus the version) hasn't changed."""
    if _is_cached(cache_key, url) and dest.exists():
        return
    print(f"Downloading {url} ...")
    urllib.request.urlretrieve(url, dest)
    _mark_cached(cache_key, url)


# --- CSS ---
print("Compiling web/sass/main.scss ...")
custom_css = sass.compile(filename=str(root / "web" / "sass" / "main.scss"))

for output_name, theme_name in THEMES.items():
    vendor_file = vendor_dir / f"{theme_name}.min.css"
    theme_url = (
        f"https://cdn.jsdelivr.net/npm/bootswatch@{BOOTSWATCH_VERSION}"
        f"/dist/{theme_name}/bootstrap.min.css"
    )
    download_file(theme_url, vendor_file, f"css/{theme_name}")

    print(f"Building static/css/{output_name}.css ...")
    vendor_css = vendor_file.read_text(encoding="utf-8")
    out = static_css_dir / f"{output_name}.css"
    out.write_text(vendor_css + "\n" + custom_css, encoding="utf-8")

# --- Templates ---
subprocess.run(
    [sys.executable, root / "scripts" / "translate_templates.py",
     "--lang-dir", pkg_dir / "lang",
     "--template-dir", root / "web" / "templates",
     "--output-dir", templates_out_dir],
    check=True,
)