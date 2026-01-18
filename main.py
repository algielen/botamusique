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
import variables as var
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
    var.config = config

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

    if args.verbose:
        bot_logger.setLevel(logging.DEBUG)
        bot_logger.debug("Starting in DEBUG loglevel")
    elif args.quiet:
        bot_logger.setLevel(logging.ERROR)
        bot_logger.error("Starting in ERROR loglevel")

    logfile = util.solve_filepath(var.config.get('bot', 'logfile').strip())
    if logfile:
        print(f"Redirecting stdout and stderr to log file: {logfile}")
        # Rotate after 10KB, leave 3 old logs
        handler: Handler = RotatingFileHandler(logfile, mode='a', maxBytes=10240, backupCount=3)
        if var.config.getboolean("bot", "redirect_stderr"):
            sys.stderr = util.LoggerIOWrapper(bot_logger, logging.INFO, fallback_io_buffer=sys.stderr.buffer)
    else:
        handler: Handler = logging.StreamHandler()

    util.set_logging_formatter(handler, bot_logger.level)
    bot_logger.addHandler(handler)
    logging.getLogger("root").addHandler(handler)
    var.bot_logger = bot_logger

    # ======================
    #     Load Database
    # ======================
    if args.user:
        username: str = args.user
    else:
        username: str = var.config.get("bot", "username")

    sanitized_username: str = "".join([x if x.isalnum() else "_" for x in username])
    var.settings_db_path = args.db if args.db is not None else util.solve_filepath(
        config.get("bot", "database_path") or f"settings-{sanitized_username}.db")
    var.music_db_path = args.music_db if args.music_db is not None else util.solve_filepath(
        config.get("bot", "music_database_path"))

    var.db = SettingsDatabase(var.settings_db_path)

    if var.config.get("bot", "save_music_library"):
        var.music_db = MusicDatabase(var.music_db_path)
    else:
        var.music_db = MusicDatabase(":memory:")

    DatabaseMigration(var.db, var.music_db).migrate()

    var.music_folder = util.solve_filepath(var.config.get('bot', 'music_folder'))
    if not var.music_folder.endswith(os.sep):
        # The file searching logic assumes that the music folder ends in a /
        var.music_folder = var.music_folder + os.sep
    var.tmp_folder = util.solve_filepath(var.config.get('bot', 'tmp_folder'))

    # ======================
    #      Translation
    # ======================

    lang: str = ""
    if args.lang:
        lang = args.lang
    else:
        lang = var.config.get('bot', 'language')

    if lang not in supported_languages:
        raise KeyError(f"Unsupported language {lang}")
    var.language = lang
    constants.load_lang(lang)

    # ======================
    #     Prepare Cache
    # ======================
    var.cache = MusicCache(var.music_db)

    if var.config.getboolean("bot", "refresh_cache_on_startup"):
        var.cache.build_dir_cache()

    # ======================
    #   Load playback mode
    # ======================

    if var.db.has_option("playlist", "playback_mode"):
        playback_mode: str = var.db.get('playlist', 'playback_mode')
    else:
        playback_mode: str = var.config.get('bot', 'playback_mode')

    if playback_mode in ["one-shot", "repeat", "random", "autoplay"]:
        var.playlist = media.playlist.get_playlist(playback_mode)
    else:
        raise KeyError(f"Unknown playback mode '{playback_mode}'")

    # ======================
    #  Create bot instance
    # ======================
    var.bot = MumbleBot(args)
    command.register_all_commands(var.bot)

    # load playlist
    if var.config.getboolean('bot', 'save_playlist'):
        var.bot_logger.info("bot: load playlist from previous session")
        var.playlist.load()

    # ============================
    #   Start the web interface
    # ============================
    if var.config.getboolean("webinterface", "enabled"):
        wi_addr = var.config.get("webinterface", "listening_addr")
        wi_port = var.config.getint("webinterface", "listening_port")
        tt = Thread(
            target=start_web_interface, name="WebThread", args=(wi_addr, wi_port))
        tt.daemon = True
        bot_logger.info('Starting web interface on {}:{}'.format(wi_addr, wi_port))
        tt.start()

    # Start the main loop.
    var.bot.loop()

if __name__ == '__main__':
    main()