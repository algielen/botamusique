"""Tests for RadioItem in media/radio.py.

RadioItem.__init__ calls get_radio_server_description() which makes HTTP requests.
All tests use from_dict() to avoid network calls.
"""
import hashlib
import pytest

from botamusique.media.radio import RadioItem

URL = "http://example.com/stream"
NAME = "Test Radio Station"


def _make_dict(url=URL, title=NAME):
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


@pytest.fixture()
def radio_item():
    return RadioItem.from_dict(_make_dict())


# ---------------------------------------------------------------------------
# generate_id
# ---------------------------------------------------------------------------

def test_generate_id_deterministic():
    assert RadioItem.generate_id(URL) == RadioItem.generate_id(URL)


def test_generate_id_is_md5_of_url():
    expected = hashlib.md5(URL.encode()).hexdigest()
    assert RadioItem.generate_id(URL) == expected


def test_generate_id_different_urls_differ():
    assert RadioItem.generate_id("http://a.com/") != RadioItem.generate_id("http://b.com/")


# ---------------------------------------------------------------------------
# from_dict / to_dict round-trip
# ---------------------------------------------------------------------------

def test_from_dict_restores_url(radio_item):
    assert radio_item.url == URL


def test_from_dict_restores_title(radio_item):
    assert radio_item.title == NAME


def test_from_dict_restores_id(radio_item):
    assert radio_item.id == RadioItem.generate_id(URL)


def test_from_dict_restores_type(radio_item):
    assert radio_item.type == "radio"


def test_to_dict_contains_url(radio_item):
    d = radio_item.to_dict()
    assert d["url"] == URL


def test_to_dict_contains_type(radio_item):
    assert radio_item.to_dict()["type"] == "radio"


def test_round_trip(radio_item):
    d = radio_item.to_dict()
    restored = RadioItem.from_dict(d)
    assert restored.url == radio_item.url
    assert restored.title == radio_item.title
    assert restored.id == radio_item.id


# ---------------------------------------------------------------------------
# State and behaviour
# ---------------------------------------------------------------------------

def test_is_ready_always_true(radio_item):
    assert radio_item.is_ready() is True


def test_is_ready_true_even_with_pending_ready(radio_item):
    radio_item.ready = "pending"
    assert radio_item.is_ready() is True


def test_uri_returns_url(radio_item):
    assert radio_item.uri() == URL


def test_validate_returns_true(radio_item):
    assert radio_item.validate() is True


def test_validate_increments_version(radio_item):
    v = radio_item.version
    radio_item.validate()
    assert radio_item.version == v + 1


def test_validate_idempotent_increment(radio_item):
    radio_item.validate()
    radio_item.validate()
    assert radio_item.version == 2


def test_format_debug_string_contains_url(radio_item):
    s = radio_item.format_debug_string()
    assert URL in s


def test_format_debug_string_contains_name(radio_item):
    s = radio_item.format_debug_string()
    assert NAME in s
