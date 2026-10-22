"""HTML → PDF with a Chromium-based browser that is already installed (Chrome, Edge, Chromium, Brave).

No extra dependency: the browser prints the page headless. If none is found, delivery falls back to an HTML file.
Set delivery.email.browser in config/settings.json to point at a browser that is not found automatically.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CANDIDATES = {
    "win32": [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
              r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
              r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
              r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
              r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
              r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"],
    "darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
               "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
               "/Applications/Chromium.app/Contents/MacOS/Chromium",
               "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"],
}
ON_PATH = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"]


def find_browser(cfg=None):
    own = ((cfg or {}).get("delivery", {}).get("email") or {}).get("browser")
    if own and Path(own).exists():
        return own
    import sys
    for c in CANDIDATES.get(sys.platform, []):
        p = Path(os.path.expandvars(c))
        if p.exists():
            return str(p)
    for name in ON_PATH:
        found = shutil.which(name)
        if found:
            return found
    return None


def html_to_pdf(html_path, pdf_path, browser, timeout=120):
    """Prints html_path to pdf_path. Returns None on success, else a short reason."""
    html_path, pdf_path = Path(html_path).resolve(), Path(pdf_path).resolve()  # Chrome needs absolute paths
    pdf_path.unlink(missing_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}  # set by VS Code terminals
    with tempfile.TemporaryDirectory(prefix="gazette-pdf-") as profile:  # never touch the user's browser profile
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               "--no-pdf-header-footer", "--print-to-pdf-no-header", f"--user-data-dir={profile}",
               "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000",
               f"--print-to-pdf={pdf_path}", html_path.as_uri()]
        try:
            subprocess.run(cmd, capture_output=True, timeout=timeout, env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"{type(e).__name__}: {e}"
    if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
        return "the browser produced no PDF"
    return None
