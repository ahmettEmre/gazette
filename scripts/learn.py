"""Learning tracks: which lesson the editor writes next, and your progress.

Usage:  ./gazette learn next [--json]      lessons to write into this edition
        ./gazette learn status             progress per track
        ./gazette learn reset <track-id>   start a track again
Tracks live in config/learning.json (written by /gazette-setup). Progress lives in state/learning.json and
moves forward only when an edition containing the lesson is published.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONFIG, STATE, iso, load_json, now_utc, save_json, utf8_stdout  # noqa: E402

LEARNING = CONFIG / "learning.json"
PROGRESS = STATE / "learning.json"


def tracks():
    cfg = load_json(LEARNING, {})
    return cfg.get("tracks", []), max(0, int(cfg.get("per_edition", 1)))


def next_lessons():
    """Next lesson of the tracks that waited longest; as many tracks as per_edition allows."""
    ts, per = tracks()
    prog = load_json(PROGRESS, {})
    waiting = []
    for order, t in enumerate(ts):
        done = set(prog.get(t["id"], {}).get("done", []))
        nxt = next((n for n in range(1, len(t["lessons"]) + 1) if n not in done), None)
        if nxt:
            waiting.append((prog.get(t["id"], {}).get("last") or "", order, t, nxt, done))
    waiting.sort(key=lambda w: (w[0], w[1]))
    return [{"track": t["id"], "track_title": t["title"], "n": n, "total": len(t["lessons"]),
             "title": t["lessons"][n - 1], "level": t.get("level", ""), "goal": t.get("goal", ""),
             "done": [t["lessons"][i - 1] for i in sorted(done) if i <= len(t["lessons"])]}
            for _, _, t, n, done in waiting[:per]]


def validate_lessons(lessons):
    err = []
    known = {t["id"]: t for t in tracks()[0]}
    if lessons and not isinstance(lessons, list):
        return ["lessons must be a list"]
    for k, les in enumerate(lessons or []):
        w = f"lessons[{k}]"
        t = known.get(les.get("track"))
        if not t:
            err.append(f"{w}: track '{les.get('track')}' is not in config/learning.json")
            continue
        if not isinstance(les.get("n"), int) or not 1 <= les["n"] <= len(t["lessons"]):
            err.append(f"{w}: n must be a lesson number between 1 and {len(t['lessons'])}")
        for f in ("title", "body"):
            if not (isinstance(les.get(f), str) and les[f].strip()):
                err.append(f"{w}: '{f}' is empty or not text")
        if not all(isinstance(p, str) and p.strip() for p in les.get("key_points") or []):
            err.append(f"{w}: key_points must be a list of texts")
        srcs = les.get("sources")
        if not isinstance(srcs, list) or not srcs:
            err.append(f"{w}: at least one source is required")
        elif any(not str(s.get("url", "")).startswith("http") or not s.get("name") for s in srcs):
            err.append(f"{w}: every source needs a name and an http(s) url")
    return err


def annotate(lessons):
    known = {t["id"]: t for t in tracks()[0]}
    for les in lessons:
        t = known[les["track"]]
        les["track_title"], les["total"] = t["title"], len(t["lessons"])
    return lessons


def mark_done(lessons):
    if not lessons:
        return
    prog = load_json(PROGRESS, {})
    for les in lessons:
        p = prog.setdefault(les["track"], {"done": []})
        if les["n"] not in p["done"]:
            p["done"] = sorted(p["done"] + [les["n"]])
        p["last"] = iso(now_utc())
    save_json(PROGRESS, prog)


def main():
    utf8_stdout()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    ts, per = tracks()
    if not ts:
        print("No learning tracks. Add some with /gazette-setup (config/learning.json).")
        return
    if cmd == "next":
        nxt = next_lessons()
        if "--json" in sys.argv:
            print(json.dumps(nxt, ensure_ascii=False, indent=2))
        elif not nxt:
            print("All tracks are complete. Suggest new topics to the reader (/gazette-setup → learning).")
        else:
            print("Write these lessons into the edition's \"lessons\" list:")
            for les in nxt:
                print(f"- track: {les['track']} · n: {les['n']} (of {les['total']}) · title: {les['title']}")
                print(f"  level: {les['level'] or '-'} · goal: {les['goal'] or '-'}")
                if les["done"]:
                    print("  already covered: " + "; ".join(les["done"]))
    elif cmd == "status":
        prog = load_json(PROGRESS, {})
        for t in ts:
            done = len(prog.get(t["id"], {}).get("done", []))
            print(f"{t['id']}: {done}/{len(t['lessons'])} · {t['title']}")
        print(f"Lessons per edition: {per}")
    elif cmd == "reset" and len(sys.argv) > 2:
        prog = load_json(PROGRESS, {})
        prog.pop(sys.argv[2], None)
        save_json(PROGRESS, prog)
        print(f"Track {sys.argv[2]} starts again from lesson 1.")
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
