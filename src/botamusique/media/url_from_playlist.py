import hashlib
import logging
import threading
from configparser import ConfigParser
from typing import Any

import yt_dlp as youtube_dl

from botamusique.constants import tr_cli as tr
from botamusique.database import SettingsDatabase
from botamusique.media.item import BaseItem
from botamusique.media.url import URLItem

log = logging.getLogger("bot")


def get_playlist_info(url: str, config: ConfigParser, start_index: int = 0, user: str = "") -> list[dict[str, Any]] | None:
    ydl_opts = {
        'extract_flat': 'in_playlist',
        'verbose': config.getboolean('debug', 'youtube_dl')
    }

    cookie = config.get('youtube_dl', 'cookie_file')
    if cookie:
        ydl_opts['cookiefile'] = config.get('youtube_dl', 'cookie_file')

    user_agent = config.get('youtube_dl', 'user_agent')
    if user_agent:
        youtube_dl.utils.std_headers['User-Agent'] = config.get('youtube_dl', 'user_agent')

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        attempts = config.getint('bot', 'download_attempts')
        for i in range(attempts):
            items = []
            try:
                info = ydl.extract_info(url, download=False)

                playlist_title = info['title']
                for j in range(start_index, min(len(info['entries']),
                                                start_index + config.getint('bot', 'max_track_playlist'))):
                    # Unknow String if No title into the json
                    title = info['entries'][j]['title'] if 'title' in info['entries'][j] else "Unknown Title"
                    # Add youtube url if the url in the json isn't a full url
                    item_url = info['entries'][j]['url'] if info['entries'][j]['url'][0:4] == 'http' \
                        else "https://www.youtube.com/watch?v=" + info['entries'][j]['url']
                    print(info['entries'][j])

                    music = {
                        "type": "url_from_playlist",
                        "url": item_url,
                        "title": title,
                        "playlist_url": url,
                        "playlist_title": playlist_title,
                        "user": user
                    }

                    items.append(music)

            except Exception as ex:
                log.exception(ex, exc_info=True)
                continue

            return items


class PlaylistURLItem(URLItem):
    def __init__(self, url: str, title: str, playlist_url: str, playlist_title: str, temp_folder: str, config: ConfigParser, settings_db: SettingsDatabase):
        super().__init__(url, temp_folder, config, settings_db)
        self.title = title
        self.playlist_url = playlist_url
        self.playlist_title = playlist_title
        self.type = "url_from_playlist"

    @classmethod
    def from_dict(cls, d: dict[str, Any], tmp_folder: str, config: ConfigParser, settings_db: SettingsDatabase) -> 'PlaylistURLItem':
        instance = cls.__new__(cls)
        BaseItem.__init__(instance)
        instance._load_base_from_dict(d)
        # URLItem fields
        instance.validating_lock = threading.Lock()
        instance.temp_folder = tmp_folder
        instance.config = config
        instance.settings_db = settings_db
        instance.url = d['url']
        instance.thumbnail = d['thumbnail']
        instance.downloading = False
        # PlaylistURLItem fields
        instance.type = "url_from_playlist"
        instance.playlist_url = d['playlist_url']
        instance.playlist_title = d['playlist_title']
        return instance

    @staticmethod
    def generate_id(url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        tmp_dict = super().to_dict()
        tmp_dict['playlist_url'] = self.playlist_url
        tmp_dict['playlist_title'] = self.playlist_title

        return tmp_dict

    def format_debug_string(self) -> str:
        return "[url] {title} ({url}) from playlist {playlist}".format(
            title=self.title,
            url=self.url,
            playlist=self.playlist_title
        )

    def format_song_string(self, user: str) -> str:
        return tr("url_from_playlist_item",
                  title=self.title,
                  url=self.url,
                  playlist_url=self.playlist_url,
                  playlist=self.playlist_title,
                  user=user)

    def format_current_playing(self, user: str) -> str:
        display = tr("now_playing", item=self.format_song_string(user))

        if self.thumbnail:
            thumbnail_html = '<img width="80" src="data:image/jpge;base64,' + \
                             self.thumbnail + '"/>'
            display += "<br />" + thumbnail_html

        return display

    def display_type(self) -> str:
        return tr("url_from_playlist")
