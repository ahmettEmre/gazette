"""Automatic editions: registers one job with your operating system's scheduler.

Usage:  ./gazette schedule install [--dry-run]   create or update the job from config/settings.json → schedule
        ./gazette schedule remove                delete the job
        ./gazette schedule status                show what is registered
        ./gazette schedule run                   run the job now, exactly as the scheduler would (uses your quota)

Windows  Task Scheduler. Runs while you are logged in; a missed run starts as soon as the PC is on again.
macOS    launchd agent in ~/Library/LaunchAgents. A run missed during sleep starts on wake.
Linux    your crontab. A run missed while the machine was off is skipped.
The job starts scripts/scheduled.py, which runs your AI agent headless with narrow permissions (scripts/agents.py).
With Antigravity, install also adds Gazette's command rules to its settings, and remove takes them out again.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agents  # noqa: E402
from common import LOGS, ROOT, STATE, iso, load_json, load_settings, now_utc, save_json, utf8_stdout  # noqa: E402

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WIN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
JOB = "gazette-" + hashlib.sha1(str(ROOT).lower().encode()).hexdigest()[:6]  # one job per clone
RUNNER = ROOT / "scripts" / "scheduled.py"
RECORD = STATE / "schedule.json"


def job_python():
    exe = Path(sys.executable)
    if sys.platform == "win32":  # pythonw has no console window: nothing flashes on screen
        w = exe.with_name("pythonw.exe")
        if w.exists():
            return str(w)
    return str(exe)


def parse_schedule(cfg):
    sch = cfg.get("schedule") or {}
    days = [d.lower()[:3] for d in sch.get("days") or []]
    bad = [d for d in days if d not in DAYS]
    if bad or not days:
        sys.exit(f"schedule.days must list days from {DAYS} (got {sch.get('days')})")
    try:
        hh, mm = (int(x) for x in str(sch.get("time", "07:00")).split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except Exception:
        sys.exit(f"schedule.time must look like HH:MM (got {sch.get('time')})")
    return sorted(set(days), key=DAYS.index), hh, mm


# ---------------------------------------------------------------- Windows

def win_name():
    return f"Gazette\\{JOB}"


def win_xml(days, hh, mm, python):
    start = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\")
    day_tags = "".join(f"<{WIN_DAYS[DAYS.index(d)]} />" for d in days)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>{escape(f"Gazette scheduled edition ({ROOT})")}</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek><DaysOfWeek>{day_tags}</DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>{escape(user)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(python)}</Command>
      <Arguments>{escape(f'-I "{RUNNER}"')}</Arguments>
      <WorkingDirectory>{escape(str(ROOT))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def win_install(days, hh, mm, python, dry):
    xml = win_xml(days, hh, mm, python)
    if dry:
        print(xml)
        return
    tmp = STATE / "schedule-task.xml"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(xml, encoding="utf-16")
    r = subprocess.run(["schtasks", "/Create", "/TN", win_name(), "/XML", str(tmp), "/F"], capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode:
        sys.exit(f"Task Scheduler refused the job: {(r.stderr or r.stdout).strip()}")


def win_remove():
    r = subprocess.run(["schtasks", "/Delete", "/TN", win_name(), "/F"], capture_output=True, text=True)
    return r.returncode == 0


def win_status():
    ps = (f"$t = Get-ScheduledTask -TaskPath '\\Gazette\\' -TaskName '{JOB}' -ErrorAction SilentlyContinue; "
          "if ($t) { $i = $t | Get-ScheduledTaskInfo; [pscustomobject]@{State=[string]$t.State; "
          "Next=$i.NextRunTime.ToString('s'); Last=$i.LastRunTime.ToString('s'); Result=$i.LastTaskResult} | ConvertTo-Json }")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    if not r.stdout.strip():
        return None
    info = json.loads(r.stdout)
    last = info["Last"] if not info["Last"].startswith("1999") else "never"
    return f"Task Scheduler: Gazette\\{JOB} · state {info['State']} · next run {info['Next']} · last run {last} (result {info['Result']})"


# ---------------------------------------------------------------- macOS

def mac_plist_path():
    return Path.home() / "Library" / "LaunchAgents" / f"com.gazette.{JOB}.plist"


def mac_install(days, hh, mm, python, dry):
    slots = "".join(f"<dict><key>Weekday</key><integer>{(DAYS.index(d) + 1) % 7}</integer>"
                    f"<key>Hour</key><integer>{hh}</integer><key>Minute</key><integer>{mm}</integer></dict>" for d in days)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.gazette.{JOB}</string>
  <key>ProgramArguments</key><array><string>{escape(python)}</string><string>-I</string><string>{escape(str(RUNNER))}</string></array>
  <key>WorkingDirectory</key><string>{escape(str(ROOT))}</string>
  <key>StartCalendarInterval</key><array>{slots}</array>
  <key>StandardOutPath</key><string>{escape(str(LOGS / "launchd.log"))}</string>
  <key>StandardErrorPath</key><string>{escape(str(LOGS / "launchd.log"))}</string>
</dict></plist>
"""
    if dry:
        print(plist)
        return
    path = mac_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(path)], capture_output=True)
    path.write_text(plist, encoding="utf-8")
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(path)], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"launchctl refused the job: {(r.stderr or r.stdout).strip()}")


def mac_remove():
    path = mac_plist_path()
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)], capture_output=True)
    existed = path.exists()
    path.unlink(missing_ok=True)
    return existed


def mac_status():
    if not mac_plist_path().exists():
        return None
    r = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/com.gazette.{JOB}"], capture_output=True, text=True)
    keep = [ln.strip() for ln in r.stdout.splitlines() if ln.strip().startswith(("state =", "runs =", "last exit code"))]
    return f"launchd: com.gazette.{JOB} · " + (" · ".join(keep) if keep else "plist present, not loaded")


# ---------------------------------------------------------------- Linux (cron)

def cron_lines():
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else []


def cron_write(lines):
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)


def cron_install(days, hh, mm, python, dry):
    dow = ",".join(str((DAYS.index(d) + 1) % 7) for d in days)
    line = (f'{mm} {hh} * * {dow} cd "{ROOT}" && "{python}" -I scripts/scheduled.py >> logs/cron.log 2>&1'
            f"  # gazette:{JOB}")
    if dry:
        print(line)
        return
    if not shutil.which("crontab"):
        sys.exit("crontab is not available. Install cron, or run ./gazette schedule run from a systemd timer.")
    LOGS.mkdir(exist_ok=True)
    cron_write([ln for ln in cron_lines() if f"# gazette:{JOB}" not in ln] + [line])


def cron_remove():
    lines = cron_lines()
    keep = [ln for ln in lines if f"# gazette:{JOB}" not in ln]
    if len(keep) != len(lines):
        cron_write(keep)
        return True
    return False


def cron_status():
    hit = [ln for ln in cron_lines() if f"# gazette:{JOB}" in ln]
    return f"crontab: {hit[0].split('  #')[0]}" if hit else None


# ---------------------------------------------------------------- main

PLATFORM = {"win32": (win_install, win_remove, win_status), "darwin": (mac_install, mac_remove, mac_status)}
install, remove, status = PLATFORM.get(sys.platform, (cron_install, cron_remove, cron_status))


def main():
    utf8_stdout()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "install":
        cfg = load_settings()
        if not (cfg.get("schedule") or {}).get("enabled"):
            removed = remove()
            print("Schedule is off in settings" + (" — the existing job was removed." if removed else "; nothing to install."))
            return
        days, hh, mm = parse_schedule(cfg)
        eid, agent = agents.engine_id(cfg), agents.info(cfg)
        exe = agents.find(eid)
        if not exe:
            sys.exit(f"{agent['name']} ({agent['exe']}) was not found on PATH. Install it first: {agent['install']}")
        python = job_python()
        install(days, hh, mm, python, "--dry-run" in sys.argv)
        if "--dry-run" in sys.argv:
            return
        save_json(RECORD, {"job": JOB, "python": python, "engine": eid, "agent": exe, "path": os.environ.get("PATH", ""),
                           "days": days, "time": f"{hh:02d}:{mm:02d}", "installed": iso(now_utc())})
        print(f"Scheduled: {', '.join(days)} at {hh:02d}:{mm:02d} (local time) · job {JOB}")
        print(f"{agent['name']}: {exe}")
        if eid == "antigravity":
            print(agents.agy_permissions(add=True))
        print(status() or "")
    elif cmd == "remove":
        print("Removed the scheduled job." if remove() else "No scheduled job was registered.")
        if (load_json(RECORD, {}) or {}).get("engine") == "antigravity":
            print(agents.agy_permissions(add=False))
        RECORD.unlink(missing_ok=True)
    elif cmd == "status":
        print(status() or "No scheduled job is registered for this folder.")
        rec = load_json(RECORD, None)
        if rec:
            print(f"Settings at install: {', '.join(rec['days'])} at {rec['time']} · "
                  f"{rec.get('engine', 'claude')} {rec.get('agent') or rec.get('claude')}")
        log = LOGS / "scheduled.log"
        if log.exists():
            tail = [ln for ln in log.read_text(encoding="utf-8", errors="replace").splitlines() if " ===== " in ln][-2:]
            print("Last log lines: " + " | ".join(tail))
    elif cmd == "run":
        sys.exit(subprocess.run([sys.executable, "-I", str(RUNNER), *sys.argv[2:]]).returncode)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
