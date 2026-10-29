// Run with: node --test tests/test_web_text.mjs
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../src/botamusique/static/js/main.mjs', import.meta.url), 'utf8');

// Exercise the actual UI functions without starting polling or requiring a browser.
function loadFunction(name, globals) {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0);
  const end = source.indexOf('\n}', start) + 2;
  const context = vm.createContext(globals);
  vm.runInContext(source.slice(start, end), context);
  return context[name];
}

function element() {
  const children = new Map();
  return {
    textContent: '',
    style: {},
    classList: {add() {}, remove() {}},
    addEventListener() {},
    querySelector(selector) {
      if (!children.has(selector)) children.set(selector, element());
      return children.get(selector);
    },
    get innerHTML() { throw new Error('HTML serialization is unsafe for plain text'); },
    set innerHTML(_) { throw new Error('Untrusted text must not be parsed as HTML'); },
  };
}

const payload = '<img src=x onerror=alert(1)> & <b>music</b>';

test('tag labels preserve HTML-looking characters as literal text', () => {
  const clone = element();
  const makeTagElement = loadFunction('makeTagElement', {
    modal_tag: {cloneNode: () => clone},
  });
  assert.equal(makeTagElement(payload).querySelector('.modal-tag-text').textContent, payload);
});

test('upload filenames and server error bodies are rendered as text', () => {
  const clone = element();
  const filesProgressItem = {};
  const generate = loadFunction('generateUploadProgressItem', {
    uploadModalItem: {cloneNode: () => clone},
    uploadModalList: {appendChild() {}},
    filesProgressItem,
  });
  const item = generate({name: payload});
  assert.equal(item.title.textContent, payload);
  const setError = loadFunction('setUploadError', {filesProgressItem, setProgressBar() {}});
  setError(payload, payload);
  assert.equal(item.error.textContent, 'Error: ' + payload);
});

test('tag filters send the original text rather than serialized HTML entities', () => {
  const tag = element();
  tag.textContent = payload;
  const getFilters = loadFunction('getFilters', {
    document: {querySelectorAll: () => [tag]},
    filters: {},
    filter_dir: {value: ''},
    filter_keywords: {value: ''},
  });
  assert.equal(getFilters().tags, payload);
});
