from unittest.mock import MagicMock

from botamusique import command


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
