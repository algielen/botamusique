"""
Shared fixtures for botamusique unit tests.

Adds src/ to sys.path so that:
 1. Test files can import project modules directly: `from database import Condition`
 2. Intra-src imports work (e.g. `from constants import tr_cli` inside media/file.py)

Using direct (non-prefixed) imports throughout ensures all modules share the same
module-object identity, avoiding double-import issues that arise when src/ is a
package AND also on sys.path.
"""
import os
import sys

_tests_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.normpath(os.path.join(_tests_dir, "..", "src"))

if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import pytest
from configparser import ConfigParser
from unittest.mock import MagicMock

from botamusique.media.cache import MusicCache, CachedItemWrapper
from botamusique.media.radio import RadioItem
from botamusique.media.playlist import OneshotPlaylist


@pytest.fixture()
def mock_music_db():
    db = MagicMock()
    db.query_music_by_id.return_value = None
    db.insert_music.return_value = None
    db.manage_special_tags.return_value = None
    db.delete_music.return_value = None
    return db


@pytest.fixture()
def mock_settings_db():
    db = MagicMock()
    db.getint.return_value = -1
    db.items.return_value = []
    return db


@pytest.fixture()
def mock_config():
    config = ConfigParser()
    config.add_section("bot")
    config.set("bot", "tmp_folder", "/tmp/botamusique_test")
    config.set("bot", "ignored_folders", "")
    config.set("bot", "ignored_files", "")
    return config


@pytest.fixture()
def mock_cache(mock_music_db, mock_settings_db, mock_config, tmp_path):
    return MusicCache(mock_music_db, mock_settings_db, mock_config, str(tmp_path))


@pytest.fixture()
def make_radio_item():
    """Factory: create a RadioItem via from_dict (no HTTP requests)."""
    def _make(url="http://example.com/stream", title="Test Radio"):
        d = {
            "type": "radio",
            "id": RadioItem.generate_id(url),
            "ready": "pending",
            "tags": [],
            "title": title,
            "path": "",
            "keywords": "",
            "duration": 0,
            "url": url,
        }
        return RadioItem.from_dict(d)
    return _make


@pytest.fixture()
def make_playlist(mock_cache, mock_settings_db, mock_music_db, mock_config):
    """Factory: create a fresh OneshotPlaylist with no async validation."""
    def _make():
        pl = OneshotPlaylist(mock_cache, mock_settings_db, mock_music_db, mock_config)
        pl.async_validate = lambda: None
        return pl
    return _make


@pytest.fixture()
def make_wrapper(mock_cache):
    """Factory: insert an item into the cache and return a CachedItemWrapper."""
    def _make(item, user="testuser"):
        mock_cache[item.id] = item
        return CachedItemWrapper(mock_cache, item.id, item.type, user)
    return _make
