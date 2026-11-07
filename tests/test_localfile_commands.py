import json
import os
from configparser import ConfigParser
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from botamusique import command, constants


@pytest.fixture(autouse=True)
def load_english():
    constants.load_lang("en_US")


def test_local_play_selects_title_rather_than_storage_path(monkeypatch):
    bot = MagicMock()
    wrapper = MagicMock()
    bot.cache.get_cached_wrappers_from_dicts.return_value = [wrapper]
    monkeypatch.setattr(command, 'send_item_added_message', MagicMock())
    command.cmd_play_file(bot, 'listener', None, 'file', 'Public song name')
    condition = bot.music_db.query_music.call_args.args[0]
    assert 'title' in condition.sql()
    assert 'path' not in condition.sql()
    assert 'Public song name' in condition.filler
    bot.playlist.append.assert_called_once_with(wrapper)


def test_duplicate_titles_offer_selection_without_starting_playback(monkeypatch):
    bot = MagicMock()
    wrappers = [MagicMock(), MagicMock()]
    for index, wrapper in enumerate(wrappers):
        wrapper.to_dict.return_value = {'title': 'Same title', 'id': str(index)}
    bot.cache.get_cached_wrappers_from_dicts.return_value = wrappers
    send = MagicMock()
    monkeypatch.setattr(command, 'send_multi_lines', send)
    command.cmd_play_file(bot, 'listener', None, 'file', 'Same title')
    bot.playlist.append.assert_not_called()
    assert [item['id'] for item in command.song_shortlist] == ['0', '1']
    send.assert_called_once()


@pytest.fixture
def folder_listing(tmp_path, monkeypatch):
    constants.load_lang('en_US')
    bot = MagicMock()
    bot.music_folder = str(tmp_path / 'music')
    Path(bot.music_folder).mkdir()
    bot.db.get.return_value = '{}'
    send = MagicMock()
    monkeypatch.setattr(command, 'send_multi_lines', send)

    def run(pattern=''):
        send.reset_mock()
        bot.send_msg.reset_mock()
        command.cmd_list_folder(bot, 'listener', None, 'listfolder', pattern)
        return ''.join(send.call_args.args[1]) if send.called else bot.send_msg.call_args.args[0]

    return bot, run


def test_list_folder_sorted_recursive_and_shortlist_unchanged(folder_listing, monkeypatch):
    bot, run = folder_listing
    root = Path(bot.music_folder)
    (root / 'Zulu').mkdir()
    (root / 'Alpha' / 'Nested').mkdir(parents=True)
    shortlist = [{'id': 'existing'}]
    monkeypatch.setattr(command, 'song_shortlist', shortlist)
    output = run()
    assert output.index('(root) (.)') < output.index('Alpha</b>') < output.index('Alpha/Nested') < output.index('Zulu')
    assert '!file .' in output
    assert command.song_shortlist is shortlist
    bot.playlist.append.assert_not_called()
    bot.playlist.extend.assert_not_called()
    bot.db.set.assert_not_called()


def test_list_folder_labels_filter_and_escaping(folder_listing):
    bot, run = folder_listing
    root = Path(bot.music_folder)
    (root / 'generated').mkdir()
    (root / 'A&B').mkdir()
    bot.db.get.return_value = json.dumps({'<b>Public & label</b>': 'generated', 'Stale': 'missing'})
    output = run('Public')
    assert '&lt;b&gt;Public &amp; label&lt;/b&gt;' in output
    assert 'generated' not in output
    assert 'Stale' not in output
    assert '(root)' not in output
    assert 'A&amp;B' in run('^A&B$')
    assert run('public') == constants.tr_cli('no_folder')
    assert '(root)' in run(r'^\.$')


def test_list_folder_empty_library_and_invalid_regex(folder_listing):
    _, run = folder_listing
    assert '(root)' in run()
    output = run('(?P<<img>)')
    assert 'Invalid regex:' in output
    assert '<img>' not in output
    assert '&lt;' in output


@pytest.mark.parametrize('count,omitted', [(49, False), (50, True)])
def test_list_folder_pagination(folder_listing, count, omitted):
    bot, run = folder_listing
    for index in range(count):
        (Path(bot.music_folder) / f'folder{index:03}').mkdir()
    output = run()
    assert output.count('<li>') == command.ITEMS_PER_PAGE
    assert (constants.tr_cli('records_omitted') in output) is omitted
    # Pagination counts matching entries, rather than all enumerated folders.
    assert constants.tr_cli('records_omitted') not in run('folder000')


def test_list_folder_excludes_external_directory_link(folder_listing, tmp_path):
    bot, run = folder_listing
    outside = tmp_path / 'outside'
    (outside / 'secret').mkdir(parents=True)
    link = Path(bot.music_folder) / 'escape'
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(outside), str(link))
        else:
            pytest.skip('Directory symlinks unavailable')
    output = run()
    assert 'escape' not in output
    assert 'secret' not in output
    assert str(outside) not in output


def test_list_folder_registration_and_translation_fallback(monkeypatch):
    config = ConfigParser()
    config.read(Path(command.__file__).with_name('configuration.default.ini'))
    bot = MagicMock()
    bot.config = config
    command.register_all_commands(bot)
    bot.register_command.assert_any_call('listfolder', command.cmd_list_folder)
    config.set('commands', 'list_folder', 'folders')
    command.register_all_commands(bot)
    bot.register_command.assert_any_call('folders', command.cmd_list_folder)
    constants.load_lang('en_US')
    monkeypatch.setattr(constants, 'lang_dict', {'cli': {}})
    assert constants.tr_cli('list_folder_header') == 'Available folders:'
    assert 'listfolder' in constants.tr_cli('help')
