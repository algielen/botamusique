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
uv run main.py --config configuration.ini

# Run tests
uv run pytest

# Run a specific test
uv run pytest pymumble_py3/tests/test_crypto.py

# Windows: install python-magic binary (needed for Windows dev)
uv pip install python-magic-bin
```

### Web Frontend (Node/webpack)

The web interface JS/CSS must be built separately from the Python code.

```bash
cd web
npm install
npm run build      # webpack bundle
npm run lint       # eslint on js/
```

### Template Translation

After building the web frontend, translate Jinja2 templates for all supported languages:

```bash
uv run scripts/translate_templates.py --lang-dir lang/ --template-dir web/templates/
```

### Configuration

Copy `configuration.example.ini` to `configuration.ini` and edit it. Do **not** modify `configuration.default.ini` — it is the fallback for any option not set in `configuration.ini` and serves as the schema reference. The bot validates config keys against `configuration.default.ini` on startup and will refuse to start if unknown keys are found.

## Architecture

### Startup flow (`main.py`)

`main.py` is the entry point. It:
1. Parses CLI args and environment variables (`BAM_*` env vars mirror all CLI flags).
2. Loads and validates `configuration.ini` against `configuration.default.ini`.
3. Initializes two SQLite databases: a **settings DB** (`settings-<username>.db`) and a **music library DB** (`music.db`).
4. Loads the translation strings for the selected language from `lang/<lang>.json`.
5. Creates a `MusicCache` and optionally builds the directory cache.
6. Creates the `MumbleBot` instance and registers all bot commands.
7. Optionally starts the Flask web interface in a daemon thread.
8. Enters `MumbleBot.loop()`, the main audio loop.

### Global state (`variables.py`)

Most runtime state is stored as module-level globals in `variables.py`:
- `var.bot` — the `MumbleBot` instance
- `var.playlist` — the active `BasePlaylist` subclass
- `var.cache` — the `MusicCache`
- `var.db` — `SettingsDatabase` (settings/bans/etc.)
- `var.music_db` — `MusicDatabase` (music library metadata)
- `var.config` — `ConfigParser` loaded from `configuration.ini`
- `var.music_folder` — resolved path to the music directory

> The codebase is actively being refactored to remove these globals (current branch: `no_globals`).

### Bot core (`mumbleBot.py`)

`MumbleBot` owns the pymumble connection and the ffmpeg subprocess. The main loop (`loop()`) reads PCM audio from ffmpeg stdout in 960-sample chunks (stereo: 1920) and feeds it into pymumble's sound output buffer. Volume is adjusted via exponential smoothing; ducking is implemented by listening to incoming sound RMS.

Audio playback lifecycle per item:
1. `validate()` — check the item is playable (file exists, URL reachable, etc.)
2. `prepare()` — download/transcode to a local file if needed
3. `launch_music()` — spawn an ffmpeg process, start reading PCM

### Commands (`command.py`)

All chat commands are registered via `bot.register_command(command_name, handler_fn)` in `command.register_all_commands()`. Command names come from `configuration.ini` `[commands]` section (resolved via `constants.commands()`), so they are user-configurable. Partial prefix matching is supported unless `no_partial_match=True`.

### Media items (`media/`)

Each media source is a subclass of `BaseItem` (`media/item.py`):
- `FileItem` (`media/file.py`) — local audio files
- `URLItem` (`media/url.py`) — yt-dlp downloads
- `PlaylistURLItem` (`media/url_from_playlist.py`) — items expanded from a URL playlist
- `RadioItem` (`media/radio.py`) — streaming radio URLs

Items go through states: `pending → validated → yes` (or `failed`). `MusicCache` (`media/cache.py`) is a dict keyed by item ID that also persists metadata to `MusicDatabase`. The cache is the single source of truth for item objects shared between the playlist, the bot loop, and the web interface.

### Playlist modes (`media/playlist.py`)

`BasePlaylist` is a Python `list` subclass with a `current_index`. Concrete implementations: `OneshotPlaylist`, `RepeatPlaylist`, `RandomPlaylist`, `AutoPlaylist`. Mode can be changed at runtime; `get_playlist()` converts between modes.

### Web interface (`interface.py`)

A Flask app served on a daemon thread. Shares state with the bot via `variables.py`. Supports reverse-proxy deployment via `X-Script-Name` / `X-Forwarded-For` headers (`ReverseProxied` middleware).

### Translation (`constants.py`)

`tr_cli(key, **kwargs)` and `tr_web(key, **kwargs)` look up strings in `lang/<lang>.json`. The JSON has two top-level sections: `"cli"` (bot chat messages) and `"web"` (web interface strings). English (`en_US`) is the fallback.

### pymumble (`pymumble_py3/`)

Vendored fork of the pymumble library. Contains the Mumble protocol implementation (protobuf, CELT/Opus audio, crypto). Tests live in `pymumble_py3/tests/`.

## Key Conventions

- **Config reading**: use `var.config.get(section, key)` / `var.config.getboolean(...)` / `var.db.get(...)`. The settings DB (`var.db`) overrides `var.config` for user-changeable runtime settings (volume, ducking thresholds, etc.).
- **Import order matters**: `variables.py` must not import from modules that import it transitively before they are initialized. See the comment at the top of `variables.py`.
- **Thread safety**: The main audio loop runs on the main thread. Downloads run in daemon threads. The playlist uses `playlist_lock` (RLock) for concurrent access. The web interface runs on its own daemon thread and accesses shared state without locking (Flask's dev server is single-threaded by default).