"""Tests for BaseItem base class in media/item.py."""
import pytest
from media.item import BaseItem, ValidationFailedError, PreparationFailedError


class ConcreteItem(BaseItem):
    """Minimal concrete subclass for testing BaseItem directly."""
    def validate(self):
        self.ready = "yes"
        return True

    def uri(self):
        return "/fake/path"


@pytest.fixture()
def item():
    return ConcreteItem()


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initial_ready_is_pending(item):
    assert item.ready == "pending"


def test_initial_is_ready_false(item):
    assert item.is_ready() is False


def test_initial_is_failed_false(item):
    assert item.is_failed() is False


def test_initial_tags_empty(item):
    assert item.tags == []


def test_initial_version_zero(item):
    assert item.version == 0


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------

def test_ready_state_after_validate(item):
    item.validate()
    assert item.is_ready() is True


def test_failed_state(item):
    item.ready = "failed"
    assert item.is_failed() is True
    assert item.is_ready() is False


# ---------------------------------------------------------------------------
# Tag management
# ---------------------------------------------------------------------------

def test_add_tags_adds_uniquely(item):
    item.add_tags(["rock", "jazz"])
    assert item.tags == ["rock", "jazz"]


def test_add_tags_ignores_duplicates(item):
    item.add_tags(["rock"])
    item.add_tags(["rock"])
    assert item.tags == ["rock"]


def test_add_tags_increments_version_once_per_new_tag(item):
    item.add_tags(["rock", "jazz"])
    assert item.version == 2


def test_add_tags_duplicate_does_not_increment_version(item):
    item.add_tags(["rock"])
    v = item.version
    item.add_tags(["rock"])
    assert item.version == v


def test_add_empty_tag_ignored(item):
    item.add_tags([""])
    assert item.tags == []
    assert item.version == 0


def test_remove_tags_removes_existing(item):
    item.tags = ["rock", "jazz"]
    item.version = 0
    item.remove_tags(["rock"])
    assert item.tags == ["jazz"]


def test_remove_tags_increments_version(item):
    item.tags = ["rock"]
    item.version = 0
    item.remove_tags(["rock"])
    assert item.version == 1


def test_remove_tags_missing_tag_noop(item):
    item.tags = ["rock"]
    item.version = 0
    item.remove_tags(["jazz"])
    assert item.tags == ["rock"]
    assert item.version == 0


def test_clear_tags_removes_all(item):
    item.tags = ["rock", "jazz"]
    item.clear_tags()
    assert item.tags == []


def test_clear_tags_increments_version(item):
    item.tags = ["rock"]
    item.version = 0
    item.clear_tags()
    assert item.version == 1


def test_clear_tags_empty_is_noop(item):
    item.tags = []
    item.version = 0
    item.clear_tags()
    assert item.version == 0


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def test_to_dict_contains_required_keys(item):
    d = item.to_dict()
    for key in ("type", "id", "ready", "title", "path", "tags", "keywords", "duration"):
        assert key in d


def test_to_dict_ready_value(item):
    assert item.to_dict()["ready"] == "pending"


def test_load_base_from_dict_round_trip(item):
    item.id = "abc123"
    item.ready = "yes"
    item.tags = ["rock"]
    item.title = "My Song"
    item.path = "/music/song.mp3"
    item.keywords = "My Song"
    item.duration = 180

    d = item.to_dict()

    other = ConcreteItem()
    other._load_base_from_dict(d)

    assert other.id == item.id
    assert other.ready == item.ready
    assert other.tags == item.tags
    assert other.title == item.title
    assert other.path == item.path
    assert other.keywords == item.keywords
    assert other.duration == item.duration


# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------

def test_validation_failed_error_has_msg():
    exc = ValidationFailedError("file missing")
    assert exc.msg == "file missing"


def test_preparation_failed_error_has_msg():
    exc = PreparationFailedError("download failed")
    assert exc.msg == "download failed"


def test_base_item_validate_raises():
    """BaseItem.validate() itself raises ValidationFailedError (must be overridden)."""
    raw = BaseItem()
    with pytest.raises(ValidationFailedError):
        raw.validate()


def test_base_item_uri_raises():
    raw = BaseItem()
    with pytest.raises(NotImplementedError):
        raw.uri()


def test_base_item_prepare_returns_true():
    raw = BaseItem()
    assert raw.prepare() is True
