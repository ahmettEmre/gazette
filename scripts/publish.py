"""Publisher: validates the edition the editor wrote, builds the reader files and commits state.

Usage:  ./gazette publish data/editions/2026-10-12_1530.json [--open]
        ./gazette publish --rebuild        (only rebuild the archive index and the reader settings)

On errors nothing is written: the errors are listed and the exit code is 1. Fix the file and run again.
Re-running is safe: the same raw file is never committed twice, a lesson never counts twice.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import learn  # noqa: E402
from common import (DATA, EDITIONS, RAW, ROOT, STATE, TIERS, TOP, brand, iso, labels, load_json,  # noqa: E402
                    load_settings, now_utc, parse_date, save_json, sections, utf8_stdout)

ID_RX = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}$")
SLUG_RX = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


def validate(ed, section_ids):
    err = []

    def req(o, k, where):
        if not (isinstance(o.get(k), str) and o[k].strip()):
            err.append(f"{where}: '{k}' is empty or not text")

    if not ID_RX.match(str(ed.get("id", ""))):
        err.append("id must look like YYYY-MM-DD_HHMM")
    for k in ("created", "headline", "big_picture"):
        req(ed, k, "edition")
    if ed.get("created") and not parse_date(ed["created"]):
        err.append("created is not an ISO date")
    items = ed.get("items")
    if not isinstance(items, list) or not items:
        err.append("items is empty")
        items = []
    ids = set()
    for n, it in enumerate(items):
        w = f"items[{n}] ({it.get('id', '?')})"
        if not SLUG_RX.match(str(it.get("id", ""))):
            err.append(f"{w}: id must be lowercase letters, digits and dashes")
        elif it["id"] in ids:
            err.append(f"{w}: id is used twice")
        ids.add(it.get("id"))
        if it.get("section") not in section_ids:
            err.append(f"{w}: section must be one of: {', '.join(section_ids)}")
        for k in ("title", "what", "why_you", "take"):
            req(it, k, w)
        for k in ("importance", "hype"):
            if not isinstance(it.get(k), int) or not 1 <= it[k] <= 5:
                err.append(f"{w}: {k} must be a whole number from 1 to 5")
        if it.get("tier") not in TIERS:
            err.append(f"{w}: tier must be {'|'.join(TIERS)}")
        if not isinstance(it.get("verified"), bool):
            err.append(f"{w}: verified must be true or false")
        if it.get("published") and not parse_date(it["published"]):
            err.append(f"{w}: published is not an ISO date")
        if it.get("deadline") and not parse_date(it["deadline"]):
            err.append(f"{w}: deadline is not an ISO date")
        srcs = it.get("sources")
        if not isinstance(srcs, list) or not srcs:
            err.append(f"{w}: at least one source is required")
        else:
            for s in srcs:
                if not str(s.get("url", "")).startswith("http") or not s.get("name"):
                    err.append(f"{w}: every source needs a name and an http(s) url")
                if s.get("tier") and s["tier"] not in TIERS:
                    err.append(f"{w}: source tier is invalid")
        for t in it.get("terms", []) or []:
            if not (t.get("term") and t.get("explain")):
                err.append(f"{w}: every terms entry needs term and explain")
        if it.get("section") == TOP and not it.get("verified"):
            err.append(f"{w}: only verified items may go into the '{TOP}' section")
    for n, c in enumerate(ed.get("concepts", []) or []):
        for k in ("term", "short", "long"):
            req(c, k, f"concepts[{n}]")
    return err


def write_js(path, fn, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"window.{fn}({json.dumps(obj, ensure_ascii=False)});\n", encoding="utf-8")


def write_site(cfg):
    """Reader settings: brand, language, labels and the current sections (old editions carry their own)."""
    lang = cfg.get("language", "en")
    site = {"brand": brand(cfg), "lang": lang, "locale": cfg.get("locale") or lang,
            "labels": labels(cfg), "sections": sections(cfg), "generated": iso(now_utc())}
    write_js(DATA / "site.js", "__gazetteSite", site)


def rebuild_index():
    entries = []
    for f in sorted(EDITIONS.glob("*.json"), reverse=True):
        ed = load_json(f, None)
        if not ed or not ID_RX.match(ed.get("id", "")):
            continue
        counts = {}
        for it in ed["items"]:
            counts[it["section"]] = counts.get(it["section"], 0) + 1
        entries.append({"id": ed["id"], "created": ed["created"], "headline": ed["headline"],
                        "n": len(ed["items"]), "counts": counts,
                        "top": [it["title"] for it in ed["items"] if it["section"] == TOP][:5]})
    index = {"generated": iso(now_utc()), "editions": entries}
    save_json(DATA / "index.json", index)
    write_js(DATA / "index.js", "__gazetteIndex", index)
    return entries


def commit_state(raw_id):
    state = load_json(STATE / "state.json", {})
    if raw_id in state.get("committed_raw", []):
        return "raw file already committed"
    raw = load_json(RAW / f"{raw_id}.json", None)
    if raw is None:
        return f"WARNING: raw/{raw_id}.json not found; seen items were not recorded"
    seen = load_json(STATE / "seen.json", {})
    stamp = raw["created"]
    for it in raw["items"]:
        seen.setdefault(it["id"], stamp)
    for sid in raw["commit"].get("silent", []):
        seen.setdefault(sid, stamp)
    state.setdefault("sitemaps", {}).update(raw["commit"].get("sitemap", {}))
    state.setdefault("watch", {}).update(raw["commit"].get("watch", {}))
    state["sources_ok"] = sorted(set(state.get("sources_ok", [])) | set(raw["commit"].get("sources_ok", [])))
    state["last_publish"] = raw["created"]
    state["committed_raw"] = (state.get("committed_raw", []) + [raw_id])[-60:]
    # Keep the seen list from growing forever: drop entries older than 120 days.
    cutoff = now_utc().timestamp() - 120 * 86400
    seen = {k: v for k, v in seen.items() if (parse_date(v) or now_utc()).timestamp() > cutoff}
    save_json(STATE / "seen.json", seen, pretty=False)
    save_json(STATE / "state.json", state, pretty=False)
    return f"{len(raw['items'])} candidates marked as seen"


def main():
    utf8_stdout()
    cfg = load_settings()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--rebuild" in sys.argv:
        write_site(cfg)
        print(f"Index: {len(rebuild_index())} editions")
        return
    if not args:
        print(__doc__)
        sys.exit(2)
    path = Path(args[0])
    if not path.is_absolute():
        path = ROOT / path
    try:
        ed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Broken JSON: {e}")
        sys.exit(1)
    secs = sections(cfg)
    errors = validate(ed, [s["id"] for s in secs]) + learn.validate_lessons(ed.get("lessons") or [])
    if errors:
        print(f"{len(errors)} errors, nothing published:")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    raw = load_json(RAW / f"{ed.get('raw') or ed['id']}.json", None)
    if raw:  # never trust the editor with the clock: avoids time zone mistakes
        ed["created"] = raw["created"]
        ed["window_from"] = raw["window_from"]
    for it in ed["items"]:
        it["uid"] = f"{ed['id']}/{it['id']}"
    used = {it["section"] for it in ed["items"]}
    ed["sections"] = [s for s in secs if s["id"] in used]  # old editions keep rendering after sections change
    ed["lang"] = cfg.get("language", "en")
    learn.annotate(ed.get("lessons") or [])
    order = {s["id"]: n for n, s in enumerate(secs)}
    ed["items"].sort(key=lambda it: (order[it["section"]], -it["importance"]))
    save_json(EDITIONS / f"{ed['id']}.json", ed)
    write_js(EDITIONS / f"{ed['id']}.js", "__gazetteEdition", ed)
    write_site(cfg)
    entries = rebuild_index()
    msg = commit_state(ed.get("raw") or ed["id"])
    learn.mark_done(ed.get("lessons") or [])
    print(f"Published: {ed['id']} · {len(ed['items'])} items · {len(entries)} editions in the archive · {msg}")
    if "--open" in sys.argv:
        from open_reader import open_reader
        open_reader()


if __name__ == "__main__":
    main()
