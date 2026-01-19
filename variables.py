from logging import Logger

import database
import media.cache
import media.playlist
import mumbleBot
# we have to be very careful not to cause a recursive import loop
# main --> command --> constants --> variables --> mumbleBot --> constants
# this requires specific import ordering(!)
# otherwise use untyped bot and comment out "import mumbleBot":
#bot = None

# TODO delete these global variables

bot: mumbleBot.MumbleBot | None = None
playlist: media.playlist.BasePlaylist | None = None
cache: media.cache.MusicCache | None = None

user: str = ""
is_proxied: bool = False

settings_db_path = None
music_db_path = None
db = None
music_db: database.MusicDatabase | None = None
config: database.SettingsDatabase | None = None

bot_logger: Logger | None = None

music_folder: str = ""
tmp_folder: str = ""

language: str = ""
