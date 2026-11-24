# Code scanning follow-up

Review of the 12 open GitHub CodeQL alerts on 2026-10-29.
Alert links: https://github.com/algielen/botamusique/security/code-scanning

Status reviewed against the current implementation; tests and GitHub alert status
were not rechecked during this review. A new CodeQL run is needed to confirm
whether any alerts have closed.

## Implemented measures

- Alerts #1–#3: default both Docker workflows to `contents: read`. Existing
  job-specific publishing permissions remain in place.
- Alerts #11–#12: render tag labels and upload filenames with `textContent`.
  Other plain-text fields, including library metadata, playlist titles, and
  upload error responses, use the same fix. Tags are read back as text so that
  characters such as `&` and `<` survive editing and filtering unchanged.
- Alert #10: explicitly require TLS 1.2 or newer for Mumble control connections.
  This makes the existing Python default an enforced application policy.

## File paths: alerts #4–#9

Several safeguards are implemented, but the path protections are incomplete and
closure of the alerts remains unconfirmed.

- Uploads use generated storage names. Original filenames and optional `name`
  values are display metadata. Existing regular files remain supported.
- Existing folder labels resolve through server-owned enumeration. New labels
  map to generated directories; typed paths cannot create arbitrary directories.
- Local file validation rejects symlinks, junctions/reparse points, hard links,
  absolute paths, traversal, alternate data streams, and ambiguous trailing
  spaces/dots. Secured file opens are used for metadata, local playback and
  downloads/ZIPs, but scanning and deletion have the limitations below.
- On POSIX, directory descriptors and `O_NOFOLLOW` are used; subprocesses inherit
  the secured file descriptor. On Windows, reparse points are opened without
  following them and handles deny delete sharing; ancestor pinning during Windows
  subprocess use remains uncertain.
- Uploads are created exclusively and failures during saving are cleaned up.
  Uploads and rescans are serialized so partially uploaded files are not indexed.
  Empty folders are kept instead of deleting directories selected by a request.
- Cached-download playback and web downloads use secured opens under the cache
  root. Downloads and ZIPs stream secured file objects instead of reopening paths.
- Reject invalid bulk-delete inputs before changing files or library state.

Existing tests cover traversal/drive/UNC inputs, junctions and symlinks (including
links within the root), hard links, collisions, partial uploads, independent display
names, invalid database paths, normal download/ZIP/delete operations, subprocess
file access, and a POSIX parent-directory replacement race. They do not establish
Windows inherited-descriptor access or concurrent upload/rescan behavior; optional
upload `name` handling also lacks coverage.

Remaining work:

- Validate database-loaded cache IDs and bound download output paths, cleanup
  globs, thumbnail reads, and general cache cleanup to the cache root. Current
  pathname-based cleanup is vulnerable to replacement races and Windows junctions.
- Anchor directory enumeration and scanning to secured directories. Current
  pathname-based enumeration can race with directory replacement.
- Address the race between validating a deletion target and unlinking it; bulk
  prevalidation does not make subsequent deletions atomic.
- Verify Windows ancestor protection throughout subprocess use: parent handles
  are released before the subprocess reopens the file by pathname.
- Clean up uploads and folder mappings on failures after saving, including close,
  metadata extraction, and database insertion failures.

Compatibility: local play/list searches now use library titles. Existing regular
files keep their filenames and IDs; absolute-path and linked entries are rejected.
Keep both the music database and settings database when backing up app-managed
uploads, since they hold display titles and folder-label mappings.

## TLS: alert #10

The alert is from the current base commit and flags TLS 1.0/1.1 as allowed by
`ssl.create_default_context()`. The local Python 3.14 default minimum is already
TLS 1.2. The implementation makes that minimum explicit and has a regression test.
Re-run CodeQL to confirm that it recognizes the policy. Servers supporting only
TLS 1.0/1.1 cannot connect.

Certificate verification is a separate concern: the connection currently defaults
to `CERT_NONE` and does not supply a hostname. Plan configurable CA/hostname
verification or certificate pinning, with a documented migration for self-signed
Mumble servers. Test trusted, self-signed, expired, and wrong-host certificates,
as well as client-certificate authentication, before changing the default.

## Additional HTML follow-up

Playlist artist and path fields still use `innerHTML`, and the API supplies HTML
strings for URLs. Local artist metadata and paths also reach these sinks, leaving
XSS exposure beyond the two reported alerts. The playlist attribution branch is
currently unreachable because the `URLItem` check precedes its subclass check;
its interpolated title and URL would also need safe handling if made reachable.
Replace those HTML strings with separate text and URL fields, then build links
with DOM methods and permit only intended URL schemes (e.g. HTTP/HTTPS).
Test malicious artist names and paths, playlist titles, quote-containing URLs, and
`javascript:` URLs while preserving normal clickable links. Cover playlist
attribution and tag editing/filtering as well. Existing text-rendering tests do
not cover these playlist and URL cases. Treat this as high priority alongside the
path fixes.

## Validation

Suggested validation; these commands were not run during the current review:

- `node --check src/botamusique/static/js/main.mjs`
- `node --test tests/test_web_text.mjs` (literal-text rendering and tag filtering)
- `.venv/Scripts/python.exe -m pytest tests/ -q --basetemp=tmp/pytest-security-review`
- Linux-specific helper tests: `python3 -m pytest --noconftest tests/test_localfiles.py`
  with `src` on `PYTHONPATH`
- Re-run GitHub CodeQL after publishing the branch; local tests cannot confirm
  GitHub alert closure.
