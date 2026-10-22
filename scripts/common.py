"""Shared helpers for the Gazette scripts: paths, settings, labels, HTTP, dates and HTML→text.

Standard library only. Every script calls utf8_stdout() so non-ASCII output survives Windows consoles.
"""
import email.utils
import gzip
import hashlib
import html
import http.cookiejar
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
STATE = ROOT / "state"
RAW = ROOT / "raw"
DATA = ROOT / "data"
EDITIONS = DATA / "editions"
OUT = ROOT / "out"
LOGS = ROOT / "logs"
CATALOG = ROOT / "catalog"
I18N = ROOT / "i18n"
SETTINGS = CONFIG / "settings.json"
READER = ROOT / "gazette.html"

TIERS = ("official", "press", "community")
TIER_MARK = {"official": "O", "press": "P", "community": "C"}
TOP = "top"  # fixed id of the must-know section; only verified items go there

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 Gazette/1.0")

_host_locks = defaultdict(threading.Lock)
_host_last = defaultdict(float)
# Minimum gap (seconds) between two requests to hosts that answer 429 quickly.
_HOST_GAP = {"www.reddit.com": 10.0, "news.google.com": 1.5}


def utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def fetch(url, timeout=25, limit=15_000_000, retries=2):
    """Fetches a URL as bytes. Requests to the same host run one at a time (politeness + fewer 429s)."""
    parts = urllib.parse.urlsplit(url)
    # Web only: urllib would also open file:// URLs, and an unattended run that follows instructions
    # planted in a web page could otherwise be tricked into reading local files.
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"only http(s) URLs can be read: {url[:80]}")
    host = parts.netloc
    last = None
    for attempt in range(retries + 1):
        with _host_locks[host]:
            wait = _host_last[host] + _HOST_GAP.get(host, 0) - time.time()
            if wait > 0:
                time.sleep(wait)
            try:
                # A cookie jar is required: some pages set a cookie and redirect (ai.google.dev).
                opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
                with opener.open(req, timeout=timeout) as r:
                    body = r.read(limit)
                # Some servers send gzip even when it was not requested.
                return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
            except urllib.error.HTTPError as e:
                last = e
                if e.code not in (429, 500, 502, 503, 504):
                    raise
            except (urllib.error.URLError, TimeoutError) as e:
                last = e
            finally:
                _host_last[host] = time.time()
        time.sleep((8 if getattr(last, "code", 0) == 429 else 3) * (attempt + 1))
    raise last


def now_utc():
    return datetime.now(timezone.utc)


def now_local():
    return datetime.now().astimezone()


def parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    try:
        d = email.utils.parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def iso(d):
    return d.isoformat(timespec="seconds") if d else None


def norm_url(u):
    p = urllib.parse.urlsplit(u.strip())
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith(("utm_", "ref", "source"))]
    path = p.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."),
                                    path, urllib.parse.urlencode(q), ""))


def short_id(*parts):
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10]


_DROP = re.compile(r"(?is)<(script|style|noscript|svg|template)[^>]*>.*?</\1>")
_BLOCK = re.compile(r"(?i)<(br|/p|/li|/h[1-6]|/div|/tr|/section|/article|/blockquote|/pre)[^>]*>")


def clean_text(s, limit=None):
    """Turns a short HTML fragment (summary, title) into plain text."""
    if not s:
        return ""
    s = _DROP.sub(" ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + "…"
    return s


def html_lines(page, min_len=25):
    """Splits the visible text of a page into lines (for change watching and reading)."""
    t = _DROP.sub(" ", page)
    t = re.sub(r"(?i)<h([1-6])[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", t)
    t = re.sub(r"(?i)<li[^>]*>", "\n- ", t)
    t = _BLOCK.sub("\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    out = []
    for line in t.split("\n"):
        line = re.sub(r"[ \t\r\f\v\xa0]+", " ", line).strip()
        if len(line) >= min_len or (line.startswith("#") and len(line) > 3):
            out.append(line)
    return out


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path, obj, pretty=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2 if pretty else None), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- settings and labels

def load_settings(required=True):
    cfg = load_json(SETTINGS, None)
    if cfg is None and required:
        sys.exit("config/settings.json not found. Open your AI agent (Claude Code, Codex or Antigravity) in this "
                 "folder and run /gazette-setup first ($gazette-setup in Codex).")
    return cfg or {}


def sections(cfg):
    """Section definitions from settings; the must-know section always comes first."""
    secs = [s for s in (cfg.get("edition", {}).get("sections") or []) if s.get("id")]
    top = [s for s in secs if s["id"] == TOP]
    return top + [s for s in secs if s["id"] != TOP]


def labels(cfg=None):
    """UI strings: English base, then i18n/<language>.json, then config/ui.json (setup writes it for other languages)."""
    cfg = cfg if cfg is not None else load_settings(required=False)
    out = load_json(I18N / "en.json", {})
    lang = (cfg.get("language") or "en").split("-")[0].lower()
    if lang != "en":
        out.update(load_json(I18N / f"{lang}.json", {}))
    out.update(load_json(CONFIG / "ui.json", {}))
    from agents import info
    agent = info(cfg)
    return {k: v.replace("{agent}", agent["name"]).replace("{gazette}", agent["cmd"]) if isinstance(v, str) else v
            for k, v in out.items()}


def brand(cfg):
    return (cfg.get("edition", {}).get("title") or "Gazette").strip()


def fmt_date(d, L, year=True):
    """Long local date with the month names of the edition language ('22 Ekim 2026', 'October 22, 2026')."""
    d = d.astimezone()
    month = L["months"][d.month - 1]
    return L["date_long" if year else "date_short"].format(day=d.day, month=month, year=d.year)


def fmt_range(a, b, L):
    a, b = a.astimezone(), b.astimezone()
    if (a.year, a.month) == (b.year, b.month) and a.day != b.day:
        return L["date_range_month"].format(d1=a.day, d2=b.day, month=L["months"][b.month - 1], year=b.year)
    if a.date() == b.date():
        return fmt_date(b, L)
    return f"{fmt_date(a, L, year=a.year != b.year)} – {fmt_date(b, L)}"
