"""The AI agents Gazette can run on, and how an unattended edition starts each of them.

claude       Claude Code (Claude Pro or Max)      tested
codex        Codex CLI (ChatGPT Plus or Pro)      reads .agents/skills/ and AGENTS.md
antigravity  Antigravity CLI, agy (Google account) reads .agents/skills/ and AGENTS.md

settings.json → run.engine picks one (default: claude). Each gets the narrowest permissions it offers for a
scheduled run: the ./gazette collect|read|publish|learn commands, web search and page fetches, writes in this
folder. Sending e-mail is never the agent's job; scripts/scheduled.py does it afterwards.
"""
import json
import shutil
from pathlib import Path

ENGINES = {
    "claude": {"name": "Claude Code", "exe": "claude", "cmd": "/gazette",
               "install": "https://code.claude.com/docs/en/setup"},
    "codex": {"name": "Codex", "exe": "codex", "cmd": "$gazette",
              "install": "https://developers.openai.com/codex/cli"},
    "antigravity": {"name": "Antigravity CLI", "exe": "agy", "cmd": "/gazette",
                    "install": "https://antigravity.google/docs/cli"},
}
DEFAULT = "claude"

# Claude Code: the exact tools an unattended edition may use.
CLAUDE_ALLOWED = [
    "Bash(./gazette collect:*)", "Bash(./gazette read:*)", "Bash(./gazette publish:*)", "Bash(./gazette learn:*)",
    "Bash(tail:*)", "Bash(head:*)", "Edit(./data/editions/**)", "WebSearch", "WebFetch", "Skill",
]
# Antigravity: headless runs soft-deny shell commands unless they are allowed in the user's settings.
AGY_SETTINGS = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
AGY_RULES = [f"command({launcher} {c})" for launcher in ("./gazette", ".\\gazette.cmd")
             for c in ("collect", "read", "publish", "learn")] + ["read_url(*)"]
SKILL_PROMPT = "Use the gazette skill in scheduled mode: follow .agents/skills/gazette/SKILL.md with the argument `scheduled`."


def engine_id(cfg):
    e = ((cfg or {}).get("run") or {}).get("engine") or DEFAULT
    return e if e in ENGINES else DEFAULT


def info(cfg):
    return ENGINES[engine_id(cfg)]


def find(eid):
    exe = ENGINES[eid]["exe"]
    found = shutil.which(exe)
    if found:
        return found
    home = Path.home()
    extra = [home / ".local/bin/claude.exe", home / ".claude/local/claude"] if eid == "claude" else []
    for c in extra + [home / ".local/bin" / exe, Path("/opt/homebrew/bin") / exe, Path("/usr/local/bin") / exe]:
        if c.exists():
            return str(c)
    return None


def scheduled_prompt(eid):
    if eid == "claude":
        return "/gazette scheduled"
    return ("$gazette " if eid == "codex" else "") + SKILL_PROMPT


def headless_command(eid, exe, prompt, model=None):
    """The command line for one unattended run of the agent."""
    if eid == "codex":
        cmd = [exe, "exec", "--sandbox", "workspace-write", "-c", "sandbox_workspace_write.network_access=true",
               "-c", 'web_search="live"']
        return cmd + (["-m", model] if model else []) + [prompt]
    if eid == "antigravity":
        return [exe, "-p", prompt, "--print-timeout", "90m"] + (["--model", model] if model else [])
    return [exe, "-p", prompt, "--allowedTools", *CLAUDE_ALLOWED] + (["--model", model] if model else [])


def agy_permissions(add=True):
    """Adds (or removes) exactly Gazette's rules in Antigravity's settings; returns what happened."""
    path = AGY_SETTINGS
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        allow = data.setdefault("permissions", {}).setdefault("allow", [])
    except (OSError, ValueError, AttributeError):
        return (f"Could not update {path}. Add these under permissions.allow yourself (or with /permissions in agy):\n  "
                + "\n  ".join(AGY_RULES))
    changed = [r for r in AGY_RULES if (r not in allow) == add]
    if not changed:
        return "Antigravity permissions: " + ("already in place." if add else "nothing to remove.")
    data["permissions"]["allow"] = allow + changed if add else [r for r in allow if r not in AGY_RULES]
    backup = path.with_name(path.name + ".gazette-backup")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"Antigravity permissions in {path}: {'added' if add else 'removed'} " + ", ".join(changed)
