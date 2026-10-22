"""Collector: pulls candidate stories from the configured sources and writes a digest for the editor.

No AI and no API keys. It never writes to state/: seen items, watch snapshots and sitemap lists go into
the raw file, and publish.py commits them once an edition is published. Re-running is always safe.

Usage:  ./gazette collect [--hours 48] [--only id1,id2]
"""
import argparse
import json
import math
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CONFIG, RAW, STATE, TIER_MARK, clean_text, fetch, html_lines, iso, load_json,  # noqa: E402
                    norm_url, now_local, now_utc, parse_date, save_json, short_id, utf8_stdout)

SOURCES = CONFIG / "sources.json"
DEFAULTS = {"max": 8, "summary_chars": 260, "first_window_hours": 72, "max_window_days": 8}


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


_ENTITY = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)([a-zA-Z][a-zA-Z0-9]*);")


def parse_xml(body):
    try:
        return ET.fromstring(body)
    except ET.ParseError:
        # RSS often carries HTML entities (&nbsp; …) that XML does not know.
        import html as _h
        text = body.decode("utf-8", "replace")
        text = _ENTITY.sub(lambda m: _h.unescape(m.group(0)).replace("&", "&amp;"), text)
        return ET.fromstring(text.encode("utf-8"))


_MD_LINK = re.compile(r"\[([^\]]*)\]\((?:https?://)?[^)\s]+\)")
_MD_NOISE = re.compile(r"\(\s*[0-9a-f]{7,40}\s*\)|\(#\d+\)|\bby @[\w-]+ in https?://\S+|https?://github\.com/\S+")


def squash_md(s):
    # Release notes are full of link/commit/PR noise that bloats the digest; keep the text only.
    s = _MD_LINK.sub(r"\1", clean_text(s))
    s = _MD_NOISE.sub("", s)
    return re.sub(r"[#*]{2,}\s*|\s{2,}", " ", s).strip()


def item(src, title, url, date, summary="", **meta):
    summary = squash_md(summary)
    lim = src.get("summary_chars")
    if lim and len(summary) > lim:
        summary = summary[:lim].rsplit(" ", 1)[0] + "…"
    return {
        "id": short_id(norm_url(url)), "src": src["id"], "src_name": src["name"],
        "tier": src["tier"], "topic": src.get("topic", "Other"), "title": clean_text(title, 220), "url": url.strip(),
        "date": iso(date), "summary": summary,
        "meta": {k: v for k, v in meta.items() if v not in (None, "", [])},
    }


# ---------------------------------------------------------------- source types

def do_feed(src, ctx):
    root = parse_xml(fetch(src["url"]))
    out = []
    for e in root.iter():
        if local(e.tag) not in ("item", "entry"):
            continue
        f = {"title": "", "link": "", "date": None, "summary": ""}
        for c in e:
            n = local(c.tag)
            if n == "title":
                f["title"] = "".join(c.itertext())
            elif n == "link":
                href = c.get("href")
                if href and (c.get("rel") in (None, "alternate")) and not f["link"]:
                    f["link"] = href
                elif not href and c.text and not f["link"]:
                    f["link"] = c.text.strip()
            elif n in ("pubDate", "published", "date", "issued") and f["date"] is None:
                f["date"] = parse_date(c.text)
            elif n == "updated" and f["date"] is None:
                f["date"] = parse_date(c.text)
            elif n in ("description", "summary") and not f["summary"]:
                f["summary"] = "".join(c.itertext())
            elif n in ("encoded", "content") and not f["summary"]:
                f["summary"] = "".join(c.itertext())
        if f["title"] and f["link"]:
            out.append(item(src, f["title"], f["link"], f["date"], f["summary"]))
    return out


def do_gnews(src, ctx):
    # Google News search RSS: covers any topic in any language. Links point to news.google.com,
    # so the editor has to find the original article before relying on it (the summary says so).
    lang, country = src.get("lang", "en"), src.get("country", "US").upper()
    days = max(1, math.ceil((now_utc() - ctx["since"]).total_seconds() / 86400))
    q = urllib.parse.quote(f"{src['query']} when:{days}d")
    url = f"https://news.google.com/rss/search?q={q}&hl={lang}-{country}&gl={country}&ceid={country}:{lang}"
    root = parse_xml(fetch(url))
    out = []
    for e in root.iter("item"):
        title, link = e.findtext("title") or "", (e.findtext("link") or "").strip()
        pub_el = e.find("source")
        pub = (pub_el.text or "").strip() if pub_el is not None else ""
        if pub and title.endswith(" - " + pub):
            title = title[: -len(pub) - 3]
        if title and link:
            out.append(item(src, title, link, parse_date(e.findtext("pubDate")),
                            "Google News result; find the publisher's original article before using it.", publisher=pub))
    return out


def do_sitemap(src, ctx):
    root = parse_xml(fetch(src["url"]))
    inc, upd = src.get("include", []), src.get("track_updates", [])
    exc = re.compile(src["exclude_url"]) if src.get("exclude_url") else None
    current = {}
    for u in root.iter():
        if local(u.tag) != "url":
            continue
        loc = lastmod = None
        for c in u:
            if local(c.tag) == "loc":
                loc = (c.text or "").strip()
            elif local(c.tag) == "lastmod":
                lastmod = (c.text or "").strip()
        if loc and any(p in loc for p in inc) and not (exc and exc.search(loc)):
            current[loc] = lastmod or ""
    known = ctx["state"].get("sitemaps", {}).get(src["id"])
    ctx["commit"]["sitemap"][src["id"]] = current
    out = []
    for loc, lm in current.items():
        d = parse_date(lm)
        slug = loc.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
        section = loc.split("/")[3] if loc.count("/") >= 3 else ""
        if known is None:
            # First run: only pages updated inside the window.
            if d and d >= ctx["since"]:
                out.append(item(src, f"[{section}] {slug}", loc, d, "Recently updated page in the sitemap (title taken from the URL)."))
        elif loc not in known:
            out.append(item(src, f"[{section}] {slug}", loc, d, "NEW page in the sitemap (title taken from the URL)."))
        elif lm and lm != known.get(loc) and any(p in loc for p in upd):
            it = item(src, f"Updated: [{section}] {slug}", loc, d, "Existing page was updated (lastmod changed).")
            it["id"] = short_id(norm_url(loc), lm)
            out.append(it)
    return out


def do_watch(src, ctx):
    lines = html_lines(fetch(src["url"]).decode("utf-8", "replace"))
    ctx["commit"]["watch"][src["id"]] = lines
    old = ctx["state"].get("watch", {}).get(src["id"])
    if old is None:
        ctx["notes"].append(f"{src['id']}: first snapshot taken; changes show up from the next edition on.")
        return []
    oldset, seen, added = set(old), set(), []
    for line in lines:
        if line not in oldset and line not in seen:
            seen.add(line)
            added.append(line)
    if not added:
        return []
    note = " (the page may have been redesigned)" if len(added) > 150 else ""
    it = item(src, f"{src['name']}: {len(added)} new lines{note}", src["url"], now_utc())
    it["summary"] = " ⏎ ".join(added[:40])[:3000]
    it["id"] = short_id(src["id"], *added[:40])
    return [it]


def do_hn(src, ctx):
    ts = int(ctx["since"].timestamp())
    query = f"&query={urllib.parse.quote(src['query'])}" if src.get("query") else ""
    url = ("https://hn.algolia.com/api/v1/search_by_date?tags={t}&hitsPerPage=200{q}"
           "&numericFilters=created_at_i>{ts},points>{p}").format(t=src.get("tags", "story"), q=query, ts=ts,
                                                                  p=src.get("min_points", 100))
    hits = json.loads(fetch(url))["hits"]
    hits.sort(key=lambda h: h.get("points") or 0, reverse=True)
    out = []
    for h in hits:
        disc = f"https://news.ycombinator.com/item?id={h['objectID']}"
        out.append(item(src, h.get("title") or "", h.get("url") or disc, parse_date(h.get("created_at")),
                        clean_text(h.get("story_text") or "", 200), points=h.get("points"),
                        comments=h.get("num_comments"), discussion=disc))
    return out


def do_github_rising(src, ctx):
    since = (now_utc() - timedelta(days=src.get("days", 7))).strftime("%Y-%m-%d")
    lang = f"+language:{urllib.parse.quote(src['language'])}" if src.get("language") else ""
    url = f"https://api.github.com/search/repositories?q=created:%3E{since}{lang}&sort=stars&order=desc&per_page=30"
    data = json.loads(fetch(url))
    return [item(src, r["full_name"], r["html_url"], parse_date(r.get("created_at")), r.get("description") or "",
                 stars=r.get("stargazers_count"), language=r.get("language"))
            for r in data.get("items", [])]


def do_github_releases(src, ctx):
    # The keyless API (60 requests/hour) is steadier than the Atom feed and flags pre-releases.
    data = json.loads(fetch(f"https://api.github.com/repos/{src['repo']}/releases?per_page=15"))
    out = []
    for r in data:
        if r.get("draft") or (r.get("prerelease") and not src.get("prerelease")):
            continue
        name = r.get("name") or r.get("tag_name") or ""
        out.append(item(src, f"{src['repo'].split('/')[-1]} {name}".strip(), r["html_url"],
                        parse_date(r.get("published_at")), r.get("body") or ""))
    return out


def do_hf_models(src, ctx):
    data = json.loads(fetch("https://huggingface.co/api/models?sort=trendingScore&limit=40"))
    return [item(src, m["id"], f"https://huggingface.co/{m['id']}", parse_date(m.get("createdAt")),
                 m.get("pipeline_tag") or "", likes=m.get("likes"), downloads=m.get("downloads"))
            for m in data]


def do_hf_papers(src, ctx):
    data = json.loads(fetch("https://huggingface.co/api/daily_papers?limit=50"))
    out = []
    for p in data:
        paper = p.get("paper") or {}
        pid = paper.get("id")
        if not pid:
            continue
        out.append(item(src, paper.get("title") or p.get("title") or pid, f"https://huggingface.co/papers/{pid}",
                        parse_date(p.get("publishedAt") or paper.get("publishedAt")), paper.get("summary") or "",
                        upvotes=paper.get("upvotes")))
    out.sort(key=lambda i: i["meta"].get("upvotes") or 0, reverse=True)
    return out


def do_devpost(src, ctx):
    data = json.loads(fetch("https://devpost.com/api/hackathons?status[]=upcoming&status[]=open&order_by=prize-amount&per_page=30"))
    out = []
    for h in data.get("hackathons", []):
        themes = ", ".join(t.get("name", "") for t in h.get("themes", []))
        out.append(item(src, h.get("title", ""), h.get("url", ""), None,
                        f"{h.get('organization_name') or ''} · themes: {themes}",
                        prize=clean_text(h.get("prize_amount") or ""), dates=h.get("submission_period_dates"),
                        left=h.get("time_left_to_submission"), registrations=h.get("registrations_count"),
                        location=(h.get("displayed_location") or {}).get("location")))
    return out


HANDLERS = {"feed": do_feed, "gnews": do_gnews, "sitemap": do_sitemap, "watch": do_watch, "hn": do_hn,
            "github_rising": do_github_rising, "github_releases": do_github_releases,
            "hf_models": do_hf_models, "hf_papers": do_hf_papers, "devpost": do_devpost}
# Ranked rather than dated sources: no time window, 'seen' prevents repeats.
WINDOWLESS = {"github_rising", "hf_models", "hf_papers", "devpost", "sitemap", "watch"}
RANKED = {"hn", "github_rising", "hf_models", "hf_papers", "devpost"}


def run_source(src, ctx, defaults):
    src = {**defaults, **src}
    try:
        items = HANDLERS[src["type"]](src, ctx)
    except Exception as e:  # one broken source never stops the edition
        return src, [], f"{type(e).__name__}: {str(e)[:120]}"
    if src.get("exclude"):
        rx = re.compile(src["exclude"])
        items = [i for i in items if not rx.search(i["title"])]
    ok_once = src["id"] in ctx["state"].get("sources_ok", [])
    kept = []
    for i in items:
        if i["id"] in ctx["seen"]:
            continue
        if src["type"] not in WINDOWLESS:
            d = parse_date(i["date"])
            if d is None:
                if not ok_once:  # undated feed, first run: take a baseline, show nothing
                    ctx["commit"]["silent"].append(i["id"])
                    continue
            elif d < ctx["since"]:
                continue
        kept.append(i)
    if src["type"] not in RANKED:
        kept.sort(key=lambda i: i["date"] or "", reverse=True)
    return src, kept[: src["max"]], None


def load_sources(path=SOURCES):
    cfg = load_json(path, None)
    if cfg is None:
        sys.exit(f"{path.name} not found. Run /gazette-setup (or ./gazette sources init --packs …) first.")
    return {**DEFAULTS, **cfg.get("defaults", {})}, [s for s in cfg.get("sources", []) if s.get("enabled", True)]


# ---------------------------------------------------------------- digest

def fmt_meta(m):
    parts = []
    if "points" in m: parts.append(f"▲{m['points']} 💬{m.get('comments', 0)}")
    if "stars" in m: parts.append(f"★{m['stars']}" + (f" {m['language']}" if m.get("language") else ""))
    if "likes" in m: parts.append(f"♥{m['likes']} ⬇{m.get('downloads', 0)}")
    if "upvotes" in m: parts.append(f"▲{m['upvotes']}")
    if "publisher" in m: parts.append(f"publisher {m['publisher']}")
    if "prize" in m: parts.append(f"prize {m['prize']}")
    if "dates" in m: parts.append(f"submissions {m['dates']}")
    if "left" in m: parts.append(f"left {m['left']}")
    if "location" in m: parts.append(m["location"])
    if "discussion" in m: parts.append(f"discussion {m['discussion']}")
    if "also" in m: parts.append("also: " + ", ".join(m["also"]))
    return " · ".join(parts)


def write_digest(raw, path, topic_order):
    by_topic = {}
    for i in raw["items"]:
        by_topic.setdefault(i["topic"], []).append(i)
    lines = [f"# Gazette candidates — edition {raw['id']}",
             f"Window: {raw['window_from']} → {raw['created']} · {len(raw['items'])} candidates",
             "Tier: [O] official source · [P] press · [C] community/independent. Dates are UTC.", ""]
    failed = {k: v["error"] for k, v in raw["sources"].items() if v["error"]}
    if failed:
        lines.append("Unreachable sources: " + "; ".join(f"{k} ({v})" for k, v in failed.items()))
    for n in raw["notes"]:
        lines.append(f"Note: {n}")
    lines.append("")
    for t in topic_order + [t for t in by_topic if t not in topic_order]:
        group = by_topic.get(t)
        if not group:
            continue
        lines.append(f"## {t} ({len(group)})")
        for i in group:
            d = (i["date"] or "")[5:16].replace("T", " ") or "undated"
            lines.append(f"- {i['id']} | {d} | {i['src_name']} [{TIER_MARK[i['tier']]}] | {i['title']}")
            meta = fmt_meta(i["meta"])
            lines.append(f"  {i['url']}" + (f" | {meta}" if meta else ""))
            if i["summary"]:
                lines.append(f"  > {i['summary']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- main

def main():
    utf8_stdout()
    ap = argparse.ArgumentParser(description="Collect candidate stories into raw/<id>.md")
    ap.add_argument("--hours", type=int, help="set the time window by hand (hours)")
    ap.add_argument("--only", help="only these source ids (comma separated)")
    args = ap.parse_args()

    defaults, sources = load_sources()
    state = load_json(STATE / "state.json", {})
    seen = load_json(STATE / "seen.json", {})
    now = now_utc()
    if args.hours:
        since = now - timedelta(hours=args.hours)
    elif state.get("last_publish"):
        since = max(parse_date(state["last_publish"]) - timedelta(hours=12),
                    now - timedelta(days=defaults["max_window_days"]))
    else:
        since = now - timedelta(hours=defaults["first_window_hours"])

    if args.only:
        wanted = set(args.only.split(","))
        sources = [s for s in sources if s["id"] in wanted]
    topic_order = list(dict.fromkeys(s.get("topic", "Other") for s in sources))

    ctx = {"state": state, "seen": seen, "since": since, "notes": [],
           "commit": {"sitemap": {}, "watch": {}, "silent": []}}
    with ThreadPoolExecutor(12) as ex:
        results = list(ex.map(lambda s: run_source(s, ctx, defaults), sources))

    items, src_report, by_id = [], {}, {}
    for src, got, err in results:
        src_report[src["id"]] = {"count": len(got), "error": err}
        for i in got:
            if i["id"] in by_id:  # same URL from several sources: one candidate, merged sources
                prev = by_id[i["id"]]
                prev["meta"].setdefault("also", []).append(f"{i['src_name']} [{TIER_MARK[i['tier']]}]")
                for k, v in i["meta"].items():
                    prev["meta"].setdefault(k, v)
                continue
            by_id[i["id"]] = i
            items.append(i)

    stamp = now_local().strftime("%Y-%m-%d_%H%M")
    raw = {"id": stamp, "created": iso(now), "window_from": iso(since), "items": items,
           "sources": src_report, "notes": ctx["notes"],
           "commit": {**ctx["commit"], "sources_ok": [k for k, v in src_report.items() if not v["error"]]}}
    RAW.mkdir(parents=True, exist_ok=True)
    save_json(RAW / f"{stamp}.json", raw, pretty=False)
    digest = RAW / f"{stamp}.md"
    write_digest(raw, digest, topic_order)

    # Raw files older than 21 days go (published editions live under data/).
    for old in RAW.glob("*.*"):
        if (now.timestamp() - old.stat().st_mtime) > 21 * 86400:
            old.unlink(missing_ok=True)

    ok = sum(1 for v in src_report.values() if not v["error"])
    print(f"Edition id: {stamp}")
    print(f"Window: {iso(since)} → {iso(now)}")
    print(f"Sources: {ok}/{len(src_report)} worked · candidates: {len(items)}")
    for k, v in src_report.items():
        if v["error"]:
            print(f"  ERROR {k}: {v['error']}")
    print(f"Digest: raw/{stamp}.md")


if __name__ == "__main__":
    main()
