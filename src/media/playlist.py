import json
import logging
import random
import threading
import time
from configparser import ConfigParser
from typing import Callable, Any, Self

from database import Condition, MusicDatabase, SettingsDatabase
from media.cache import CachedItemWrapper, ItemNotCachedError, MusicCache
from media.item import ValidationFailedError

SendMsgCallback = Callable[[str], None]


def get_playlist(mode: str, cache: MusicCache, settings_db: SettingsDatabase, music_db: MusicDatabase, config: ConfigParser, send_channel_msg: SendMsgCallback, _list: 'BasePlaylist | None' = None, _index: int | None = None) -> 'BasePlaylist':
    index = -1
    if _list and _index is None:
        index = _list.current_index

    if _list is None:
        if mode == "one-shot":
            return OneshotPlaylist(cache, settings_db, music_db, config, send_channel_msg)
        elif mode == "repeat":
            return RepeatPlaylist(cache, settings_db, music_db, config, send_channel_msg)
        elif mode == "random":
            return RandomPlaylist(cache, settings_db, music_db, config, send_channel_msg)
        elif mode == "autoplay":
            return AutoPlaylist(cache, settings_db, music_db, config, send_channel_msg)
    else:
        if mode == "one-shot":
            return OneshotPlaylist(cache, settings_db, music_db, config, send_channel_msg).from_list(_list, index)
        elif mode == "repeat":
            return RepeatPlaylist(cache, settings_db, music_db, config, send_channel_msg).from_list(_list, index)
        elif mode == "random":
            return RandomPlaylist(cache, settings_db, music_db, config, send_channel_msg).from_list(_list, index)
        elif mode == "autoplay":
            return AutoPlaylist(cache, settings_db, music_db, config, send_channel_msg).from_list(_list, index)
    raise


class BasePlaylist(list):
    def __init__(self, cache: MusicCache, settings_db: SettingsDatabase, music_db: MusicDatabase, config: ConfigParser, send_channel_msg: SendMsgCallback | None = None) -> None:
        super().__init__()
        self.cache = cache
        self.settings_db = settings_db
        self.music_db = music_db
        self.config = config
        self.send_channel_msg = send_channel_msg or (lambda msg: None)
        self.current_index = -1
        self.version = 0  # increase by one after each change
        self.mode = "base"  # "repeat", "random"
        self.pending_items = []
        self.log = logging.getLogger("bot")
        self.validating_thread_lock = threading.Lock()
        self.playlist_lock = threading.RLock()

    def is_empty(self) -> bool:
        return True if len(self) == 0 else False

    def from_list(self, _list: list[CachedItemWrapper], current_index: int) -> Self:
        self.version += 1
        super().clear()
        self.extend(_list)
        self.current_index = current_index

        return self

    def append(self, item: CachedItemWrapper) -> CachedItemWrapper:
        with self.playlist_lock:
            self.version += 1
            super().append(item)
            self.pending_items.append(item)

        self.async_validate()

        return item

    def insert(self, index: int, item: CachedItemWrapper) -> CachedItemWrapper:
        with self.playlist_lock:
            self.version += 1
            if index == -1:
                index = self.current_index

            super().insert(index, item)

            if index <= self.current_index:
                self.current_index += 1

            self.pending_items.append(item)

        self.async_validate()

        return item

    def extend(self, items: list[CachedItemWrapper]) -> list[CachedItemWrapper]:
        with self.playlist_lock:
            self.version += 1
            super().extend(items)
            self.pending_items.extend(items)

        self.async_validate()
        return items

    def next(self) -> CachedItemWrapper | bool:
        with self.playlist_lock:
            if len(self) == 0:
                return False

            if self.current_index < len(self) - 1:
                self.current_index += 1
                return self[self.current_index]
            else:
                return False

    def point_to(self, index: int) -> None:
        with self.playlist_lock:
            if -1 <= index < len(self):
                self.current_index = index

    def find(self, id: str) -> int | None:
        with self.playlist_lock:
            for index, wrapper in enumerate(self):
                if wrapper.item.id == id:
                    return index
        return None

    def __delitem__(self, key: int) -> CachedItemWrapper | bool:
        return self.remove(key)

    def remove(self, index: int) -> CachedItemWrapper | bool:
        with self.playlist_lock:
            self.version += 1
            if index > len(self) - 1:
                return False

            removed = self[index]
            super().__delitem__(index)

            if self.current_index > index:
                self.current_index -= 1

        # reference counter
        counter = 0
        for wrapper in self:
            if wrapper.id == removed.id:
                counter += 1

        if counter == 0:
            self.cache.free(removed.id)
        return removed

    def remove_by_id(self, id: str) -> None:
        to_be_removed = []
        for index, wrapper in enumerate(self):
            if wrapper.id == id:
                to_be_removed.append(index)

        if to_be_removed:
            self.version += 1

        for index in to_be_removed:
            self.remove(index)

    def current_item(self) -> CachedItemWrapper | bool:
        with self.playlist_lock:
            if len(self) == 0:
                return False

            return self[self.current_index]

    def next_index(self) -> int | bool:
        with self.playlist_lock:
            if self.current_index < len(self) - 1:
                return self.current_index + 1

        return False

    def next_item(self) -> CachedItemWrapper | bool:
        with self.playlist_lock:
            if self.current_index < len(self) - 1:
                return self[self.current_index + 1]

        return False

    def randomize(self) -> None:
        with self.playlist_lock:
            random.shuffle(self)
            self.current_index = -1
            self.version += 1

    def clear(self) -> None:
        with self.playlist_lock:
            self.version += 1
            self.current_index = -1
            super().clear()

        self.cache.free_all()

    def save(self) -> None:
        with self.playlist_lock:
            self.settings_db.remove_section("playlist_item")
            assert self.current_index is not None
            self.settings_db.set("playlist", "current_index", self.current_index)

            for index, music in enumerate(self):
                self.settings_db.set("playlist_item", str(index), json.dumps({'id': music.id, 'user': music.user}))

    def load(self) -> None:
        current_index = self.settings_db.getint("playlist", "current_index", fallback=-1)
        if current_index == -1:
            return

        items = self.settings_db.items("playlist_item")
        if items:
            music_wrappers = []
            items.sort(key=lambda v: int(v[0]))
            for item in items:
                item = json.loads(item[1])
                music_wrapper = self.cache.get_cached_wrapper_by_id(item['id'], item['user'])
                if music_wrapper:
                    music_wrappers.append(music_wrapper)
            self.from_list(music_wrappers, current_index)

    def _debug_print(self) -> None:
        print("===== Playlist(%d) =====" % self.current_index)
        for index, item_wrapper in enumerate(self):
            if index == self.current_index:
                print("-> %d %s" % (index, item_wrapper.format_debug_string()))
            else:
                print("%d %s" % (index, item_wrapper.format_debug_string()))
        print("=====     End     =====")

    def async_validate(self) -> None:
        if not self.validating_thread_lock.locked():
            time.sleep(0.1)  # Just avoid validation finishes too fast and delete songs while something is reading it.
            th = threading.Thread(target=self._check_valid, name="Validating")
            th.daemon = True
            th.start()

    def _check_valid(self) -> None:
        self.log.debug("playlist: start validating...")
        self.validating_thread_lock.acquire()
        while len(self.pending_items) > 0:
            item = self.pending_items.pop()
            try:
                item.item()
            except ItemNotCachedError:
                # In some very subtle case, items are removed and freed from
                # the playlist and the cache, before validation even starts,
                # causes, freed items remain in pending_items.
                # Simply ignore these items here.
                continue

            self.log.debug("playlist: validating %s" % item.format_debug_string())
            ver = item.version

            try:
                item.validate()
            except ValidationFailedError as e:
                self.log.debug("playlist: validating failed.")
                self.send_channel_msg(e.msg)
                self.remove_by_id(item.id)
                self.cache.free_and_delete(item.id)
                continue

            if item.version > ver:
                self.version += 1

        self.log.debug("playlist: validating finished.")
        self.validating_thread_lock.release()


class OneshotPlaylist(BasePlaylist):
    def __init__(self, cache: MusicCache, settings_db: SettingsDatabase, music_db: MusicDatabase, config: ConfigParser, send_channel_msg: SendMsgCallback | None = None) -> None:
        super().__init__(cache, settings_db, music_db, config, send_channel_msg)
        self.mode = "one-shot"
        self.current_index = -1

    def current_item(self) -> CachedItemWrapper | bool:
        with self.playlist_lock:
            if len(self) == 0:
                self.current_index = -1
                return False

            if self.current_index == -1:
                self.current_index = 0

            return self[self.current_index]

    def from_list(self, _list: list[CachedItemWrapper], current_index: int) -> Self:
        with self.playlist_lock:
            if len(_list) > 0:
                if current_index > -1:
                    for i in range(current_index):
                        _list.pop(0)
                    return super().from_list(_list, 0)
                return super().from_list(_list, -1)
            return self

    def next(self) -> CachedItemWrapper | bool:
        with self.playlist_lock:
            if len(self) > 0:
                self.version += 1

                if self.current_index != -1:
                    super().__delitem__(self.current_index)
                    if len(self) == 0:
                        return False
                else:
                    self.current_index = 0

                return self[0]
            else:
                self.current_index = -1
                return False

    def next_index(self) -> int | bool:
        if len(self) > 1:
            return 1
        else:
            return False

    def next_item(self) -> CachedItemWrapper | bool:
        if len(self) > 1:
            return self[1]
        else:
            return False

    def point_to(self, index: int) -> None:
        with self.playlist_lock:
            self.version += 1
            self.current_index = -1
            for i in range(index):
                super().__delitem__(0)


class RepeatPlaylist(BasePlaylist):
    def __init__(self, cache: MusicCache, settings_db: SettingsDatabase, music_db: MusicDatabase, config: ConfigParser, send_channel_msg: SendMsgCallback | None = None) -> None:
        super().__init__(cache, settings_db, music_db, config, send_channel_msg)
        self.mode = "repeat"

    def next(self) -> CachedItemWrapper | bool:
        with self.playlist_lock:
            if len(self) == 0:
                return False

            if self.current_index < len(self) - 1:
                self.current_index += 1
                return self[self.current_index]
            else:
                self.current_index = 0
                return self[0]

    def next_index(self) -> int:
        with self.playlist_lock:
            if self.current_index < len(self) - 1:
                return self.current_index + 1
            else:
                return 0

    def next_item(self) -> CachedItemWrapper | bool:
        if len(self) == 0:
            return False
        return self[self.next_index()]


class RandomPlaylist(BasePlaylist):
    def __init__(self, cache: MusicCache, settings_db: SettingsDatabase, music_db: MusicDatabase, config: ConfigParser, send_channel_msg: SendMsgCallback | None = None) -> None:
        super().__init__(cache, settings_db, music_db, config, send_channel_msg)
        self.mode = "random"

    def from_list(self, _list: list[CachedItemWrapper], current_index: int) -> Self:
        self.version += 1
        random.shuffle(_list)
        return super().from_list(_list, -1)

    def next(self) -> CachedItemWrapper | bool:
        with self.playlist_lock:
            if len(self) == 0:
                return False

            if self.current_index < len(self) - 1:
                self.current_index += 1
                return self[self.current_index]
            else:
                self.version += 1
                self.randomize()
                self.current_index = 0
                return self[0]


class AutoPlaylist(OneshotPlaylist):
    def __init__(self, cache: MusicCache, settings_db: SettingsDatabase, music_db: MusicDatabase, config: ConfigParser, send_channel_msg: SendMsgCallback | None = None) -> None:
        super().__init__(cache, settings_db, music_db, config, send_channel_msg)
        self.mode = "autoplay"

    def refresh(self) -> None:
        dicts = self.music_db.query_random_music(self.config.getint("bot", "autoplay_length"),
                                                 Condition().and_not_sub_condition(
                                                     Condition().and_like('tags', "%don't autoplay,%")))

        if dicts:
            _list = [self.cache.get_cached_wrapper_from_dict(_dict, "AutoPlay") for _dict in dicts]
            self.from_list(_list, -1)

    def clear(self) -> None:
        super().clear()
        self.refresh()

    def next(self) -> CachedItemWrapper | bool:
        if len(self) == 0:
            self.refresh()
        return super().next()
