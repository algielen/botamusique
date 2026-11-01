import os
import subprocess
import sys

import pytest

from botamusique.localfiles import LocalFiles, UnsafePath, subprocess_input


@pytest.mark.parametrize('name', ['', '..', '../outside', 'a/../outside', '/outside',
                                 'C:/outside', 'C:outside', '//server/share',
                                 'a\\outside', 'a//b', './a', 'a:stream', 'a\x00b', '.. /file', 'a./file'])
def test_rejects_nonrelative_names(tmp_path, name):
    store = LocalFiles(tmp_path)
    with pytest.raises(UnsafePath):
        store.open(name, create=True)


def test_create_read_delete_and_collision(tmp_path):
    store = LocalFiles(tmp_path)
    with store.open('folder/song.mp3', create=True) as output:
        output.write(b'music')
    with pytest.raises(FileExistsError):
        store.open('folder/song.mp3', create=True)
    with store.open('folder/song.mp3') as source:
        assert source.read() == b'music'
    store.delete('folder/song.mp3')
    assert not (tmp_path / 'folder/song.mp3').exists()


def make_link(target, link, directory=False):
    try:
        os.symlink(target, link, target_is_directory=directory)
    except OSError:
        if os.name == 'nt' and directory:
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            pytest.skip('Creating symlinks requires OS privileges')


def test_linked_directory_is_not_scanned_or_used(tmp_path):
    root = tmp_path / 'music'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.mp3').write_bytes(b'secret')
    make_link(outside, root / 'escape', directory=True)
    store = LocalFiles(root)
    assert 'escape' not in store.folders().values()
    for operation in [lambda: store.open('escape/secret.mp3'),
                      lambda: store.open('escape/new.mp3', create=True),
                      lambda: store.delete('escape/secret.mp3')]:
        with pytest.raises((OSError, UnsafePath)):
            operation()
    assert (outside / 'secret.mp3').read_bytes() == b'secret'
    assert not (outside / 'new.mp3').exists()


def test_even_links_inside_root_are_rejected(tmp_path):
    (tmp_path / 'actual').mkdir()
    make_link(tmp_path / 'actual', tmp_path / 'alias', directory=True)
    with pytest.raises((OSError, UnsafePath)):
        LocalFiles(tmp_path).open('alias/song.mp3', create=True)


def test_linked_root_is_rejected(tmp_path):
    (tmp_path / 'actual').mkdir()
    make_link(tmp_path / 'actual', tmp_path / 'alias', directory=True)
    with pytest.raises((OSError, UnsafePath)):
        LocalFiles(tmp_path / 'alias').open('song.mp3', create=True)


def test_linked_file_is_never_read_or_overwritten(tmp_path):
    (tmp_path / 'target.mp3').write_bytes(b'original')
    make_link(tmp_path / 'target.mp3', tmp_path / 'alias.mp3')
    store = LocalFiles(tmp_path)
    with pytest.raises((OSError, UnsafePath)):
        store.open('alias.mp3')
    with pytest.raises((OSError, UnsafePath)):
        store.open('alias.mp3', create=True)
    assert (tmp_path / 'target.mp3').read_bytes() == b'original'


def test_hardlinked_file_is_rejected(tmp_path):
    (tmp_path / 'target.mp3').write_bytes(b'original')
    os.link(tmp_path / 'target.mp3', tmp_path / 'alias.mp3')
    with pytest.raises(UnsafePath):
        LocalFiles(tmp_path).open('alias.mp3')


def test_subprocess_reads_the_secured_open_file(tmp_path):
    store = LocalFiles(tmp_path)
    with store.open('song.mp3', create=True) as output:
        output.write(b'music')
    with store.open('song.mp3') as source:
        name, options = subprocess_input(source)
        result = subprocess.run([sys.executable, '-c',
                                 'import sys; print(open(sys.argv[1], "rb").read().decode())',
                                 name or store.path('song.mp3')],
                                check=True, capture_output=True, **options)
    assert result.stdout.strip() == b'music'


@pytest.mark.skipif(os.name != 'nt', reason='Windows handle sharing semantics')
def test_windows_pins_parent_and_file_against_replacement(tmp_path):
    store = LocalFiles(tmp_path)
    with store.open('folder/song.mp3', create=True) as output:
        output.write(b'music')
    with store.parent('folder/song.mp3'):
        with pytest.raises(OSError):
            (tmp_path / 'folder').rename(tmp_path / 'moved')
    with store.open('folder/song.mp3'):
        with pytest.raises(OSError):
            (tmp_path / 'folder').rename(tmp_path / 'moved')
        with pytest.raises(OSError):
            (tmp_path / 'folder/song.mp3').write_bytes(b'changed')
        with pytest.raises(OSError):
            (tmp_path / 'folder/song.mp3').unlink()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX directory descriptor semantics')
def test_parent_replacement_cannot_redirect_an_open_operation(tmp_path, monkeypatch):
    root = tmp_path / 'music'
    (root / 'folder').mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    original_open = os.open

    def racing_open(path, flags, *args, **kwargs):
        if path == 'song.mp3':
            (root / 'folder').rename(root / 'old-folder')
            (root / 'folder').symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', racing_open)
    with LocalFiles(root).open('folder/song.mp3', create=True) as output:
        output.write(b'music')
    assert not (outside / 'song.mp3').exists()
    assert (root / 'old-folder/song.mp3').read_bytes() == b'music'
