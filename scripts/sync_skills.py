"""Copies the skills to .agents/skills/, where Codex and Antigravity CLI look for them.

.claude/skills/<name>/ is the source (Claude Code reads it). Run this after editing a skill:
    python scripts/sync_skills.py           write the copies
    python scripts/sync_skills.py --check   exit 1 if a copy is out of date
Claude-only frontmatter keys (argument-hint) are left out of the copies.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, DST = ROOT / ".claude" / "skills", ROOT / ".agents" / "skills"
CLAUDE_ONLY = re.compile(r"\nargument-hint:[^\n]*")


def wanted():
    out = {}
    for f in sorted(SRC.rglob("*")):
        if f.is_file():
            data = f.read_bytes()
            if f.name == "SKILL.md":
                head, sep, body = data.decode("utf-8").partition("\n---\n")
                data = (CLAUDE_ONLY.sub("", head) + sep + body).encode("utf-8")
            out[DST / f.relative_to(SRC)] = data
    return out


def main():
    files = wanted()
    stale = [p for p, data in files.items() if not p.exists() or p.read_bytes() != data]
    extra = [p for p in DST.rglob("*") if p.is_file() and p not in files] if DST.exists() else []
    if "--check" in sys.argv:
        for p in stale + extra:
            print(f"out of date: {p.relative_to(ROOT)}")
        sys.exit(1 if stale or extra else 0)
    for p in stale:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(files[p])
        print(f"wrote {p.relative_to(ROOT)}")
    for p in extra:
        p.unlink()
        print(f"removed {p.relative_to(ROOT)}")
    if not stale and not extra:
        print("Skills already in sync.")


if __name__ == "__main__":
    main()
