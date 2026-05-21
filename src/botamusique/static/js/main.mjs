import {
  getColor,
  isOverflown,
  setProgressBar,
  secondsToStr,
} from './lib/util.mjs';
import {limitChars} from './lib/text.mjs';


// ----------------------
// ------ Playlist ------
// ----------------------

const pl_item_template = document.querySelector('.playlist-item-template');
const pl_tag_edit_element = document.querySelector('.playlist-item-edit');

const notag_element = document.querySelector('.library-item-notag');
const tag_element = document.querySelector('.library-item-tag');

const addTagModal = document.getElementById('addTagModal');

const playlist_loading = document.getElementById('playlist-loading');
const playlist_table = document.getElementById('playlist-table');
const playlist_empty = document.getElementById('playlist-empty');
const playlist_expand = document.querySelector('.playlist-expand');

let playlist_items = null;

let playlist_ver = 0;
let playlist_current_index = 0;

let playlist_range_from = 0;
let playlist_range_to = 0;

let last_volume = 0;

let playing = false;

const playPauseBtn = document.getElementById('play-pause-btn');
const playPauseIconPlay = document.getElementById('play-pause-icon-play');
const playPauseIconPause = document.getElementById('play-pause-icon-pause');
const fastForwardBtn = document.getElementById('fast-forward-btn');
const volumeSlider = document.getElementById('volume-slider');

const playModeBtns = {
  'one-shot': document.getElementById('one-shot-mode-btn'),
  'random': document.getElementById('random-mode-btn'),
  'repeat': document.getElementById('repeat-mode-btn'),
  'autoplay': document.getElementById('autoplay-mode-btn'),
};
const playModeIcon = {
  'one-shot': 'list-check',
  'random': 'shuffle',
  'repeat': 'rotate-right',
  'autoplay': 'robot',
};

playPauseBtn.addEventListener('click', togglePlayPause);

fastForwardBtn.addEventListener('click', () => {
  request('post', {action: 'next'});
});

document.getElementById('clear-playlist-btn').addEventListener('click', () => {
  request('post', {action: 'clear'});
});

for (const playMode in playModeBtns) {
  playModeBtns[playMode].addEventListener('click', () => {
    changePlayMode(playMode);
  });
}

function request(_url, _data, refresh = false) {
  const body = new URLSearchParams(_data);
  fetch(_url, {method: 'POST', body})
      .then((r) => {
        if (r.status === 403) {
          location.reload(true);
          return null;
        }
        return r.json();
      })
      .then((data) => {
        if (!data) return;
        if (data.ver !== playlist_ver) {
          checkForPlaylistUpdate();
        }
        updateControls(data.empty, data.play, data.mode, data.volume);
        updatePlayerPlayhead(data.playhead);
      });
  if (refresh) {
    location.reload(true);
  }
}

function addPlaylistItem(item) {
  const item_copy = pl_item_template.cloneNode(true);
  item_copy.id = 'playlist-item-' + item.index;
  item_copy.classList.add('playlist-item');
  item_copy.classList.remove('d-none');

  item_copy.querySelector('.playlist-item-id').value = item.id;
  item_copy.querySelector('.playlist-item-index').innerHTML = item.index + 1;
  item_copy.querySelector('.playlist-item-title').innerHTML = item.title;
  item_copy.querySelector('.playlist-item-artist').innerHTML = item.artist;
  const thumb = item_copy.querySelector('.playlist-item-thumbnail');
  thumb.src = item.thumbnail;
  thumb.alt = limitChars(item.title);
  item_copy.querySelector('.playlist-item-type').innerHTML = item.type;
  item_copy.querySelector('.playlist-item-path').innerHTML = item.path;

  const tags = item_copy.querySelector('.playlist-item-tags');
  tags.innerHTML = '';

  const tag_edit_copy = pl_tag_edit_element.cloneNode(true);
  tag_edit_copy.addEventListener('click', () => {
    addTagModalShow(item.id, item.title, item.tags);
  });
  tags.appendChild(tag_edit_copy);

  if (item.tags.length > 0) {
    item.tags.forEach((tag_tuple) => {
      const tag_copy = tag_element.cloneNode(true);
      tag_copy.innerHTML = tag_tuple[0];
      tag_copy.classList.add('bg-' + tag_tuple[1]);
      tags.appendChild(tag_copy);
    });
  } else {
    tags.appendChild(notag_element.cloneNode(true));
  }

  playlist_table.appendChild(item_copy);
}

function withFade(el, callback) {
  el.style.transition = 'opacity 200ms';
  el.style.opacity = '0';
  setTimeout(() => {
    callback();
    el.style.opacity = '1';
  }, 200);
}

function displayPlaylist(data) {
  withFade(playlist_table, () => {
    playlist_loading.style.display = 'none';
    playlist_table.querySelectorAll('.playlist-item').forEach((el) => el.remove());
    const items = data.items;
    const length = data.length;
    if (items.length === 0) {
      playlist_empty.classList.remove('d-none');
      return;
    }
    playlist_items = {};
    for (const i in items) {
      playlist_items[items[i].index] = items[i];
    }
    const start_from = data.start_from;
    playlist_range_from = start_from;
    playlist_range_to = start_from + items.length - 1;

    if (items.length < length && start_from > 0) {
      let _from = start_from - 5;
      _from = _from > 0 ? _from : 0;
      const _to = start_from - 1;
      if (_to > 0) {
        insertExpandPrompt(_from, start_from + length - 1, _from, _to, length);
      }
    }

    items.forEach((item) => addPlaylistItem(item));

    if (items.length < length && start_from + items.length < length) {
      const _from = start_from + items.length;
      let _to = start_from + items.length - 1 + 10;
      _to = _to < length - 1 ? _to : length - 1;
      if (start_from + items.length < _to) {
        insertExpandPrompt(start_from, _to, _from, _to, length);
      }
    }

    displayActiveItem(data.current_index);
    updatePlayerInfo(playlist_items[data.current_index]);
  });
}

function displayActiveItem(current_index) {
  playlist_table.querySelectorAll('.playlist-item').forEach((el) => el.classList.remove('table-active'));
  const active = document.getElementById('playlist-item-' + current_index);
  if (active) active.classList.add('table-active');
}

function insertExpandPrompt(real_from, real_to, display_from, display_to, total_length) {
  const expand_copy = playlist_expand.cloneNode(true);
  expand_copy.classList.add('playlist-item');
  expand_copy.classList.remove('d-none');
  const range_el = expand_copy.querySelector('.playlist-expand-item-range');
  if (range_el) {
    if (display_from !== display_to) {
      range_el.innerHTML = (display_from + 1) + '~' + (display_to + 1) + ' of ' + total_length + ' items';
    } else {
      range_el.innerHTML = display_from + ' of ' + total_length + ' items';
    }
  }
  expand_copy.addEventListener('click', () => {
    playlist_range_from = real_from;
    playlist_range_to = real_to;
    updatePlaylist();
  });
  playlist_table.appendChild(expand_copy);
}

function updatePlaylist() {
  withFade(playlist_table, () => {
    playlist_empty.classList.add('d-none');
    playlist_loading.style.display = '';
    let params = {};
    if (!(playlist_range_from === 0 && playlist_range_to === 0)) {
      params = {range_from: playlist_range_from, range_to: playlist_range_to};
    }
    const url = 'playlist' + (Object.keys(params).length ? '?' + new URLSearchParams(params) : '');
    fetch(url)
        .then((r) => r.status === 200 ? r.json() : null)
        .then((data) => { if (data) displayPlaylist(data); });
  });
}

function checkForPlaylistUpdate() {
  fetch('post', {method: 'POST', body: new URLSearchParams()})
      .then((r) => {
        if (r.status === 403) { location.reload(true); return null; }
        return r.json();
      })
      .then((data) => {
        if (!data) return;
        if (data.ver !== playlist_ver) {
          playlist_ver = data.ver;
          playlist_range_from = 0;
          playlist_range_to = 0;
          updatePlaylist();
        }
        if (data.current_index !== playlist_current_index) {
          if (data.current_index !== -1) {
            if (data.current_index > playlist_range_to || data.current_index < playlist_range_from) {
              playlist_range_from = 0;
              playlist_range_to = 0;
              updatePlaylist();
            } else {
              playlist_current_index = data.current_index;
              updatePlayerInfo(playlist_items[data.current_index]);
              displayActiveItem(data.current_index);
            }
          }
        }
        updateControls(data.empty, data.play, data.mode, data.volume);
        if (!data.empty) {
          updatePlayerPlayhead(data.playhead);
        }
        if (data.bot_version) {
          document.getElementById('bot-version').textContent = data.bot_version;
        }
      });
}

playlist_table.addEventListener('click', (e) => {
  const playBtn = e.target.closest('.playlist-item-play');
  if (playBtn) {
    const index = Number(playBtn.closest('tr').querySelector('.playlist-item-index').innerHTML) - 1;
    request('post', {'play_music': index});
    return;
  }
  const trashBtn = e.target.closest('.playlist-item-trash');
  if (trashBtn) {
    const index = Number(trashBtn.closest('tr').querySelector('.playlist-item-index').innerHTML) - 1;
    request('post', {'delete_music': index});
  }
});

function updateControls(empty, play, mode, volume) {
  updatePlayerControls(play, empty);
  if (empty) {
    playPauseBtn.disabled = true;
    fastForwardBtn.disabled = true;
  } else {
    playPauseBtn.disabled = false;
    fastForwardBtn.disabled = false;
    if (play) {
      playing = true;
      playPauseIconPlay.classList.add('d-none');
      playPauseIconPause.classList.remove('d-none');
      playPauseBtn.setAttribute('aria-label', 'Pause');
    } else {
      playing = false;
      playPauseIconPause.classList.add('d-none');
      playPauseIconPlay.classList.remove('d-none');
      playPauseBtn.setAttribute('aria-label', 'Play');
    }
  }

  for (const otherMode of Object.values(playModeBtns)) {
    otherMode.classList.remove('active');
  }
  playModeBtns[mode].classList.add('active');

  document.getElementById('modeIndicatorUse').setAttribute(
      'href', 'static/image/icons.svg#icon-' + playModeIcon[mode]);

  if (volume !== last_volume) {
    last_volume = volume;
    volumeSlider.value = Math.max(0, Math.min(1, volume));
  }
}

function togglePlayPause() {
  request('post', {action: playing ? 'pause' : 'resume'});
}

function changePlayMode(mode) {
  request('post', {action: mode});
}


// ---------------------
// ------ Browser ------
// ---------------------

const filters = {
  file: document.getElementById('filter-type-file'),
  url: document.getElementById('filter-type-url'),
  radio: document.getElementById('filter-type-radio'),
};
const filter_dir = document.getElementById('filter-dir');
const filter_keywords = document.getElementById('filter-keywords');

for (const filter in filters) {
  filters[filter].addEventListener('click', (e) => {
    setFilterType(e, filter);
  });
}

function setFilterType(event, type) {
  event.preventDefault();
  if (filters[type].classList.contains('active')) {
    filters[type].classList.remove('active', 'btn-info');
    filters[type].classList.add('btn-primary');
  } else {
    filters[type].classList.remove('btn-primary');
    filters[type].classList.add('active', 'btn-info');
  }
  if (type === 'file') {
    filter_dir.disabled = !filters[type].classList.contains('active');
  }
  updateResults();
}

filter_dir.addEventListener('change', () => updateResults());
filter_keywords.addEventListener('change', () => updateResults());

const item_template = document.getElementById('library-item');
const lib_filter_tag_group = document.getElementById('filter-tags');
const lib_filter_tag_element = document.querySelector('.filter-tag');
const lib_group = document.getElementById('library-group');
const id_element = item_template.querySelector('.library-item-id');
const title_element = item_template.querySelector('.library-item-title');
const artist_element = item_template.querySelector('.library-item-artist');
const thumb_element = item_template.querySelector('.library-item-thumb');
const type_element = item_template.querySelector('.library-item-type');
const path_element = item_template.querySelector('.library-item-path');
const tag_edit_element = item_template.querySelector('.library-item-edit');

function updateLibraryControls() {
  fetch('library/info')
      .then((r) => {
        if (r.status === 403) { location.reload(true); return null; }
        return r.json();
      })
      .then((data) => { if (data) displayLibraryControls(data); });
}

function displayLibraryControls(data) {
  document.getElementById('maxUploadFileSize').value = data.max_upload_file_size;
  const uploadSection = document.getElementById('upload');
  if (data.upload_enabled) {
    document.getElementById('uploadDisabled').value = 'false';
    uploadSection.style.display = '';
  } else {
    document.getElementById('uploadDisabled').value = 'true';
    uploadSection.style.display = 'none';
  }

  if (data.delete_allowed) {
    document.getElementById('deleteAllowed').value = 'true';
  } else {
    document.getElementById('deleteAllowed').value = 'false';
    document.querySelectorAll('.library-delete').forEach((el) => el.remove());
  }

  const dataList = document.getElementById('upload-target-dirs');
  const dirs = Array.from(filter_dir.options).map((o) => o.value);
  if (data.dirs.length > 0) {
    data.dirs.forEach((dir) => {
      if (!dirs.includes(dir)) {
        const opt = document.createElement('option');
        opt.value = dir;
        opt.textContent = dir;
        filter_dir.appendChild(opt);

        const dopt = document.createElement('option');
        dopt.value = dir;
        dataList.appendChild(dopt);
      }
    });
  }

  const tags_dict = {};
  const existing_tags = [];
  document.querySelectorAll('.filter-tag').forEach((tag_el) => {
    tags_dict[tag_el.innerHTML] = tag_el;
    existing_tags.push(tag_el.innerHTML);
  });
  const stale_tags = [...existing_tags];

  if (data.tags.length > 0) {
    for (const tag of data.tags) {
      if (existing_tags.includes(tag)) {
        const idx = stale_tags.indexOf(tag);
        if (idx !== -1) stale_tags.splice(idx, 1);
      } else {
        const tag_copy = lib_filter_tag_element.cloneNode(true);
        tag_copy.innerHTML = tag;
        tag_copy.classList.add('bg-' + getColor(tag));
        lib_filter_tag_group.appendChild(tag_copy);
        tag_copy.addEventListener('click', () => {
          tag_copy.classList.toggle('tag-clicked');
          tag_copy.classList.toggle('tag-unclicked');
          updateResults();
        });
      }
    }
    for (const tag of stale_tags) {
      tags_dict[tag].remove();
    }
  } else {
    document.querySelectorAll('.filter-tag').forEach((el) => el.remove());
  }
}

function addResultItem(item) {
  id_element.value = item.id;
  title_element.innerHTML = item.title;
  artist_element.innerHTML = item.artist ? ('- ' + item.artist) : '';
  thumb_element.src = item.thumb;
  thumb_element.alt = limitChars(item.title);
  type_element.innerHTML = '[' + item.type + ']';
  path_element.innerHTML = item.path;

  const item_copy = item_template.cloneNode(true);
  item_copy.classList.add('library-item-active');
  item_copy.removeAttribute('id');

  const tags = item_copy.querySelector('.library-item-tags');
  tags.innerHTML = '';

  const tag_edit_copy = tag_edit_element.cloneNode(true);
  tag_edit_copy.addEventListener('click', () => {
    addTagModalShow(item.id, item.title, item.tags);
  });
  tags.appendChild(tag_edit_copy);

  if (item.tags.length > 0) {
    item.tags.forEach((tag_tuple) => {
      const tag_copy = tag_element.cloneNode(true);
      tag_copy.innerHTML = tag_tuple[0];
      tag_copy.classList.add('bg-' + tag_tuple[1]);
      tags.appendChild(tag_copy);
    });
  } else {
    tags.appendChild(notag_element.cloneNode(true));
  }

  item_copy.querySelector('.library-item-play').addEventListener('click', () => {
    const id = item_copy.querySelector('.library-item-id').value;
    request('post', {'add_item_at_once': id});
  });

  item_copy.querySelector('.library-item-trash').addEventListener('click', () => {
    const id = item_copy.querySelector('.library-item-id').value;
    request('post', {'delete_item_from_library': id});
    updateResults(active_page);
  });

  item_copy.querySelector('.library-item-download').addEventListener('click', () => {
    downloadId(item_copy.querySelector('.library-item-id').value);
  });

  item_copy.querySelector('.library-item-add-next').addEventListener('click', () => {
    request('post', {'add_item_next': item_copy.querySelector('.library-item-id').value});
  });

  item_copy.querySelector('.library-item-add-bottom').addEventListener('click', () => {
    request('post', {'add_item_bottom': item_copy.querySelector('.library-item-id').value});
  });

  lib_group.appendChild(item_copy);
  item_copy.style.display = '';
}

function getFilters(dest_page = 1) {
  const tags_list = [];
  document.querySelectorAll('.tag-clicked').forEach((tag) => {
    tags_list.push(tag.innerHTML);
  });

  const filter_types = [];
  for (const filter in filters) {
    if (filters[filter].classList.contains('active')) {
      filter_types.push(filter);
    }
  }

  return {
    type: filter_types.join(','),
    dir: filter_dir.value,
    tags: tags_list.join(','),
    keywords: filter_keywords.value,
    page: String(dest_page),
  };
}

const lib_loading = document.getElementById('library-item-loading');
const lib_empty = document.getElementById('library-item-empty');
let active_page = 1;

function updateResults(dest_page = 1) {
  active_page = dest_page;
  const data = getFilters(dest_page);
  data.action = 'query';

  withFade(lib_group, () => {
    const body = new URLSearchParams(data);
    fetch('library', {method: 'POST', body})
        .then((r) => {
          if (r.status === 403) { location.reload(true); return null; }
          return r.json();
        })
        .then((data) => { if (data) processResults(data); });

    lib_group.querySelectorAll('.library-item-active').forEach((el) => el.remove());
    lib_empty.style.display = 'none';
    lib_loading.style.display = '';
  });

  updateLibraryControls();
}

const download_form = document.getElementById('download-form');

document.getElementById('add-to-playlist-btn').addEventListener('click', () => {
  const data = getFilters();
  data.action = 'add';
  fetch('library', {method: 'POST', body: new URLSearchParams(data)});
  checkForPlaylistUpdate();
});

document.getElementById('library-delete-btn').addEventListener('click', () => {
  const data = getFilters();
  data.action = 'delete';
  fetch('library', {method: 'POST', body: new URLSearchParams(data)});
  document.getElementById('deleteWarningModal').close();
  checkForPlaylistUpdate();
  updateResults();
});

document.getElementById('library-download-btn').addEventListener('click', () => {
  const cond = getFilters();
  download_form.querySelector('input[name="type"]').value = cond.type;
  download_form.querySelector('input[name="dir"]').value = cond.dir;
  download_form.querySelector('input[name="tags"]').value = cond.tags;
  download_form.querySelector('input[name="keywords"]').value = cond.keywords;
  download_form.submit();
});

document.getElementById('library-rescan-btn').addEventListener('click', () => {
  request('post', {action: 'rescan'});
  updateResults();
});

document.getElementById('delete-all-btn').addEventListener('click', () => {
  document.getElementById('deleteWarningModal').showModal();
});

document.getElementById('deleteWarningCloseBtn').addEventListener('click', () => {
  document.getElementById('deleteWarningModal').close();
});

function downloadId(id) {
  download_form.querySelector('input[name="id"]').value = id;
  download_form.querySelector('input[name="type"]').value = '';
  download_form.querySelector('input[name="dir"]').value = '';
  download_form.querySelector('input[name="tags"]').value = '';
  download_form.querySelector('input[name="keywords"]').value = '';
  download_form.submit();
}

const page_ul = document.getElementById('library-page-ul');
const page_li_template = document.querySelector('.library-page-li');
const page_no_template = document.querySelector('.library-page-no');

function processResults(data) {
  withFade(lib_group, () => {
    lib_loading.style.display = 'none';
    const total_pages = data.total_pages;
    const active_page = data.active_page;
    const items = data.items;
    if (items.length === 0) {
      lib_empty.style.display = '';
      page_ul.innerHTML = '';
      return;
    }
    items.forEach((item) => addResultItem(item));

    page_ul.innerHTML = '';

    let i = 1;
    if (total_pages > 25) {
      i = (active_page - 12 >= 1) ? active_page - 12 : 1;
      const _i = total_pages - 23;
      i = (i < _i) ? i : _i;

      const li = page_li_template.cloneNode(true);
      const a = page_no_template.cloneNode(true);
      a.innerHTML = '&laquo;';
      a.addEventListener('click', () => updateResults(1));
      li.appendChild(a);
      page_ul.appendChild(li);
    }

    const limit = i + 24;
    for (; i <= total_pages && i <= limit; i++) {
      const li = page_li_template.cloneNode(true);
      const a = page_no_template.cloneNode(true);
      a.textContent = i.toString();
      if (active_page === i) {
        li.classList.add('active');
      } else {
        const page_num = i;
        a.addEventListener('click', () => updateResults(page_num));
      }
      li.appendChild(a);
      page_ul.appendChild(li);
    }

    if (limit < total_pages) {
      const li = page_li_template.cloneNode(true);
      const a = page_no_template.cloneNode(true);
      a.innerHTML = '&raquo;';
      a.addEventListener('click', () => updateResults(total_pages));
      li.appendChild(a);
      page_ul.appendChild(li);
    }
  });
}

// ---------------------
// ------ Tagging ------
// ---------------------

const add_tag_modal_title = document.getElementById('addTagModalTitle');
const add_tag_modal_item_id = document.getElementById('addTagModalItemId');
const add_tag_modal_tags = document.getElementById('addTagModalTags');
const add_tag_modal_input = document.getElementById('addTagModalInput');
const modal_tag = document.querySelector('.modal-tag');

function makeTagElement(text) {
  const tag_copy = modal_tag.cloneNode(true);
  tag_copy.querySelector('.modal-tag-text').innerHTML = text;
  tag_copy.querySelector('.modal-tag-remove').addEventListener('click', (e) => {
    e.currentTarget.parentElement.remove();
  });
  tag_copy.style.display = '';
  return tag_copy;
}

function addTagModalShow(_id, _title, _tag_tuples) {
  add_tag_modal_title.innerHTML = _title;
  add_tag_modal_item_id.value = _id;
  add_tag_modal_tags.innerHTML = '';
  _tag_tuples.forEach((tag_tuple) => {
    add_tag_modal_tags.appendChild(makeTagElement(tag_tuple[0]));
  });
  addTagModal.showModal();
}

document.getElementById('addTagModalClose').addEventListener('click', () => addTagModal.close());
document.getElementById('addTagModalCloseBtn').addEventListener('click', () => addTagModal.close());

document.getElementById('addTagModalAddBtn').addEventListener('click', () => {
  const new_tags = add_tag_modal_input.value.split(',').map((s) => s.trim()).filter(Boolean);
  new_tags.forEach((tag) => {
    add_tag_modal_tags.appendChild(makeTagElement(tag));
  });
  add_tag_modal_input.value = '';
});

document.getElementById('addTagModalSubmit').addEventListener('click', () => {
  const tags = [];
  add_tag_modal_tags.querySelectorAll('.modal-tag-text').forEach((el) => {
    if (el.innerHTML) tags.push(el.innerHTML);
  });

  fetch('library', {
    method: 'POST',
    body: new URLSearchParams({
      action: 'edit_tags',
      id: add_tag_modal_item_id.value,
      tags: tags.join(','),
    }),
  }).then(() => updateResults(active_page));

  addTagModal.close();
});

// ---------------------
// ------- Volume ------
// ---------------------

const volumePopoverBtn = document.getElementById('volume-popover-btn');
const volumePopoverDiv = document.getElementById('volume-popover');
let volume_popover_show = false;
let volume_update_timer;

volumePopoverBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  volume_popover_show = !volume_popover_show;
  if (volume_popover_show) {
    volumePopoverDiv.setAttribute('data-show', '');
  } else {
    volumePopoverDiv.removeAttribute('data-show');
  }
});

volumePopoverDiv.addEventListener('click', (e) => e.stopPropagation());

document.addEventListener('click', () => {
  if (volume_popover_show) {
    volumePopoverDiv.removeAttribute('data-show');
    volume_popover_show = false;
  }
});

volumeSlider.addEventListener('change', () => {
  window.clearTimeout(volume_update_timer);
  volume_update_timer = window.setTimeout(() => {
    request('post', {action: 'volume_set_value', new_volume: volumeSlider.value});
  }, 500);
});

document.getElementById('volume-down-btn').addEventListener('click', () => {
  request('post', {action: 'volume_down'});
});

document.getElementById('volume-up-btn').addEventListener('click', () => {
  request('post', {action: 'volume_up'});
});

// ---------------------
// ------- Upload ------
// ---------------------

const uploadModal = document.getElementById('uploadModal');

const uploadFileInput = document.getElementById('uploadSelectFile');
const uploadModalItem = document.getElementsByClassName('uploadItem')[0];
const uploadModalList = document.getElementById('uploadModalList');
const uploadTargetDir = document.getElementById('uploadTargetDir');
const uploadSuccessAlert = document.getElementById('uploadSuccessAlert');
const uploadSubmitBtn = document.getElementById('uploadSubmit');
const uploadCancelBtn = document.getElementById('uploadCancel');
const uploadCloseBtn = document.getElementById('uploadClose');

const maxFileSize = parseInt(document.getElementById('maxUploadFileSize').value);

let filesToProceed = [];
const filesProgressItem = {};
let runningXHR = null;

uploadSubmitBtn.addEventListener('click', uploadStart);
uploadCancelBtn.addEventListener('click', uploadCancel);
uploadCloseBtn.addEventListener('click', () => uploadModal.close());

function uploadStart() {
  uploadModalList.textContent = '';
  uploadSuccessAlert.style.display = 'none';
  uploadCancelBtn.style.display = 'none';
  uploadCloseBtn.style.display = 'block';
  const file_list = uploadFileInput.files;

  if (file_list.length) {
    for (const file of file_list) {
      generateUploadProgressItem(file);
      if (file.size > maxFileSize) {
        setUploadError(file.name, 'File too large!');
        continue;
      } else if (!(file.type.includes('audio') || file.type.includes('video'))) {
        setUploadError(file.name, 'Unsupported media format!');
        continue;
      }
      filesToProceed.push(file);
    }

    uploadFileInput.value = '';
    uploadModal.showModal();
    uploadNextFile();
  }
}

function setUploadError(filename, error) {
  const file_progress_item = filesProgressItem[filename];
  file_progress_item.title.classList.add('text-muted');
  file_progress_item.error.innerHTML += 'Error: ' + error;
  setProgressBar(file_progress_item.progress, 1);
  file_progress_item.progress.classList.add('bg-danger');
  file_progress_item.progress.classList.remove('progress-bar-animated');
}

function generateUploadProgressItem(file) {
  const item_clone = uploadModalItem.cloneNode(true);
  const title = item_clone.querySelector('.uploadItemTitle');
  title.innerHTML = file.name;
  const error = item_clone.querySelector('.uploadItemError');
  const progress = item_clone.querySelector('.uploadProgress');
  item_clone.style.display = 'block';

  const item = {title, error, progress};
  filesProgressItem[file.name] = item;
  uploadModalList.appendChild(item_clone);
  return item;
}

function uploadNextFile() {
  uploadCancelBtn.style.display = 'block';
  uploadCloseBtn.style.display = 'none';

  const req = new XMLHttpRequest();
  const file = filesToProceed.shift();
  const file_progress_item = filesProgressItem[file.name];

  req.addEventListener('load', function() {
    if (this.status === 200) {
      setProgressBar(file_progress_item.progress, 1);
      file_progress_item.progress.classList.add('bg-success');
      file_progress_item.progress.classList.remove('progress-bar-animated');
    } else if (this.status === 400 || this.status === 403) {
      setUploadError(file.name, 'Illegal request!');
    } else if (this.status === 500) {
      setUploadError(file.name, 'Server internal error!');
    } else {
      setUploadError(file.name, this.responseText || 'Unknown error!');
    }

    if (filesToProceed.length) {
      uploadNextFile();
    } else {
      uploadSuccessAlert.style.display = 'block';
      runningXHR = null;
      uploadCancelBtn.style.display = 'none';
      uploadCloseBtn.style.display = 'block';
      request('post', {action: 'rescan'});
      updateResults();
    }
  });

  req.upload.addEventListener('progress', (e) => {
    if (e.lengthComputable) {
      const percent = e.loaded / e.total;
      setProgressBar(file_progress_item.progress, percent, Math.floor(percent * 100) + '%');
    }
  });

  const form = new FormData();
  form.append('file', file);
  form.append('targetdir', uploadTargetDir.value);

  req.open('POST', 'upload');
  req.withCredentials = true;
  req.send(form);

  file_progress_item.progress.classList.add('progress-bar-striped', 'progress-bar-animated');
  runningXHR = req;
}

function uploadCancel() {
  if (!confirm('Cancel the upload?')) return;
  uploadModal.close();
  if (runningXHR) runningXHR.abort();
  filesToProceed = [];
  uploadFileInput.value = '';
  request('post', {action: 'rescan'});
  updateResults();
}

// ---------------------
// --- Play-mode menu --
// ---------------------

const playModeDropdownBtn = document.getElementById('play-mode');
const playModeDropdownMenu = playModeDropdownBtn.nextElementSibling;
const playModeDropdown = playModeDropdownBtn.closest('.dropdown');

playModeDropdownBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  const open = playModeDropdownMenu.classList.toggle('show');
  playModeDropdown.classList.toggle('show', open);
  playModeDropdownBtn.setAttribute('aria-expanded', String(open));
});

document.addEventListener('click', () => {
  playModeDropdownMenu.classList.remove('show');
  playModeDropdown.classList.remove('show');
  playModeDropdownBtn.setAttribute('aria-expanded', 'false');
});

//
// URLS & Radio
//

const musicUrlInput = document.getElementById('music-url-input');
const radioUrlInput = document.getElementById('radio-url-input');

document.getElementById('add-music-url').querySelector('button').addEventListener('click', () => {
  request('post', {add_url: musicUrlInput.value});
  musicUrlInput.value = '';
});

document.getElementById('add-radio-url').querySelector('button').addEventListener('click', () => {
  request('post', {add_radio: radioUrlInput.value});
  radioUrlInput.value = '';
});

// ---------------------
// ------  Player ------
// ---------------------

const playerToastEl = document.getElementById('playerToast');
const playerArtwork = document.getElementById('playerArtwork');
const playerArtworkIdle = document.getElementById('playerArtworkIdle');
const playerTitle = document.getElementById('playerTitle');
const playerArtist = document.getElementById('playerArtist');
const playerBar = document.getElementById('playerBar');
const playerBarBox = document.getElementById('playerBarBox');
const playerPlayBtn = document.getElementById('playerPlayBtn');
const playerPauseBtn = document.getElementById('playerPauseBtn');
const playerSkipBtn = document.getElementById('playerSkipBtn');

let currentPlayingItem = null;

playerPlayBtn.addEventListener('click', () => request('post', {action: 'resume'}));
playerPauseBtn.addEventListener('click', () => request('post', {action: 'pause'}));
playerSkipBtn.addEventListener('click', () => request('post', {action: 'next'}));

document.getElementById('player-toast').addEventListener('click', () => {
  playerToastEl.classList.add('show');
});

playerToastEl.querySelector('.btn-close').addEventListener('click', () => {
  playerToastEl.classList.remove('show');
});

function playerSetIdle() {
  playerArtwork.style.display = 'none';
  playerArtworkIdle.style.display = 'block';
  playerTitle.textContent = '-- IDLE --';
  playerArtist.textContent = '';
  setProgressBar(playerBar, 0);
  clearInterval(playhead_timer);
}

function updatePlayerInfo(item) {
  if (!item) {
    playerSetIdle();
    return;
  }
  playerArtwork.style.display = 'block';
  playerArtworkIdle.style.display = 'none';
  currentPlayingItem = item;
  playerTitle.textContent = item.title;
  playerArtist.textContent = item.artist;
  playerArtwork.setAttribute('src', item.thumbnail);
  playerArtwork.setAttribute('alt', limitChars(item.title));

  playerTitle.classList.toggle('scrolling', isOverflown(playerTitle));
  playerArtist.classList.toggle('scrolling', isOverflown(playerArtist));
}

function updatePlayerControls(play, empty) {
  if (empty) {
    playerSetIdle();
    playerPlayBtn.disabled = true;
    playerPauseBtn.disabled = true;
    playerSkipBtn.disabled = true;
  } else {
    playerPlayBtn.disabled = false;
    playerPauseBtn.disabled = false;
    playerSkipBtn.disabled = false;
  }
  if (play) {
    playerPlayBtn.style.display = 'none';
    playerPauseBtn.style.display = 'block';
  } else {
    playerPlayBtn.style.display = 'block';
    playerPauseBtn.style.display = 'none';
  }
}

let playhead_timer;
let player_playhead_position;
let playhead_dragging = false;

function updatePlayerPlayhead(playhead) {
  if (!currentPlayingItem || playhead_dragging) return;
  if (currentPlayingItem.duration !== 0 || currentPlayingItem.duration < playhead) {
    playerBar.classList.remove('progress-bar-animated');
    clearInterval(playhead_timer);
    player_playhead_position = playhead;
    setProgressBar(playerBar, player_playhead_position / currentPlayingItem.duration, secondsToStr(player_playhead_position));
    if (playing) {
      playhead_timer = setInterval(() => {
        player_playhead_position += 0.3;
        setProgressBar(playerBar, player_playhead_position / currentPlayingItem.duration, secondsToStr(player_playhead_position));
      }, 300);
    }
  } else {
    playerBar.classList.toggle('progress-bar-animated', playing);
    setProgressBar(playerBar, 1);
  }
}

playerBarBox.addEventListener('mousedown', () => {
  if (currentPlayingItem && currentPlayingItem.duration > 0) {
    playerBarBox.addEventListener('mousemove', playheadDragged);
    clearInterval(playhead_timer);
    playhead_dragging = true;
  }
});

playerBarBox.addEventListener('mouseup', (event) => {
  playerBarBox.removeEventListener('mousemove', playheadDragged);
  const percent = (event.clientX - playerBarBox.getBoundingClientRect().x) / playerBarBox.clientWidth;
  request('post', {move_playhead: percent * currentPlayingItem.duration});
  playhead_dragging = false;
});

function playheadDragged(event) {
  const percent = (event.clientX - playerBarBox.getBoundingClientRect().x) / playerBarBox.clientWidth;
  setProgressBar(playerBar, percent, secondsToStr(percent * currentPlayingItem.duration));
}

// -----------------------
// ----- Application -----
// -----------------------

document.addEventListener('DOMContentLoaded', () => {
  updateResults();
  updatePlaylist();
  setInterval(checkForPlaylistUpdate, 3000);
});
