"""Checks the setup and says what is missing. Nothing is changed.

Usage:  ./gazette doctor [--smtp]     (--smtp also tries the e-mail login)
"""
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONFIG, EDITIONS, LOGS, SETTINGS, TOP, load_json, sections, utf8_stdout  # noqa: E402

problems = 0


def line(ok, text, hint=""):
    global problems
    mark = {True: "ok ", False: "!! ", None: " · "}[ok]
    if ok is False:
        problems += 1
    print(f"{mark} {text}" + (f"\n      → {hint}" if hint else ""))


def main():
    utf8_stdout()
    from schedule import find_claude, status as schedule_status
    from secret import get_password

    v = sys.version_info
    line(v >= (3, 9), f"Python {v.major}.{v.minor}.{v.micro} on {platform.system()}", "" if v >= (3, 9) else "install Python 3.9+")
    claude = find_claude()
    if claude:
        r = subprocess.run([claude, "--version"], capture_output=True, text=True)
        line(True, f"Claude Code {r.stdout.strip() or '?'} ({claude})")
    else:
        line(False, "Claude Code not found", "install it: https://code.claude.com/docs/en/setup")

    cfg = load_json(SETTINGS, None)
    if not cfg:
        line(False, "config/settings.json is missing", "open Claude Code in this folder and run /gazette-setup")
        sys.exit(1)
    secs = sections(cfg)
    line(bool(secs) and secs[0]["id"] == TOP, f"language {cfg.get('language', '?')} · {len(secs)} sections",
         "" if secs and secs[0]["id"] == TOP else f"edition.sections needs a '{TOP}' section")
    line((CONFIG / "profile.md").exists(), "reader profile (config/profile.md)", "" if (CONFIG / "profile.md").exists() else "run /gazette-setup")
    src = load_json(CONFIG / "sources.json", {}).get("sources", [])
    line(bool(src), f"{len(src)} sources (config/sources.json)", "" if src else "./gazette sources init --packs …")
    tracks = load_json(CONFIG / "learning.json", {}).get("tracks", [])
    line(None, f"{len(tracks)} learning tracks")

    d = cfg.get("delivery", {})
    channels = [c for c in ("email", "kindle") if (d.get(c) or {}).get("enabled")]
    if channels:
        user = (d.get("smtp") or {}).get("user", "")
        _, where = get_password(user) if user else (None, None)
        line(bool(where), f"delivery: {', '.join(channels)} via {user or '?'}" + (f" · password in {where}" if where else ""),
             "" if where else "store the app password: ./gazette secret set (in your own terminal)")
        if "--smtp" in sys.argv and where:
            r = subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("deliver.py")), "--check"],
                               capture_output=True, text=True)
            line(r.returncode == 0, (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else "SMTP check")
    else:
        line(None, "delivery: reader only (no e-mail/Kindle)")

    sch = cfg.get("schedule") or {}
    if sch.get("enabled"):
        st = schedule_status()
        line(bool(st), st or f"schedule wanted ({', '.join(sch.get('days', []))} {sch.get('time', '')}) but not installed",
             "" if st else "./gazette schedule install")
    else:
        line(None, "schedule: off (editions only when you run /gazette)")

    eds = sorted(EDITIONS.glob("*.json"))
    line(None, f"{len(eds)} editions" + (f", newest {eds[-1].stem}" if eds else ""))
    log = LOGS / "scheduled.log"
    if log.exists():
        last = [ln for ln in log.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()][-1:]
        line(None, f"last scheduled log line: {last[0] if last else '-'}")
    print("\nAll good." if not problems else f"\n{problems} thing(s) to fix.")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
