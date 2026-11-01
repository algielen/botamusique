#!/usr/bin/python3

import json
import logging
import math
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import (
    Blueprint,
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
)
from werkzeug.utils import secure_filename

from botamusique import media, util
from botamusique.database import Condition
from botamusique.localfiles import (
    LocalFiles,
    UnsafePath,
    cache_location,
    relative_parts,
)
from botamusique.media.file import FileItem
from botamusique.media.item import BaseItem
from botamusique.media.radio import RadioItem
from botamusique.media.url import URLItem
from botamusique.media.url_from_playlist import PlaylistURLItem
from botamusique.mumbleBot import MumbleBot

_bot: MumbleBot | None = None

def set_bot(bot: MumbleBot) -> None:
    global _bot
    _bot = bot


class ReverseProxied(object):
    """Wrap the application in this middleware and configure the
    front-end server to add these headers, to let you quietly bind
    this to a URL other than / and to an HTTP scheme that is
    different than what is used locally.

    In nginx:
    location /myprefix {
        proxy_pass http://192.168.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Scheme $scheme;
        proxy_set_header X-Script-Name /myprefix;
        }

    :param app: the WSGI application
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    def __call__(self, environ: dict[str, Any], start_response: Any) -> Any:
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]

        scheme = environ.get('HTTP_X_SCHEME', '')
        if scheme:
            environ['wsgi.url_scheme'] = scheme
        real_ip = environ.get('HTTP_X_REAL_IP', '')
        if real_ip:
            environ['REMOTE_ADDR'] = real_ip
        return self.app(environ, start_response)


root_dir = Path(__file__).parent
web: Flask | None = None
bp = Blueprint('main', __name__)
log = logging.getLogger("bot")
user = 'Remote Control'


def init_app() -> None:
    global web
    web = Flask(
        __name__,
        template_folder=root_dir.joinpath("web"),
        static_folder=root_dir.joinpath("static"),
    )
    web.register_blueprint(bp)


def init_proxy() -> None:
    global web
    if _bot.is_proxied:
        web.wsgi_app = ReverseProxied(web.wsgi_app)


# https://stackoverflow.com/questions/29725217/password-protect-one-webpage-in-flask-app


def check_auth(username: str, password: str) -> bool:
    """This function is called to check if a username /
    password combination is valid.
    """

    conf_user = _bot.config.get("webinterface", "user")
    conf_password = _bot.config.get("webinterface", "password")
    # Require both to be configured: otherwise an empty configured password
    # would let a client authenticate with empty Basic-auth credentials.
    if conf_user and conf_password and username == conf_user and password == conf_password:
        return True

    web_users = json.loads(_bot.db.get("privilege", "web_access", fallback='[]'))
    if username in web_users:
        user_dict = json.loads(_bot.db.get("user", username, fallback='{}'))
        if 'password' in user_dict and 'salt' in user_dict and \
                util.verify_password(password, user_dict['password'], user_dict['salt']):
            return True

    return False


def authenticate() -> Response:
    """Sends a 401 response that enables basic auth"""
    global log
    return Response('Could not verify your access level for that URL.\n'
                    'You have to login with proper credentials', 401,
                    {'WWW-Authenticate': 'Basic realm="Login Required"'})


bad_access_count = {}
banned_ip = []


def requires_auth(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        global log, user, bad_access_count, banned_ip

        if request.remote_addr in banned_ip:
            abort(403)

        auth_method = _bot.config.get("webinterface", "auth_method")

        if auth_method == 'password':
            auth = request.authorization
            if auth:
                user = auth.username
                if not check_auth(auth.username, auth.password):
                    if request.remote_addr in bad_access_count:
                        bad_access_count[request.remote_addr] += 1
                        log.info(f"web: failed login attempt, user: {auth.username}, from ip {request.remote_addr}."
                                 f"{bad_access_count[request.remote_addr]} attempts.")
                        if bad_access_count[request.remote_addr] > _bot.config.getint("webinterface", "max_attempts",
                                                                                     fallback=10):
                            banned_ip.append(request.remote_addr)
                            log.info(f"web: access banned for {request.remote_addr}")
                    else:
                        bad_access_count[request.remote_addr] = 1
                        log.info(f"web: failed login attempt, user: {auth.username}, from ip {request.remote_addr}.")
                    return authenticate()
            else:
                return authenticate()
        if auth_method == 'token':
            ttl = _bot.config.getint("webinterface", "token_ttl", fallback=604800)

            if 'user' in session and 'token' not in request.args:
                # Resume an existing browser session, but only while it still
                # matches the user's current token hash and that token is
                # within its TTL. Matching the hash ensures a regenerated or
                # revoked token (which overwrites the stored hash) kills any
                # session minted from the old one, instead of the signed
                # cookie outliving the token it was minted from.
                sess_info = _bot.db.get("user", session['user'], fallback=None)
                user_dict = json.loads(sess_info) if sess_info else {}
                if user_dict and session.get('token') == user_dict.get('token') \
                        and not util.is_token_expired(user_dict, ttl):
                    user = session['user']
                    return f(*args, **kwargs)
                session.pop('user', None)
                session.pop('token', None)

            elif 'token' in request.args:
                token = request.args.get('token')
                token_hash = util.hash_token(token)
                token_user = _bot.db.get("web_token", token_hash, fallback=None)
                if token_user is not None:
                    user_info = _bot.db.get("user", token_user, fallback=None)
                    user_dict = json.loads(user_info) if user_info else {}
                    if not util.is_token_expired(user_dict, ttl):
                        user = token_user
                        user_dict['IP'] = request.remote_addr
                        _bot.db.set("user", token_user, json.dumps(user_dict))

                        log.debug(
                            f"web: new user access, token validated for the user: {token_user}, from ip {request.remote_addr}.")
                        session['token'] = token_hash
                        session['user'] = token_user
                        return f(*args, **kwargs)

                    # Expired token: revoke it so the stale link stops working.
                    _bot.db.remove_option("web_token", token_hash)
                    log.info(f"web: expired token for user {token_user} from ip {request.remote_addr}.")

                # A token was supplied but is invalid or expired: count it as a
                # bad attempt and ban the IP after too many. Requests that carry
                # no token at all simply get the "need token" page below.
                if request.remote_addr in bad_access_count:
                    bad_access_count[request.remote_addr] += 1
                    log.info(f"web: bad token from ip {request.remote_addr}, "
                             f"{bad_access_count[request.remote_addr]} attempts.")
                    if bad_access_count[request.remote_addr] > _bot.config.getint("webinterface", "max_attempts"):
                        banned_ip.append(request.remote_addr)
                        log.info(f"web: access banned for {request.remote_addr}")
                else:
                    bad_access_count[request.remote_addr] = 1
                    log.info(f"web: bad token from ip {request.remote_addr}.")

            return render_template(f'need_token.{_bot.config.get('bot', 'language')}.html',
                                   name=_bot.config.get('bot', 'username'),
                                   command=f"{_bot.config.get('commands', 'command_symbol')[0]}"
                                           f"{_bot.config.get('commands', 'requests_webinterface_access')}")

        return f(*args, **kwargs)

    return decorated


def tag_color(tag: str) -> str:
    num = hash(tag) % 8
    if num == 0:
        return "primary"
    elif num == 1:
        return "secondary"
    elif num == 2:
        return "success"
    elif num == 3:
        return "danger"
    elif num == 4:
        return "warning"
    elif num == 5:
        return "info"
    elif num == 6:
        return "light"
    elif num == 7:
        return "dark"


def build_tags_color_lookup() -> dict[str, str]:
    color_lookup = {}
    for tag in _bot.music_db.query_all_tags():
        color_lookup[tag] = tag_color(tag)

    return color_lookup


def get_all_dirs() -> list[str]:
    return list(local_folders())


def local_folders() -> dict[str, str]:
    """Resolve public folder labels through server-owned storage metadata."""
    paths = set(LocalFiles(_bot.music_folder).folders().values())
    registry = json.loads(_bot.db.get('library', 'folders', fallback='{}'))
    aliases = {path: label for label, path in registry.items()}
    return {aliases.get(path, path): path for path in sorted(paths)}


def delete_local_item(item) -> None:
    if item.type == 'file':
        try:
            LocalFiles(_bot.music_folder).delete(item.path)
        except FileNotFoundError:
            pass
        except (OSError, UnsafePath):
            abort(403)


def validate_item_storage(item) -> None:
    try:
        if item.type == 'file':
            store, name = LocalFiles(_bot.music_folder), item.path
        elif item.type == 'url':
            store, name = cache_location(_bot.cache.tmp_folder, item.path)
        else:
            return
        with store.open(name):
            pass
    except FileNotFoundError:
        # A stale library record can still be removed without touching storage.
        pass
    except (OSError, UnsafePath):
        abort(403)


def media_source(item):
    if item['type'] == 'file':
        return LocalFiles(_bot.music_folder).open(item['path'])
    if item['type'] == 'url':
        store, name = cache_location(_bot.cache.tmp_folder, item['path'])
        return store.open(name)
    abort(404)


@bp.route("/", methods=["GET"])
@requires_auth
def index() -> str:
    return open(
        root_dir.joinpath(
            f"web/index.{_bot.config.get('bot', 'language')}.html"
        ),
        "r",
    ).read()


@bp.route("/playlist", methods=['GET'])
@requires_auth
def playlist() -> Response:
    if len(_bot.playlist) == 0:
        return jsonify({
            'items': [],
            'current_index': -1,
            'length': 0,
            'start_from': 0
        })

    DEFAULT_DISPLAY_COUNT = 11
    _from = 0
    _to = 10

    if 'range_from' in request.args and 'range_to' in request.args:
        _from = int(request.args['range_from'])
        _to = int(request.args['range_to'])
    else:
        if _bot.playlist.current_index - int(DEFAULT_DISPLAY_COUNT / 2) > 0:
            _from = _bot.playlist.current_index - int(DEFAULT_DISPLAY_COUNT / 2)
            _to = _from - 1 + DEFAULT_DISPLAY_COUNT

    tags_color_lookup = build_tags_color_lookup()  # TODO: cached this?
    items = []

    for index, item_wrapper in enumerate(_bot.playlist[_from: _to + 1]):
        tag_tuples = []
        for tag in item_wrapper.item().tags:
            tag_tuples.append([tag, tags_color_lookup[tag]])

        item: BaseItem = item_wrapper.item()

        title = item.format_title()
        artist = "??"
        path = ""
        duration = 0
        if isinstance(item, FileItem):
            path = item.path
            if item.artist:
                artist = item.artist
            duration = item.duration
        elif isinstance(item, URLItem):
            path = f" <a href=\"{item.url}\"><i>{item.url}</i></a>"
            duration = item.duration
        elif isinstance(item, PlaylistURLItem):
            path = f" <a href=\"{item.url}\"><i>{item.url}</i></a>"
            artist = f" <a href=\"{item.playlist_url}\"><i>{item.playlist_title}</i></a>"
            duration = item.duration
        elif isinstance(item, RadioItem):
            path = f" <a href=\"{item.url}\"><i>{item.url}</i></a>"

        thumb = ""
        if item.type != 'radio' and item.thumbnail:
            thumb = f"data:image/PNG;base64,{item.thumbnail}"
        else:
            thumb = "static/image/unknown-album.png"

        items.append({
            'index': _from + index,
            'id': item.id,
            'type': item.display_type(),
            'path': path,
            'title': title,
            'artist': artist,
            'thumbnail': thumb,
            'tags': tag_tuples,
            'duration': duration
        })

    return jsonify({
        'items': items,
        'current_index': _bot.playlist.current_index,
        'length': len(_bot.playlist),
        'start_from': _from
    })


def status() -> Response:
    bot_version = _bot.get_version()
    if len(_bot.playlist) > 0:
        return jsonify({'ver': _bot.playlist.version,
                        'current_index': _bot.playlist.current_index,
                        'empty': False,
                        'play': not _bot.is_pause,
                        'mode': _bot.playlist.mode,
                        'volume': _bot.volume_helper.plain_volume_set,
                        'playhead': _bot.playhead,
                        'bot_version': bot_version,
                        })

    else:
        return jsonify({'ver': _bot.playlist.version,
                        'current_index': _bot.playlist.current_index,
                        'empty': True,
                        'play': not _bot.is_pause,
                        'mode': _bot.playlist.mode,
                        'volume': _bot.volume_helper.plain_volume_set,
                        'playhead': 0,
                        'bot_version': bot_version,
                        })


@bp.route("/post", methods=['POST'])
@requires_auth
def post() -> Response:
    global log

    payload = request.get_json() if request.is_json else request.form
    if payload:
        log.debug("web: Post request from %s (user: %s): %s" % (request.remote_addr, user, str(payload)))

        if 'add_item_at_once' in payload:
            music_wrapper = _bot.cache.get_cached_wrapper_by_id(payload['add_item_at_once'], user)
            if music_wrapper:
                _bot.playlist.insert(_bot.playlist.current_index + 1, music_wrapper)
                log.info('web: add to playlist(next): ' + music_wrapper.format_debug_string())
                if not _bot.is_pause:
                    _bot.interrupt()
                else:
                    _bot.is_pause = False
            else:
                abort(404)

        if 'add_item_bottom' in payload:
            music_wrapper = _bot.cache.get_cached_wrapper_by_id(payload['add_item_bottom'], user)

            if music_wrapper:
                _bot.playlist.append(music_wrapper)
                log.info('web: add to playlist(bottom): ' + music_wrapper.format_debug_string())
            else:
                abort(404)

        elif 'add_item_next' in payload:
            music_wrapper = _bot.cache.get_cached_wrapper_by_id(payload['add_item_next'], user)
            if music_wrapper:
                _bot.playlist.insert(_bot.playlist.current_index + 1, music_wrapper)
                log.info('web: add to playlist(next): ' + music_wrapper.format_debug_string())
            else:
                abort(404)

        elif 'add_url' in payload:
            music_wrapper = _bot.cache.get_cached_wrapper_from_scrap(type='url', url=payload['add_url'], user=user)
            _bot.playlist.append(music_wrapper)

            log.info("web: add to playlist: " + music_wrapper.format_debug_string())
            if len(_bot.playlist) == 2:
                # If I am the second item on the playlist. (I am the next one!)
                _bot.async_download_next()

        elif 'add_radio' in payload:
            url = payload['add_radio']
            music_wrapper = _bot.cache.get_cached_wrapper_from_scrap(type='radio', url=url, user=user)
            _bot.playlist.append(music_wrapper)

            log.info("cmd: add to playlist: " + music_wrapper.format_debug_string())

        elif 'delete_music' in payload:
            music_wrapper = _bot.playlist[int(payload['delete_music'])]
            log.info("web: delete from playlist: " + music_wrapper.format_debug_string())

            if len(_bot.playlist) >= int(payload['delete_music']):
                index = int(payload['delete_music'])

                if index == _bot.playlist.current_index:
                    _bot.playlist.remove(index)

                    if index < len(_bot.playlist):
                        if not _bot.is_pause:
                            _bot.interrupt()
                            _bot.playlist.current_index -= 1
                            # then the bot will move to next item

                    else:  # if item deleted is the last item of the queue
                        _bot.playlist.current_index -= 1
                        if not _bot.is_pause:
                            _bot.interrupt()
                else:
                    _bot.playlist.remove(index)

        elif 'play_music' in payload:
            music_wrapper = _bot.playlist[int(payload['play_music'])]
            log.info("web: jump to: " + music_wrapper.format_debug_string())

            if len(_bot.playlist) >= int(payload['play_music']):
                _bot.play(int(payload['play_music']))
                time.sleep(0.1)
        elif 'move_playhead' in payload:
            if float(payload['move_playhead']) < _bot.playlist.current_item().item().duration:
                log.info(f"web: move playhead to {float(payload['move_playhead'])} s.")
                _bot.play(_bot.playlist.current_index, float(payload['move_playhead']))

        elif 'delete_item_from_library' in payload:
            _id = payload['delete_item_from_library']
            if not _bot.config.getboolean('bot', 'delete_allowed'):
                abort(403)
            item = _bot.cache.get_item_by_id(_id)
            if item is None:
                abort(404)
            validate_item_storage(item)
            delete_local_item(item)
            _bot.playlist.remove_by_id(_id)

            _bot.cache.free_and_delete(_id)
            time.sleep(0.1)

        elif 'add_tag' in payload:
            music_wrappers = _bot.cache.get_cached_wrappers_by_tags([payload['add_tag']], user)
            for music_wrapper in music_wrappers:
                log.info("cmd: add to playlist: " + music_wrapper.format_debug_string())
            _bot.playlist.extend(music_wrappers)

        elif 'action' in payload:
            action = payload['action']
            if action == "random":
                if _bot.playlist.mode != "random":
                    _bot.playlist = media.playlist.get_playlist("random", _bot.cache, _bot.db, _bot.music_db, _bot.config, _bot.send_channel_msg, _bot.playlist)
                else:
                    _bot.playlist.randomize()
                _bot.interrupt()
                _bot.db.set('playlist', 'playback_mode', "random")
                log.info("web: playback mode changed to random.")
            if action == "one-shot":
                _bot.playlist = media.playlist.get_playlist("one-shot", _bot.cache, _bot.db, _bot.music_db, _bot.config, _bot.send_channel_msg, _bot.playlist)
                _bot.db.set('playlist', 'playback_mode', "one-shot")
                log.info("web: playback mode changed to one-shot.")
            if action == "repeat":
                _bot.playlist = media.playlist.get_playlist("repeat", _bot.cache, _bot.db, _bot.music_db, _bot.config, _bot.send_channel_msg, _bot.playlist)
                _bot.db.set('playlist', 'playback_mode', "repeat")
                log.info("web: playback mode changed to repeat.")
            if action == "autoplay":
                _bot.playlist = media.playlist.get_playlist("autoplay", _bot.cache, _bot.db, _bot.music_db, _bot.config, _bot.send_channel_msg, _bot.playlist)
                _bot.db.set('playlist', 'playback_mode', "autoplay")
                log.info("web: playback mode changed to autoplay.")
            if action == "rescan":
                _bot.cache.build_dir_cache()
                _bot.music_db.manage_special_tags()
                log.info("web: Local file cache refreshed.")
            elif action == "stop":
                if _bot.config.getboolean("bot", "clear_when_stop_in_oneshot") \
                        and _bot.playlist.mode == 'one-shot':
                    _bot.clear()
                else:
                    _bot.stop()
            elif action == "next":
                if not _bot.is_pause:
                    _bot.interrupt()
                else:
                    _bot.playlist.next()
                    _bot.wait_for_ready = True
            elif action == "pause":
                _bot.pause()
            elif action == "resume":
                _bot.resume()
            elif action == "clear":
                _bot.clear()
            elif action == "volume_up":
                if _bot.volume_helper.plain_volume_set + 0.03 < 1.0:
                    _bot.volume_helper.set_volume(_bot.volume_helper.plain_volume_set + 0.03)
                else:
                    _bot.volume_helper.set_volume(1.0)
                _bot.db.set('bot', 'volume', str(_bot.volume_helper.plain_volume_set))
                log.info("web: volume up to %d" % (_bot.volume_helper.plain_volume_set * 100))
            elif action == "volume_down":
                if _bot.volume_helper.plain_volume_set - 0.03 > 0:
                    _bot.volume_helper.set_volume(_bot.unconverted_volume - 0.03)
                else:
                    _bot.volume_helper.set_volume(1.0)
                _bot.db.set('bot', 'volume', str(_bot.volume_helper.plain_volume_set))
                log.info("web: volume down to %d" % (_bot.volume_helper.plain_volume_set * 100))
            elif action == "volume_set_value":
                if 'new_volume' in payload:
                    if float(payload['new_volume']) > 1:
                        _bot.volume_helper.set_volume(1.0)
                    elif float(payload['new_volume']) < 0:
                        _bot.volume_helper.set_volume(0)
                    else:
                        # value for new volume is between 0 and 1, round to two decimal digits
                        _bot.volume_helper.set_volume(round(float(payload['new_volume']), 2))

                    _bot.db.set('bot', 'volume', str(_bot.volume_helper.plain_volume_set))
                    log.info("web: volume set to %d" % (_bot.volume_helper.plain_volume_set * 100))

    return status()


def build_library_query_condition(form: dict[str, Any]) -> Condition:
    try:
        condition = Condition()

        types = form['type'].split(",")
        sub_cond = Condition()
        for type in types:
            sub_cond.or_equal("type", type)
        condition.and_sub_condition(sub_cond)

        if form['type'] == 'file':
            folder = local_folders().get(form['dir'])
            if folder is None:
                abort(403)
            if folder == ".":
                folder = ""
            if not folder.endswith('/') and folder:
                folder += '/'
            condition.and_like('path', folder + '%')

        tags = form['tags'].split(",")
        for tag in tags:
            if tag:
                condition.and_like("tags", f"%{tag},%", case_sensitive=False)

        _keywords = form['keywords'].split(" ")
        keywords = []
        for kw in _keywords:
            if kw:
                keywords.append(kw)

        for keyword in keywords:
            condition.and_like("keywords", f"%{keyword}%", case_sensitive=False)

        condition.order_by('create_at', desc=True)

        return condition
    except KeyError:
        abort(400)


@bp.route("/library/info", methods=['GET'])
@requires_auth
def library_info() -> Response:
    global log

    while _bot.cache.dir_lock.locked():
        time.sleep(0.1)

    tags = _bot.music_db.query_all_tags()
    max_upload_file_size = util.parse_file_size(_bot.config.get("webinterface", "max_upload_file_size"))

    return jsonify(dict(
        dirs=get_all_dirs(),
        upload_enabled=_bot.config.getboolean("webinterface", "upload_enabled") or _bot.is_admin(user),
        delete_allowed=_bot.config.getboolean("bot", "delete_allowed") or _bot.is_admin(user),
        tags=tags,
        max_upload_file_size=max_upload_file_size
    ))


@bp.route("/library", methods=['POST'])
@requires_auth
def library() -> Response:
    global log
    ITEM_PER_PAGE = 10

    payload = request.form if request.form else request.json
    if payload:
        log.debug("web: Post request from %s (user: %s): %s" % (request.remote_addr, user, str(payload)))

        if payload['action'] in ['add', 'query', 'delete']:
            condition = build_library_query_condition(payload)

            total_count = 0
            try:
                total_count = _bot.music_db.query_music_count(condition)
            except sqlite3.OperationalError:
                pass

            if not total_count:
                return jsonify({
                    'items': [],
                    'total_pages': 0,
                    'active_page': 0
                })

            if payload['action'] == 'add':
                items = _bot.cache.dicts_to_items(_bot.music_db.query_music(condition))
                music_wrappers = []
                for item in items:
                    music_wrapper = _bot.cache.get_cached_wrapper(item, user)
                    music_wrappers.append(music_wrapper)

                    log.info("cmd: add to playlist: " + music_wrapper.format_debug_string())

                _bot.playlist.extend(music_wrappers)

                return redirect("./", code=302)
            elif payload['action'] == 'delete':
                if _bot.config.getboolean("bot", "delete_allowed"):
                    items = _bot.cache.dicts_to_items(_bot.music_db.query_music(condition))
                    # Validate the entire batch before changing files or library state.
                    for item in items:
                        validate_item_storage(item)
                    for item in items:
                        delete_local_item(item)
                        _bot.playlist.remove_by_id(item.id)
                        _bot.cache.free_and_delete(item.id)

                    time.sleep(0.1)
                    return redirect("./", code=302)
                else:
                    abort(403)
            else:
                page_count = math.ceil(total_count / ITEM_PER_PAGE)

                current_page = int(payload['page']) if 'page' in payload else 1
                if current_page <= page_count:
                    condition.offset((current_page - 1) * ITEM_PER_PAGE)
                else:
                    current_page = 1

                condition.limit(ITEM_PER_PAGE)
                items = _bot.cache.dicts_to_items(_bot.music_db.query_music(condition))

                results = []
                for item in items:
                    result = {'id': item.id, 'title': item.title, 'type': item.display_type(),
                              'tags': [(tag, tag_color(tag)) for tag in item.tags]}
                    if item.type != 'radio' and item.thumbnail:
                        result['thumb'] = f"data:image/PNG;base64,{item.thumbnail}"
                    else:
                        result['thumb'] = "static/image/unknown-album.png"

                    if item.type == 'file':
                        result['path'] = item.path
                        result['artist'] = item.artist
                    else:
                        result['path'] = item.url
                        result['artist'] = "??"

                    results.append(result)

                return jsonify({
                    'items': results,
                    'total_pages': page_count,
                    'active_page': current_page
                })
        elif payload['action'] == 'edit_tags':
            tags = list(dict.fromkeys(payload['tags'].split(",")))  # remove duplicated items
            if payload['id'] in _bot.cache:
                music_wrapper = _bot.cache.get_cached_wrapper_by_id(payload['id'], user)
                music_wrapper.clear_tags()
                music_wrapper.add_tags(tags)
                _bot.playlist.version += 1
            else:
                item = _bot.music_db.query_music_by_id(payload['id'])
                item['tags'] = tags
                _bot.music_db.insert_music(item)
            return redirect("./", code=302)

    else:
        abort(400)


@bp.route('/upload', methods=["POST"])
@requires_auth
def upload() -> tuple[str, int]:
    global log

    if not _bot.config.getboolean("webinterface", "upload_enabled"):
        abort(403)

    file = request.files['file']
    if not file:
        abort(400)

    # The original name is display metadata; storage uses a generated name.
    original_name = (file.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
    if not original_name.strip():
        abort(400)

    if not ("audio" in file.mimetype or "video" in file.mimetype):
        return 'Unsupported media type!', 415

    label = request.form.get('targetdir', '').strip() or 'Uploads'
    store = LocalFiles(_bot.music_folder)
    try:
        # Serialize with rescans and other uploads: partially written files must
        # not be indexed, and folder-label registrations must not overwrite peers.
        with _bot.cache.dir_lock:
            choices = local_folders()
            directory = choices.get(label)
            if directory is None:
                # A new folder label is data, never a path. Nested user paths are forbidden.
                if len(relative_parts(label)) != 1 or len(label) > 128:
                    abort(400)
                directory = 'uploads/' + uuid.uuid4().hex
            extension = Path(original_name).suffix.lower()
            if extension not in {'.mp3', '.mp4', '.m4a', '.m4b', '.m4p', '.ogg', '.opus', '.flac', '.wav', '.webm', '.aac'}:
                extension = '.media'
            relative = directory + '/' + uuid.uuid4().hex + extension if directory != '.' else uuid.uuid4().hex + extension
            with store.open(relative, create=True) as output:
                try:
                    file.save(output)
                except BaseException:
                    output.close()
                    store.delete(relative)
                    raise
            registry = json.loads(_bot.db.get('library', 'folders', fallback='{}'))
            registry[label] = directory
            _bot.db.set('library', 'folders', json.dumps(registry))
            item = FileItem(relative, _bot.music_folder)
            item.title = request.form.get('name', '').strip()[:256] or Path(original_name).stem
            item.keywords = item.title + ' ' + item.artist
            _bot.music_db.insert_music(item.to_dict())
    except FileExistsError:
        return 'File existed!', 409
    except UnsafePath:
        abort(403)
    except OSError:
        log.exception('web: local file upload failed')
        abort(403)

    return '', 200


@bp.route('/download', methods=["GET"])
@requires_auth
def download() -> Response:
    global log

    try:
        if request.args.get('id'):
            rows = _bot.music_db.query_music(Condition().and_equal('id', request.args['id']))
            if not rows:
                abort(404)
            item = rows[0]
            source = media_source(item)
            name = secure_filename(item['title']) or 'music'
            name += Path(item['path']).suffix
            try:
                response = send_file(source, as_attachment=True, download_name=name)
            except BaseException:
                source.close()
                raise
        else:
            rows = _bot.music_db.query_music(build_library_query_condition(request.args))
            source = tempfile.TemporaryFile()
            try:
                with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for item in rows:
                        if item['type'] not in ('file', 'url'):
                            continue
                        name = (secure_filename(item['title']) or 'music') + '-' + item['id'][:8] + Path(item['path']).suffix
                        with media_source(item) as media_input, archive.open(name, 'w') as output:
                            shutil.copyfileobj(media_input, output)
                source.seek(0)
                response = send_file(source, as_attachment=True, download_name='music.zip')
            except BaseException:
                source.close()
                raise
        response.call_on_close(source.close)
        return response
    except (OSError, UnsafePath):
        abort(403)


if __name__ == '__main__':
    web.run(port=8181, host="127.0.0.1")
