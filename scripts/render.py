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


# ================================================================ e-mail and the full edition document

SERIF = "Georgia,'Times New Roman',serif"
SANS = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _first_para(text):
    return str(text).split("\n\n")[0].strip()


def _excerpt(text, limit=260):
    """Opening sentences of a story, cut at a sentence end. Plain text: a cut could split **bold** or `code`."""
    first = plain(_first_para(text))
    if len(first) <= limit:
        return first
    cut = first[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > limit // 3 else cut.rsplit(" ", 1)[0] + "…"


def highlights(ed, n=5, at_least=3):
    """The must-know stories (up to n), topped up with the most important others to at least `at_least`."""
    top = sorted((it for it in ed["items"] if it["section"] == TOP), key=lambda it: -it["importance"])[:n]
    rest = sorted((it for it in ed["items"] if it["section"] != TOP), key=lambda it: -it["importance"])
    return top + rest[: max(0, at_least - len(top))]


def upcoming_deadlines(ed, n=3):
    today = now_utc().date()
    dated = [(parse_date(it["deadline"]), it) for it in ed["items"] if it.get("deadline")]
    return sorted(((d, it) for d, it in dated if d and d.date() >= today), key=lambda x: x[0])[:n]


def section_counts(ed, cfg):
    return [(sec["title"], sum(1 for it in ed["items"] if it["section"] == sec["id"]))
            for sec in edition_sections(ed, cfg) if any(it["section"] == sec["id"] for it in ed["items"])]


# Layout with tables and short classes. Gmail, Apple Mail and Outlook honour a <style> block in <head>; a client
# that strips it still shows clean, readable HTML. No text-transform: upper-casing is not language-aware everywhere.
MAIL_CSS = f"""body{{margin:0;padding:0;background:#F6F3EC}}
.wrap{{max-width:600px;background:#FFFDF8;border:1px solid #DFD8CA;border-radius:12px}}
.pad{{padding:26px 26px 22px}}
p,li,td,div{{font-family:{SANS}}}
p{{margin:0 0 10px;font-size:15px;line-height:1.55;color:#1D1B17}}
a{{color:#2A55A0}}
.mast{{padding:0 0 14px;border-bottom:2px solid #1D1B17}}
.kick{{font-size:11px;font-weight:600;letter-spacing:.15em;color:#7A746A}}
.brand{{font:700 32px/1.15 {SERIF};color:#1D1B17;margin:6px 0 4px}}
.small{{font-size:13px;line-height:1.45;color:#7A746A}}
.head{{font:600 23px/1.28 {SERIF};color:#1D1B17;padding:20px 0 10px}}
.lab{{font-size:11px;font-weight:700;letter-spacing:.06em;margin:0 0 8px;color:#C4401C}}
.blk{{padding:18px 0 4px;border-top:1px solid #DFD8CA}}
.hl{{padding:0 0 14px}}
.hlt{{font:600 17px/1.3 {SERIF};color:#1D1B17;text-decoration:none}}
.hl p{{font-size:14px;color:#4A463F;margin:5px 0 3px}}
.src{{font-size:12px;color:#7A746A}}
.unv{{background:#FBEFD8;color:#9A5800;padding:1px 6px;border-radius:9px;font-size:11px;font-family:{SANS}}}
.dl{{font-size:14px;line-height:1.5;margin:0 0 6px}} .dl b{{color:#C4401C}}
.box{{background:#F1EDE4;border-radius:10px;padding:14px 16px;font-size:14px;line-height:1.5;color:#1D1B17}}
.foot{{padding:18px 0 0;font-size:12px;line-height:1.5;color:#7A746A}}
"""


def email_html(ed, cfg, L, attachment=None):
    """A short e-mail: intro, a few highlights, deadlines and the lesson. The whole edition is the attachment."""
    lang = (ed.get("lang") or cfg.get("language") or "en").split("-")[0]
    n = len(ed["items"])
    rows = [
        f'<tr><td class="mast"><div class="kick">{esc(L["kicker"])}</div><div class="brand">{esc(brand(cfg))}</div>'
        f'<div class="small">{esc(dateline(ed, L))} · {esc(L["fact_items"].format(n=n))}</div></td></tr>',
        f'<tr><td class="head">{inline(ed["headline"])}</td></tr>',
        f'<tr><td><div class="lab">{esc(L["big_picture"])}</div>{paras(_first_para(ed["big_picture"]))}</td></tr>',
    ]
    hl = []
    for it in highlights(ed):
        unv = f' <span class="unv">{esc(L["unverified"])}</span>' if not it["verified"] else ""
        names = ", ".join(dict.fromkeys(s["name"] for s in it["sources"]))
        hl.append(f'<div class="hl"><a class="hlt" href="{esc(it["sources"][0]["url"])}">{inline(it["title"])}</a>{unv}'
                  f'<p>{esc(_excerpt(it["what"]))}</p><div class="src">{esc(names)}</div></div>')
    rows.append(f'<tr><td class="blk"><div class="lab">{esc(L["highlights"])}</div>{"".join(hl)}</td></tr>')
    dls = upcoming_deadlines(ed)
    if dls:
        rows.append(f'<tr><td class="blk"><div class="lab">{esc(L["email_deadlines"])}</div>' + "".join(
            f'<p class="dl"><b>{esc(fmt_date(d, L, year=False))}</b> · {inline(it["title"])}</p>' for d, it in dls) + "</td></tr>")
    for les in ed.get("lessons") or []:
        rows.append(f'<tr><td class="blk"><div class="lab">{esc(L["email_lesson"])}</div>'
                    f'<p><b>{inline(les["title"])}</b><br><span class="small">{esc(les.get("track_title", les["track"]))} · '
                    f'{esc(L["lesson_of"].format(n=les["n"], total=les.get("total", "?")))}</span></p></td></tr>')
    contents = " · ".join(f"{esc(t)} {c}" for t, c in section_counts(ed, cfg))
    rows.append(f'<tr><td class="blk"><div class="lab">{esc(L["email_contents"])}</div><p class="small">{contents}</p></td></tr>')
    note = (L["email_attached"].format(n=n, file=attachment) if attachment else L["email_no_attachment"].format(n=n))
    rows.append(f'<tr><td><div class="box">{"📎 " if attachment else ""}{esc(note)}</div></td></tr>')
    rows.append(f'<tr><td class="foot">{esc(L["email_more"])}<br>{esc(L["email_footer"])}</td></tr>')
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light">'
            f'<title>{esc(title_of(ed, cfg, L))}</title><style>{MAIL_CSS}</style></head><body>'
            f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{esc(plain(ed["headline"]))}</div>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#F6F3EC"><tr>'
            '<td align="center" style="padding:20px 10px">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="wrap" bgcolor="#FFFDF8"><tr>'
            '<td class="pad"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            + "\n".join(rows) + "</table></td></tr></table></td></tr></table></body></html>")


def email_text(ed, cfg, L, attachment=None):
    n = len(ed["items"])
    out = [title_of(ed, cfg, L), "", plain(ed["headline"]), "", plain(_first_para(ed["big_picture"])), "",
           f"{L['highlights']}:"]
    for it in highlights(ed):
        out += [f"* {plain(it['title'])}", f"  {_excerpt(it['what'])}", f"  {it['sources'][0]['url']}"]
    dls = upcoming_deadlines(ed)
    if dls:
        out += ["", f"{L['email_deadlines']}:"] + [f"- {fmt_date(d, L, year=False)} · {plain(it['title'])}" for d, it in dls]
    for les in ed.get("lessons") or []:
        out += ["", f"{L['email_lesson']}: {plain(les['title'])}"]
    out += ["", f"{L['email_contents']}: " + " · ".join(f"{t} {c}" for t, c in section_counts(ed, cfg)), "",
            L["email_attached"].format(n=n, file=attachment) if attachment else L["email_no_attachment"].format(n=n),
            "", L["email_footer"]]
    return "\n".join(out)


# The full edition as one self-contained page: the e-mail attachment (as HTML or printed to PDF).
# A5 pages read well on a phone without zooming and still print fine.
DOC_CSS = f""":root{{color-scheme:light}}
*{{box-sizing:border-box}}
body{{margin:0;background:#F6F3EC;color:#1D1B17;font:15px/1.6 {SANS};-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.page{{max-width:720px;margin:0 auto;padding:28px 22px 40px;background:#FFFDF8}}
.mast{{text-align:center;border-bottom:2px solid #1D1B17;padding:4px 0 14px;margin-bottom:18px}}
.kick{{font-size:11px;font-weight:700;letter-spacing:.18em;color:#7A746A}}
.brand{{font:700 40px/1.1 {SERIF};margin:6px 0}}
.small{{font-size:13px;color:#7A746A}}
h1{{font:600 25px/1.25 {SERIF};margin:0 0 14px}}
.lab{{font-size:11px;font-weight:700;letter-spacing:.06em;color:#C4401C;margin:0 0 6px}}
p{{margin:0 0 9px}}
.toc{{background:#F1EDE4;border-radius:10px;padding:14px 16px;margin:18px 0 8px;font-size:14px}}
.toc ol{{margin:0;padding-left:18px}} .toc li{{margin:5px 0}}
.toc ul{{margin:3px 0 6px;padding-left:16px;font-size:13px;color:#4A463F}}
.toc a{{color:inherit;text-decoration:none}}
.sec{{margin-top:26px}}
h2{{font:600 21px/1.2 {SERIF};color:#C4401C;border-top:3px solid #C4401C;padding-top:10px;margin:0 0 2px;break-after:avoid}}
.desc{{font-size:13px;color:#7A746A;margin:0 0 4px}}
.item{{border-top:1px solid #DFD8CA;padding:14px 0 4px}}
.meta{{font-size:12px;color:#7A746A;margin:0 0 4px}}
.t-official{{color:#1E6B47;font-weight:700}} .t-press{{color:#2A55A0;font-weight:700}} .t-community{{color:#94600F;font-weight:700}}
.unv{{background:#FBEFD8;color:#9A5800;padding:0 6px;border-radius:9px}}
.dl{{color:#C4401C;font-weight:700}}
h3{{font:600 18px/1.3 {SERIF};margin:0 0 6px;break-after:avoid}}
.orig{{font-size:12px;font-style:italic;color:#7A746A;margin:-2px 0 6px}}
.you{{border-left:3px solid #1E6B47;padding:2px 0 2px 12px;margin:0 0 10px;color:#4A463F;font-size:14px;break-inside:avoid}}
.take{{background:#EEEAF6;border-radius:8px;padding:10px 12px;margin:0 0 10px;font-size:14px;break-inside:avoid}}
.you .lab{{color:#1E6B47}} .take .lab{{color:#57478A}} .you p:last-child,.take p:last-child{{margin:0}}
dl.terms{{font-size:13px;margin:0 0 8px}} dl.terms dt{{font-weight:700}} dl.terms dd{{margin:0 0 4px}}
.src{{font-size:12px;color:#7A746A;margin:0 0 8px}} .src a{{color:#2A55A0}}
code{{font-family:Consolas,Menlo,monospace;font-size:.88em;background:#EFEAE0;padding:0 3px;border-radius:3px}}
.lesson,.concept{{border:1px solid #DFD8CA;border-radius:10px;padding:14px 16px;margin:12px 0}}
.lesson{{border-left:4px solid #1E6B47}}
.points{{background:#E2F0E7;border-radius:8px;padding:10px 12px 10px 30px;margin:0 0 10px;font-size:14px}}
.example{{background:#F1EDE4;border-radius:8px;padding:10px 12px;margin:0 0 10px;font-size:14px}}
.foot{{margin-top:28px;border-top:1px solid #DFD8CA;padding-top:12px;font-size:12px;color:#7A746A}}
@page{{size:A5;margin:12mm 10mm 14mm;@bottom-center{{content:counter(page);font:9pt {SANS};color:#7A746A}}}}
@media print{{body{{background:#fff;font-size:10.5pt}} .page{{max-width:none;padding:0;background:#fff}}
  h1{{font-size:17pt}} .brand{{font-size:28pt}} h2{{font-size:15pt}} h3{{font-size:12.5pt}} .toc ul li{{break-inside:avoid}} .sec.first{{break-before:page}} .desc{{break-after:avoid}}}}
"""


def _doc_item(it, L):
    badges = [f'<span class="t-{esc(it["tier"])}">{esc(L.get("tier_" + it["tier"], it["tier"]))}</span>']
    if not it["verified"]:
        badges.append(f'<span class="unv">{esc(L["unverified"])}</span>')
    deadline = parse_date(it.get("deadline"))
    if deadline:
        badges.append(f'<span class="dl">{esc(L["deadline"].format(date=fmt_date(deadline, L)))}</span>')
    pub = parse_date(it.get("published"))
    if pub:
        badges.append(esc(fmt_date(pub, L, year=False)))
    badges.append(esc(L["importance"].format(n=it["importance"])))
    out = [f'<article class="item" id="m-{esc(it["id"])}"><div class="meta">{" · ".join(badges)}</div>',
           f"<h3>{inline(it['title'])}</h3>"]
    orig = (it.get("original_title") or "").strip()
    if orig and orig != it["title"]:
        out.append(f'<p class="orig">{esc(orig)}</p>')
    out += [paras(it["what"]),
            f'<div class="you"><div class="lab">{esc(L["for_you"])}</div>{paras(it["why_you"])}</div>',
            f'<div class="take"><div class="lab">{esc(L["take"])}</div>{paras(it["take"])}</div>']
    terms = it.get("terms") or []
    if terms:
        out.append('<dl class="terms">' + "".join(f"<dt>{inline(t['term'])}</dt><dd>{inline(t['explain'])}</dd>"
                                                 for t in terms) + "</dl>")
    links = " · ".join(f'<a href="{esc(s["url"])}">{esc(s["name"])}</a>' for s in it["sources"])
    out.append(f'<div class="src">{esc(L["source"])}: {links}</div></article>')
    return "".join(out)


def document_html(ed, cfg, L):
    lang = (ed.get("lang") or cfg.get("language") or "en").split("-")[0]
    secs = [(sec, sorted((it for it in ed["items"] if it["section"] == sec["id"]), key=lambda it: -it["importance"]))
            for sec in edition_sections(ed, cfg)]
    secs = [(sec, items) for sec, items in secs if items]
    lessons, concepts = ed.get("lessons") or [], ed.get("concepts") or []
    toc = "".join(f'<li><a href="#s-{esc(sec["id"])}">{esc(sec["title"])}</a> ({len(items)})<ul>'
                  + "".join(f'<li><a href="#m-{esc(it["id"])}">{inline(it["title"])}</a></li>' for it in items) + "</ul></li>"
                  for sec, items in secs)
    if lessons:
        toc += f'<li><a href="#lessons">{esc(L["lessons"])}</a></li>'
    if concepts:
        toc += f'<li><a href="#concepts">{esc(L["concepts"])}</a></li>'
    body = [f'<header class="mast"><div class="kick">{esc(L["kicker"])}</div><div class="brand">{esc(brand(cfg))}</div>'
            f'<div class="small">{esc(dateline(ed, L))} · {esc(" · ".join(facts(ed, L)))}</div></header>',
            f"<h1>{inline(ed['headline'])}</h1>",
            f'<div class="lab">{esc(L["big_picture"])}</div>{paras(ed["big_picture"])}',
            f'<nav class="toc"><div class="lab">{esc(L["contents"])}</div><ol>{toc}</ol></nav>']
    for n, (sec, items) in enumerate(secs):
        desc = f'<p class="desc">{esc(sec.get("desc", ""))}</p>' if sec.get("desc") else ""
        body.append(f'<section class="sec{" first" if n == 0 else ""}" id="s-{esc(sec["id"])}"><h2>{esc(sec["title"])}</h2>{desc}'
                    + "".join(_doc_item(it, L) for it in items) + "</section>")
    if lessons:
        parts = []
        for les in lessons:
            pts = "".join(f"<li>{inline(p)}</li>" for p in les.get("key_points") or [])
            links = " · ".join(f'<a href="{esc(s["url"])}">{esc(s["name"])}</a>' for s in les.get("sources", []))
            parts.append(f'<div class="lesson"><div class="meta">{esc(les.get("track_title", les["track"]))} · '
                         f'{esc(L["lesson_of"].format(n=les["n"], total=les.get("total", "?")))}</div>'
                         f"<h3>{inline(les['title'])}</h3>{paras(les['body'])}"
                         + (f'<div class="lab">{esc(L["key_points"])}</div><ul class="points">{pts}</ul>' if pts else "")
                         + (f'<div class="example"><div class="lab">{esc(L["example"])}</div>{paras(les["example"])}</div>'
                            if les.get("example") else "")
                         + f'<div class="src">{esc(L["source"])}: {links}</div></div>')
        body.append(f'<section class="sec" id="lessons"><h2>{esc(L["lessons"])}</h2>'
                    f'<p class="desc">{esc(L["lessons_desc"])}</p>{"".join(parts)}</section>')
    if concepts:
        body.append(f'<section class="sec" id="concepts"><h2>{esc(L["concepts"])}</h2>'
                    f'<p class="desc">{esc(L["concepts_desc"])}</p>' + "".join(
                        f'<div class="concept"><h3>{inline(c["term"])}</h3>{paras(c["short"])}{paras(c["long"])}'
                        + (f'<div class="example"><div class="lab">{esc(L["example"])}</div>{paras(c["example"])}</div>'
                           if c.get("example") else "") + "</div>" for c in concepts) + "</section>")
    body.append(f'<footer class="foot">{esc(L["trust_note"].format(take=L["take"], unverified=L["unverified"]))}<br>'
                f'{esc(L["email_footer"])}</footer>')
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title_of(ed, cfg, L))}</title><style>{DOC_CSS}</style></head>'
            f'<body><div class="page">{"".join(body)}</div></body></html>')
