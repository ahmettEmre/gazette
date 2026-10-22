"""One unattended edition. Started by your OS scheduler (see ./gazette schedule); you can also run it by hand.

1. If an edition was published in the last `schedule.skip_if_recent_hours` (default 12), no new one is
   written: that edition is delivered instead (if it was not yet). This saves your quota.
2. Otherwise it waits for the network and runs your AI agent headless (run.engine; see scripts/agents.py),
   e.g. claude -p "/gazette scheduled". Permissions are as narrow as the agent allows: this project's
   collect/read/publish/learn commands, web search/fetch and writing in this folder. The agent never sends
   e-mail: delivery is done here, by plain Python, after it has finished.
3. If no new edition appeared, you get a short failure e-mail (when e-mail delivery is on).

Options (for testing): --prompt "<text>" replaces the prompt · --dry-run prints the command only.
Log: logs/scheduled.log
"""
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agents  # noqa: E402
from common import EDITIONS, LOGS, ROOT, STATE, fetch, load_json, load_settings, now_utc, parse_date  # noqa: E402

LOG = LOGS / "scheduled.log"
LOCK = STATE / "scheduled.lock"
TIMEOUT_MIN = 90


def log(msg):
    LOGS.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{now_utc().astimezone().strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def trim_log(limit=1_000_000):
    if LOG.exists() and LOG.stat().st_size > limit:
        data = LOG.read_bytes()[-limit // 2:]
        LOG.write_bytes(data[data.find(b"\n") + 1:])


def newest_edition():
    files = sorted(EDITIONS.glob("*.json"))
    return files[-1].stem if files else None


def wait_for_network(tries=10):
    for n in range(tries):
        try:
            fetch("https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=1", timeout=15, retries=0)
            return True
        except Exception:
            if n < tries - 1:
                time.sleep(60)
    return False


def delivery_on(cfg):
    d = cfg.get("delivery") or {}
    return any((d.get(c) or {}).get("enabled") and (d.get(c) or {}).get("to") for c in ("email", "kindle"))


def deliver(*args):
    r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "deliver.py"), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in (r.stdout + r.stderr).strip().splitlines():
        log(f"deliver: {line}")
    return r.returncode


def agent_command(cfg, rec, prompt):
    eid = agents.engine_id(cfg)
    exe = (rec.get("agent") or rec.get("claude")) if rec.get("engine", "claude") == eid else None
    return agents.headless_command(eid, exe or agents.find(eid) or agents.ENGINES[eid]["exe"], prompt,
                                   (cfg.get("run") or {}).get("model"))


def main():
    os.chdir(ROOT)
    cfg = load_settings()
    rec = load_json(STATE / "schedule.json", {})
    default = agents.scheduled_prompt(agents.engine_id(cfg))
    prompt = sys.argv[sys.argv.index("--prompt") + 1] if "--prompt" in sys.argv else default
    cmd = agent_command(cfg, rec, prompt)
    if "--dry-run" in sys.argv:
        print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
        return

    trim_log()
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 3 * 3600:
        log("===== skipped: another scheduled run is still going (state/scheduled.lock)")
        return
    STATE.mkdir(exist_ok=True)
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    try:
        run(cfg, rec, cmd, prompt)
    finally:
        LOCK.unlink(missing_ok=True)


def run(cfg, rec, cmd, prompt):
    log(f"===== started ({prompt})")
    before = newest_edition()
    recent_h = float((cfg.get("schedule") or {}).get("skip_if_recent_hours", 12))
    if before and "--prompt" not in sys.argv:
        created = parse_date(load_json(EDITIONS / f"{before}.json", {}).get("created"))
        if created and (now_utc() - created).total_seconds() < recent_h * 3600:
            if not delivery_on(cfg):
                log(f"===== finished (edition {before} is younger than {recent_h:g} h and already in the reader)")
                return
            log(f"edition {before} is younger than {recent_h:g} h: delivering it instead of writing a new one")
            ok = deliver(before) == 0
            log(f"===== finished ({'delivered the recent edition' if ok else 'delivery of the recent edition failed'})")
            return
    if not wait_for_network():
        log("no network after 10 minutes; giving up")
        if delivery_on(cfg):
            deliver("--notify-failure")
        log("===== finished (no network)")
        return

    env = dict(os.environ)
    if rec.get("path"):  # the scheduler starts with a bare PATH; use the one from install time
        env["PATH"] = rec["path"] + os.pathsep + env.get("PATH", "")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    started = time.time()
    with LOG.open("a", encoding="utf-8") as out:
        try:
            p = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env,
                               cwd=ROOT, creationflags=flags, timeout=TIMEOUT_MIN * 60)
            code = p.returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
        except FileNotFoundError:
            code = f"{cmd[0]} not found (run ./gazette schedule install again)"
    log(f"{agents.info(cfg)['name']} finished in {(time.time() - started) / 60:.1f} min (exit {code})")

    after = newest_edition()
    if "--prompt" in sys.argv:
        log("===== finished (test prompt, no delivery)")
    elif after and after != before and not delivery_on(cfg):
        log(f"===== finished (edition {after}, in the reader)")
    elif after and after != before:
        ok = deliver(after) == 0
        log(f"===== finished (edition {after}{'' if ok else ', delivery failed'})")
    else:
        log("no new edition was published")
        if delivery_on(cfg):
            deliver("--notify-failure")
        log("===== finished (failed)")


if __name__ == "__main__":
    main()
