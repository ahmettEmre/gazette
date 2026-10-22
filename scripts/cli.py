"""Single entry point behind ./gazette and gazette.cmd: maps a command to its script."""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMANDS = {
    "collect": ("collect.py", "gather candidate stories from your sources"),
    "read": ("read.py", "print the main text of a web page"),
    "publish": ("publish.py", "validate an edition and add it to the reader"),
    "deliver": ("deliver.py", "send an edition by e-mail and/or to Kindle"),
    "open": ("open_reader.py", "open the reader (gazette.html) in your browser"),
    "learn": ("learn.py", "learning tracks: next lesson, progress"),
    "sources": ("sources.py", "list catalog packs, build and test your source list"),
    "schedule": ("schedule.py", "install, remove or inspect the automatic schedule"),
    "secret": ("secret.py", "store or check the e-mail password in the OS keychain"),
    "doctor": ("doctor.py", "check that everything is set up"),
}


def usage():
    print("usage: ./gazette <command> [options]      (Windows terminal: gazette <command>)\n")
    for name, (_, desc) in COMMANDS.items():
        print(f"  {name:<9} {desc}")
    print("\nMost of the time you only need your AI agent: /gazette-setup once, then /gazette "
          "(Codex: $gazette-setup, $gazette).")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        usage()
        sys.exit(0 if len(sys.argv) >= 2 else 2)
    name = sys.argv[1]
    if name not in COMMANDS:
        print(f"unknown command: {name}\n")
        usage()
        sys.exit(2)
    sys.argv = [f"gazette {name}", *sys.argv[2:]]
    sys.path.insert(0, str(HERE))
    runpy.run_path(str(HERE / COMMANDS[name][0]), run_name="__main__")


if __name__ == "__main__":
    main()
