# Licence

Your licence is a small text file (`*.uptivora-license`) signed by Uptivora. The installation
checks the signature itself; there is no activation, no internet connection and no expiry
date. Any modification to the file makes it invalid.

Without a licence the installation runs in evaluation mode: 3 monitors, 1 user, checks every
5 minutes at most.

## Installing

Either way works; use one of them.

**In the web interface.** Admin → Licence → *Choose licence file* (or paste the text) →
*Verify & install*. The licence is stored in the database and is therefore part of your
backups.

**As a file.** Copy it to `license/uptivora.license` next to `compose.yaml`. The worker picks
it up within five minutes; restart to apply it at once:

```bash
cp ~/Example_AG.uptivora-license license/uptivora.license
docker compose restart api worker
```

A file in `license/` takes precedence over a licence installed in the web interface.

## What changes

Installing or replacing a licence applies the new limits immediately. If you go below your
current usage — for example by removing the licence — the newest monitors above the limit are
**paused, never deleted**, and resume automatically when there is room again. Accounts are
never removed; inviting more users than the licence allows is refused.

## Replacing or removing

- Replacing: install the new file the same way. The history on the Licence page lists every
  licence that was installed.
- Removing: *Remove licence* on the Licence page (for a licence installed in the web
  interface) or delete `license/uptivora.license`.

## Moving to a new server

The licence is not tied to a machine. Restore your backup on the new server (it contains a
licence installed through the web interface) or copy the licence file. Run one production
installation per licence.

## "Licence rejected"

| Message | Cause |
| --- | --- |
| *not signed by a trusted Uptivora key* | The file was changed, is a test licence, or is newer than this version of Uptivora — upgrade first |
| *malformed* | Part of the text is missing; upload the original file instead of copying the text |
