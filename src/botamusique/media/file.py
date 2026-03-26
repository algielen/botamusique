import base64
import hashlib
import os
from io import BytesIO
from typing import Any

import mutagen
from PIL import Image

from botamusique import util
from botamusique.constants import tr_cli as tr
from botamusique.media.item import BaseItem, ValidationFailedError

'''
type : file
    id
    path
    title
    artist
    duration
    thumbnail
    user
'''


class FileItem(BaseItem):
    def __init__(self, path: str, music_folder: str):
        super().__init__()
        self.type = "file"
        self.path = path
        self.title = ""
        self.artist = ""
        self.thumbnail = None
        self.music_folder = music_folder
        self.id = self.generate_id(path)
        if os.path.exists(self.uri()):
            self._get_info_from_tag()
            self.ready = "yes"
            self.duration = util.get_media_duration(self.uri())
        self.keywords = self.title + " " + self.artist

    @classmethod
    def from_dict(cls, d: dict[str, Any], music_folder: str) -> 'FileItem':
        instance = cls.__new__(cls)
        BaseItem.__init__(instance)
        instance._load_base_from_dict(d)
        instance.type = "file"
        instance.artist = d['artist']
        instance.thumbnail = d['thumbnail']
        instance.music_folder = music_folder
        try:
            instance.validate()
        except ValidationFailedError:
            instance.ready = "failed"
        return instance

    @staticmethod
    def generate_id(path: str) -> str:
        return hashlib.md5(path.encode()).hexdigest()

    def uri(self) -> str:
        return self.music_folder + self.path if self.path[0] != "/" else self.path

    def is_ready(self) -> bool:
        return True

    def validate(self) -> bool:
        if not os.path.exists(self.uri()):
            self.log.info(
                "file: music file missed for %s" % self.format_debug_string())
            raise ValidationFailedError(tr('file_missed', file=self.path))

        if self.duration == 0:
            self.duration = util.get_media_duration(self.uri())
            self.version += 1  # 0 -> 1, notify the wrapper to save me
        self.ready = "yes"
        return True

    def _get_info_from_tag(self) -> None:
        path, file_name_ext = os.path.split(self.uri())
        file_name, ext = os.path.splitext(file_name_ext)

        assert path is not None and file_name is not None

        try:
            im = None
            path_thumbnail = os.path.join(path, file_name + ".jpg")

            if os.path.isfile(path_thumbnail):
                im = Image.open(path_thumbnail)
            else:
                path_thumbnail = os.path.join(path, "cover.jpg")
                if os.path.isfile(path_thumbnail):
                    im = Image.open(path_thumbnail)

            if ext == ".mp3":
                tags = mutagen.File(self.uri())
                if 'TIT2' in tags:
                    self.title = tags['TIT2'].text[0]
                if 'TPE1' in tags:  # artist
                    self.artist = tags['TPE1'].text[0]

                if im is None:
                    if "APIC:" in tags:
                        im = Image.open(BytesIO(tags["APIC:"].data))

            elif ext == ".m4a" or ext == ".m4b" or ext == ".mp4" or ext == ".m4p":
                tags = mutagen.File(self.uri())
                if '©nam' in tags:
                    self.title = tags['©nam'][0]
                if '©ART' in tags:  # artist
                    self.artist = tags['©ART'][0]

                if im is None:
                    if "covr" in tags:
                        im = Image.open(BytesIO(tags["covr"][0]))

            elif ext == ".opus":
                tags = mutagen.File(self.uri())
                if 'title' in tags:
                    self.title = tags['title'][0]
                if 'artist' in tags:
                    self.artist = tags['artist'][0]

                if im is None:
                    if 'metadata_block_picture' in tags:
                        pic_as_base64 = tags['metadata_block_picture'][0]
                        as_flac_picture = mutagen.flac.Picture(base64.b64decode(pic_as_base64))
                        im = Image.open(BytesIO(as_flac_picture.data))

            elif ext == ".flac":
                tags = mutagen.File(self.uri())
                if 'title' in tags:
                    self.title = tags['title'][0]
                if 'artist' in tags:
                    self.artist = tags['artist'][0]

                if im is None:
                    for flac_picture in tags.pictures:
                        if flac_picture.type == 3:
                            im = Image.open(BytesIO(flac_picture.data))

            if im:
                self.thumbnail = self._prepare_thumbnail(im)
        except:
            pass

        if not self.title:
            self.title = file_name

    @staticmethod
    def _prepare_thumbnail(im: Image.Image) -> str:
        im.thumbnail((100, 100), Image.LANCZOS)
        buffer = BytesIO()
        im = im.convert('RGB')
        im.save(buffer, format="JPEG")
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def to_dict(self) -> dict[str, Any]:
        dict = super().to_dict()
        dict['type'] = 'file'
        dict['path'] = self.path
        dict['title'] = self.title
        dict['artist'] = self.artist
        dict['thumbnail'] = self.thumbnail
        return dict

    def format_debug_string(self) -> str:
        return "[file] {descrip} ({path})".format(
            descrip=self.format_title(),
            path=self.path
        )

    def format_song_string(self, user: str) -> str:
        return tr("file_item",
                  title=self.title,
                  artist=self.artist if self.artist else '??',
                  user=user
                  )

    def format_current_playing(self, user: str) -> str:
        display = tr("now_playing", item=self.format_song_string(user))
        if self.thumbnail:
            thumbnail_html = '<img width="80" src="data:image/jpge;base64,' + \
                             self.thumbnail + '"/>'
            display += "<br />" + thumbnail_html

        return display

    def format_title(self) -> str:
        title = self.title if self.title else self.path
        if self.artist:
            return self.artist + " - " + title
        else:
            return title

    def display_type(self) -> str:
        return tr("file")
