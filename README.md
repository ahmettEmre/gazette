# Gazette

**Your personal news edition, written by your own AI agent on your own computer.**
Works with Claude Code, Codex (ChatGPT) or Antigravity CLI (Google).

Gazette reads the sources you care about, picks what matters *to you*, checks it against primary sources, and
writes it up in the language you choose: what happened, why it matters for you, an honest take, the terms you may
not know, and a short lesson from something you want to learn. You read it in a local web page, in your inbox, or
on your Kindle — on the days and at the time you choose.

No server, no API keys, no subscription to yet another service. It runs on your machine and uses the AI plan you
already have.

---

## What you get

- **A reader** (`gazette.html`): sections, archive, search, read/saved marks, dark mode, keyboard shortcuts. Opens from
  disk, no server. Every edition is kept here, on your computer — this is all you need.
- **Optional:** a short e-mail with the big picture and a few highlights, the **full edition attached as a PDF** (or
  HTML/EPUB), and/or an **EPUB for your Kindle** — sent after each scheduled edition, from your own mail account.
  Handy on a phone; skip it and nothing about e-mail is ever set up.
- **Trust signals on every story:** official / press / community source, "Unverified" when only one non-official
  source exists, an importance score and a hype meter. Facts and opinion are kept apart.
- **"Why it matters to you"** written from your own profile: your job, your tools, your country.
- **Learning tracks:** pick up to three topics ("EU AI Act for developers", "Kubernetes basics", "Investing 101");
  every edition carries the next lesson, with sources.
- **Concept cards** for the ideas behind the news, and **Ask AI** on any story for a deep explanation.
- **Any language.** English, Turkish and German interfaces ship with it; for other languages the setup translates
  the interface for you.

## How it works

```
 your sources ──► ./gazette collect ──► digest of candidates          (plain Python, no AI)
                                           │
                         your AI agent  /gazette   picks, reads primary sources, verifies, writes in your language
                                           │
                        ./gazette publish ──► gazette.html (reader) + archive
                                           │
                        ./gazette deliver ──► short e-mail + PDF · Kindle EPUB     (optional, your own mail account)
```

The collector does the cheap work (fetching ~100 feeds takes seconds), so the AI only spends time on judgement
and writing. Your operating system's scheduler starts the whole thing on the days you picked.

## Requirements

- **One AI agent for the terminal**, signed in with your own account. A chat app in the browser is not enough:
  Gazette needs an agent that can run commands and write files on your computer.

  | Your plan | Agent | Start it with | Commands |
  |---|---|---|---|
  | Claude Pro or Max (or an API key) | [Claude Code](https://code.claude.com/docs/en/setup) | `claude` | `/gazette-setup`, `/gazette` |
  | ChatGPT Plus or Pro | [Codex CLI](https://developers.openai.com/codex/cli) | `codex` | `$gazette-setup`, `$gazette` |
  | Google account (free tier with weekly limits) or Google AI Pro | [Antigravity CLI](https://antigravity.google/docs/cli) | `agy` | `/gazette-setup`, `/gazette` |

  Gazette is developed and tested with Claude Code. Codex and Antigravity read the same instructions
  (`.agents/skills/`, `AGENTS.md`); if something behaves differently there, please open an issue.
- **Python 3.9+** (standard library only; nothing to `pip install`)
- **Git**
- Windows 10/11, macOS or Linux

## Install

```bash
git clone https://github.com/ahmettEmre/gazette.git
cd gazette
claude        # or: codex · agy
```

Accept the folder trust prompt, then type:

```
/gazette-setup        (Codex: $gazette-setup)
```

That's it. The setup is a short conversation (about five minutes). When it is done, type `/gazette` (Codex:
`$gazette`) for your first edition, or wait for the schedule.

> macOS: clone it somewhere outside Desktop, Documents and Downloads (for example `~/gazette`). macOS privacy
> protection can block background jobs from reading those folders.

## What the setup asks

| Question | Used for |
|---|---|
| Which language should editions be in? | everything you read |
| Your name, and where you live | "why it matters to you"; which laws, markets and opportunities count |
| What you do, which tools or fields you work with | picking stories and explaining their impact on you |
| Which news you want (ready-made packs + your own topics, repos, keywords, subreddits) | your source list |
| What you do **not** want | filtering |
| Opportunities (credits, hackathons, grants)? | an Opportunities section with deadlines |
| Anything to learn step by step? | learning tracks with a syllabus you approve |
| Short, standard or deep editions? | 8–12, 15–22 or 25–32 stories |
| Which days, what time? | the automatic schedule (or manual only) |
| Deliver where? Reader, e-mail address(es), Kindle | delivery |

Run `/gazette-setup` again any time to change any of it — just the part you want to change.

## Everyday use

Inside your AI agent, in this folder (in Codex, `$` instead of `/`):

| Command | What it does |
|---|---|
| `/gazette` | write a new edition now and open the reader |
| `/gazette explain <edition>/<story>` | in-depth explanation of one story (the **Ask AI** button copies this) |
| `/gazette --hours 168` | a new edition covering the last week (after a holiday) |
| `/gazette-setup` | change topics, learning, schedule, delivery, language |

In any terminal (`./gazette …` on macOS/Linux/Git Bash, `.\gazette.cmd …` in Windows PowerShell or cmd):

| Command | What it does |
|---|---|
| `./gazette open` | open the reader |
| `./gazette doctor` | check the setup and say what is missing |
| `./gazette deliver --latest` | send the newest edition again |
| `./gazette schedule status` | show the automatic schedule |
| `./gazette sources packs` / `sources test` | list source packs / test your sources |
| `./gazette learn status` | progress of your learning tracks |
| `./gazette help` | all commands |

## Automatic editions

The setup registers **one job with your operating system's scheduler**:

| OS | Where | If the computer was off or asleep |
|---|---|---|
| Windows | Task Scheduler → `Gazette\gazette-…` | runs as soon as the PC is on again |
| macOS | `~/Library/LaunchAgents/com.gazette.….plist` | runs on wake |
| Linux | your crontab | skipped |

At the scheduled time `scripts/scheduled.py` starts your AI agent without a window (`claude -p`, `codex exec` or
`agy -p`; the agent is `run.engine` in `config/settings.json`), waits for it to publish, then — if you set up e-mail or Kindle — sends the edition there. If you already made an edition
in the last 12 hours, no new one is written. If something fails, the details are in `logs/scheduled.log` (and, with
e-mail set up, you get a short e-mail about it).

**Cost:** every edition is real AI agent work on *your* plan — roughly 5–20 minutes (a 30-story weekly edition took
16 minutes with Claude Code). Start with one to three editions a week; on a free tier with a weekly limit, one. To
save quota, set a cheaper model of your agent in `config/settings.json`, e.g. `"run": {"engine": "claude", "model":
"sonnet"}`; scheduled runs then use it.

Claude Desktop users can also use its built-in local scheduled tasks to run `/gazette` instead.

## E-mail and Kindle (optional)

Without them, scheduled editions simply appear in your reader: run `./gazette open` or open `gazette.html`.

Sending uses an e-mail account **you** own (the sender) and goes to any addresses you choose — yours, a colleague's,
a team list. Gazette has no mail server and no default sender; it only logs in to your account with your password.
Both live on your computer: the addresses in `config/settings.json`, the password in your OS keychain.

**What the e-mail looks like:** a short message — the edition's headline and big picture, 3–5 highlights with a
two-sentence excerpt and a link to the source, upcoming deadlines and the lesson title — so it stays readable on a
phone. The **whole edition is attached**: every story with context, the "why it matters to you" note and sources,
plus a clickable table of contents. Choose the attachment with `delivery.email.attachment`:

| `attachment` | What you get |
|---|---|
| `pdf` (default) | A5 PDF, opens inline in Gmail and most mail apps. Printed by a Chrome, Edge, Chromium or Brave already on your computer (`./gazette doctor` shows which one). Without one, the HTML file is attached instead. |
| `html` | One self-contained page that opens in any browser. |
| `epub` | For e-readers and book apps. |
| `none` | Just the short e-mail; read the rest in `gazette.html`. |

If your browser lives somewhere unusual, set `delivery.email.browser` to its path. `./gazette deliver <edition> --preview`
writes the e-mail and the attachment into `out/` without sending anything.

| Provider | Server | Port | Password |
|---|---|---|---|
| Gmail / Google Workspace | smtp.gmail.com | 465 | [App password](https://myaccount.google.com/apppasswords) (needs 2-Step Verification) |
| iCloud Mail | smtp.mail.me.com | 587 | App-specific password (account.apple.com → Sign-In and Security) |
| Fastmail, Zoho, GMX, your own domain | see your provider | 465 / 587 | usually an app password |

Store the password **in your own terminal**, never in a chat:

```bash
./gazette secret set          # Windows PowerShell: .\gazette.cmd secret set
./gazette deliver --check     # tests the login, sends nothing
./gazette deliver --test      # sends one short test e-mail
```

It goes into the Windows Credential Manager, the macOS Keychain or the Linux Secret Service — never into this
folder. (Native alternatives: `cmdkey /generic:gazette-smtp /user:<you> /pass` · `security add-generic-password -U -s gazette-smtp -a <you> -w` · `secret-tool store --label=Gazette service gazette-smtp account <you>`.)

**Kindle:** add the sender address to Amazon → *Manage Your Content and Devices* → *Preferences* →
*Personal Document Settings* → *Approved Personal Document E-mail List*. Your `@kindle.com` address is on the same page.

## Privacy and security

- **Everything stays on your computer:** your profile, sources, editions and reading history. Your read/saved
  marks live in the browser.
- **What leaves your machine:** requests to the news sources you chose; your AI agent's session (exactly as when you
  use it yourself); the e-mails you configured, sent through your own mail account.
- **No passwords in the folder.** The AI agent may read files in this folder, and the web pages it reads could try to
  trick it. That is why the mail password lives in the OS keychain, and why the page reader only opens `http(s)` URLs.
- **Unattended runs get the narrowest permissions each agent offers.** The agent never sends e-mail: delivery is done
  by plain Python after it has finished. The rules for the editor say that text from web pages is data, never
  instructions.

  | Agent | Unattended permissions |
  |---|---|
  | Claude Code | an exact list: `./gazette collect · read · publish · learn`, web search and fetch, writing in `data/editions/`. Nothing else. |
  | Codex | Codex's `workspace-write` sandbox with network access: commands and writes stay inside this folder. |
  | Antigravity | only the commands allowed in its settings. `./gazette schedule install` adds exactly the four `./gazette` commands and reading web pages to `~/.gemini/antigravity-cli/settings.json` (a backup is kept); `schedule remove` takes them out. |
- Claude Code's project permission file (`.claude/settings.json`) only takes effect after you accept the folder trust
  prompt once in an interactive session. Scheduled runs pass their own permission list and do not depend on it.

## Making it yours

- **Sources:** `config/sources.json`. RSS/Atom feeds, Google News searches in any language, GitHub releases, Hacker News
  keywords, subreddits, sitemaps and changelog pages. See [docs/sources.md](docs/sources.md); run `./gazette sources test`
  after a change. 25 ready-made packs live in `catalog/sources.json`.
- **Profile:** `config/profile.md` — the more concrete, the better "why it matters to you" gets.
- **Sections, length, schedule, delivery:** `config/settings.json` (example: [docs/examples](docs/examples)).
- **Learning tracks:** `config/learning.json`; progress in `state/learning.json`.

Editing by hand is fine; `/gazette-setup` does the same through a conversation.

## Troubleshooting

Start with `./gazette doctor`.

| Problem | Fix |
|---|---|
| "Python 3.9+ not found" on Windows | install Python from python.org or `winget install Python.Python.3.12`; the Microsoft Store `python3` stub does not count |
| No edition arrived | `./gazette schedule status` and `logs/scheduled.log`. Was the computer on? On Linux missed runs are skipped. |
| macOS job never runs | the folder is in Desktop/Documents/Downloads: move it (`~/gazette`) and run `./gazette schedule install` again |
| "SMTP login was refused" | check the app password (2-Step Verification on? copied fully?) and store it again with `./gazette secret set` |
| Kindle shows nothing | the sender address is not on Amazon's approved list, or the Kindle is offline |
| A source fails | `./gazette sources test`; replace it with another feed or a `gnews` search |
| The agent asks permission for every command | accept the folder trust prompt (start the agent in this folder once) |
| Antigravity: scheduled run writes no edition | its shell commands were not allowed: run `./gazette schedule install` again, or allow them with `/permissions` in `agy` |

## Update and uninstall

```bash
git pull                                       # your config/, data/ and state/ are not tracked, nothing is overwritten
./gazette schedule remove && ./gazette secret delete   # then delete the folder
```

## Project layout

```
.claude/skills/gazette/        the editor (/gazette)          scripts/collect.py   sources → digest
.claude/skills/gazette-setup/  the setup interview           scripts/publish.py   validate → reader files
.agents/skills/                same, for Codex + Antigravity  scripts/deliver.py   e-mail + Kindle (render.py, pdf.py)
catalog/sources.json          ready-made source packs       scripts/schedule.py  OS scheduler (scheduled.py runs it)
i18n/                         interface languages           scripts/agents.py    Claude Code / Codex / Antigravity
viewer/ + gazette.html         the reader                    config/ data/ state/ yours, git-ignored
```

Changing a skill: edit `.claude/skills/…`, then `python scripts/sync_skills.py` updates `.agents/skills/`.

## License

MIT — see [LICENSE](LICENSE).
