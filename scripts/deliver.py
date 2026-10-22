"""Delivery: sends a published edition by e-mail and/or as an EPUB to a Kindle.

The e-mail itself is short (intro, highlights, deadlines, the lesson); the whole edition is attached as a PDF
(printed by a Chromium browser you already have), an HTML file or an EPUB — delivery.email.attachment.

Usage:  ./gazette deliver <edition-id>             every channel enabled in settings (skips ones already sent)
        ./gazette deliver --latest                 the newest published edition
        ./gazette deliver <id> --email | --kindle  only that channel
        ./gazette deliver <id> --force             send again even if it was sent before
        ./gazette deliver <id> --preview           only write the e-mail and its attachment to out/, send nothing
        ./gazette deliver --check                  test the SMTP login without sending anything
        ./gazette deliver --test                   send a short test e-mail to the e-mail recipients

Settings: config/settings.json → delivery. The password comes from your OS keychain (./gazette secret).
"""
import argparse
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdf  # noqa: E402
import render  # noqa: E402
from common import (EDITIONS, OUT, STATE, brand, iso, labels, load_json, load_settings, now_utc,  # noqa: E402
                    save_json, utf8_stdout)
from publish import validate  # noqa: E402
from secret import get_password, set_command  # noqa: E402

SENT = STATE / "delivered.json"


def smtp_settings(cfg):
    s = dict(cfg.get("delivery", {}).get("smtp") or {})
    missing = [k for k in ("host", "user") if not str(s.get(k, "")).strip()]
    if missing:
        sys.exit(f"ERROR: delivery.smtp is missing {', '.join(missing)} in config/settings.json (run /gazette-setup).")
    pw, _ = get_password(s["user"])
    if not pw:
        sys.exit(f"ERROR: no password stored for {s['user']}. In your own terminal run:  ./gazette secret set\n"
                 f"       (or the native command: {set_command(s['user'])})")
    s["password"] = pw.replace(" ", "") if s["host"] == "smtp.gmail.com" else pw  # Google shows it in groups of four
    s["port"] = int(s.get("port") or 465)
    s["from"] = s.get("from") or formataddr((brand(cfg), s["user"]))
    return s


def connect(s):
    ctx = ssl.create_default_context()
    if s["port"] == 465:
        conn = smtplib.SMTP_SSL(s["host"], s["port"], context=ctx, timeout=60)
    else:
        conn = smtplib.SMTP(s["host"], s["port"], timeout=60)
        conn.starttls(context=ctx)
    try:
        conn.login(s["user"], s["password"])
    except smtplib.SMTPAuthenticationError:
        conn.close()
        sys.exit("ERROR: the SMTP login was refused. Check the app password (is 2-step verification on, was it "
                 "copied completely, does your provider allow SMTP?) and store it again with ./gazette secret set.")
    return conn


def send(s, msg):
    with connect(s) as conn:
        conn.send_message(msg)


def recipients(cfg, channel):
    d = cfg.get("delivery", {}).get(channel) or {}
    if not d.get("enabled"):
        return []
    to = d.get("to") or []
    return [to] if isinstance(to, str) else list(to)


def load_edition(arg):
    if arg == "--latest" or arg is None:
        files = sorted(EDITIONS.glob("*.json"))
        if not files:
            sys.exit("No published edition yet.")
        path = files[-1]
    else:
        path = Path(arg)
        if not path.suffix:
            path = EDITIONS / f"{arg}.json"
    ed = load_json(path, None)
    if not ed:
        sys.exit(f"ERROR: could not read {path}")
    err = validate(ed, [s["id"] for s in ed.get("sections") or []] or [it["section"] for it in ed["items"]])
    if err:
        sys.exit("ERROR: the edition is not valid (fix it with ./gazette publish first):\n- " + "\n- ".join(err))
    return ed


def build_epub(ed, cfg, L):
    title, files = render.epub_files(ed, cfg, L)
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{render.file_stem(cfg)}_{ed['id']}.epub"
    render.write_epub(path, files)
    return title, path


ATTACHMENTS = ("pdf", "html", "epub", "none")
MIME = {".pdf": ("application", "pdf"), ".html": ("text", "html"), ".epub": ("application", "epub+zip")}


def attachment_kind(cfg):
    email = cfg.get("delivery", {}).get("email") or {}
    kind = email.get("attachment") or ("epub" if email.get("attach_epub") else "pdf")
    return kind if kind in ATTACHMENTS else "pdf"


def build_attachment(ed, cfg, L):
    """The full edition as a file for the e-mail. A PDF falls back to HTML when no browser can print it."""
    kind = attachment_kind(cfg)
    if kind == "none":
        return None
    if kind == "epub":
        return build_epub(ed, cfg, L)[1]
    OUT.mkdir(exist_ok=True)
    html_path = OUT / f"{render.file_stem(cfg)}_{ed['id']}.html"
    html_path.write_bytes(render.document_html(ed, cfg, L).encode("utf-8"))
    if kind == "html":
        return html_path
    browser = pdf.find_browser(cfg)
    problem = pdf.html_to_pdf(html_path, html_path.with_suffix(".pdf"), browser) if browser else "no Chrome/Edge/Chromium found"
    if problem:
        print(f"PDF not possible ({problem}); attaching HTML instead. Set delivery.email.attachment to \"html\" "
              "to silence this, or delivery.email.browser to a Chromium-based browser.")
        return html_path
    return html_path.with_suffix(".pdf")


def mail_edition(ed, cfg, L, s, to, attachment=None):
    msg = EmailMessage()
    msg["From"], msg["To"] = s["from"], ", ".join(to)
    msg["Subject"] = f"{render.title_of(ed, cfg, L)} — {render.plain(ed['headline'])}"[:180]
    msg["Message-ID"] = make_msgid(domain=s["user"].split("@")[-1])
    name = attachment.name if attachment else None
    msg.set_content(render.email_text(ed, cfg, L, name))
    msg.add_alternative(render.email_html(ed, cfg, L, name), subtype="html")
    if attachment:
        maintype, subtype = MIME[attachment.suffix]
        msg.add_attachment(attachment.read_bytes(), maintype=maintype, subtype=subtype, filename=attachment.name)
    send(s, msg)


def mail_kindle(ed, cfg, L, s, to, epub):
    title = render.title_of(ed, cfg, L)
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s["from"], ", ".join(to), title
    msg.set_content(f"{title}\n\n{render.plain(ed['headline'])}\n")
    msg.add_attachment(epub.read_bytes(), maintype="application", subtype="epub+zip", filename=epub.name)
    send(s, msg)


def mail_plain(cfg, s, to, subject, body):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s["from"], ", ".join(to), subject
    msg.set_content(body)
    send(s, msg)


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser(description="Send an edition by e-mail and/or to Kindle.")
    ap.add_argument("edition", nargs="?", help="edition id or data/editions/<id>.json")
    ap.add_argument("--latest", action="store_true", help="use the newest published edition")
    ap.add_argument("--email", action="store_true", help="only the e-mail channel")
    ap.add_argument("--kindle", action="store_true", help="only the Kindle channel")
    ap.add_argument("--force", action="store_true", help="send even if it was sent before")
    ap.add_argument("--preview", action="store_true", help="write the e-mail, its attachment and the EPUB to out/, send nothing")
    ap.add_argument("--check", action="store_true", help="test the SMTP login")
    ap.add_argument("--test", action="store_true", help="send a short test e-mail")
    ap.add_argument("--notify-failure", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    cfg = load_settings()
    L = labels(cfg)

    if args.check:
        s = smtp_settings(cfg)
        with connect(s):
            pass
        print(f"SMTP login OK: {s['user']} via {s['host']}:{s['port']}")
        return
    if args.test or args.notify_failure:
        to = recipients(cfg, "email")
        if not to:
            sys.exit("No e-mail recipients enabled in settings (delivery.email).")
        s = smtp_settings(cfg)
        key = "email_test" if args.test else "email_failed"
        mail_plain(cfg, s, to, L[f"{key}_subject"].format(brand=brand(cfg)), L[f"{key}_body"])
        print(f"Sent to {', '.join(to)}")
        return
    if not args.edition and not args.latest:
        ap.error("edition id (or --latest) is required")

    ed = load_edition("--latest" if args.latest else args.edition)
    channels = [c for c in ("email", "kindle") if (not (args.email or args.kindle)) or getattr(args, c)]
    if args.preview:
        attachment = build_attachment(ed, cfg, L)
        mail = OUT / f"{ed['id']}.email.html"
        mail.write_bytes(render.email_html(ed, cfg, L, attachment.name if attachment else None).encode("utf-8"))
        _, epub = build_epub(ed, cfg, L)
        files = [mail, epub] + ([attachment] if attachment and attachment != epub else [])
        print("Preview: " + " · ".join(f"{p.relative_to(OUT.parent)} ({p.stat().st_size // 1024} KB)" for p in files))
        return

    sent = load_json(SENT, {})
    done = sent.setdefault(ed["id"], {})
    todo = [c for c in channels if recipients(cfg, c) and (args.force or c not in done)]
    skipped = [c for c in channels if c in done and not args.force and recipients(cfg, c)]
    if skipped:
        print(f"Already sent ({', '.join(skipped)}); use --force to send again.")
    if not todo:
        if not any(recipients(cfg, c) for c in channels):
            print("No delivery channel is enabled in settings (delivery.email / delivery.kindle).")
        return
    s = smtp_settings(cfg)
    failures = 0
    for c in todo:
        to = recipients(cfg, c)
        try:
            if c == "kindle":
                _, epub = build_epub(ed, cfg, L)
                mail_kindle(ed, cfg, L, s, to, epub)
            else:
                mail_edition(ed, cfg, L, s, to, build_attachment(ed, cfg, L))
        except (smtplib.SMTPException, OSError, ValueError) as e:
            failures += 1
            print(f"FAILED {c} → {', '.join(to)}: {type(e).__name__}: {e}")
            continue
        done[c] = iso(now_utc())
        save_json(SENT, sent)
        print(f"Sent {c} → {', '.join(to)}" + (" (Kindle shows it within minutes; Wi-Fi must be on)" if c == "kindle" else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
