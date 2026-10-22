"""Renders a published edition for e-mail (HTML newsletter + plain text) and for e-readers (EPUB)."""
import html
import re
import sys
import unicodedata
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import TOP, brand, fmt_date, fmt_range, now_utc, parse_date, sections  # noqa: E402


def esc(s):
    return html.escape(str(s), quote=True)


def plain(s):
    return re.sub(r"\*\*|`", "", str(s))


def inline(s):
    # Edition texts only use `code` and **bold** (see the /gazette skill schema).
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(s))
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)


def paras(s, cls=""):
    attr = f' class="{cls}"' if cls else ""
    return "\n".join(f"<p{attr}>{inline(p.strip()).replace(chr(10), '<br/>')}</p>"
                     for p in str(s).split("\n\n") if p.strip())


def file_stem(cfg):
    """ASCII-only brand for file names: e-mail attachments and Kindle are picky about non-ASCII names."""
    ascii_ = unicodedata.normalize("NFKD", brand(cfg)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", ascii_).strip("_") or "Gazette"


def edition_sections(ed, cfg):
    """Sections in display order: the snapshot stored in the edition, else the current settings."""
    return ed.get("sections") or sections(cfg)


def title_of(ed, cfg, L):
    return f"{brand(cfg)} · {fmt_date(parse_date(ed['created']), L)}"


def dateline(ed, L):
    created = parse_date(ed["created"])
    start = parse_date(ed.get("window_from"))
    # Long windows (weekly editions) show the range they cover.
    if start and (created - start).days >= 2:
        return fmt_range(start, created, L)
    return fmt_date(created, L)


def facts(ed, L):
    st = ed.get("stats") or {}
    out = [L["fact_items"].format(n=len(ed["items"]))]
    if st.get("sources_total"):
        out.append(L["fact_sources"].format(ok=st.get("sources_ok", st["sources_total"]), total=st["sources_total"]))
    if st.get("candidates"):
        out.append(L["fact_candidates"].format(n=st["candidates"]))
    if st.get("read"):
        out.append(L["fact_read"].format(n=st["read"]))
    return out


def top_items(ed):
    ranked = sorted(ed["items"], key=lambda it: -it["importance"])
    return [it for it in ranked if it["importance"] == 5][:6] or ranked[:5]


def item_meta(it, L, with_date=True):
    meta = [L.get(f"tier_{it['tier']}", it["tier"]), L["verified"] if it["verified"] else L["unverified"],
            L["importance"].format(n=it["importance"]), L["hype"][it["hype"]]]
    pub = parse_date(it.get("published"))
    if pub and with_date:
        meta.insert(0, fmt_date(pub, L, year=False))
    return meta


# ================================================================ EPUB

# The reader picks the font on e-ink; only spacing and hierarchy here. No text-transform: upper-casing
# is not language-aware on every e-reader (Turkish i/İ), so upper-case labels are written as such.
EPUB_CSS = """body { margin: 0; line-height: 1.45; }
h1 { font-size: 1.5em; line-height: 1.2; margin: 0 0 0.4em; }
h2 { font-size: 1.15em; line-height: 1.25; margin: 0 0 0.25em; page-break-after: avoid; }
p { margin: 0 0 0.55em; text-indent: 0; }
a { color: inherit; }
.masthead { text-align: center; margin: 1.2em 0 1em; padding-bottom: 0.8em; border-bottom: 2px solid #000; }
.kicker { font-size: 0.75em; letter-spacing: 0.15em; margin: 0; }
.brand { font-size: 2.6em; font-weight: bold; line-height: 1.1; margin: 0.1em 0; }
.dateline { font-size: 0.9em; margin: 0; }
.headline { font-size: 1.35em; margin-bottom: 0.8em; }
.plain { margin-top: 1.2em; }
.desc { font-style: italic; margin-bottom: 1em; }
.item { border-top: 1px solid #999; padding-top: 0.7em; margin-top: 1.1em; }
.orig, .meta, .src, .note { font-size: 0.8em; }
.meta { margin-bottom: 0.6em; }
.deadline { font-weight: bold; }
.label { font-size: 0.8em; font-weight: bold; letter-spacing: 0.05em; margin: 0.9em 0 0.2em; page-break-after: avoid; }
.lead { font-weight: bold; }
.note { margin-top: 1.5em; }
blockquote { margin: 0 0 0.6em 0; padding-left: 0.7em; border-left: 3px solid #666; }
dt { font-weight: bold; margin-top: 0.3em; }
dd { margin: 0 0 0.3em 0; }
code { font-family: monospace; font-size: 0.9em; }
ul.top li, ul.points li { margin-bottom: 0.3em; }
nav ol { list-style-type: none; padding-left: 0; margin: 0; }
nav li { margin: 0.35em 0; }
nav ol ol { padding-left: 1.2em; font-size: 0.9em; }
"""


def _page(title, body, lang):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">\n'
            f'<head><meta charset="utf-8"/><title>{esc(title)}</title>'
            '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
            f"<body>\n{body}\n</body>\n</html>\n")


def _epub_item(it, L):
    out = [f'<div class="item" id="m-{esc(it["id"])}">', f"<h2>{inline(it['title'])}</h2>"]
    orig = (it.get("original_title") or "").strip()
    if orig and orig != it["title"]:
        out.append(f'<p class="orig">{esc(orig)}</p>')
    out.append(f'<p class="meta">{" · ".join(esc(m) for m in item_meta(it, L))}</p>')
    deadline = parse_date(it.get("deadline"))
    if deadline:
        out.append(f'<p class="deadline">{esc(L["deadline"].format(date=fmt_date(deadline, L)))}</p>')
    out.append(paras(it["what"]))
    out.append(f'<p class="label">{esc(L["for_you"])}</p>\n' + paras(it["why_you"]))
    out.append(f'<p class="label">{esc(L["take"])}</p>\n<blockquote>' + paras(it["take"]) + "</blockquote>")
    terms = it.get("terms") or []
    if terms:
        out.append(f'<p class="label">{esc(L["terms"])}</p>\n<dl>' + "".join(
            f"<dt>{inline(t['term'])}</dt><dd>{inline(t['explain'])}</dd>" for t in terms) + "</dl>")
    links = " · ".join(f'<a href="{esc(s["url"])}">{esc(s["name"])}</a>' for s in it["sources"])
    out.append(f'<p class="src">{esc(L["source"])}: {links}</p>\n</div>')
    return "\n".join(out)


def _nav(toc, L, lang):
    lis = []
    for href, title, kids in toc:
        sub = "<ol>" + "".join(f'<li><a href="{esc(h)}">{esc(t)}</a></li>' for h, t in kids) + "</ol>" if kids else ""
        lis.append(f'<li><a href="{esc(href)}">{esc(title)}</a>{sub}</li>')
    return _page(L["contents"], f'<nav epub:type="toc" id="toc"><h1>{esc(L["contents"])}</h1>\n<ol>{"".join(lis)}</ol></nav>\n'
                 '<nav epub:type="landmarks" hidden="hidden"><ol>'
                 f'<li><a epub:type="bodymatter" href="c00.xhtml">{esc(L["start"])}</a></li></ol></nav>', lang)


def _ncx(uid, title, toc, lang):
    points, n = [], 0
    for href, label, kids in toc:
        n += 1
        own, inner = n, []
        for h, t in kids:
            n += 1
            inner.append(f'<navPoint id="p{n}" playOrder="{n}"><navLabel><text>{esc(t)}</text></navLabel>'
                         f'<content src="{esc(h)}"/></navPoint>')
        points.append(f'<navPoint id="p{own}" playOrder="{own}"><navLabel><text>{esc(label)}</text></navLabel>'
                      f'<content src="{esc(href)}"/>{"".join(inner)}</navPoint>')
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            f'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="{lang}">\n'
            f'<head><meta name="dtb:uid" content="{uid}"/><meta name="dtb:depth" content="2"/>'
            '<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>\n'
            f'<docTitle><text>{esc(title)}</text></docTitle>\n<navMap>{"".join(points)}</navMap>\n</ncx>\n')


def _opf(uid, title, created, docs, lang, creator, L):
    manifest = "".join(f'<item id="{d}" href="{d}.xhtml" media-type="application/xhtml+xml"/>' for d in docs if d != "nav")
    spine = "".join(f'<itemref idref="{d}"/>' for d in docs)
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{lang}">\n'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:identifier id="bookid">{uid}</dc:identifier><dc:title>{esc(title)}</dc:title>'
            f'<dc:language>{lang}</dc:language><dc:creator>{esc(creator)}</dc:creator>'
            f'<dc:date>{created.astimezone().date().isoformat()}</dc:date>'
            f'<meta property="dcterms:modified">{now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")}</meta></metadata>\n'
            '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            f'<item id="css" href="style.css" media-type="text/css"/>{manifest}</manifest>\n'
            f'<spine toc="ncx">{spine}</spine>\n'
            f'<guide><reference type="text" title="{esc(L["start"])}" href="c00.xhtml"/>'
            f'<reference type="toc" title="{esc(L["contents"])}" href="nav.xhtml"/></guide>\n</package>\n')


def epub_files(ed, cfg, L):
    """Builds the EPUB content: (title, {path inside the zip: text})."""
    lang = (ed.get("lang") or cfg.get("language") or "en").split("-")[0]
    created = parse_date(ed["created"])
    title = title_of(ed, cfg, L)
    uid = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'gazette:' + ed['id'])}"

    pages, toc, where = {}, [], {}
    for n, sec in enumerate(edition_sections(ed, cfg), 1):
        items = sorted((it for it in ed["items"] if it["section"] == sec["id"]), key=lambda it: -it["importance"])
        if not items:
            continue
        doc = f"s{n:02d}"
        where.update({it["id"]: doc for it in items})
        pages[doc] = _page(sec["title"], f"<h1>{esc(sec['title'])}</h1>\n<p class=\"desc\">{esc(sec.get('desc', ''))}</p>\n"
                           + "\n".join(_epub_item(it, L) for it in items), lang)
        toc.append((f"{doc}.xhtml", sec["title"], [(f"{doc}.xhtml#m-{it['id']}", plain(it["title"])) for it in items]))

    lessons = ed.get("lessons") or []
    if lessons:
        body = [f"<h1>{esc(L['lessons'])}</h1>"]
        for n, les in enumerate(lessons):
            body += [f'<div class="item" id="l-{n}">',
                     f'<p class="meta">{esc(les.get("track_title", les["track"]))} · '
                     f'{esc(L["lesson_of"].format(n=les["n"], total=les.get("total", "?")))}</p>',
                     f"<h2>{inline(les['title'])}</h2>", paras(les["body"])]
            if les.get("key_points"):
                body.append(f'<p class="label">{esc(L["key_points"])}</p>\n<ul class="points">'
                            + "".join(f"<li>{inline(p)}</li>" for p in les["key_points"]) + "</ul>")
            if les.get("example"):
                body.append(f'<p class="label">{esc(L["example"])}</p>\n' + paras(les["example"]))
            links = " · ".join(f'<a href="{esc(s["url"])}">{esc(s["name"])}</a>' for s in les.get("sources", []))
            body.append(f'<p class="src">{esc(L["source"])}: {links}</p></div>')
        pages["lessons"] = _page(L["lessons"], "\n".join(body), lang)
        toc.append(("lessons.xhtml", L["lessons"], [(f"lessons.xhtml#l-{n}", plain(les["title"])) for n, les in enumerate(lessons)]))

    concepts = ed.get("concepts") or []
    if concepts:
        body = [f"<h1>{esc(L['concepts'])}</h1>"]
        for n, c in enumerate(concepts):
            body += [f'<div class="item" id="k-{n}">', f"<h2>{inline(c['term'])}</h2>",
                     paras(c["short"], "lead"), paras(c["long"])]
            if c.get("example"):
                body.append(f'<p class="label">{esc(L["example"])}</p>\n' + paras(c["example"]))
            body.append("</div>")
        pages["concepts"] = _page(L["concepts"], "\n".join(body), lang)
        toc.append(("concepts.xhtml", L["concepts"], [(f"concepts.xhtml#k-{n}", plain(c["term"])) for n, c in enumerate(concepts)]))

    cover = [
        '<div class="masthead">', f'<p class="kicker">{esc(L["kicker"])}</p>',
        f'<p class="brand">{esc(brand(cfg))}</p>', f'<p class="dateline">{esc(dateline(ed, L))}</p>', "</div>",
        f'<h1 class="headline">{inline(ed["headline"])}</h1>',
        f'<h2 class="plain">{esc(L["big_picture"])}</h2>', paras(ed["big_picture"]),
        f'<h2 class="plain">{esc(L["highlights"])}</h2>',
        '<ul class="top">' + "".join(f'<li><a href="{where[it["id"]]}.xhtml#m-{esc(it["id"])}">{inline(it["title"])}</a></li>'
                                     for it in top_items(ed) if it["id"] in where) + "</ul>",
        f'<p class="note">{esc(" · ".join(facts(ed, L)))}. '
        f'{esc(L["trust_note"].format(take=L["take"], unverified=L["unverified"]))}</p>',
    ]
    toc.insert(0, ("c00.xhtml", L["cover"], []))
    docs = ["c00", "nav", *pages]
    files = {
        "META-INF/container.xml": '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
        '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>\n',
        "OEBPS/content.opf": _opf(uid, title, created, docs, lang, brand(cfg), L),
        "OEBPS/toc.ncx": _ncx(uid, title, toc, lang),
        "OEBPS/nav.xhtml": _nav(toc, L, lang),
        "OEBPS/style.css": EPUB_CSS,
        "OEBPS/c00.xhtml": _page(title, "\n".join(cover), lang),
        **{f"OEBPS/{doc}.xhtml": text for doc, text in pages.items()},
    }
    return title, files


def write_epub(path, files):
    # Amazon silently rejects broken XHTML (a "could not be delivered" mail comes later); catch it here.
    for name, text in files.items():
        if name.endswith((".xhtml", ".opf", ".ncx", ".xml")):
            try:
                ElementTree.fromstring(text.encode("utf-8"))
            except ElementTree.ParseError as e:
                raise ValueError(f"{name} is not valid XML: {e}") from e
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")  # must be first and uncompressed
        for name, text in files.items():
            z.writestr(name, text, compress_type=zipfile.ZIP_DEFLATED)
    tmp.replace(path)


# ================================================================ e-mail

# Layout with tables and short classes. Gmail, Apple Mail and Outlook honour a <style> block in <head>; a client
# that strips it still shows clean, readable HTML. Repeating inline styles on every element would push a long
# edition past Gmail's ~102 KB clipping limit. No text-transform: upper-casing is not language-aware everywhere.
SERIF = "Georgia,'Times New Roman',serif"
SANS = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MAIL_CSS = f"""body{{margin:0;padding:0;background:#F6F3EC}}
.wrap{{max-width:640px;background:#FFFDF8;border:1px solid #DFD8CA;border-radius:12px}}
.pad{{padding:26px 26px 22px}}
p,li,td,div{{font-family:{SANS}}}
p{{margin:0 0 10px;font-size:15px;line-height:1.55;color:#1D1B17}}
a{{color:#2A55A0}}
code{{font-family:Consolas,Menlo,monospace;font-size:.9em;background:#EFEAE0;padding:0 3px;border-radius:3px}}
.mast{{padding:0 0 14px;border-bottom:2px solid #1D1B17}}
.kick{{font-size:11px;font-weight:600;letter-spacing:.15em;color:#7A746A}}
.brand{{font:700 34px/1.15 {SERIF};color:#1D1B17;margin:6px 0 4px}}
.small{{font-size:13px;line-height:1.4;color:#7A746A}}
.head{{font:600 25px/1.25 {SERIF};color:#1D1B17;padding:20px 0 6px}}
.lab{{font-size:11px;font-weight:700;letter-spacing:.06em;margin:0 0 5px;color:#7A746A}}
.acc{{color:#C4401C}}
.sec{{padding:26px 0 2px;border-top:3px solid #C4401C}}
.sect{{font:600 22px/1.2 {SERIF};color:#C4401C}}
.item{{padding:18px 0 4px;border-top:1px solid #DFD8CA}}
.meta{{font-size:12px;line-height:1.4;color:#7A746A;margin:0 0 6px}}
.t-official{{color:#1E6B47;font-weight:600}} .t-press{{color:#2A55A0;font-weight:600}} .t-community{{color:#94600F;font-weight:600}}
.unv{{background:#FBEFD8;color:#9A5800;padding:1px 6px;border-radius:9px}}
.dl{{color:#C4401C;font-weight:700}}
.title{{font:600 19px/1.3 {SERIF};color:#1D1B17;text-decoration:none;display:block;margin:0 0 8px}}
.you{{border-left:3px solid #1E6B47;padding:2px 0 2px 12px;margin:0 0 10px}}
.you .lab{{color:#1E6B47}} .you p{{font-size:14px;color:#4A463F;margin:0}}
.take{{background:#EEEAF6;border-radius:8px;padding:10px 12px;margin:0 0 10px}}
.take .lab{{color:#57478A}} .take p{{font-size:14px;margin:0}}
.src{{font-size:12px;line-height:1.5;color:#7A746A;margin:0 0 6px}}
.les{{padding:16px 0 6px}}
.pts{{margin:0 0 10px;padding-left:20px;font-size:14px;line-height:1.5;color:#1D1B17}} .pts li{{margin:0 0 4px}}
.foot{{padding:22px 0 0;border-top:1px solid #DFD8CA;font-size:12px;line-height:1.5;color:#7A746A}}
"""
GMAIL_CLIP = 95_000  # Gmail cuts messages above ~102 KB; stay below with some margin


def _links(sources):
    return " · ".join(f'<a href="{esc(s["url"])}">{esc(s["name"])}</a>' for s in sources)


def _mail_item(it, L, compact):
    badges = [f'<span class="t-{esc(it["tier"])}">{esc(L.get("tier_" + it["tier"], it["tier"]))}</span>']
    if not it["verified"]:
        badges.append(f'<span class="unv">{esc(L["unverified"])}</span>')
    deadline = parse_date(it.get("deadline"))
    if deadline:
        badges.append(f'<span class="dl">{esc(L["deadline"].format(date=fmt_date(deadline, L)))}</span>')
    badges.append(esc(", ".join(dict.fromkeys(s["name"] for s in it["sources"]))))
    what = it["what"].split("\n\n")[0] if compact else it["what"]
    out = [f'<tr><td class="item"><div class="meta">{" · ".join(badges)}</div>',
           f'<a class="title" href="{esc(it["sources"][0]["url"])}">{inline(it["title"])}</a>', paras(what),
           f'<div class="you"><div class="lab">{esc(L["for_you"])}</div>{paras(it["why_you"])}</div>']
    if not compact:
        out.append(f'<div class="take"><div class="lab">{esc(L["take"])}</div>{paras(it["take"])}</div>')
    out.append(f'<div class="src">{esc(L["source"])}: {_links(it["sources"])}</div></td></tr>')
    return "".join(out)


def _section_head(title, desc=""):
    d = f'<div class="small">{esc(desc)}</div>' if desc else ""
    return f'<tr><td class="sec"><div class="sect">{esc(title)}</div>{d}</td></tr>'


def email_html(ed, cfg, L, compact=False):
    """compact: topic sections keep the first paragraph and "why it matters", drop the take; cards stay short."""
    lang = (ed.get("lang") or cfg.get("language") or "en").split("-")[0]
    rows = [
        f'<tr><td class="mast"><div class="kick">{esc(L["kicker"])}</div><div class="brand">{esc(brand(cfg))}</div>'
        f'<div class="small">{esc(dateline(ed, L))} · {esc(" · ".join(facts(ed, L)[:2]))}</div></td></tr>',
        f'<tr><td class="head">{inline(ed["headline"])}</td></tr>',
        f'<tr><td><div class="lab acc">{esc(L["big_picture"])}</div>{paras(ed["big_picture"])}</td></tr>',
    ]
    for sec in edition_sections(ed, cfg):
        items = sorted((it for it in ed["items"] if it["section"] == sec["id"]), key=lambda it: -it["importance"])
        if items:
            rows.append(_section_head(sec["title"], sec.get("desc", "")))
            rows += [_mail_item(it, L, compact and sec["id"] != TOP) for it in items]
    lessons = ed.get("lessons") or []
    if lessons:
        rows.append(_section_head(L["lessons"], L["lessons_desc"]))
        for les in lessons:
            pts = "".join(f"<li>{inline(p)}</li>" for p in les.get("key_points") or [])
            rows.append(
                f'<tr><td class="les"><div class="meta">{esc(les.get("track_title", les["track"]))} · '
                f'{esc(L["lesson_of"].format(n=les["n"], total=les.get("total", "?")))}</div>'
                f'<div class="title">{inline(les["title"])}</div>{paras(les["body"])}'
                + (f'<div class="lab">{esc(L["key_points"])}</div><ul class="pts">{pts}</ul>' if pts else "")
                + (f'<div class="lab">{esc(L["example"])}</div>{paras(les["example"])}' if les.get("example") else "")
                + f'<div class="src">{esc(L["source"])}: {_links(les.get("sources", []))}</div></td></tr>')
    concepts = ed.get("concepts") or []
    if concepts:
        rows.append(_section_head(L["concepts"], L["concepts_desc"]))
        for c in concepts:
            rows.append(f'<tr><td class="les"><div class="title">{inline(c["term"])}</div>'
                        f'<p><b>{inline(c["short"])}</b></p>{"" if compact else paras(c["long"])}</td></tr>')
    rows.append(f'<tr><td class="foot">{esc(L["email_more"])}<br>'
                f'{esc(L["trust_note"].format(take=L["take"], unverified=L["unverified"]))}<br>{esc(L["email_footer"])}</td></tr>')
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light">'
            f'<title>{esc(title_of(ed, cfg, L))}</title><style>{MAIL_CSS}</style></head><body>'
            f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{esc(plain(ed["headline"]))}</div>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#F6F3EC"><tr>'
            '<td align="center" style="padding:20px 10px">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="wrap" bgcolor="#FFFDF8"><tr>'
            '<td class="pad"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            + "\n".join(rows) + "</table></td></tr></table></td></tr></table></body></html>")


def email_html_fitted(ed, cfg, L):
    """Full newsletter, or the compact one when the full one would be clipped by Gmail."""
    full = email_html(ed, cfg, L)
    return full if len(full.encode("utf-8")) <= GMAIL_CLIP else email_html(ed, cfg, L, compact=True)


def email_text(ed, cfg, L):
    out = [title_of(ed, cfg, L), "", plain(ed["headline"]), "", f"{L['big_picture']}:", plain(ed["big_picture"]), ""]
    for sec in edition_sections(ed, cfg):
        items = [it for it in ed["items"] if it["section"] == sec["id"]]
        if not items:
            continue
        out += ["=" * 60, sec["title"], ""]
        for it in sorted(items, key=lambda it: -it["importance"]):
            flag = "" if it["verified"] else f" [{L['unverified']}]"
            out += [f"* {plain(it['title'])}{flag}", plain(it["what"]), f"{L['for_you']}: {plain(it['why_you'])}",
                    f"{L['take']}: {plain(it['take'])}", "  " + " | ".join(s["url"] for s in it["sources"]), ""]
    for les in ed.get("lessons") or []:
        out += ["=" * 60, f"{L['lessons']}: {les.get('track_title', les['track'])} · "
                f"{L['lesson_of'].format(n=les['n'], total=les.get('total', '?'))}", plain(les["title"]), "", plain(les["body"]), ""]
        out += [f"- {plain(p)}" for p in les.get("key_points") or []] + [""]
    for c in ed.get("concepts") or []:
        out += [f"{L['concepts']}: {plain(c['term'])} — {plain(c['short'])}", ""]
    out += ["-" * 60, L["email_more"], L["email_footer"]]
    return "\n".join(out)
