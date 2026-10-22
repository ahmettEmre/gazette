"""Opens the reader (gazette.html) in your default browser. No server needed: it works from file://."""
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import READER, utf8_stdout  # noqa: E402


def open_reader():
    webbrowser.open(READER.as_uri())


if __name__ == "__main__":
    utf8_stdout()
    open_reader()
    print(f"Reader: {READER}")
