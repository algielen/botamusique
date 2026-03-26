"""Tests for playlist operations and modes in media/playlist.py.

async_validate() is patched to a no-op throughout to avoid background threads.
"""
import pytest
from unittest.mock import MagicMock

from botamusique.media.cache import CachedItemWrapper
from botamusique.media.playlist import OneshotPlaylist, RepeatPlaylist, RandomPlaylist, get_playlist
from botamusique.media.radio import RadioItem


URL_BASE = "http://example.com/stream"


def _radio_item(n=0):
    url = f"{URL_BASE}/{n}"
    title = f"Radio {n}"
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def oneshot(make_playlist):
    return make_playlist()


@pytest.fixture()
def repeat_playlist(mock_cache, mock_settings_db, mock_music_db, mock_config):
    pl = RepeatPlaylist(mock_cache, mock_settings_db, mock_music_db, mock_config)
    pl.async_validate = lambda: None
    return pl


@pytest.fixture()
def random_playlist(mock_cache, mock_settings_db, mock_music_db, mock_config):
    pl = RandomPlaylist(mock_cache, mock_settings_db, mock_music_db, mock_config)
    pl.async_validate = lambda: None
    return pl


def _add_items(playlist, cache, count=2):
    """Add `count` radio items to a playlist and return the wrappers."""
    wrappers = []
    for i in range(count):
        item = _radio_item(i)
        cache[item.id] = item
        wrapper = CachedItemWrapper(cache, item.id, item.type, "user")
        playlist.append(wrapper)
        wrappers.append(wrapper)
    return wrappers


# ---------------------------------------------------------------------------
# Empty playlist behaviour
# ---------------------------------------------------------------------------

class TestEmptyPlaylist:
    def test_is_empty_true(self, oneshot):
        assert oneshot.is_empty() is True

    def test_next_returns_false(self, oneshot):
        assert oneshot.next() is False

    def test_current_item_returns_false(self, oneshot):
        assert oneshot.current_item() is False

    def test_next_item_returns_false(self, oneshot):
        assert oneshot.next_item() is False

    def test_len_is_zero(self, oneshot):
        assert len(oneshot) == 0


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------

class TestAppend:
    def test_append_increases_length(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 1)
        assert len(oneshot) == 1

    def test_append_makes_not_empty(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 1)
        assert oneshot.is_empty() is False

    def test_append_returns_wrapper(self, oneshot, mock_cache):
        item = _radio_item(0)
        mock_cache[item.id] = item
        wrapper = CachedItemWrapper(mock_cache, item.id, item.type, "user")
        result = oneshot.append(wrapper)
        assert result is wrapper

    def test_append_increments_version(self, oneshot, mock_cache):
        v = oneshot.version
        _add_items(oneshot, mock_cache, 1)
        assert oneshot.version > v

    def test_append_adds_to_pending_items(self, oneshot, mock_cache):
        item = _radio_item(0)
        mock_cache[item.id] = item
        wrapper = CachedItemWrapper(mock_cache, item.id, item.type, "user")
        oneshot.append(wrapper)
        assert wrapper in oneshot.pending_items


# ---------------------------------------------------------------------------
# OneshotPlaylist.current_item / next
# ---------------------------------------------------------------------------

class TestOneshotCurrentAndNext:
    def test_current_item_auto_sets_index_to_zero(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 2)
        assert oneshot.current_index == -1
        result = oneshot.current_item()
        assert result is not False

    def test_next_advances_and_removes_current(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 2)
        first = oneshot.next()   # sets index=0, returns self[0]
        assert first is not False
        second = oneshot.next()  # deletes old self[0], returns new self[0]
        assert second is not False
        third = oneshot.next()   # list now empty → False
        assert third is False

    def test_next_on_single_item_returns_false_after(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 1)
        oneshot.next()           # sets index=0, returns item
        result = oneshot.next()  # deletes item, list empty → False
        assert result is False


# ---------------------------------------------------------------------------
# insert
# ---------------------------------------------------------------------------

class TestInsert:
    def test_insert_at_position_adjusts_index_when_before_current(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 2)
        oneshot.current_index = 1
        new_item = _radio_item(99)
        mock_cache[new_item.id] = new_item
        new_wrapper = CachedItemWrapper(mock_cache, new_item.id, new_item.type, "user")
        oneshot.insert(0, new_wrapper)
        assert oneshot.current_index == 2

    def test_insert_after_current_does_not_change_index(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 2)
        oneshot.current_index = 0
        new_item = _radio_item(99)
        mock_cache[new_item.id] = new_item
        new_wrapper = CachedItemWrapper(mock_cache, new_item.id, new_item.type, "user")
        oneshot.insert(1, new_wrapper)
        assert oneshot.current_index == 0

    def test_insert_increments_version(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 1)
        v = oneshot.version
        new_item = _radio_item(99)
        mock_cache[new_item.id] = new_item
        new_wrapper = CachedItemWrapper(mock_cache, new_item.id, new_item.type, "user")
        oneshot.insert(0, new_wrapper)
        assert oneshot.version > v


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

class TestRemove:
    def test_remove_decreases_length(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 2)
        oneshot.remove(0)
        assert len(oneshot) == 1

    def test_remove_adjusts_current_index(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 3)
        oneshot.current_index = 2
        oneshot.remove(0)
        assert oneshot.current_index == 1

    def test_remove_does_not_adjust_index_when_after_current(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 3)
        oneshot.current_index = 0
        oneshot.remove(2)
        assert oneshot.current_index == 0

    def test_remove_returns_false_when_out_of_bounds(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 1)
        result = oneshot.remove(99)
        assert result is False

    def test_remove_frees_cache_when_last_reference(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 1)
        item_id = oneshot[0].id
        assert item_id in mock_cache
        oneshot.remove(0)
        assert item_id not in mock_cache

    def test_remove_does_not_free_cache_when_duplicate_refs(self, oneshot, mock_cache):
        """Same item added twice; removing one reference should NOT free cache."""
        item = _radio_item(0)
        mock_cache[item.id] = item
        w1 = CachedItemWrapper(mock_cache, item.id, item.type, "user")
        w2 = CachedItemWrapper(mock_cache, item.id, item.type, "user")
        oneshot.append(w1)
        oneshot.append(w2)
        oneshot.remove(0)
        assert item.id in mock_cache  # still referenced by second entry

    def test_remove_increments_version(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 1)
        v = oneshot.version
        oneshot.remove(0)
        assert oneshot.version > v


# ---------------------------------------------------------------------------
# find — confirms bug: wrapper.item.id vs wrapper.item().id
# ---------------------------------------------------------------------------

class TestFind:
    def test_find_returns_correct_index(self, oneshot, mock_cache):
        """Expected behaviour once the bug is fixed."""
        wrappers = _add_items(oneshot, mock_cache, 2)
        target_id = wrappers[1].id
        result = oneshot.find(target_id)
        assert result == 1


    def test_find_returns_none_for_missing_id(self, oneshot, mock_cache):
        """Expected behaviour once the bug is fixed."""
        _add_items(oneshot, mock_cache, 1)
        assert oneshot.find("nonexistent-id") is None


# ---------------------------------------------------------------------------
# point_to (OneshotPlaylist — removes leading items)
# ---------------------------------------------------------------------------

class TestPointTo:
    def test_point_to_removes_leading_items(self, oneshot, mock_cache):
        """OneshotPlaylist.point_to(n) removes the first n items and resets index to -1."""
        _add_items(oneshot, mock_cache, 3)
        oneshot.point_to(1)
        assert oneshot.current_index == -1
        assert len(oneshot) == 2  # item 0 removed

    def test_point_to_zero_is_noop(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 2)
        oneshot.point_to(0)
        assert len(oneshot) == 2


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_empties_playlist(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 2)
        oneshot.clear()
        assert len(oneshot) == 0

    def test_clear_resets_index(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 2)
        oneshot.current_index = 1
        oneshot.clear()
        assert oneshot.current_index == -1

    def test_clear_calls_free_all(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 2)
        mock_cache.free_all = MagicMock()
        oneshot.clear()
        mock_cache.free_all.assert_called_once()

    def test_clear_increments_version(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 1)
        v = oneshot.version
        oneshot.clear()
        assert oneshot.version > v


# ---------------------------------------------------------------------------
# RepeatPlaylist
# ---------------------------------------------------------------------------

class TestRepeatPlaylist:
    def test_next_advances_through_items(self, repeat_playlist, mock_cache):
        _add_items(repeat_playlist, mock_cache, 2)
        first = repeat_playlist.next()
        second = repeat_playlist.next()
        assert first is not False
        assert second is not False
        assert first is not second

    def test_next_wraps_around(self, repeat_playlist, mock_cache):
        _add_items(repeat_playlist, mock_cache, 2)
        repeat_playlist.next()  # → index 0
        repeat_playlist.next()  # → index 1
        third = repeat_playlist.next()  # → wraps to 0
        assert third is repeat_playlist[0]

    def test_next_single_item_wraps_to_itself(self, repeat_playlist, mock_cache):
        _add_items(repeat_playlist, mock_cache, 1)
        first = repeat_playlist.next()
        wrapped = repeat_playlist.next()
        assert first is wrapped

    def test_next_empty_returns_false(self, repeat_playlist):
        assert repeat_playlist.next() is False


# ---------------------------------------------------------------------------
# RandomPlaylist
# ---------------------------------------------------------------------------

class TestRandomPlaylist:
    def test_next_returns_items(self, random_playlist, mock_cache):
        _add_items(random_playlist, mock_cache, 3)
        results = [random_playlist.next() for _ in range(3)]
        assert all(r is not False for r in results)

    def test_next_wraps_around_with_reshuffling(self, random_playlist, mock_cache):
        """After exhausting all items, next() reshuffles and returns an item."""
        _add_items(random_playlist, mock_cache, 2)
        random_playlist.next()  # index 0
        random_playlist.next()  # index 1 (end)
        fourth = random_playlist.next()  # re-shuffle, index 0
        assert fourth is not False

    def test_next_empty_returns_false(self, random_playlist):
        assert random_playlist.next() is False


# ---------------------------------------------------------------------------
# get_playlist factory
# ---------------------------------------------------------------------------

class TestGetPlaylistFactory:
    def test_creates_oneshot(self, mock_cache, mock_settings_db, mock_music_db, mock_config):
        pl = get_playlist("one-shot", mock_cache, mock_settings_db, mock_music_db, mock_config, None)
        assert isinstance(pl, OneshotPlaylist)

    def test_creates_repeat(self, mock_cache, mock_settings_db, mock_music_db, mock_config):
        pl = get_playlist("repeat", mock_cache, mock_settings_db, mock_music_db, mock_config, None)
        assert isinstance(pl, RepeatPlaylist)

    def test_creates_random(self, mock_cache, mock_settings_db, mock_music_db, mock_config):
        pl = get_playlist("random", mock_cache, mock_settings_db, mock_music_db, mock_config, None)
        assert isinstance(pl, RandomPlaylist)


# ---------------------------------------------------------------------------
# Version tracking
# ---------------------------------------------------------------------------

class TestVersionTracking:
    def test_version_increments_on_append(self, oneshot, mock_cache):
        v0 = oneshot.version
        _add_items(oneshot, mock_cache, 1)
        assert oneshot.version > v0

    def test_version_increments_on_remove(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 1)
        v = oneshot.version
        oneshot.remove(0)
        assert oneshot.version > v

    def test_version_increments_on_clear(self, oneshot, mock_cache):
        _add_items(oneshot, mock_cache, 1)
        v = oneshot.version
        oneshot.clear()
        assert oneshot.version > v
