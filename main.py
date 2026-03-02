import argparse
import configparser
import logging
import os
import sys
from argparse import ArgumentParser, Namespace
from configparser import ConfigParser
from logging import Logger, Handler
from logging.handlers import RotatingFileHandler
from threading import Thread
from typing import Any

import command
import constants
import media.playlist
import util
from database import SettingsDatabase, MusicDatabase, DatabaseMigration
from media.cache import MusicCache
from mumbleBot import MumbleBot, start_web_interface


def main():
    # Set defaults from environment variables
    env_config: str = os.getenv('BAM_CONFIG_FILE', 'configuration.ini')
    env_db: str | None = os.getenv('BAM_DB')
    env_music_db: str | None = os.getenv('BAM_MUSIC_DB')
    env_verbose: object = os.getenv('BAM_VERBOSE') is not None
    env_host: str | None = os.getenv('BAM_MUMBLE_SERVER')
    env_password: str | None = os.getenv('BAM_MUMBLE_PASSWORD')
    env_port: int | None = int(os.getenv('BAM_MUMBLE_PORT')) if os.getenv('BAM_MUMBLE_PORT') else None
    env_user: str | None = os.getenv('BAM_USER')
    env_tokens: str | None = os.getenv('BAM_TOKENS')
    env_channel: str | None = os.getenv('BAM_CHANNEL')
    env_certificate: str | None = os.getenv('BAM_CERTIFICATE')
    env_bandwidth: int | None = int(os.getenv('BAM_BANDWIDTH')) if os.getenv('BAM_BANDWIDTH') else None

    supported_languages: list[Any] = util.get_supported_language()

    parser: ArgumentParser = argparse.ArgumentParser(
        description='Bot for playing music on Mumble')

    # General arguments
    parser.add_argument("--config", dest='config', type=str,
                        help='Load configuration from this file. Default: configuration.ini')
    parser.add_argument("--db", dest='db', type=str,
                        default=None, help='Settings database file')
    parser.add_argument("--music-db", dest='music_db', type=str,
                        default=None, help='Music library database file')
    parser.add_argument("--lang", dest='lang', type=str,
                        help='Preferred language. Support ' + ", ".join(supported_languages))

    parser.add_argument("-q", "--quiet", dest="quiet",
                        action="store_true", help="Only Error logs")
    parser.add_argument("-v", "--verbose", dest="verbose",
                        action="store_true", help="Show debug log")

    # Mumble arguments
    parser.add_argument("-s", "--server", dest="host",
                        type=str, help="Hostname of the Mumble server")
    parser.add_argument("-u", "--user", dest="user",
                        type=str, help="Username for the bot")
    parser.add_argument("-P", "--password", dest="password",
                        type=str, help="Server password, if required")
    parser.add_argument("-T", "--tokens", dest="tokens",
                        type=str,
                        help="Server tokens to enter a channel, if required (multiple entries separated with comma ','")
    parser.add_argument("-p", "--port", dest="port",
                        type=int, help="Port for the Mumble server")
    parser.add_argument("-c", "--channel", dest="channel",
                        type=str, help="Default channel for the bot")
    parser.add_argument("-C", "--cert", dest="certificate",
                        type=str, default=None, help="Certificate file")
    parser.add_argument("-b", "--bandwidth", dest="bandwidth",
                        type=int, help="Bandwidth used by the bot")

    # Update parser defaults with environment variables
    parser.set_defaults(
        config=env_config,
        db=env_db,
        music_db=env_music_db,
        verbose=env_verbose,
        host=env_host,
        password=env_password,
        port=env_port,
        user=env_user,
        tokens=env_tokens,
        channel=env_channel,
        certificate=env_certificate,
        bandwidth=env_bandwidth
    )

    args: Namespace = parser.parse_args()

    print("=" * 60)
    print("Final configuration values:")
    print("=" * 60)
    print(f"Config file:      {args.config}")
    print(f"Database:         {args.db}")
    print(f"Music database:   {args.music_db}")
    print(f"Language:         {args.lang}")
    print(f"Verbose mode:     {args.verbose}")
    print(f"Quiet mode:       {args.quiet}")
    print(f"Server:           {args.host}")
    print(f"Port:             {args.port}")
    print(f"User:             {args.user}")
    print(f"Password:         {'***' if args.password else None}")
    print(f"Tokens:           {args.tokens}")
    print(f"Channel:          {args.channel}")
    print(f"Certificate:      {args.certificate}")
    print(f"Bandwidth:        {args.bandwidth}")
    print("=" * 60)

    # ======================
    #     Load Config
    # ======================

    config: ConfigParser = configparser.ConfigParser(interpolation=None, allow_no_value=True)
    default_config: ConfigParser = configparser.ConfigParser(interpolation=None, allow_no_value=True)

    if len(default_config.read(
            util.solve_filepath('configuration.default.ini'),
            encoding='utf-8')) == 0:
        logging.error("Could not read default configuration file 'configuration.default.ini', please check"
                      "your installation.")
        sys.exit()

    if len(config.read(
            [util.solve_filepath('configuration.default.ini'), util.solve_filepath(args.config)],
            encoding='utf-8')) == 0:
        logging.error(f'Could not read configuration from file "{args.config}"')
        sys.exit()

    extra_configs: list[tuple[str, str]] = util.check_extra_config(config, default_config)
    if extra_configs:
        extra_str = ", ".join([f"'[{k}] {v}'" for (k, v) in extra_configs])
        logging.error(f'Unexpected config items {extra_str} defined in your config file. '
                      f'This is likely caused by a recent change in the names of config items, '
                      f'or the removal of obsolete config items. Please refer to the changelog.')
        sys.exit()

    # ======================
    #     Setup Logger
    # ======================

    bot_logger: Logger = logging.getLogger("bot")
    bot_logger.setLevel(logging.INFO)
    bot_logger.propagate = False

    if args.verbose:
        bot_logger.setLevel(logging.DEBUG)
        bot_logger.debug("Starting in DEBUG loglevel")
    elif args.quiet:
        bot_logger.setLevel(logging.ERROR)
        bot_logger.error("Starting in ERROR loglevel")

    logfile = util.solve_filepath(config.get('bot', 'logfile').strip())
    if logfile:
        print(f"Redirecting stdout and stderr to log file: {logfile}")
        # Rotate after 10KB, leave 3 old logs
        handler: Handler = RotatingFileHandler(logfile, mode='a', maxBytes=10240, backupCount=3)
        if config.getboolean("bot", "redirect_stderr"):
            sys.stderr = util.LoggerIOWrapper(bot_logger, logging.INFO, fallback_io_buffer=sys.stderr.buffer)
    else:
        handler: Handler = logging.StreamHandler()
    util.set_logging_formatter(handler, bot_logger.level)

    # replace bot_logger handlers with ours
    for handler in list(bot_logger.handlers):
        if isinstance(handler, logging.StreamHandler):
            bot_logger.removeHandler(handler)
            handler.close()
    bot_logger.addHandler(handler)

    # ======================
    #     Load Database
    # ======================
    if args.user:
        username: str = args.user
    else:
        username: str = config.get("bot", "username")

    sanitized_username: str = "".join([x if x.isalnum() else "_" for x in username])
    settings_db_path = args.db if args.db is not None else util.solve_filepath(
        config.get("bot", "database_path") or f"settings-{sanitized_username}.db")
    music_db_path = args.music_db if args.music_db is not None else util.solve_filepath(
        config.get("bot", "music_database_path"))

    settings_db = SettingsDatabase(settings_db_path)

    if config.get("bot", "save_music_library"):
        music_db = MusicDatabase(music_db_path)
    else:
        music_db = MusicDatabase(":memory:")

    DatabaseMigration(settings_db, music_db).migrate()

    music_folder = util.solve_filepath(config.get('bot', 'music_folder'))
    if not music_folder.endswith(os.sep):
        # The file searching logic assumes that the music folder ends in a /
        music_folder = music_folder + os.sep

    # ======================
    #      Translation
    # ======================

    lang: str = ""
    if args.lang:
        lang = args.lang
    else:
        lang = config.get('bot', 'language')

    if lang not in supported_languages:
        raise KeyError(f"Unsupported language {lang}")
    constants.load_lang(lang)

    # ======================
    #     Prepare Cache
    # ======================
    cache = MusicCache(music_db, settings_db, config, music_folder)

    if config.getboolean("bot", "refresh_cache_on_startup"):
        cache.build_dir_cache()

    # ======================
    #   Load playback mode
    # ======================

    if settings_db.has_option("playlist", "playback_mode"):
        playback_mode: str = settings_db.get('playlist', 'playback_mode')
    else:
        playback_mode: str = config.get('bot', 'playback_mode')

    if playback_mode in ["one-shot", "repeat", "random", "autoplay"]:
        playlist = media.playlist.get_playlist(
            playback_mode, cache, settings_db, music_db, config, send_channel_msg=None)
    else:
        raise KeyError(f"Unknown playback mode '{playback_mode}'")

    # ======================
    #  Create bot instance
    # ======================
    bot = MumbleBot(args, config, settings_db, music_db, cache, playlist, music_folder,
                    settings_db_path, music_db_path)

    # Wire up the playlist's send_channel_msg callback now that bot exists
    playlist.send_channel_msg = bot.send_channel_msg

    command.register_all_commands(bot)

    # load playlist
    if config.getboolean('bot', 'save_playlist'):
        bot_logger.info("bot: load playlist from previous session")
        playlist.load()

    # ============================
    #   Start the web interface
    # ============================
    if config.getboolean("webinterface", "enabled"):
        wi_addr = config.get("webinterface", "listening_addr")
        wi_port = config.getint("webinterface", "listening_port")
        tt = Thread(
            target=start_web_interface, name="WebThread", args=(wi_addr, wi_port, bot))
        tt.daemon = True
        bot_logger.info('Starting web interface on {}:{}'.format(wi_addr, wi_port))
        tt.start()

    # Start the main loop.
    bot.loop()

if __name__ == '__main__':
    main()
