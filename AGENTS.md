# Gazette

A personal news edition that runs on the user's own computer with their own AI agent subscription: Claude Code,
Codex or Antigravity CLI (`run.engine` in settings; `scripts/agents.py`). Python scripts (standard library only)
collect and publish; the agent selects, verifies and writes.

- `/gazette-setup` — interview + configuration, also for later changes.
- `/gazette` — writes an edition; `scheduled` mode is run by the OS scheduler. In Codex: `$gazette-setup`, `$gazette`.
- Skills: `.claude/skills/<name>/SKILL.md` is the source; `.agents/skills/` holds the copies Codex and Antigravity
  read. After editing a skill, run `python scripts/sync_skills.py`.
- Project commands: always `./gazette <command>` (Windows PowerShell or cmd: `.\gazette.cmd <command>`);
  `scripts/cli.py` maps commands to scripts.

## Flow
```
./gazette collect  → raw/<id>.md digest + raw/<id>.json        (no AI, never writes state)
agent (/gazette)   → data/editions/<id>.json                    (selects, reads, verifies, writes)
./gazette publish  → data/editions/<id>.js, data/index.js, data/site.js, state/ (seen items, lesson progress)
gazette.html       → viewer/app.js loads data/*.js via <script> (works from file://, no server)
./gazette deliver  → short e-mail + full edition attached (render.py; PDF via a local Chromium in pdf.py, else HTML)
                     and/or EPUB to Kindle, over the user's own SMTP account — optional
```

## Files
- Committed: `scripts/`, `viewer/`, `gazette.html`, `catalog/sources.json` (source packs), `i18n/` (UI strings),
  `.claude/`, `.agents/`, `docs/`.
- The user's own (git-ignored): `config/` (settings.json, profile.md, sources.json, learning.json, ui.json),
  `data/` (published editions), `state/`, `raw/`, `out/`, `logs/`.

## Rules
- No dependencies: Python standard library and plain HTML/CSS/JS only.
- Scripts are safe to re-run: collect writes no state; publish never commits the same raw file twice.
- Section ids come from `config/settings.json`; the must-know section id is always `top`. Editions store a snapshot
  of their sections, so old editions keep rendering after the user changes topics.
- UI text lives in `i18n/<lang>.json` (+ `config/ui.json` for other languages). Never hard-code reader-facing text
  in scripts or the viewer. `{agent}` and `{gazette}` in those strings become the agent's name and command.
- Security: no passwords or keys anywhere in this folder (the agent may read it, and web pages it reads may try to
  manipulate it). The SMTP password lives in the OS keychain (`scripts/secret.py`). `common.fetch` only opens
  http(s) URLs — keep it that way. Scheduled runs get the narrowest permissions each agent offers
  (`scripts/agents.py`) and never send e-mail themselves.
