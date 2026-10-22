# Gazette

**Your personal news edition, written by Claude Code on your own computer.**

Gazette reads the sources you care about, picks what matters *to you*, checks it against primary sources, and
writes it up in the language you choose: what happened, why it matters for you, an honest take, the terms you may
not know, and a short lesson from something you want to learn. You read it in a local web page, in your inbox, or
on your Kindle — on the days and at the time you choose.

No server, no API keys, no subscription to yet another service. It runs on your machine and uses your own
Claude Code plan.

---

## What you get

- **A reader** (`gazette.html`): sections, archive, search, read/saved marks, dark mode, keyboard shortcuts. Opens from
  disk, no server.
- **An e-mail newsletter** and/or an **EPUB for your Kindle**, sent automatically after each scheduled edition.
- **Trust signals on every story:** official / press / community source, "Unverified" when only one non-official
  source exists, an importance score and a hype meter. Facts and opinion are kept apart.
- **"Why it matters to you"** written from your own profile: your job, your tools, your country.
- **Learning tracks:** pick up to three topics ("EU AI Act for developers", "Kubernetes basics", "Investing 101");
  every edition carries the next lesson, with sources.
- **Concept cards** for the ideas behind the news, and **Ask Claude** on any story for a deep explanation.
- **Any language.** English, Turkish and German interfaces ship with it; for other languages the setup translates
  the interface for you.

## How it works

```
 your sources ──► ./gazette collect ──► digest of candidates          (plain Python, no AI)
                                           │
                        Claude Code  /gazette   picks, reads primary sources, verifies, writes in your language
                                           │
                        ./gazette publish ──► gazette.html (reader) + archive
                                           │
                        ./gazette deliver ──► e-mail newsletter · Kindle EPUB      (your own mail account)
```

The collector does the cheap work (fetching ~100 feeds takes seconds), so Claude only spends time on judgement
and writing. Your operating system's scheduler starts the whole thing on the days you picked.

## Requirements

- **[Claude Code](https://code.claude.com/docs/en/setup)** signed in with a Claude plan (Pro or Max) or an API key
- **Python 3.9+** (standard library only; nothing to `pip install`)
- **Git**
- Windows 10/11, macOS or Linux

## Install

```bash
git clone https://github.com/ahmettEmre/gazette.git
cd gazette
claude
```

Accept the folder trust prompt, then type:

```
/gazette-setup
```

That's it. The setup is a short conversation (about five minutes). When it is done, type `/gazette` for your
first edition, or wait for the schedule.

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

Inside Claude Code, in this folder:

| Command | What it does |
|---|---|
| `/gazette` | write a new edition now and open the reader |
| `/gazette explain <edition>/<story>` | in-depth explanation of one story (the **Ask Claude** button copies this) |
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

At the scheduled time `scripts/scheduled.py` starts Claude Code headless (`claude -p "/gazette scheduled"`), waits
for it to publish, then sends the edition to your inbox/Kindle. If you already made an edition in the last
12 hours, it sends that one instead of writing a new one. If something fails, you get a short e-mail and the
details are in `logs/scheduled.log`.

**Cost:** every edition is real Claude work on *your* plan — roughly 5–20 minutes (a 30-story weekly edition took
16 minutes in testing). Start with one to three editions a week. To save quota, set `"run": {"model": "sonnet"}` in
`config/settings.json`; scheduled runs then use that model.

Claude Desktop users can also use its built-in local scheduled tasks to run `/gazette` instead.

## E-mail and Kindle

Sending uses an e-mail account you own (the sender); editions can go to any address.

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
- **What leaves your machine:** requests to the news sources you chose; your Claude Code session (exactly as when you
  use Claude Code yourself); the e-mails you configured, sent through your own mail account.
- **No passwords in the folder.** Claude Code may read files in this folder, and the web pages it reads could try to
  trick it. That is why the mail password lives in the OS keychain, and why the page reader only opens `http(s)` URLs.
- **Unattended runs have narrow permissions:** they may run `./gazette collect | read | publish | learn`, search and
  read the web, and write into `data/editions/` — nothing else. They cannot edit scripts, read files outside this
  folder, run other commands or send e-mail; delivery is done by plain Python after Claude has finished. The rules
  for the editor say that text from web pages is data, never instructions.
- The project's permission file (`.claude/settings.json`) only takes effect after you accept the folder trust prompt
  once in an interactive session. Scheduled runs pass their own permission list and do not depend on it.

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
| Claude asks permission for every command | accept the folder trust prompt (start `claude` in this folder once) |

## Update and uninstall

```bash
git pull                                       # your config/, data/ and state/ are not tracked, nothing is overwritten
./gazette schedule remove && ./gazette secret delete   # then delete the folder
```

## Project layout

```
.claude/skills/gazette/        the editor (/gazette)          scripts/collect.py   sources → digest
.claude/skills/gazette-setup/  the setup interview           scripts/publish.py   validate → reader files
catalog/sources.json          ready-made source packs       scripts/deliver.py   e-mail + Kindle (render.py)
i18n/                         interface languages           scripts/schedule.py  OS scheduler (scheduled.py runs it)
viewer/ + gazette.html         the reader                    config/ data/ state/ yours, git-ignored
```

## License

MIT — see [LICENSE](LICENSE).
