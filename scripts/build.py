#!/usr/bin/env python3
"""Build the web frontend assets (CSS and JS) without Node.js/npm.

Steps:
  1. Download pre-built Bootswatch theme CSS if not already cached.
  2. Compile web/sass/main.scss with libsass.
  3. Concatenate theme CSS + custom CSS → static/css/{main,dark}.css
  4. Download JS vendor libraries into static/js/vendor/.
  5. Copy web/js/**/*.mjs → static/js/**/*.mjs
  6. Translate Jinja2 templates for all supported languages.
"""
import io
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
from pathlib import Path

import sass  # libsass-python

root = Path(__file__).parent.parent

with open(root / "pyproject.toml", "rb") as f:
    _build_cfg = tomllib.load(f)["tool"]["botamusique"]["build"]

BOOTSWATCH_VERSION  = _build_cfg["bootswatch_version"]
JQUERY_VERSION      = _build_cfg["jquery_version"]
BOOTSTRAP_VERSION   = _build_cfg["bootstrap_version"]
POPPERJS_VERSION    = _build_cfg["popperjs_version"]
FONTAWESOME_VERSION = _build_cfg["fontawesome_version"]

THEMES = {
    "main": "flatly",
    "dark": "darkly",
}

# Single-file ESM downloads (self-contained bundles)
JS_VENDOR_FILES = {
    "jquery.module.min.js": f"https://cdn.jsdelivr.net/npm/jquery@{JQUERY_VERSION}/dist-module/jquery.module.min.js",
    "bootstrap.esm.min.js": f"https://cdn.jsdelivr.net/npm/bootstrap@{BOOTSTRAP_VERSION}/dist/js/bootstrap.esm.min.js",
}

# Packages whose entire dist/esm/ tree must be extracted (they use relative imports)
JS_VENDOR_TARBALLS = {
    "popper": (f"https://registry.npmjs.org/@popperjs/core/-/core-{POPPERJS_VERSION}.tgz", "dist/esm/"),
}

vendor_dir = root / "web" / "vendor" / "css"
static_css_dir = root / "static" / "css"
static_webfonts_dir = root / "static" / "webfonts"
js_src_dir = root / "web" / "js"
js_dst_dir = root / "static" / "js"
js_vendor_dir = root / "static" / "js" / "vendor"

vendor_dir.mkdir(parents=True, exist_ok=True)
static_css_dir.mkdir(parents=True, exist_ok=True)
static_webfonts_dir.mkdir(parents=True, exist_ok=True)
js_dst_dir.mkdir(parents=True, exist_ok=True)
js_vendor_dir.mkdir(parents=True, exist_ok=True)


def download_if_missing(url: str, dest: Path) -> None:
    if dest.exists():
        return
    print(f"Downloading {url} ...")
    urllib.request.urlretrieve(url, dest)


def extract_tarball_subdir_if_missing(url: str, subdir: str, dest: Path) -> None:
    """Download an npm tarball and extract a subdirectory into dest, if not done yet."""
    sentinel = dest / ".extracted"
    if sentinel.exists():
        return
    print(f"Downloading and extracting {url} ({subdir}) ...")
    with urllib.request.urlopen(url) as response:
        data = response.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            # Tarball entries are under package/ prefix, e.g. package/dist/esm/foo.js
            needle = f"package/{subdir}"
            if member.name.startswith(needle) and member.isfile():
                rel = member.name[len(needle):]
                dest_file = dest / rel
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_bytes(tar.extractfile(member).read())
    sentinel.touch()


# --- CSS ---
print("Compiling web/sass/main.scss ...")
custom_css = sass.compile(filename=str(root / "web" / "sass" / "main.scss"))

for output_name, theme_name in THEMES.items():
    vendor_file = vendor_dir / f"{theme_name}.min.css"
    theme_url = (
        f"https://cdn.jsdelivr.net/npm/bootswatch@{BOOTSWATCH_VERSION}"
        f"/dist/{theme_name}/bootstrap.min.css"
    )
    download_if_missing(theme_url, vendor_file)

    print(f"Building static/css/{output_name}.css ...")
    vendor_css = vendor_file.read_text(encoding="utf-8")
    out = static_css_dir / f"{output_name}.css"
    out.write_text(vendor_css + "\n" + custom_css, encoding="utf-8")

# --- JS vendor ---
print("Downloading JS vendor libraries ...")
for filename, url in JS_VENDOR_FILES.items():
    download_if_missing(url, js_vendor_dir / filename)

for name, (url, subdir) in JS_VENDOR_TARBALLS.items():
    extract_tarball_subdir_if_missing(url, subdir, js_vendor_dir)

# --- Font Awesome ---
fa_css_dest = static_css_dir / "font-awesome.min.css"
if not fa_css_dest.exists():
    fa_url = (
        f"https://registry.npmjs.org/@fortawesome/fontawesome-free"
        f"/-/fontawesome-free-{FONTAWESOME_VERSION}.tgz"
    )
    print(f"Downloading and extracting Font Awesome {FONTAWESOME_VERSION} ...")
    with urllib.request.urlopen(fa_url) as response:
        data = response.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            if member.name == "package/css/all.min.css":
                fa_css_dest.write_bytes(tar.extractfile(member).read())
            elif member.name.startswith("package/webfonts/"):
                filename = member.name[len("package/webfonts/"):]
                (static_webfonts_dir / filename).write_bytes(tar.extractfile(member).read())

# --- JS ---
print("Copying JS modules to static/js/ ...")
for src_file in js_src_dir.rglob("*.mjs"):
    rel = src_file.relative_to(js_src_dir)
    dst_file = js_dst_dir / rel
    dst_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_file, dst_file)
    print(f"  {rel}")

# --- Templates ---
subprocess.run(
    [sys.executable, root / "scripts" / "translate_templates.py",
     "--lang-dir", root / "lang",
     "--template-dir", root / "web" / "templates"],
    check=True,
)
