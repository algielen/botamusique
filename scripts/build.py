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
import urllib.request
from pathlib import Path

import sass  # libsass-python

BOOTSWATCH_VERSION = "5.3.8"
THEMES = {
    "main": "flatly",
    "dark": "darkly",
}

# Single-file ESM downloads (self-contained bundles)
JS_VENDOR_FILES = {
    "jquery.module.min.js": "https://cdn.jsdelivr.net/npm/jquery@4.0.0/dist-module/jquery.module.min.js",
    "bootstrap.esm.min.js": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.esm.min.js",
}

# Packages whose entire dist/esm/ tree must be extracted (they use relative imports)
JS_VENDOR_TARBALLS = {
    "popper": ("https://registry.npmjs.org/@popperjs/core/-/core-2.11.8.tgz", "dist/esm/"),
}

root = Path(__file__).parent.parent
vendor_dir = root / "web" / "vendor" / "css"
static_css_dir = root / "static" / "css"
js_src_dir = root / "web" / "js"
js_dst_dir = root / "static" / "js"
js_vendor_dir = root / "static" / "js" / "vendor"

vendor_dir.mkdir(parents=True, exist_ok=True)
static_css_dir.mkdir(parents=True, exist_ok=True)
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
