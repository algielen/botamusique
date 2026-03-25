import logging
import magic
import os
import threading
from configparser import ConfigParser
from typing import Any

from database import MusicDatabase, Condition, SettingsDatabase
from media.file import FileItem
from media.item import BaseItem
from media.radio import RadioItem
from media.url import URLItem
from media.url_from_playlist import PlaylistURLItem


class ItemNotCachedError(Exception):
    pass


def solve_filepath(path: str) -> str:
    if not path:
        return ''

    if path[0] == '/':
        return path
    elif os.path.exists(path):
        return path
    else:
        mydir = os.path.dirname(os.path.realpath(__file__))
        return mydir + '/' + path


class MusicCache(dict):
    def __init__(self, music_db: MusicDatabase, settings_db: SettingsDatabase, config: ConfigParser, music_folder: str) -> None:
        super().__init__()
        self.music_db = music_db
        self.settings_db = settings_db
        self.config = config
        self.music_folder = music_folder
        self.tmp_folder = solve_filepath(config.get('bot', 'tmp_folder'))
        self.log = logging.getLogger("bot")
        self.dir_lock = threading.Lock()

    def get_item_by_id(self, id: str) -> BaseItem | None:
        if id in self:
            return self[id]

        # if not cached, query the database
        item = self.fetch(id)
        if item is not None:
            self[id] = item
            self.log.debug("library: music found in database: %s" % item.format_debug_string())
            return item
        else:
            return None

    def get_item(self, **kwargs: Any) -> BaseItem:
        # kwargs should provide type and other parameters to build the item if not in the library.
        item_type = kwargs['type']

        if 'id' in kwargs:
            id = kwargs['id']
        else:
            match item_type:
                case 'file':
                    id = FileItem.generate_id(kwargs['path'])
                case 'url':
                    id = URLItem.generate_id(kwargs['url'])
                case 'url_from_playlist':
                    id = PlaylistURLItem.generate_id(kwargs['url'])
                case 'radio':
                    id = RadioItem.generate_id(kwargs['url'])
                case _:
                    raise ValueError(f"Unknown item type: {item_type}")

        if id in self:
            return self[id]

        # if not cached, query the database
        item = self.fetch(id)
        if item is not None:
            self[id] = item
            self.log.debug("library: music found in database: %s" % item.format_debug_string())
            return item

        # if not in the database, build one
        match item_type:
            case 'file':
                self[id] = FileItem(kwargs['path'], self.music_folder)
            case 'url':
                self[id] = URLItem(kwargs['url'], self.tmp_folder, self.config, self.settings_db)
            case 'url_from_playlist':
                self[id] = PlaylistURLItem(
                    kwargs['url'],
                    kwargs.get('title', ''),
                    kwargs['playlist_url'],
                    kwargs['playlist_title'],
                    self.tmp_folder,
                    self.config,
                    self.settings_db,
                )
            case 'radio':
                self[id] = RadioItem(kwargs['url'], kwargs.get('name', ''))
            case _:
                raise ValueError(f"Unknown item type: {item_type}")

        return self[id]

    def get_items_by_tags(self, tags: list[str]) -> list[BaseItem]:
        music_dicts = self.music_db.query_music_by_tags(tags)
        items = []
        if music_dicts:
            for music_dict in music_dicts:
                id = music_dict['id']
                self[id] = self.dict_to_item(music_dict)
                items.append(self[id])

        return items

    def fetch(self, id: str) -> BaseItem | None:
        music_dict = self.music_db.query_music_by_id(id)
        if music_dict:
            self[id] = self.dict_to_item(music_dict)
            return self[id]
        else:
            return None

    def dict_to_item(self, d: dict[str, Any]) -> BaseItem:
        match d['type']:
            case 'file':
                return FileItem.from_dict(d, self.music_folder)
            case 'url':
                return URLItem.from_dict(d, self.tmp_folder, self.config, self.settings_db)
            case 'url_from_playlist':
                return PlaylistURLItem.from_dict(d, self.tmp_folder, self.config, self.settings_db)
            case 'radio':
                return RadioItem.from_dict(d)
            case _:
                raise ValueError(f"Unknown item type: {d['type']}")

    def dicts_to_items(self, dicts: list[dict[str, Any]]) -> list[BaseItem]:
        return [self.dict_to_item(d) for d in dicts]

    def save(self, id: str) -> None:
        self.log.debug("library: music save into database: %s" % self[id].format_debug_string())
        self.music_db.insert_music(self[id].to_dict())
        self.music_db.manage_special_tags()

    def free_and_delete(self, id: str) -> None:
        item = self.get_item_by_id(id)
        if item:
            self.log.debug("library: DELETE item from the database: %s" % item.format_debug_string())

            if item.type == 'url':
                if os.path.exists(item.path):
                    os.remove(item.path)

            if item.id in self:
                del self[item.id]
            self.music_db.delete_music(Condition().and_equal("id", item.id))

    def free(self, id: str) -> None:
        if id in self:
            self.log.debug("library: cache freed for item: %s" % self[id].format_debug_string())
            del self[id]

    def free_all(self) -> None:
        self.log.debug("library: all cache freed")
        self.clear()

    def build_dir_cache(self) -> None:
        self.dir_lock.acquire()
        self.log.info("library: rebuild directory cache")
        files = self.get_recursive_file_list_sorted(self.music_folder)

        # remove deleted files
        results = self.music_db.query_music(Condition().or_equal('type', 'file'))
        for result in results:
            if result['path'] not in files:
                self.log.debug("library: music file missed: %s, delete from library." % result['path'])
                self.music_db.delete_music(Condition().and_equal('id', result['id']))
            else:
                files.remove(result['path'])

        for file in files:
            results = self.music_db.query_music(Condition().and_equal('path', file))
            if not results:
                item = FileItem(file, self.music_folder)
                self.log.debug("library: music save into database: %s" % item.format_debug_string())
                self.music_db.insert_music(item.to_dict())

        self.music_db.manage_special_tags()
        self.dir_lock.release()

    def get_recursive_file_list_sorted(self, path: str) -> list[str]:
        filelist = []

        if not os.access(path, os.R_OK):
            self.log.error(f"Unable to list files at {path}. Verify it exists and traverse permission is granted for all parent paths.")
            return filelist

        for root, dirs, files in os.walk(path, topdown=True, onerror=None, followlinks=True):
            relroot = root.replace(path, '', 1)
            if relroot != '' and relroot in self.config.get('bot', 'ignored_folders'):
                continue
            for file in files:
                if file in self.config.get('bot', 'ignored_files'):
                    continue

                fullpath = os.path.join(path, relroot, file)
                if not os.access(fullpath, os.R_OK):
                    continue

                try:
                    mime = magic.from_file(fullpath, mime=True).lower()
                    if 'audio' in mime or 'video' in mime:
                        filelist.append(os.path.join(relroot, file))
                except:
                    pass

        filelist.sort()
        return filelist

    # -------------------------
    # Cached wrapper helpers
    # -------------------------

    def get_cached_wrapper(self, item: BaseItem | None, user: str) -> 'CachedItemWrapper | None':
        if item:
            self[item.id] = item
            return CachedItemWrapper(self, item.id, item.type, user)
        return None

    def get_cached_wrappers(self, items: list[BaseItem], user: str) -> 'list[CachedItemWrapper]':
        wrappers = []
        for item in items:
            if item:
                wrappers.append(self.get_cached_wrapper(item, user))
        return wrappers

    def get_cached_wrapper_from_scrap(self, **kwargs: Any) -> 'CachedItemWrapper':
        item = self.get_item(**kwargs)
        if 'user' not in kwargs:
            raise KeyError("Which user added this song?")
        return CachedItemWrapper(self, item.id, kwargs['type'], kwargs['user'])

    def get_cached_wrapper_from_dict(self, dict_from_db: dict[str, Any] | None, user: str) -> 'CachedItemWrapper | None':
        if dict_from_db:
            item = self.dict_to_item(dict_from_db)
            return self.get_cached_wrapper(item, user)
        return None

    def get_cached_wrappers_from_dicts(self, dicts_from_db: list[dict[str, Any]], user: str) -> 'list[CachedItemWrapper]':
        items = []
        for dict_from_db in dicts_from_db:
            if dict_from_db:
                items.append(self.get_cached_wrapper_from_dict(dict_from_db, user))
        return items

    def get_cached_wrapper_by_id(self, id: str, user: str) -> 'CachedItemWrapper | None':
        item = self.get_item_by_id(id)
        if item:
            return CachedItemWrapper(self, item.id, item.type, user)

    def get_cached_wrappers_by_tags(self, tags: list[str], user: str) -> 'list[CachedItemWrapper]':
        items = self.get_items_by_tags(tags)
        ret = []
        for item in items:
            ret.append(CachedItemWrapper(self, item.id, item.type, user))
        return ret


class CachedItemWrapper:
    def __init__(self, lib: MusicCache, id: str, type: str, user: str) -> None:
        self.lib = lib
        self.id = id
        self.user = user
        self.type = type
        self.log = logging.getLogger("bot")
        self.version = 0

    def item(self) -> BaseItem:
        if self.id in self.lib:
            return self.lib[self.id]
        else:
            raise ItemNotCachedError(f"Uncached item of id {self.id}, type {self.type}.")

    def to_dict(self) -> dict[str, Any]:
        dict = self.item().to_dict()
        dict['user'] = self.user
        return dict

    def validate(self) -> bool:
        ret = self.item().validate()
        if ret and self.item().version > self.version:
            self.version = self.item().version
            self.lib.save(self.id)
        return ret

    def prepare(self) -> bool:
        ret = self.item().prepare()
        if ret and self.item().version > self.version:
            self.version = self.item().version
            self.lib.save(self.id)
        return ret

    def uri(self) -> str:
        return self.item().uri()

    def add_tags(self, tags: list[str]) -> None:
        self.item().add_tags(tags)
        if self.item().version > self.version:
            self.version = self.item().version
            self.lib.save(self.id)

    def remove_tags(self, tags: list[str]) -> None:
        self.item().remove_tags(tags)
        if self.item().version > self.version:
            self.version = self.item().version
            self.lib.save(self.id)

    def clear_tags(self) -> None:
        self.item().clear_tags()
        if self.item().version > self.version:
            self.version = self.item().version
            self.lib.save(self.id)

    def is_ready(self) -> bool:
        return self.item().is_ready()

    def is_failed(self) -> bool:
        return self.item().is_failed()

    def format_current_playing(self) -> str:
        return self.item().format_current_playing(self.user)

    def format_song_string(self) -> str:
        return self.item().format_song_string(self.user)

    def format_title(self) -> str:
        return self.item().format_title()

    def format_debug_string(self) -> str:
        return self.item().format_debug_string()

    def display_type(self) -> str:
        return self.item().display_type()
