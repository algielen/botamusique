# Code scanning follow-up

Review of the 12 open GitHub CodeQL alerts on 2026-10-29.
Alert links: https://github.com/algielen/botamusique/security/code-scanning

## Changes in this branch

- Alerts #1–#3: default both Docker workflows to `contents: read`. Existing
  job-specific publishing permissions remain in place.
- Alerts #11–#12: render tag labels and upload filenames with `textContent`.
  Apply the same fix to other plain-text fields, including library metadata,
  playlist titles, and upload error responses. Read tags back as text so that
  characters such as `&` and `<` survive editing and filtering unchanged.
- Alert #10: explicitly require TLS 1.2 or newer for Mumble control connections.
  This makes the existing Python default an enforced application policy.

These fixes need a new CodeQL run before their alerts can be confirmed closed.

## File paths: alerts #4–#9

Implemented on `fix/restrict-local-filepaths`; a new CodeQL run must confirm closure.

- Uploads use generated storage names. Original filenames and optional `name`
  values are display metadata. Existing regular files remain supported.
- Existing folder labels resolve through server-owned enumeration. New labels
  map to generated directories; typed paths cannot create arbitrary directories.
- Reject symlinks, junctions/reparse points, hard links, absolute paths, traversal,
  alternate data streams, and ambiguous trailing spaces/dots. Apply this to
  scans, metadata, local playback, downloads/ZIPs, and local deletion.
- On POSIX, use directory descriptors and `O_NOFOLLOW`; subprocesses inherit the
  secured file descriptor. On Windows, open reparse points without following
  them and pin ancestors/files with handles that deny delete sharing.
- Create uploads exclusively and clean up partial writes. Serialize uploads with
  rescans so partially uploaded files are not indexed. Keep empty folders instead
  of deleting directories selected by a request.
- Bound cached-download playback, downloads, and cleanup to their separate cache
  root. Downloads and ZIPs stream secured file objects instead of reopening paths.
- Reject invalid bulk-delete inputs before changing files or library state.

Tests cover traversal/drive/UNC inputs, junctions and symlinks (including links
within the root), hard links, collisions, partial uploads, independent display
names, invalid database paths, normal download/ZIP/delete operations, subprocess
file access, and a POSIX parent-directory replacement race.

Compatibility: local play/list searches now use library titles. Existing regular
files keep their filenames and IDs; absolute-path and linked entries are rejected.
Keep both the music database and settings database when backing up app-managed
uploads, since they hold display titles and folder-label mappings.

## TLS: alert #10

The alert is from the current base commit and flags TLS 1.0/1.1 as allowed by
`ssl.create_default_context()`. The local Python 3.14 default minimum is already
TLS 1.2. This branch makes that minimum explicit and adds a regression test.
Re-run CodeQL to confirm that it recognizes the policy. Servers supporting only
TLS 1.0/1.1 cannot connect.

Certificate verification is a separate concern: the connection currently defaults
to `CERT_NONE` and does not supply a hostname. Plan configurable CA/hostname
verification or certificate pinning, with a documented migration for self-signed
Mumble servers. Test trusted, self-signed, expired, and wrong-host certificates,
as well as client-certificate authentication, before changing the default.

## Additional HTML follow-up

Playlist artist and path fields still use `innerHTML` because the API supplies
link markup for URLs and playlist attribution. Local artist metadata also reaches
this sink, so there is remaining XSS exposure beyond the two reported alerts.
Replace those HTML strings with separate text and URL fields, then build links
with DOM methods and permit only intended URL schemes (e.g. HTTP/HTTPS).
Test malicious artist names, playlist titles, quote-containing URLs, and
`javascript:` URLs while preserving normal clickable links. Treat this as high
priority alongside the path fixes.

## Validation

- `node --check src/botamusique/static/js/main.mjs`
- `node --test tests/test_web_text.mjs` (literal-text rendering and tag round trip)
- `.venv/Scripts/python.exe -m pytest tests/ -q --basetemp=tmp/pytest-security-review`
- Linux-specific helper tests: `python3 -m pytest --noconftest tests/test_localfiles.py`
  with `src` on `PYTHONPATH`
- Re-run GitHub CodeQL after publishing the branch; local tests cannot confirm
  GitHub alert closure.
