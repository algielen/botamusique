import re
import logging
import struct
import requests
import traceback
import hashlib
from typing import Any

from media.item import BaseItem
from constants import tr_cli as tr

log = logging.getLogger("bot")


def get_radio_server_description(url: str) -> str:
    global log

    log.debug("radio: fetching radio server description")
    p = re.compile('(https?://[^/]*)', re.IGNORECASE)
    res = re.search(p, url)
    base_url = res.group(1)
    url_icecast = base_url + '/status-json.xsl'
    url_shoutcast = base_url + '/stats?json=1'
    try:
        response = requests.head(url_shoutcast, timeout=3)
        if not response.headers.get('content-type', '').startswith(("audio/", "video/")):
            response = requests.get(url_shoutcast, timeout=10)
            data = response.json()
            title_server = data['servertitle']
            return title_server
            # logging.info("TITLE FOUND SHOUTCAST: " + title_server)
    except (requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            requests.exceptions.ReadTimeout,
            requests.exceptions.Timeout):
        error_traceback = traceback.format_exc()
        error = error_traceback.rstrip().split("\n")[-1]
        log.debug("radio: unsuccessful attempts on fetching radio description (shoutcast): " + error)
    except ValueError:
        return url

    try:
        response = requests.head(url_shoutcast, timeout=3)
        if not response.headers.get('content-type', '').startswith(("audio/", "video/")):
            response = requests.get(url_icecast, timeout=10)
            data = response.json()
            source = data['icestats']['source']
            if type(source) is list:
                source = source[0]
            title_server = source['server_name']
            if 'server_description' in source:
                title_server += ' - ' + source['server_description']
            # logging.info("TITLE FOUND ICECAST: " + title_server)
            return title_server
    except (requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            requests.exceptions.ReadTimeout,
            requests.exceptions.Timeout):
        error_traceback = traceback.format_exc()
        error = error_traceback.rstrip().split("\n")[-1]
        log.debug("radio: unsuccessful attempts on fetching radio description (icecast): " + error)

    return url


def get_radio_title(url: str) -> str:
    global log

    log.debug("radio: fetching radio server description")
    try:
        r = requests.get(url, headers={'Icy-MetaData': '1'}, stream=True, timeout=10)
        icy_metaint_header = int(r.headers['icy-metaint'])
        r.raw.read(icy_metaint_header)

        metadata_length = struct.unpack('B', r.raw.read(1))[0] * 16  # length byte
        metadata = r.raw.read(metadata_length).rstrip(b'\0')
        logging.info(metadata)
        # extract title from the metadata
        m = re.search(br"StreamTitle='([^']*)';", metadata)
        if m:
            title = m.group(1)
            if title:
                return title.decode()
    except (requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            requests.exceptions.ReadTimeout,
            requests.exceptions.Timeout,
            KeyError):
        log.debug("radio: unsuccessful attempts on fetching radio title (icy)")
    return url


class RadioItem(BaseItem):
    def __init__(self, url: str, name: str = ""):
        super().__init__()
        self.url = url
        self.title = name if name else get_radio_server_description(url)
        self.id = self.generate_id(url)
        self.type = "radio"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'RadioItem':
        instance = cls.__new__(cls)
        BaseItem.__init__(instance)
        instance._load_base_from_dict(d)
        instance.url = d['url']
        instance.title = d['title']
        instance.type = "radio"
        return instance

    @staticmethod
    def generate_id(url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def validate(self) -> bool:
        self.version += 1  # 0 -> 1, notify the wrapper to save me when validate() is visited the first time
        return True

    def is_ready(self) -> bool:
        return True

    def uri(self) -> str:
        return self.url

    def to_dict(self) -> dict[str, Any]:
        dict = super().to_dict()
        dict['url'] = self.url
        dict['title'] = self.title

        return dict

    def format_debug_string(self) -> str:
        return "[radio] {name} ({url})".format(
            name=self.title,
            url=self.url
        )

    def format_song_string(self, user: str) -> str:
        return tr("radio_item",
                  url=self.url,
                  title=get_radio_title(self.url),  # the title of current song
                  name=self.title,  # the title of radio station
                  user=user
                  )

    def format_current_playing(self, user: str) -> str:
        return tr("now_playing", item=self.format_song_string(user))

    def format_title(self) -> str:
        return self.title if self.title else self.url

    def display_type(self) -> str:
        return tr("radio")
