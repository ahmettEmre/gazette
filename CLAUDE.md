# Gazette

A personal news edition that runs on the user's own computer with their own Claude Code subscription.
Python scripts (standard library only) collect and publish; Claude Code selects, verifies and writes.

- `/gazette-setup` (`.claude/skills/gazette-setup/`) — interview + configuration, also for later changes.
- `/gazette` (`.claude/skills/gazette/`) — writes an edition; `scheduled` mode is run by the OS scheduler.
- Project commands: always `./gazette <command>` (`scripts/cli.py` maps commands to scripts).

## Flow
```
./gazette collect  → raw/<id>.md digest + raw/<id>.json        (no AI, never writes state)
Claude (/gazette)  → data/editions/<id>.json                    (selects, reads, verifies, writes)
./gazette publish  → data/editions/<id>.js, data/index.js, data/site.js, state/ (seen items, lesson progress)
gazette.html       → viewer/app.js loads data/*.js via <script> (works from file://, no server)
./gazette deliver  → short e-mail + full edition attached (render.py; PDF via a local Chromium in pdf.py, else HTML)
                     and/or EPUB to Kindle, over the user's own SMTP account
```

## Files
- Committed: `scripts/`, `viewer/`, `gazette.html`, `catalog/sources.json` (source packs), `i18n/` (UI strings),
  `.claude/`, `docs/`.
- The user's own (git-ignored): `config/` (settings.json, profile.md, sources.json, learning.json, ui.json),
  `data/` (published editions), `state/`, `raw/`, `out/`, `logs/`.

## Rules
- No dependencies: Python standard library and plain HTML/CSS/JS only.
- Scripts are safe to re-run: collect writes no state; publish never commits the same raw file twice.
- Section ids come from `config/settings.json`; the must-know section id is always `top`. Editions store a snapshot
  of their sections, so old editions keep rendering after the user changes topics.
- UI text lives in `i18n/<lang>.json` (+ `config/ui.json` for other languages). Never hard-code reader-facing text
  in scripts or the viewer.
- Security: no passwords or keys anywhere in this folder (Claude may read it, and web pages it reads may try to
  manipulate it). The SMTP password lives in the OS keychain (`scripts/secret.py`). `common.fetch` only opens
  http(s) URLs — keep it that way. Scheduled runs get a narrow `--allowedTools` list (`scripts/scheduled.py`) and
  never send e-mail themselves.
