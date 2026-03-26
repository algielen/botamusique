"""Tests for FileItem in media/file.py."""
import hashlib
import pytest
from unittest.mock import patch

from botamusique.media.file import FileItem
from botamusique.media.file import ValidationFailedError
from botamusique.constants import load_lang

# Ensure lang strings are available (FileItem.validate() calls tr())
load_lang("en_US")

MUSIC_FOLDER = "/music/"


# ---------------------------------------------------------------------------
# generate_id
# ---------------------------------------------------------------------------

def test_generate_id_deterministic():
    path = "songs/test.mp3"
    assert FileItem.generate_id(path) == FileItem.generate_id(path)


def test_generate_id_is_md5():
    path = "songs/test.mp3"
    expected = hashlib.md5(path.encode()).hexdigest()
    assert FileItem.generate_id(path) == expected


def test_generate_id_different_paths_differ():
    assert FileItem.generate_id("a.mp3") != FileItem.generate_id("b.mp3")


# ---------------------------------------------------------------------------
# Constructor with non-existent file (no mocking needed)
# ---------------------------------------------------------------------------

def test_constructor_nonexistent_path_ready_pending():
    item = FileItem("/nonexistent/path/song.mp3", MUSIC_FOLDER)
    # File does not exist → ready stays "pending"
    assert item.ready == "pending"


def test_constructor_sets_id_from_path():
    path = "/nonexistent/song.mp3"
    item = FileItem(path, MUSIC_FOLDER)
    assert item.id == FileItem.generate_id(path)


def test_constructor_type_is_file():
    item = FileItem("/nonexistent/song.mp3", MUSIC_FOLDER)
    assert item.type == "file"


# ---------------------------------------------------------------------------
# uri()
# ---------------------------------------------------------------------------

def test_uri_absolute_path_returned_directly():
    item = FileItem("/absolute/song.mp3", MUSIC_FOLDER)
    assert item.uri() == "/absolute/song.mp3"


def test_uri_relative_path_prepends_music_folder():
    item = FileItem("relative/song.mp3", MUSIC_FOLDER)
    assert item.uri() == MUSIC_FOLDER + "relative/song.mp3"


def test_is_ready_always_true():
    """FileItem overrides is_ready() to always return True."""
    item = FileItem("/nonexistent/song.mp3", MUSIC_FOLDER)
    assert item.is_ready() is True


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------

def test_validate_raises_when_file_missing():
    item = FileItem("/nonexistent/song.mp3", MUSIC_FOLDER)
    with patch("botamusique.media.file.os.path.exists", return_value=False):
        with pytest.raises(ValidationFailedError):
            item.validate()


def test_validate_succeeds_when_file_exists():
    item = FileItem("/nonexistent/song.mp3", MUSIC_FOLDER)
    item.duration = 0
    with patch("botamusique.media.file.os.path.exists", return_value=True), \
         patch("botamusique.media.file.util.get_media_duration", return_value=120):
        result = item.validate()
    assert result is True
    assert item.ready == "yes"
    assert item.duration == 120


def test_validate_skips_duration_when_already_set():
    item = FileItem("/nonexistent/song.mp3", MUSIC_FOLDER)
    item.duration = 60
    with patch("botamusique.media.file.os.path.exists", return_value=True), \
         patch("botamusique.media.file.util.get_media_duration") as mock_dur:
        item.validate()
    mock_dur.assert_not_called()


def test_validate_increments_version_when_duration_computed():
    item = FileItem("/nonexistent/song.mp3", MUSIC_FOLDER)
    item.duration = 0
    v = item.version
    with patch("botamusique.media.file.os.path.exists", return_value=True), \
         patch("botamusique.media.file.util.get_media_duration", return_value=180):
        item.validate()
    assert item.version > v


# ---------------------------------------------------------------------------
# from_dict / to_dict round-trip
# ---------------------------------------------------------------------------

def _make_file_dict(path="/absolute/song.mp3"):
    return {
        "type": "file",
        "id": FileItem.generate_id(path),
        "ready": "yes",
        "tags": ["rock"],
        "title": "My Song",
        "path": path,
        "keywords": "My Song artist",
        "duration": 200,
        "artist": "My Artist",
        "thumbnail": None,
    }


def test_from_dict_restores_fields():
    d = _make_file_dict()
    with patch("botamusique.media.file.os.path.exists", return_value=True):
        item = FileItem.from_dict(d, MUSIC_FOLDER)
    assert item.id == d["id"]
    assert item.title == d["title"]
    assert item.artist == d["artist"]
    assert item.tags == d["tags"]
    assert item.duration == d["duration"]
    assert item.path == d["path"]


def test_to_dict_includes_artist_and_thumbnail():
    item = FileItem("/nonexistent/song.mp3", MUSIC_FOLDER)
    d = item.to_dict()
    assert "artist" in d
    assert "thumbnail" in d
    assert d["type"] == "file"
