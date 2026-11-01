"""Local media storage. Names from requests are never filesystem capabilities."""
import hashlib
import os
import stat
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _windows_api():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


class UnsafePath(ValueError):
    pass


def relative_parts(name: str) -> list[str]:
    if not isinstance(name, str) or not name or '\x00' in name or '\\' in name:
        raise UnsafePath('Invalid relative name')
    if name.startswith('/') or PureWindowsPath(name).drive:
        raise UnsafePath('Absolute paths are forbidden')
    parts = name.split('/')
    if any(p in ('', '.', '..') or ':' in p or p.rstrip(' .') != p for p in parts):
        raise UnsafePath('Invalid path component')
    return parts


def _check(path):
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & FILE_ATTRIBUTE_REPARSE_POINT:
        raise UnsafePath('Links and reparse points are forbidden')
    return info


class LocalFiles:
    def __init__(self, root: str | Path):
        self.root = Path(os.path.abspath(root))

    def path(self, name: str) -> str:
        parts = relative_parts(name)
        # Inspect the configured root's ancestors too; resolve() would hide links.
        current = Path(self.root.anchor)
        for part in (*self.root.parts[1:], *parts):
            current /= part
            try:
                _check(current)
            except FileNotFoundError:
                continue
        return str(self.root.joinpath(*parts))

    @contextmanager
    def parent(self, name, create=False):
        """Pin parent directories; POSIX operations use no-follow directory FDs."""
        parts = relative_parts(name)
        if os.name == 'nt':
            # Deny write/delete sharing: ancestors cannot be renamed or converted
            # into reparse points while we operate beneath them.
            import ctypes
            from ctypes import wintypes
            kernel = _windows_api()
            handles = []
            current = Path(self.root.anchor)
            try:
                for part in (*self.root.parts[1:], *parts[:-1]):
                    current /= part
                    if create and not current.exists():
                        current.mkdir()
                    handle = kernel.CreateFileW(str(current), 0x80000000, 1, None, 3, 0x02200000, None)
                    if handle == wintypes.HANDLE(-1).value:
                        raise ctypes.WinError(ctypes.get_last_error())
                    handles.append(handle)
                    info = _check(current)
                    if not stat.S_ISDIR(info.st_mode):
                        raise UnsafePath('Expected a directory')
                yield None, self.path(name)
            finally:
                for handle in reversed(handles):
                    kernel.CloseHandle(handle)
        else:
            fd = os.open(self.root.anchor, os.O_RDONLY | os.O_DIRECTORY)
            try:
                for part in (*self.root.parts[1:], *parts[:-1]):
                    if create:
                        try:
                            os.mkdir(part, dir_fd=fd)
                        except FileExistsError:
                            pass
                    new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = new
                yield fd, parts[-1]
            finally:
                os.close(fd)

    def open(self, name, create=False):
        with self.parent(name, create=create) as (parent, leaf):
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL if create else os.O_RDONLY
            if os.name == 'nt':
                import ctypes
                import msvcrt
                from ctypes import wintypes
                kernel = _windows_api()
                handle = kernel.CreateFileW(leaf, 0x40000000 if create else 0x80000000,
                                            1, None, 1 if create else 3, 0x00200000, None)
                if handle == wintypes.HANDLE(-1).value:
                    error = ctypes.get_last_error()
                    if error in (80, 183):
                        raise FileExistsError(leaf)
                    raise ctypes.WinError(error)
                try:
                    fd = msvcrt.open_osfhandle(handle, flags & (os.O_RDONLY | os.O_WRONLY) | os.O_BINARY)
                except BaseException:
                    kernel.CloseHandle(handle)
                    raise
            else:
                fd = os.open(leaf, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or getattr(info, 'st_file_attributes', 0) & FILE_ATTRIBUTE_REPARSE_POINT):
                    raise UnsafePath('Only regular files with one hard link are allowed')
                return os.fdopen(fd, 'wb' if create else 'rb')
            except BaseException:
                os.close(fd)
                raise

    def delete(self, name):
        with self.parent(name) as (parent, leaf):
            info = os.stat(leaf, dir_fd=parent, follow_symlinks=False) if parent is not None else _check(leaf)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise UnsafePath('Only regular files may be deleted')
            os.unlink(leaf, dir_fd=parent)

    def folders(self) -> dict[str, str]:
        self.path('__root_check__')
        result = {folder_id('.'): '.'}
        for root, dirs, _ in os.walk(self.root, followlinks=False):
            dirs[:] = [d for d in dirs if self._safe_dir(Path(root) / d)]
            for directory in dirs:
                name = (Path(root) / directory).relative_to(self.root).as_posix()
                result[folder_id(name)] = name
        return result

    def _safe_dir(self, path):
        try:
            return stat.S_ISDIR(_check(self.path(path.relative_to(self.root).as_posix())).st_mode)
        except (OSError, UnsafePath):
            return False


def folder_id(name):
    return hashlib.sha256(name.encode()).hexdigest()


def subprocess_input(stream):
    if os.name == 'nt':
        return None, {}
    prefix = '/proc/self/fd' if os.path.isdir('/proc/self/fd') else '/dev/fd'
    return f'{prefix}/{stream.fileno()}', {'pass_fds': (stream.fileno(),)}


def cache_location(root, path):
    """Convert an internal cached-download path to a bounded storage reference."""
    root = os.path.abspath(root)
    path = os.path.abspath(path)
    try:
        contained = os.path.commonpath([root, path]) == root
    except ValueError:
        contained = False
    if not contained:
        raise UnsafePath('Download is outside the cache')
    relative = os.path.relpath(path, root).replace(os.sep, '/')
    relative_parts(relative)
    return LocalFiles(root), relative
