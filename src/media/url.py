import base64
import glob
import hashlib
import logging
import os
import threading
import traceback
from configparser import ConfigParser
from io import BytesIO
from typing import Any

import yt_dlp as youtube_dl
from PIL import Image

import util
from constants import tr_cli as tr
from database import SettingsDatabase
from media.item import BaseItem, ValidationFailedError, PreparationFailedError
from util import format_time

log = logging.getLogger("bot")


class URLItem(BaseItem):
    def __init__(self, url: str, temp_folder: str, config: ConfigParser, settings_db: SettingsDatabase):
        super().__init__()
        self.validating_lock = threading.Lock()
        self.temp_folder = temp_folder
        self.config = config
        self.settings_db = settings_db
        self.url = url if url[-1] != "/" else url[:-1]
        self.title = ""
        self.duration = 0
        self.id = self.generate_id(url)
        self.path = temp_folder + self.id
        self.thumbnail = ""
        self.keywords = ""
        self.downloading = False
        self.type = "url"

    @classmethod
    def from_dict(cls, d: dict[str, Any], tmp_folder: str, config: ConfigParser, settings_db: SettingsDatabase) -> 'URLItem':
        instance = cls.__new__(cls)
        BaseItem.__init__(instance)
        instance._load_base_from_dict(d)
        instance.validating_lock = threading.Lock()
        instance.temp_folder = tmp_folder
        instance.config = config
        instance.settings_db = settings_db
        instance.url = d['url']
        instance.thumbnail = d['thumbnail']
        instance.downloading = False
        instance.type = "url"
        return instance

    @staticmethod
    def generate_id(url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def uri(self) -> str:
        return self.path

    def is_ready(self) -> bool:
        if self.downloading or self.ready != 'yes':
            return False
        if self.ready == 'yes' and not os.path.exists(self.path):
            self.log.info(
                "url: music file missed for %s" % self.format_debug_string())
            self.ready = 'validated'
            return False

        return True

    def validate(self) -> bool:
        try:
            self.validating_lock.acquire()
            if self.ready in ['yes', 'validated']:
                return True

            if os.path.exists(self.path):
                self.ready = "yes"
                return True

            # Check if this url is banned
            if self.settings_db.has_option('url_ban', self.url):
                raise ValidationFailedError(tr('url_ban', url=self.url))

            # avoid multiple process validating in the meantime
            info = self._get_info_from_url()

            if not info:
                return False

            # Check if the song is too long and is not whitelisted
            max_duration = self.config.getint('bot', 'max_track_duration') * 60
            if max_duration and \
                    not self.settings_db.has_option('url_whitelist', self.url) and \
                    self.duration > max_duration:
                log.info(
                    "url: " + self.url + " has a duration of " + str(self.duration / 60) + " min -- too long")
                raise ValidationFailedError(tr('too_long', song=self.format_title(),
                                               duration=format_time(self.duration),
                                               max_duration=format_time(max_duration)))
            else:
                self.ready = "validated"
                self.version += 1  # notify wrapper to save me
                return True
        finally:
            self.validating_lock.release()

    # Run in a other thread
    def prepare(self) -> bool:
        if not self.downloading:
            assert self.ready == 'validated'
            return self._download()
        else:
            assert self.ready == 'yes'
            return True

    def _get_info_from_url(self) -> bool | None:
        self.log.info("url: fetching metadata of url %s " % self.url)
        ydl_opts = {
            'noplaylist': True
        }

        cookie = self.config.get('youtube_dl', 'cookie_file')
        if cookie:
            ydl_opts['cookiefile'] = self.config.get('youtube_dl', 'cookie_file')

        user_agent = self.config.get('youtube_dl', 'user_agent')
        if user_agent:
            youtube_dl.utils.std_headers['User-Agent'] = self.config.get('youtube_dl', 'user_agent')

        succeed = False
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            attempts = self.config.getint('bot', 'download_attempts')
            for i in range(attempts):
                try:
                    info = ydl.extract_info(self.url, download=False)
                    self.duration = info['duration']
                    self.title = info['title'].strip()
                    self.keywords = self.title
                    succeed = True
                    return True
                except youtube_dl.utils.DownloadError:
                    pass
                except KeyError:  # info has no 'duration'
                    break

        if not succeed:
            self.ready = 'failed'
            self.log.error("url: error while fetching info from the URL")
            raise ValidationFailedError(tr('unable_download', item=self.format_title()))

    def _download(self) -> bool:
        util.clear_tmp_folder(self.temp_folder, self.config.getint('bot', 'tmp_folder_max_size'))

        self.downloading = True
        base_path = self.temp_folder + self.id
        save_path = base_path

        # Download only if music is not existed
        self.ready = "preparing"

        self.log.info("bot: downloading url (%s) %s " % (self.title, self.url))
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': base_path,
            'noplaylist': True,
            'writethumbnail': True,
            'updatetime': False,
            'verbose': self.config.getboolean('debug', 'youtube_dl'),
            'postprocessors': [{
                'key': 'FFmpegThumbnailsConvertor',
                'format': 'jpg',
                'when': 'before_dl'
            }]
        }

        cookie = self.config.get('youtube_dl', 'cookie_file')
        if cookie:
            ydl_opts['cookiefile'] = self.config.get('youtube_dl', 'cookie_file')

        user_agent = self.config.get('youtube_dl', 'user_agent')
        if user_agent:
            youtube_dl.utils.std_headers['User-Agent'] = self.config.get('youtube_dl', 'user_agent')

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            attempts = self.config.getint('bot', 'download_attempts')
            download_succeed = False
            for i in range(attempts):
                self.log.info("bot: download attempts %d / %d" % (i + 1, attempts))
                try:
                    ydl.extract_info(self.url)
                    download_succeed = True
                    break
                except:
                    error_traceback = traceback.format_exc().split("During")[0]
                    error = error_traceback.rstrip().split("\n")[-1]
                    self.log.error("bot: download failed with error:\n %s" % error)

            if download_succeed:
                self.path = save_path
                self.ready = "yes"
                self.log.info(
                    "bot: finished downloading url (%s) %s, saved to %s." % (self.title, self.url, self.path))
                self.downloading = False
                self._read_thumbnail_from_file(base_path + ".jpg")
                self.version += 1  # notify wrapper to save me
                return True
            else:
                for f in glob.glob(base_path + "*"):
                    os.remove(f)
                self.ready = "failed"
                self.downloading = False
                raise PreparationFailedError(tr('unable_download', item=self.format_title()))

    def _read_thumbnail_from_file(self, path_thumbnail: str) -> None:
        if os.path.isfile(path_thumbnail):
            im = Image.open(path_thumbnail)
            self.thumbnail = self._prepare_thumbnail(im)

    def _prepare_thumbnail(self, im: Image.Image) -> str:
        im.thumbnail((100, 100), Image.LANCZOS)
        buffer = BytesIO()
        im = im.convert('RGB')
        im.save(buffer, format="JPEG")
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def to_dict(self) -> dict[str, Any]:
        dict = super().to_dict()
        dict['type'] = 'url'
        dict['url'] = self.url
        dict['duration'] = self.duration
        dict['path'] = self.path
        dict['title'] = self.title
        dict['thumbnail'] = self.thumbnail

        return dict

    def format_debug_string(self) -> str:
        return "[url] {title} ({url})".format(
            title=self.title,
            url=self.url
        )

    def format_song_string(self, user: str) -> str:
        if self.ready in ['validated', 'yes']:
            return tr("url_item",
                      title=self.title if self.title else "??",
                      url=self.url,
                      user=user)
        return self.url

    def format_current_playing(self, user: str) -> str:
        display = tr("now_playing", item=self.format_song_string(user))

        if self.thumbnail:
            thumbnail_html = '<img width="80" src="data:image/jpge;base64,' + \
                             self.thumbnail + '"/>'
            display += "<br />" + thumbnail_html

        return display

    def format_title(self) -> str:
        return self.title if self.title else self.url

    def display_type(self) -> str:
        return tr("url")
