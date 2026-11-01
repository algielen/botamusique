import io
import json
import zipfile
from configparser import ConfigParser
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

from botamusique import interface
from botamusique.localfiles import LocalFiles
from botamusique.media.file import FileItem


@pytest.fixture
def local_web(tmp_path, monkeypatch):
    root = tmp_path / 'music'
    root.mkdir()
    config = ConfigParser()
    config.read_dict({'webinterface': {'upload_enabled': 'true'},
                      'bot': {'delete_allowed': 'true'}})
    settings = {}
    rows = []
    db = MagicMock()
    db.get.side_effect = lambda section, key, fallback=None: settings.get((section, key), fallback)
    db.set.side_effect = lambda section, key, value: settings.__setitem__((section, key), value)
    music_db = MagicMock()
    music_db.insert_music.side_effect = rows.append
    music_db.query_music.side_effect = lambda condition: rows.copy()
    bot = SimpleNamespace(music_folder=str(root), config=config, db=db, music_db=music_db,
                          cache=MagicMock(), playlist=MagicMock())
    monkeypatch.setattr(interface, '_bot', bot)
    monkeypatch.setattr(FileItem, '_duration', lambda self: 10)
    app = Flask(__name__)
    app.add_url_rule('/upload', view_func=interface.upload.__wrapped__, methods=['POST'])
    app.add_url_rule('/download', view_func=interface.download.__wrapped__)
    app.add_url_rule('/library', view_func=interface.library.__wrapped__, methods=['POST'])
    return app.test_client(), bot, rows, settings


def upload(client, folder='My music', name='Nice song.wav'):
    return client.post('/upload', data={'targetdir': folder,
                       'file': (io.BytesIO(b'RIFF audio bytes'), name, 'audio/wav')})


def test_upload_uses_generated_names_and_separate_folder_labels(local_web):
    client, bot, rows, settings = local_web
    assert upload(client).status_code == 200
    assert rows[0]['title'] == 'Nice song'
    assert 'Nice song' not in rows[0]['path']
    folders = json.loads(settings['library', 'folders'])
    assert folders['My music'].startswith('uploads/')
    assert upload(client).status_code == 200
    assert rows[0]['path'] != rows[1]['path']
    assert rows[0]['path'].rsplit('/', 1)[0] == rows[1]['path'].rsplit('/', 1)[0]
    for row in rows:
        with LocalFiles(bot.music_folder).open(row['path']) as source:
            assert source.read() == b'RIFF audio bytes'


@pytest.mark.parametrize('folder', ['../outside', '/outside', 'C:\\outside', 'new/nested'])
def test_upload_rejects_paths_without_changing_library(local_web, folder):
    client, bot, rows, settings = local_web
    assert upload(client, folder).status_code in (400, 403)
    assert rows == []
    assert settings == {}
    assert list(LocalFiles(bot.music_folder).root.iterdir()) == []


def test_existing_folders_are_selected_through_server_lookup(local_web):
    client, bot, rows, _ = local_web
    (LocalFiles(bot.music_folder).root / 'existing').mkdir()
    assert upload(client, 'existing').status_code == 200
    assert rows[0]['path'].startswith('existing/')


def test_unicode_upload_name_is_only_display_metadata(local_web):
    client, _, rows, _ = local_web
    assert upload(client, name='音楽.wav').status_code == 200
    assert rows[0]['title'] == '音楽'
    assert rows[0]['path'].endswith('.wav')
    assert '音楽' not in rows[0]['path']


def test_download_by_id_and_zip_use_display_names(local_web):
    client, _, rows, _ = local_web
    assert upload(client).status_code == 200
    response = client.get('/download', query_string={'id': rows[0]['id']})
    assert response.status_code == 200
    assert response.data == b'RIFF audio bytes'
    response.close()
    response = client.get('/download', query_string={
        'type': 'file', 'dir': 'My music', 'tags': '', 'keywords': ''})
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert archive.namelist()[0].startswith('Nice_song-')
        assert archive.read(archive.namelist()[0]) == b'RIFF audio bytes'
    response.close()


def test_untrusted_database_path_is_not_downloadable(local_web, tmp_path):
    client, _, rows, _ = local_web
    outside = tmp_path / 'secret.wav'
    outside.write_bytes(b'secret')
    rows.append({'id': 'test', 'path': str(outside), 'type': 'file', 'title': 'Secret'})
    assert client.get('/download?id=test').status_code == 403
    assert outside.read_bytes() == b'secret'


def test_invalid_bulk_delete_does_not_mutate_playlist_or_database(local_web, tmp_path):
    client, bot, _, _ = local_web
    outside = tmp_path / 'secret.wav'
    outside.write_bytes(b'secret')
    bot.music_db.query_music_count.return_value = 1
    bot.cache.dicts_to_items.return_value = [SimpleNamespace(type='file', path='../secret.wav', id='bad')]
    response = client.post('/library', data={'action': 'delete', 'type': 'file',
                           'dir': '.', 'tags': '', 'keywords': ''})
    assert response.status_code == 403
    bot.playlist.remove_by_id.assert_not_called()
    bot.cache.free_and_delete.assert_not_called()
    assert outside.read_bytes() == b'secret'


def test_existing_file_can_be_deleted_without_removing_its_folder(local_web):
    client, bot, rows, _ = local_web
    assert upload(client).status_code == 200
    item = SimpleNamespace(type='file', path=rows[0]['path'], id=rows[0]['id'])
    bot.music_db.query_music_count.return_value = 1
    bot.cache.dicts_to_items.return_value = [item]
    response = client.post('/library', data={'action': 'delete', 'type': 'file',
                           'dir': 'My music', 'tags': '', 'keywords': ''})
    assert response.status_code == 302
    assert not LocalFiles(bot.music_folder).root.joinpath(item.path).exists()
    assert LocalFiles(bot.music_folder).root.joinpath(item.path).parent.is_dir()
    bot.playlist.remove_by_id.assert_called_once_with(item.id)


def test_failed_upload_removes_partial_file(local_web, monkeypatch):
    from werkzeug.datastructures import FileStorage

    client, bot, rows, settings = local_web

    def fail_save(self, output):
        output.write(b'partial')
        raise OSError('Upload interrupted')

    monkeypatch.setattr(FileStorage, 'save', fail_save)
    assert upload(client).status_code == 403
    assert rows == []
    assert settings == {}
    assert not list(LocalFiles(bot.music_folder).root.rglob('*.wav'))


def test_generated_name_collision_never_overwrites(local_web, monkeypatch):
    client, bot, rows, _ = local_web
    monkeypatch.setattr(interface.uuid, 'uuid4', lambda: SimpleNamespace(hex='a' * 32))
    assert upload(client).status_code == 200
    assert upload(client).status_code == 409
    assert len(rows) == 1
    with LocalFiles(bot.music_folder).open(rows[0]['path']) as source:
        assert source.read() == b'RIFF audio bytes'


def test_cached_download_is_bounded_to_separate_cache_root(local_web, tmp_path):
    client, bot, rows, _ = local_web
    cache = tmp_path / 'cache'
    cache.mkdir()
    bot.cache.tmp_folder = str(cache)
    (cache / 'download').write_bytes(b'downloaded')
    rows.append({'type': 'url', 'id': 'cached', 'title': 'Cached', 'path': str(cache / 'download')})
    response = client.get('/download?id=cached')
    assert response.status_code == 200
    assert response.data == b'downloaded'
    response.close()
    rows[0]['path'] = str(tmp_path / 'secret')
    (tmp_path / 'secret').write_bytes(b'secret')
    assert client.get('/download?id=cached').status_code == 403
