"""Prints the main text of a web page (so the editor can read the primary source).

Usage:  ./gazette read URL [max_chars=7000]
Pages rendered by JavaScript may come back empty; use WebFetch for those.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import clean_text, fetch, html_lines, utf8_stdout  # noqa: E402


def meta(page, *names):
    for n in names:
        m = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*content=["\']([^"\']+)' % re.escape(n), page, re.I)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']%s["\']' % re.escape(n), page, re.I)
        if m:
            return clean_text(m.group(1))
    return ""


def main_block(page):
    # Longest <article>, else <main>, else <body>; navigation and footer blocks are dropped.
    page = re.sub(r"(?is)<(nav|header|footer|aside|form)[^>]*>.*?</\1>", " ", page)
    for tag in ("article", "main"):
        blocks = re.findall(r"(?is)<%s[^>]*>(.*?)</%s>" % (tag, tag), page)
        if blocks:
            best = max(blocks, key=len)
            if len(clean_text(best)) > 400:
                return best
    m = re.search(r"(?is)<body[^>]*>(.*)</body>", page)
    return m.group(1) if m else page


def main():
    utf8_stdout()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    url = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 7000
    page = fetch(url, limit=8_000_000).decode("utf-8", "replace")
    if page.lstrip().startswith(("{", "[")):
        print(page[:limit])
        return
    title = meta(page, "og:title") or clean_text((re.search(r"(?is)<title[^>]*>(.*?)</title>", page) or [None, ""])[1])
    published = meta(page, "article:published_time", "og:published_time", "date", "publish-date", "parsely-pub-date")
    desc = meta(page, "og:description", "description")
    body = "\n".join(html_lines(main_block(page), min_len=2))
    print(f"TITLE: {title}")
    if published:
        print(f"PUBLISHED: {published}")
    if desc:
        print(f"SUMMARY: {desc}")
    print(f"URL: {url}\n")
    print(body[:limit] + ("\n…[truncated]" if len(body) > limit else ""))


if __name__ == "__main__":
    main()
