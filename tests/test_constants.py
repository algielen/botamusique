"""Tests for the translation system in constants.py."""
import pytest
import constants
from constants import load_lang, tr_cli, tr_web, _tr


@pytest.fixture(autouse=True)
def load_english():
    """Load English translations before each test."""
    load_lang("en_US")


def test_load_lang_en_us_succeeds():
    load_lang("en_US")
    assert constants.default_lang_dict != {}
    assert "cli" in constants.default_lang_dict
    assert "web" in constants.default_lang_dict


def test_tr_cli_returns_nonempty_string():
    result = tr_cli("cleared")
    assert isinstance(result, str)
    assert len(result) > 0


def test_tr_cli_known_value():
    result = tr_cli("cleared")
    assert result == "Playlist emptied."


def test_tr_cli_with_kwargs():
    result = tr_cli("change_volume", volume=75, user="Alice")
    assert "75" in result
    assert "Alice" in result


def test_tr_cli_missing_key_raises():
    with pytest.raises(KeyError):
        tr_cli("this_key_does_not_exist_xyz")


def test_tr_web_returns_nonempty_string():
    result = tr_web("add")
    assert isinstance(result, str)
    assert len(result) > 0


def test_tr_web_known_value():
    result = tr_web("add")
    assert result == "Add"


def test_tr_web_missing_key_raises():
    with pytest.raises(KeyError):
        tr_web("no_such_web_key_xyz")


def test_tr_internal_no_args_passthrough():
    assert _tr("hello world") == "hello world"


def test_tr_internal_with_kwargs():
    assert _tr("hello {name}", name="world") == "hello world"


def test_tr_internal_with_positional_args():
    assert _tr("hello {0}", "world") == "hello world"


def test_tr_internal_wrong_placeholder_raises():
    with pytest.raises(KeyError):
        _tr("hello {x}", y="z")
