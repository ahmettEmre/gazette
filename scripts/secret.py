"""Keeps the e-mail (SMTP) password in your operating system's keychain, never inside this folder.

Usage:  ./gazette secret set       ask for the password (hidden) and store it
        ./gazette secret check     say whether a password is stored (it is never printed)
        ./gazette secret delete    remove it

Where it is stored: Windows Credential Manager · macOS Keychain · Linux Secret Service (secret-tool).
Without a keychain: the GAZETTE_SMTP_PASSWORD environment variable, or ~/.config/gazette/smtp-password
(readable only by you). Run 'set' in your own terminal window, not inside an AI agent's chat:
a password typed into a chat ends up in the conversation.

Why not a file in this folder? The AI agent may read any file here, and the pages it reads while
writing your edition could try to talk it into sending that file somewhere.
"""
import getpass
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings, utf8_stdout  # noqa: E402

SERVICE = "gazette-smtp"
ENV = "GAZETTE_SMTP_PASSWORD"
FALLBACK = Path.home() / ".config" / "gazette" / "smtp-password"


# ---------------------------------------------------------------- Windows Credential Manager

def _win():
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    advapi.CredReadW.restype = wintypes.BOOL
    advapi.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
    advapi.CredWriteW.restype = wintypes.BOOL
    advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    advapi.CredDeleteW.restype = wintypes.BOOL
    advapi.CredFree.argtypes = [ctypes.c_void_p]
    return ctypes, CREDENTIAL, advapi


def _win_get():
    ctypes, CREDENTIAL, advapi = _win()
    cred = ctypes.POINTER(CREDENTIAL)()
    if not advapi.CredReadW(SERVICE, 1, 0, ctypes.byref(cred)):  # 1 = CRED_TYPE_GENERIC
        return None
    try:
        return ctypes.string_at(cred.contents.CredentialBlob, cred.contents.CredentialBlobSize).decode("utf-16-le")
    finally:
        advapi.CredFree(cred)


def _win_set(user, password):
    ctypes, CREDENTIAL, advapi = _win()
    blob = password.encode("utf-16-le")
    buf = ctypes.create_string_buffer(blob, len(blob))
    cred = CREDENTIAL(Type=1, TargetName=SERVICE, UserName=user, CredentialBlobSize=len(blob),
                      CredentialBlob=ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)), Persist=2)  # 2 = local machine
    if not advapi.CredWriteW(ctypes.byref(cred), 0):
        raise OSError(f"CredWriteW failed ({ctypes.get_last_error()})")


def _win_delete():
    _, _, advapi = _win()
    return bool(advapi.CredDeleteW(SERVICE, 1, 0))


# ---------------------------------------------------------------- lookup

def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def get_password(user):
    """Returns (password, where) or (None, None). Order: environment, keychain, fallback file."""
    if os.environ.get(ENV):
        return os.environ[ENV], "environment variable"
    if sys.platform == "win32":
        pw = _win_get()
        if pw:
            return pw, "Windows Credential Manager"
    elif sys.platform == "darwin":
        r = _run(["security", "find-generic-password", "-s", SERVICE, "-a", user, "-w"])
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.rstrip("\n"), "macOS Keychain"
    elif shutil.which("secret-tool"):
        r = _run(["secret-tool", "lookup", "service", SERVICE, "account", user])
        if r.returncode == 0 and r.stdout:
            return r.stdout.rstrip("\n"), "Secret Service"
    if FALLBACK.exists():
        return FALLBACK.read_text(encoding="utf-8").strip(), str(FALLBACK)
    return None, None


def set_command(user):
    """The native one-liner for this OS, for people who prefer it (the setup shows it)."""
    if sys.platform == "win32":
        return f"cmdkey /generic:{SERVICE} /user:{user} /pass"
    if sys.platform == "darwin":
        return f"security add-generic-password -U -s {SERVICE} -a {user} -w"
    return f"secret-tool store --label='Gazette SMTP' service {SERVICE} account {user}"


def interactive():
    """A real keyboard on stdin. On Windows the NUL device also passes isatty(), and getpass would wait forever."""
    if not (sys.stdin and sys.stdin.isatty()):
        return False
    if sys.platform == "win32":
        import ctypes
        import msvcrt
        mode = ctypes.c_uint()
        return bool(ctypes.windll.kernel32.GetConsoleMode(msvcrt.get_osfhandle(sys.stdin.fileno()), ctypes.byref(mode)))
    return True


def smtp_user(args):
    if len(args) > 1 and "@" in args[1]:
        return args[1]
    user = load_settings(required=False).get("delivery", {}).get("smtp", {}).get("user", "")
    if not user:
        sys.exit("No SMTP user in config/settings.json (delivery.smtp.user). Run /gazette-setup, or pass the address: "
                 "./gazette secret set you@example.com")
    return user


def main():
    utf8_stdout()
    args = sys.argv[1:] or ["check"]
    cmd = args[0]
    if cmd == "check":
        user = smtp_user(args)
        _, where = get_password(user)
        print(f"Password for {user}: stored in {where}." if where else
              f"No password stored for {user}. In your own terminal run:  ./gazette secret set   (or: {set_command(user)})")
        sys.exit(0 if where else 1)
    if cmd == "set":
        user = smtp_user(args)
        if sys.platform == "darwin":
            print(f"macOS will ask for the password of {user} twice (input is hidden).")
            sys.exit(subprocess.run(["security", "add-generic-password", "-U", "-s", SERVICE, "-a", user, "-w"]).returncode)
        if not interactive():
            sys.exit("This needs an interactive terminal (the password must not pass through a chat or a pipe).\n"
                     f"Open PowerShell / Terminal and run:  {set_command(user)}")
        pw = getpass.getpass(f"App password for {user} (hidden): ").strip()
        if not pw:
            sys.exit("Nothing stored.")
        if sys.platform == "win32":
            _win_set(user, pw)
            print("Stored in Windows Credential Manager (entry 'gazette-smtp').")
        elif shutil.which("secret-tool"):
            r = subprocess.run(["secret-tool", "store", "--label=Gazette SMTP", "service", SERVICE, "account", user],
                               input=pw, text=True)
            if r.returncode:
                sys.exit("secret-tool failed; is a keyring (GNOME Keyring / KWallet) running?")
            print("Stored in the Secret Service keyring.")
        else:
            ans = input(f"No keychain found. Store it in {FALLBACK} (readable only by you)? [y/N] ")
            if ans.strip().lower() != "y":
                sys.exit("Nothing stored. You can also set the GAZETTE_SMTP_PASSWORD environment variable.")
            FALLBACK.parent.mkdir(parents=True, exist_ok=True)
            FALLBACK.touch(mode=0o600)
            FALLBACK.chmod(0o600)
            FALLBACK.write_text(pw, encoding="utf-8")
            print(f"Stored in {FALLBACK}.")
        return
    if cmd == "delete":
        user = smtp_user(args)
        done = False
        if sys.platform == "win32":
            done = _win_delete()
        elif sys.platform == "darwin":
            done = _run(["security", "delete-generic-password", "-s", SERVICE, "-a", user]).returncode == 0
        elif shutil.which("secret-tool"):
            done = _run(["secret-tool", "clear", "service", SERVICE, "account", user]).returncode == 0
        if FALLBACK.exists():
            FALLBACK.unlink()
            done = True
        print("Removed." if done else "Nothing was stored.")
        return
    print(__doc__)
    sys.exit(2)


if __name__ == "__main__":
    main()
