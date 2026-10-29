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

## File paths: alerts #4–#9 (high priority)

The upload and empty-directory deletion routes already check lexical absolute
paths against the music folder. Those checks do not resolve symlinks/junctions;
an in-folder link can point outside the music folder. Upload also checks for an
existing file separately from saving it, leaving a race that can overwrite a
file. Deletion of individual library files uses database-provided paths and
also needs an explicit storage-boundary review.

1. Define the storage policy: uploads and deletion must stay within the music
   folder; decide whether links inside that folder are supported or rejected.
   Identify which downloaded/cache files, if any, may legitimately be deleted
   outside that root before applying restrictions to all item types.
2. Add a shared path-validation helper using resolved paths and component-aware
   containment checks. Validate request directories before any library or
   filesystem mutation. Check both parent directories and final upload paths,
   including existing symlinks. Return 400/403 for invalid paths.
3. Use exclusive file creation rather than `exists()` followed by `save()`;
   preserve the 409 response for collisions and remove partial uploads on errors.
   If local users can change directories concurrently, use directory-relative
   filesystem operations that reject symlink traversal on Linux, and define an
   equivalent Windows strategy. Resolved-path checks alone do not eliminate races.
4. Test traversal with `/` and `\`, absolute/drive/UNC paths, sibling directories
   sharing a prefix, symlinks/junctions escaping the root, existing target links,
   collisions, and normal upload/deletion. Assert outside files remain untouched
   and invalid requests do not alter the playlist/database.
5. Run CodeQL on the changed routes and inspect any remaining dataflow findings.
   Document verified false positives individually rather than suppressing the rule.

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
- Re-run GitHub CodeQL after publishing the branch; local tests cannot confirm
  GitHub alert closure.
