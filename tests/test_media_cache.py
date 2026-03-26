"""Tests for MusicCache and CachedItemWrapper in media/cache.py."""
import pytest
from unittest.mock import MagicMock

from botamusique.media.cache import ItemNotCachedError
from botamusique.media.radio import RadioItem

URL = "http://example.com/stream"
NAME = "Test Radio"


def _radio_dict(url=URL, title=NAME):
    return {
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


# ---------------------------------------------------------------------------
# MusicCache — get_item_by_id
# ---------------------------------------------------------------------------

class TestGetItemById:
    def test_returns_none_when_not_in_cache_or_db(self, mock_cache, mock_music_db):
        mock_music_db.query_music_by_id.return_value = None
        result = mock_cache.get_item_by_id("nonexistent-id")
        assert result is None

    def test_returns_item_when_in_memory_cache(self, mock_cache, make_radio_item):
        item = make_radio_item()
        mock_cache[item.id] = item
        result = mock_cache.get_item_by_id(item.id)
        assert result is item

    def test_fetches_from_db_when_not_in_cache(self, mock_cache, mock_music_db):
        d = _radio_dict()
        mock_music_db.query_music_by_id.return_value = d
        result = mock_cache.get_item_by_id(d["id"])
        assert result is not None
        assert result.type == "radio"
        assert d["id"] in mock_cache

    def test_does_not_call_db_when_cached(self, mock_cache, mock_music_db, make_radio_item):
        item = make_radio_item()
        mock_cache[item.id] = item
        mock_cache.get_item_by_id(item.id)
        mock_music_db.query_music_by_id.assert_not_called()


# ---------------------------------------------------------------------------
# MusicCache — get_item (factory)
# ---------------------------------------------------------------------------

class TestGetItem:
    def test_creates_radio_item(self, mock_cache, mock_music_db):
        mock_music_db.query_music_by_id.return_value = None
        item = mock_cache.get_item(type="radio", url=URL, name=NAME)
        assert item.type == "radio"
        assert item.url == URL

    def test_caches_newly_created_item(self, mock_cache, mock_music_db):
        mock_music_db.query_music_by_id.return_value = None
        item = mock_cache.get_item(type="radio", url=URL, name=NAME)
        assert item.id in mock_cache

    def test_returns_cached_item_on_second_call(self, mock_cache, mock_music_db):
        mock_music_db.query_music_by_id.return_value = None
        item1 = mock_cache.get_item(type="radio", url=URL, name=NAME)
        item2 = mock_cache.get_item(type="radio", url=URL, name=NAME)
        assert item1 is item2

    def test_fetches_from_db_if_not_in_cache(self, mock_cache, mock_music_db):
        d = _radio_dict()
        mock_music_db.query_music_by_id.return_value = d
        item = mock_cache.get_item(type="radio", url=URL, name=NAME)
        assert item.type == "radio"

    def test_unknown_type_raises(self, mock_cache, mock_music_db):
        mock_music_db.query_music_by_id.return_value = None
        with pytest.raises(ValueError):
            mock_cache.get_item(type="unknown_type", url=URL)


# ---------------------------------------------------------------------------
# MusicCache — free / free_all
# ---------------------------------------------------------------------------

class TestFree:
    def test_free_removes_item_from_cache(self, mock_cache, make_radio_item):
        item = make_radio_item()
        mock_cache[item.id] = item
        mock_cache.free(item.id)
        assert item.id not in mock_cache

    def test_free_nonexistent_is_noop(self, mock_cache):
        mock_cache.free("does-not-exist")  # should not raise

    def test_free_all_empties_cache(self, mock_cache, make_radio_item):
        for i in range(3):
            item = make_radio_item(url=f"http://example.com/stream{i}", title=f"R{i}")
            mock_cache[item.id] = item
        assert len(mock_cache) == 3
        mock_cache.free_all()
        assert len(mock_cache) == 0


# ---------------------------------------------------------------------------
# CachedItemWrapper — item()
# ---------------------------------------------------------------------------

class TestCachedItemWrapper:
    def test_item_returns_underlying_baseitem(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        wrapper = make_wrapper(item)
        assert wrapper.item() is item

    def test_item_raises_when_freed(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        wrapper = make_wrapper(item)
        mock_cache.free(item.id)
        with pytest.raises(ItemNotCachedError):
            wrapper.item()

    def test_wrapper_id_matches_item_id(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        wrapper = make_wrapper(item)
        assert wrapper.id == item.id

    def test_wrapper_type_matches_item_type(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        wrapper = make_wrapper(item)
        assert wrapper.type == item.type

    def test_uri_delegates_to_item(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        wrapper = make_wrapper(item)
        assert wrapper.uri() == item.uri()

    def test_is_ready_delegates_to_item(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        wrapper = make_wrapper(item)
        assert wrapper.is_ready() == item.is_ready()

    def test_format_debug_string_delegates(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        wrapper = make_wrapper(item)
        assert wrapper.format_debug_string() == item.format_debug_string()


# ---------------------------------------------------------------------------
# CachedItemWrapper — auto-save on version bump
# ---------------------------------------------------------------------------

class TestWrapperAutoSave:
    def test_add_tags_triggers_save_on_version_bump(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        wrapper = make_wrapper(item)
        mock_cache.save = MagicMock()
        wrapper.add_tags(["rock"])
        mock_cache.save.assert_called_once_with(item.id)

    def test_add_duplicate_tag_does_not_trigger_save(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        item.tags = ["rock"]
        item.version = 5
        wrapper = make_wrapper(item)
        wrapper.version = 5
        mock_cache.save = MagicMock()
        wrapper.add_tags(["rock"])
        mock_cache.save.assert_not_called()

    def test_remove_tags_triggers_save(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        item.tags = ["rock"]
        wrapper = make_wrapper(item)
        mock_cache.save = MagicMock()
        wrapper.remove_tags(["rock"])
        mock_cache.save.assert_called_once_with(item.id)

    def test_clear_tags_triggers_save_when_nonempty(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        item.tags = ["rock"]
        wrapper = make_wrapper(item)
        mock_cache.save = MagicMock()
        wrapper.clear_tags()
        mock_cache.save.assert_called_once_with(item.id)

    def test_clear_tags_no_save_when_already_empty(self, mock_cache, make_radio_item, make_wrapper):
        item = make_radio_item()
        item.tags = []
        item.version = 3
        wrapper = make_wrapper(item)
        wrapper.version = 3
        mock_cache.save = MagicMock()
        wrapper.clear_tags()
        mock_cache.save.assert_not_called()

    def test_validate_triggers_save_on_first_call(self, mock_cache, make_radio_item, make_wrapper):
        """RadioItem.validate() increments version → wrapper should auto-save."""
        item = make_radio_item()
        wrapper = make_wrapper(item)
        mock_cache.save = MagicMock()
        wrapper.validate()
        mock_cache.save.assert_called_once_with(item.id)
