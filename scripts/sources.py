"""Your source list: ready-made packs from catalog/sources.json plus your own sources.

Usage:  ./gazette sources packs                      list the catalog packs
        ./gazette sources init --packs ai-labs,security [--replace]
                                                    add packs to config/sources.json (--replace: start over;
                                                    without it your own custom sources are kept)
        ./gazette sources remove-pack <pack-id>      drop the sources that came from a pack
        ./gazette sources list                       what is in config/sources.json
        ./gazette sources test [--ids a,b] [--pack p] [--catalog]
                                                    fetch each source once and report items / errors
                                                    (--catalog tests the catalog instead of your list)

Source types (fields besides id, name, tier, topic): feed (url) · gnews (query, lang, country) ·
github_releases (repo) · hn (min_points, tags, query) · sitemap (url, include) · watch (url) ·
github_rising (days, language) · hf_models · hf_papers · devpost.  Details: docs/sources.md
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import DEFAULTS, HANDLERS, SOURCES  # noqa: E402
from common import CATALOG, TIERS, load_json, now_utc, parse_date, save_json, utf8_stdout  # noqa: E402

CATALOG_FILE = CATALOG / "sources.json"
GITHUB_HOURLY = 60


def catalog():
    return load_json(CATALOG_FILE, {"packs": []})


def pack_sources(pack):
    return [{**s, "topic": s.get("topic") or pack["title"], "pack": pack["id"]} for s in pack["sources"]]


def check(sources):
    """Problems a source list should not have."""
    err, ids = [], set()
    for s in sources:
        sid = s.get("id", "?")
        if sid in ids:
            err.append(f"duplicate id {sid}")
        ids.add(sid)
        if s.get("type") not in HANDLERS:
            err.append(f"{sid}: unknown type {s.get('type')}")
        if s.get("tier") not in TIERS:
            err.append(f"{sid}: tier must be one of {', '.join(TIERS)}")
        need = {"feed": "url", "sitemap": "url", "watch": "url", "gnews": "query", "github_releases": "repo"}.get(s.get("type"))
        if need and not s.get(need):
            err.append(f"{sid}: '{need}' is required for type {s['type']}")
    gh = sum(1 for s in sources if s.get("enabled", True) and s.get("type") in ("github_releases", "github_rising"))
    if gh > 40:
        err.append(f"{gh} GitHub sources: the keyless GitHub API allows {GITHUB_HOURLY} requests per hour; keep it under 40")
    return err


def cmd_packs(_):
    for p in catalog()["packs"]:
        print(f"{p['id']:<18} {len(p['sources']):>2} sources · {p['title']} — {p.get('desc', '')}")


def cmd_init(args):
    packs = {p["id"]: p for p in catalog()["packs"]}
    wanted = [x.strip() for x in (args.packs or "").split(",") if x.strip()]
    unknown = [w for w in wanted if w not in packs]
    if unknown:
        sys.exit(f"unknown packs: {', '.join(unknown)} (see ./gazette sources packs)")
    current = load_json(SOURCES, None) or {"defaults": catalog().get("defaults", {}), "sources": []}
    have = [] if args.replace else current["sources"]
    ids = {s["id"] for s in have}
    added = 0
    for w in wanted:
        for s in pack_sources(packs[w]):
            if s["id"] not in ids:
                have.append(s)
                ids.add(s["id"])
                added += 1
    current["sources"] = have
    problems = check(have)
    save_json(SOURCES, current)
    print(f"config/sources.json: {len(have)} sources ({added} added from {', '.join(wanted) or 'no packs'})")
    for p in problems:
        print(f"  WARNING {p}")


def cmd_remove_pack(args):
    current = load_json(SOURCES, None)
    if not current:
        sys.exit("config/sources.json does not exist yet")
    before = len(current["sources"])
    current["sources"] = [s for s in current["sources"] if s.get("pack") != args.pack]
    save_json(SOURCES, current)
    print(f"Removed {before - len(current['sources'])} sources of pack {args.pack}")


def cmd_list(_):
    current = load_json(SOURCES, None)
    if not current:
        sys.exit("config/sources.json does not exist yet")
    by_topic = {}
    for s in current["sources"]:
        by_topic.setdefault(s.get("topic", "Other"), []).append(s)
    for topic, group in by_topic.items():
        print(f"## {topic}")
        for s in group:
            off = "" if s.get("enabled", True) else " (off)"
            where = s.get("url") or s.get("repo") or s.get("query") or ""
            print(f"  {s['id']:<24} {s['type']:<16} {s['tier']:<10} {where}{off}")
    for p in check(current["sources"]):
        print(f"WARNING {p}")


def test_one(src, defaults):
    src = {**defaults, **src}
    ctx = {"state": {}, "seen": {}, "since": now_utc() - timedelta(days=7), "notes": [],
           "commit": {"sitemap": {}, "watch": {}, "silent": []}}
    try:
        items = HANDLERS[src["type"]](src, ctx)
    except Exception as e:
        return src, None, f"{type(e).__name__}: {str(e)[:100]}"
    if src["type"] == "watch":
        n = len(ctx["commit"]["watch"].get(src["id"], []))
        return src, f"{n} lines watched", None if n else "page has no readable text"
    if not items and src["type"] in ("gnews", "hn", "sitemap"):
        # These only return the last 7 days: a quiet topic is not a broken source.
        return src, "reachable, nothing in the last 7 days (quiet topic?)", None
    dates = [d for d in (parse_date(i["date"]) for i in items) if d]
    newest = max(dates).strftime("%Y-%m-%d") if dates else "undated"
    return src, f"{len(items)} items, newest {newest}", None if items else "no items"


def cmd_test(args):
    if args.catalog:
        cat = catalog()
        defaults = {**DEFAULTS, **cat.get("defaults", {})}
        sources = [s for p in cat["packs"] if not args.pack or p["id"] == args.pack for s in pack_sources(p)]
    else:
        current = load_json(SOURCES, None)
        if not current:
            sys.exit("config/sources.json does not exist yet (./gazette sources init --packs …)")
        defaults = {**DEFAULTS, **current.get("defaults", {})}
        sources = [s for s in current["sources"] if not args.pack or s.get("pack") == args.pack]
    if args.ids:
        wanted = set(args.ids.split(","))
        sources = [s for s in sources if s["id"] in wanted]
    with ThreadPoolExecutor(10) as ex:
        results = list(ex.map(lambda s: test_one(s, defaults), sources))
    bad = 0
    for src, info, err in results:
        if err:
            bad += 1
        print(f"{'FAIL' if err else 'ok  '} {src['id']:<24} {err or info}")
    print(f"\n{len(results) - bad}/{len(results)} sources work")
    sys.exit(1 if bad else 0)


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser(description="Manage your source list.")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("packs")
    p = sub.add_parser("init")
    p.add_argument("--packs", default="")
    p.add_argument("--replace", action="store_true")
    p = sub.add_parser("remove-pack")
    p.add_argument("pack")
    sub.add_parser("list")
    p = sub.add_parser("test")
    p.add_argument("--ids")
    p.add_argument("--pack")
    p.add_argument("--catalog", action="store_true")
    args = ap.parse_args()
    handler = {"packs": cmd_packs, "init": cmd_init, "remove-pack": cmd_remove_pack, "list": cmd_list,
               "test": cmd_test}.get(args.cmd)
    if not handler:
        print(__doc__)
        sys.exit(2)
    handler(args)


if __name__ == "__main__":
    main()
