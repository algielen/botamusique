# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Botamusique is a Mumble (VoIP) music bot written in Python 3.14+. It connects to a Mumble server, plays audio (local files, YouTube/SoundCloud URLs via yt-dlp, radio streams), and offers a Flask-based web remote control interface. This is a personal fork of the upstream azlux/botamusique project.

## Commands

### Python Environment (uv)

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install/sync dependencies
uv sync

# Install dev dependencies
uv sync --dev

# Run the bot
uv run src/botamusique/main.py --config configuration.ini

# Run tests
uv run pytest

# Run a specific test
uv run pytest src/pymumble_py3/tests/test_crypto.py

```

### Web Frontend (Python)

Build assets and translate templates in one step. No Node.js required.

```bash
uv run --group build scripts/build.py
```

This downloads the two pre-built Bootswatch themes directly to `src/botamusique/static/css/{main,dark}.css` and translates Jinja2 templates for all supported languages. The custom stylesheet, JS modules, and images live directly in `src/botamusique/static/` and are tracked in git — there is no compilation or copy step for them.

To run the translation step on its own (e.g. after editing a `lang/*.json` file):

```bash
uv run scripts/translate_templates.py --lang-dir lang/ --template-dir src/botamusique/web/templates/
```

**Frontend source layout:**
- `src/botamusique/static/css/{main,dark}.css` — raw Bootswatch themes (flatly/darkly), downloaded by the build; swapped at runtime by the JS theme switcher (`#pagestyle` link)
- `src/botamusique/static/css/custom.css` — custom CSS (uses native CSS nesting), loaded as a constant second `<link>` after the theme so it layers on top; tracked in git, edit in place
- `src/botamusique/web/templates/*.template.html` — template sources → translated to `src/botamusique/web/*.{lang}.html` alongside them (tracked in git)
- `src/botamusique/static/js/` — JS source modules (tracked in git, edit in place)
- `src/botamusique/static/image/` — image assets (tracked in git, edit in place)
- `tmp/vendor/build_cache.json` — URL-based download cache (gitignored)

**Frontend stack:** The web UI is intentionally dependency-light. Bootstrap CSS (Bootswatch themes) is the only external dependency — everything else is vanilla browser APIs:
- `fetch()` + `URLSearchParams` for all server communication
- Native DOM APIs (`querySelector`, `classList`, `addEventListener`)
- Native `<dialog>` elements for modals
- CSS absolute positioning for the volume popover (no Popper.js)
- An SVG sprite (`src/botamusique/static/image/icons.svg`) for all icons (no Font Awesome)
- Bootstrap CSS-only for Toast visibility, dropdown open/close handled in JS

When adding icons, add a `<symbol>` to `src/botamusique/static/image/icons.svg` and reference it with `<svg class="svg-icon"><use href="static/image/icons.svg#icon-NAME"/></svg>`. When adding modals, use native `<dialog>` + `.showModal()` / `.close()` rather than Bootstrap modal markup.

### Running CI workflows locally (act)

The GitHub Actions workflows in `.github/workflows/` can be run locally with [`act`](https://github.com/nektos/act) (requires Docker). An `.actrc` in the repo root maps the GitHub-hosted runner labels (`ubuntu-latest`, `ubuntu-24.04-arm`) to a local container image.

```bash
# Run the PR-check workflow (test + Docker build), amd64 leg only
act pull_request -W .github/workflows/docker-pr-check.yml -j build --matrix platform:linux/amd64

# List jobs without running them
act pull_request -W .github/workflows/docker-pr-check.yml --list
```

Caveats:
- **arm64 leg**: building `linux/arm64` on an amd64 host needs QEMU/binfmt emulation. Drop the `--matrix` flag to run both legs; if arm fails, run `docker run --privileged --rm tonistiigi/binfmt --install arm64` first. `act` cannot reproduce the native `ubuntu-24.04-arm` runner.
- **`docker-image.yml`**: `act` can run its `test` and matrix `build` jobs, but the `merge` job's `docker buildx imagetools create` pushes to a real registry, so it can't be meaningfully validated locally without a throwaway registry.

### Configuration

Copy `configuration.example.ini` to `configuration.ini` and edit it. Do **not** modify `configuration.default.ini` — it is the fallback for any option not set in `configuration.ini` and serves as the schema reference. The bot validates config keys against `configuration.default.ini` on startup and will refuse to start if unknown keys are found.

## Architecture

### Startup flow (`src/botamusique/main.py`)

`src/botamusique/main.py` is the entry point. It:
1. Parses CLI args and environment variables (`BAM_*` env vars mirror all CLI flags).
2. Loads and validates `configuration.ini` against `configuration.default.ini`.
3. Initializes two SQLite databases: a **settings DB** (`settings-<username>.db`) and a **music library DB** (`music.db`).
4. Loads the translation strings for the selected language from `lang/<lang>.json`.
5. Creates a `MusicCache` and optionally builds the directory cache.
6. Creates the `MumbleBot` instance and registers all bot commands.
7. Optionally starts the Flask web interface in a daemon thread.
8. Enters `MumbleBot.loop()`, the main audio loop.

### Bot core (`src/mumbleBot.py`)

`MumbleBot` owns the pymumble connection and the ffmpeg subprocess. The main loop (`loop()`) reads PCM audio from ffmpeg stdout in 960-sample chunks (stereo: 1920) and feeds it into pymumble's sound output buffer. Volume is adjusted via exponential smoothing; ducking is implemented by listening to incoming sound RMS.

Audio playback lifecycle per item:
1. `validate()` — check the item is playable (file exists, URL reachable, etc.)
2. `prepare()` — download/transcode to a local file if needed
3. `launch_music()` — spawn an ffmpeg process, start reading PCM

### Commands (`src/command.py`)

All chat commands are registered via `bot.register_command(command_name, handler_fn)` in `command.register_all_commands()`. Command names come from `configuration.ini` `[commands]` section (resolved via `constants.commands()`), so they are user-configurable. Partial prefix matching is supported unless `no_partial_match=True`.

### Media items (`src/media/`)

Each media source is a subclass of `BaseItem` (`src/media/item.py`):
- `FileItem` (`src/media/file.py`) — local audio files
- `URLItem` (`src/media/url.py`) — yt-dlp downloads
- `PlaylistURLItem` (`src/media/url_from_playlist.py`) — items expanded from a URL playlist
- `RadioItem` (`src/media/radio.py`) — streaming radio URLs

Items go through states: `pending → validated → yes` (or `failed`). `MusicCache` (`src/media/cache.py`) is a dict keyed by item ID that also persists metadata to `MusicDatabase`. The cache is the single source of truth for item objects shared between the playlist, the bot loop, and the web interface.

### Playlist modes (`src/media/playlist.py`)

`BasePlaylist` is a Python `list` subclass with a `current_index`. Concrete implementations: `OneshotPlaylist`, `RepeatPlaylist`, `RandomPlaylist`, `AutoPlaylist`. Mode can be changed at runtime; `get_playlist()` converts between modes.

### Web interface (`src/interface.py`)

A Flask app served on a daemon thread. Holds a module-level `_bot` reference set via `set_bot(bot)`, called from `start_web_interface(addr, port, bot)` in `src/botamusique/main.py`. Supports reverse-proxy deployment via `X-Script-Name` / `X-Forwarded-For` headers (`ReverseProxied` middleware).

### Translation (`src/constants.py`)

`tr_cli(key, **kwargs)` and `tr_web(key, **kwargs)` look up strings in `lang/<lang>.json`. The JSON has two top-level sections: `"cli"` (bot chat messages) and `"web"` (web interface strings). English (`en_US`) is the fallback.

### pymumble (`src/pymumble_py3/`)

Vendored fork of the pymumble library. Contains the Mumble protocol implementation (protobuf, CELT/Opus audio, crypto). Tests live in `src/pymumble_py3/tests/`.

#### Protobuf regeneration

The Mumble protocol is defined in two `.proto` files vendored alongside the library:

- `src/pymumble_py3/Mumble.proto` — main protocol messages (source of truth: `mumble-voip/mumble` → `src/Mumble.proto`)
- `src/pymumble_py3/MumbleUDP.proto` — UDP protocol messages (source of truth: `mumble-voip/mumble` → `src/MumbleUDP.proto`)

`mumble_pb2.py` is generated from `Mumble.proto` and checked in. To regenerate it after updating either the `.proto` files or the `protobuf` dependency:

**Preferred — local `protoc` (use a version matching the `protobuf` runtime):**

```bash
protoc -I src/pymumble_py3 --python_out=src/pymumble_py3 src/pymumble_py3/Mumble.proto
```

**Fallback — `grpcio-tools` (no separate install needed):**

```bash
uv run --with grpcio-tools python -m grpc_tools.protoc \
    -I src/pymumble_py3 \
    --python_out=src/pymumble_py3 \
    src/pymumble_py3/Mumble.proto
```

`grpcio-tools` bundles its own `protoc` which may lag behind the `protobuf` runtime version — harmless, but the local binary produces a cleaner match. Verify with `uv run python -c "import src.pymumble_py3.mumble_pb2"`.

## Key Conventions

- **State ownership**: `MumbleBot` is the central owner of runtime state (`config`, `db`, `music_db`, `cache`, `playlist`, `music_folder`). All dependencies are passed explicitly via constructors — there are no module-level globals.
- **Config reading**: `bot.config.get(section, key)` / `bot.config.getboolean(...)`. The settings DB (`bot.db`) overrides config for user-changeable runtime settings (volume, ducking thresholds, etc.).
- **`MusicCache` as item factory**: Construct items via `cache.get_item(type=..., ...)` or `cache.get_cached_wrapper_from_scrap(...)` rather than directly calling item constructors, so the cache stays consistent.
- **Playlist / bot wiring**: `BasePlaylist` is created before `MumbleBot` with `send_channel_msg=None`, then wired after: `playlist.send_channel_msg = bot.send_channel_msg`.
- **Thread safety**: The main audio loop runs on the main thread. Downloads run in daemon threads. The playlist uses `playlist_lock` (RLock) for concurrent access. The web interface runs on its own daemon thread and accesses shared state without locking (Flask's dev server is single-threaded by default).