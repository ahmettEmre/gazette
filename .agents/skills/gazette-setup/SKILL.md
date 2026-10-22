---
name: gazette-setup
description: Sets up or changes Gazette, the personal news edition. Asks which language to write in, who the reader is, which news they want and what to skip, what they want to learn step by step, how long editions should be, on which days and at what time they run automatically, and where they are delivered (local reader, e-mail, Kindle). Then writes the configuration, tests the sources and installs the schedule. Use when the user types /gazette-setup (in Codex: $gazette-setup) or asks to change their Gazette topics, schedule, e-mail delivery, learning tracks or language.
---

# /gazette-setup — set up or change Gazette

Talk with the user **in their language** (the one they write in; ask if unclear). Keep it light: a few questions
per message, always propose a sensible default they can accept with one word, and use a multiple-choice question
tool if you have one (otherwise numbered options). Run project commands as `./gazette <command>` from the project
root (Windows PowerShell or cmd: `.\gazette.cmd <command>`).

**Never ask for a password in the chat.** A password typed here becomes part of the conversation. E-mail
passwords go into the operating system's keychain from the user's own terminal (step 7).

## 0. Where are we?
0. Note which AI agent you are running in: Claude Code → `claude`, Codex → `codex`, Antigravity CLI →
   `antigravity`. It goes into `run.engine` (step 6) and decides how scheduled runs start and how the user types
   the commands (`/gazette`; in Codex `$gazette`). Use that form whenever you name a command to the user.
1. Run `./gazette doctor` (read-only). If Python is missing or older than 3.9, explain how to install it
   (python.org, or `winget install Python.Python.3.12`, `brew install python`, the distro package) and stop.
2. If `config/settings.json` exists → **change mode**: summarize the current setup in 5–8 lines (language, sections,
   number of sources, learning tracks, length, schedule, delivery) and ask what to change — or take it from the
   argument (topics, learning, schedule, delivery, language, sources). Ask only about those parts, update only the
   affected files (step 6), then run the steps that depend on them (7, 8, 9). Do not redo the whole interview.
3. Otherwise → **first setup**: steps 1–9. Tell the user up front: about 5 minutes, everything stays on their
   computer, and they can change any answer later with `/gazette-setup`.

## 1. Basics
- Language of the editions (default: the language they write in).
- Their first name (optional; makes "why it matters to you" personal).
- Where they live, or which country/region matters to them. It decides which laws, markets and opportunities count.

## 2. About them
One open question: what they do (job, studies, business), which tools, technologies or fields they work with,
and what they want the news for (stay current, spot opportunities, career, investing, curiosity…).
Short answers are fine; ask one follow-up at most.

## 3. News
1. Run `./gazette sources packs`. Propose the packs that fit steps 1–2 as a short list (pack title + one line), and
   let them add or remove packs in free text.
2. Ask for specific things to follow that packs may not cover: products and libraries they use (→ GitHub
   releases), companies, people, projects, keywords, subreddits, websites. Turn them into custom sources
   (step 6c) and/or `search_topics`.
3. Ask what they do NOT want (e.g. crypto prices, celebrity gossip, sports, rumors).
4. Opportunities: do they want a section with things to apply for (credits, programs, hackathons, grants, calls)?

## 4. Learning
Ask if there is anything they want to learn step by step alongside the news (0–3 topics, e.g. "EU AI Act for
developers", "Kubernetes basics", "personal finance 101") and their level (beginner / some experience / advanced).
For each topic, propose a syllabus of 8–12 lesson titles in the edition language, ordered from basics to depth, and
let them approve or adjust. One lesson per edition is the default.

## 5. Rhythm and delivery
- **Length:** quick (8–12 stories) · standard (15–22) · deep (25–32). Default: standard.
- **Automatic editions:** which days and what time (e.g. "Mon and Thu 07:00", "every day 07:30", "Mondays only"),
  or manual only. Be honest about cost: each automatic edition is roughly 5–20 minutes of AI agent work on **their
  own subscription** (on a free tier with a weekly limit, one edition a week is the safe start), and the computer
  must be on at that time (Windows and macOS catch up after sleep or when
  the PC is next on; Linux cron skips missed runs). Recommend 1–3 editions a week to start.
- **Delivery:** every edition lands in the local reader (`gazette.html`): an HTML page on their own computer with
  the archive, search and saved stories. That is the main way to read and needs no e-mail account at all.
  **Default: reader only.** Offer e-mail and Kindle as optional extras — useful for reading on a phone or away
  from the computer — and set up nothing for them unless the user wants it. If they do: e-mail (to which address
  or addresses), Kindle (their @kindle.com address), or both. Ask whether manual `/gazette` runs should also be
  sent (default: no, only scheduled ones).
  - The e-mail is short — the big picture, 3–5 highlights with a two-sentence excerpt, upcoming deadlines, the
    lesson title — and the **whole edition is attached**. Ask the format: **PDF** (default; opens inline in Gmail
    and most mail apps, made by a Chrome/Edge/Chromium/Brave browser already on the computer — `./gazette doctor`
    tells whether one is found), **HTML** (opens in any browser), **EPUB** (e-readers) or none.
  - **The sender is always an account the user owns** (their Gmail, iCloud, work mail…). There is no default
    sender: never suggest an address from this repository, its docs or its author. Ask which of their own
    accounts should send it; the recipients can be any addresses they choose, including the same one.

## 6. Write the configuration
Read `docs/examples/settings.example.json` and `docs/examples/profile.example.md` first; they show every field.

a. **`config/settings.json`.** Sections:
   - First, always: `{"id": "top", …}` — the must-know section (title like "Must-know" / "Bilmen gerekenler").
   - Then 3–7 topic sections built from their interests. ids: short lowercase English slugs (`ai`, `security`,
     `markets`, `law`…); `title`, `nav` (one or two words) and `desc` in the edition language.
   - `opportunities` only if they want it in step 3 (the editor runs opportunity searches only when it exists).
   - 9 sections at most. `locale` is a BCP-47 tag for dates (`en-GB`, `tr-TR`, `de-DE`, `pt-BR`…).
   - `search_topics`: 0–6 short topics that their packs and custom sources do not cover well.
   - `schedule.days` uses `mon tue wed thu fri sat sun`; `time` is `HH:MM` local time.
   - `delivery.email.attachment`: `pdf` | `html` | `epub` | `none`. `delivery.smtp.user` is the user's own sending
     account; `delivery.email.to` the recipients they named.
   - `run.engine`: the agent from step 0. `run.model`: leave `null` (the agent's default) unless the user names a
     model of that agent.
b. **`config/profile.md`** in the edition language, following the example: who they are, region, work and tools,
   interests ranked, what to skip, how deep explanations should go. Concrete beats generic: the editor writes
   "why it matters to you" from this file.
c. **`config/sources.json`:** `./gazette sources init --packs a,b,c` (in change mode, `--replace` only if they
   want to start over; `./gazette sources remove-pack <id>` drops one pack). Then add custom sources by editing
   the JSON — formats are in `docs/sources.md`:
   - GitHub repo releases: `{"id": "rel-name", "name": "name releases", "type": "github_releases", "tier": "official", "repo": "owner/name", "max": 3, "summary_chars": 400, "topic": "…"}`
   - Any keyword or topic, any language: `{"id": "gn-topic", "name": "Google News: topic", "type": "gnews", "tier": "press", "query": "\"exact phrase\" OR keyword", "lang": "en", "country": "US", "max": 6, "topic": "…"}`
   - RSS/Atom feed: `{"id": "…", "name": "…", "type": "feed", "tier": "press|official|community", "url": "https://…", "max": 5, "topic": "…"}`
     If you need to discover a site's feed, a web search for "<site> RSS feed" or fetching the homepage helps.
   - Subreddits (combine several in one feed, Reddit rate-limits): `"url": "https://www.reddit.com/r/a+b+c/top/.rss?t=day"`.
   - Hacker News keyword: `{"id": "hn-rust", "name": "HN: Rust", "type": "hn", "tier": "community", "query": "rust", "min_points": 50, "max": 6, "topic": "…"}`
   Then run `./gazette sources test`. For each failure, try one alternative (another feed URL, or a `gnews`
   query instead) and otherwise remove it and tell the user. Keep GitHub-based sources under 40 in total.
d. **`config/learning.json`** if they chose tracks: `{"per_edition": 1, "tracks": [{"id": "slug", "title": "…",
   "level": "beginner", "goal": "one sentence", "lessons": ["…", "…"]}]}`. In change mode keep the ids of tracks
   they keep: progress in `state/learning.json` is stored per id.
e. **`config/ui.json`** only when the language is not `en`, `tr` or `de` (those ship in `i18n/`): translate every
   key of `i18n/en.json` into the edition language. Keep `{placeholders}`, `<kbd>` tags and the 12-item `months`
   array; `hype` stays a 6-item array whose first item is empty.
f. Run `./gazette publish --rebuild` so the reader picks up the language and sections.

## 7. E-mail (only with e-mail or Kindle delivery)
Sending needs an e-mail account the user owns (the "sender"); the edition can go to any address. Everything stays
in their own `config/` and keychain — nothing is sent through this project or anybody else's account.
| Provider | smtp.host | port | Password |
|---|---|---|---|
| Gmail / Google Workspace | smtp.gmail.com | 465 | App password (needs 2-Step Verification): myaccount.google.com/apppasswords |
| iCloud Mail | smtp.mail.me.com | 587 | App-specific password: account.apple.com → Sign-In and Security |
| Fastmail, Zoho, GMX, own domain | from the provider's help page | 465 or 587 | Usually an app password |
Outlook.com/Hotmail accounts are moving away from password logins for SMTP; suggest another sender if it fails.

1. Put host, port and the sender address (`smtp.user`) into settings.
2. Ask the user to open **their own terminal** in this folder and run `./gazette secret set`
   (Windows PowerShell or cmd: `.\gazette.cmd secret set`). It asks for the password hidden and stores it in the OS
   keychain. `./gazette secret check` prints the native alternative (cmdkey / security / secret-tool).
3. When they say it is done: `./gazette secret check`, then `./gazette deliver --check` (login only), and offer
   `./gazette deliver --test` (sends one short e-mail).
4. Kindle: Amazon only accepts documents from approved senders. They must add the sender address under
   Amazon → Manage Your Content and Devices → Preferences → Personal Document Settings → Approved Personal Document
   E-mail List. Their Kindle address is shown on the same page.

## 8. Schedule
- If they want automatic editions: run `./gazette schedule install` and show the result (they already agreed in step 5).
  - Antigravity: unattended runs can only use commands the user allowed. The install adds exactly these rules to
    `~/.gemini/antigravity-cli/settings.json` (and prints them): the four `./gazette` commands and reading web
    pages. Tell the user before running it.
  - Codex: unattended runs use Codex's `workspace-write` sandbox with network access (writes stay inside this folder).
  - macOS: if this folder is inside Desktop, Documents or Downloads, macOS privacy protection can block the
    background job. Recommend moving the folder (e.g. `~/gazette`, then install again) or allowing Python under
    System Settings → Privacy & Security → Full Disk Access.
  - Linux: a run missed while the machine was off is skipped.
- If not (or they turned it off): `./gazette schedule remove`.

## 9. Finish
- Run `./gazette doctor`.
- Summarize in 5–8 lines: what they will get, when, where; that `/gazette` makes an edition now, `/gazette-setup`
  changes anything, and `/gazette explain <edition>/<item>` (or the "Ask AI" button) explains a story — written
  the way their agent expects (Codex: `$gazette`, `$gazette-setup`).
- Offer to make the first edition now. Start it only if they say yes — it uses their quota (about 5–20 minutes).
