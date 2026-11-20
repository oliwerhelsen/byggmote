import errno
import json
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

__version__ = "2026.1118.1"
# Bumped when the app–engine contract (docs/SPEC.md) changes incompatibly; the app refuses other protocols.
PROTOCOL = 29
MAC, WINDOWS, LINUX = sys.platform == "darwin", sys.platform == "win32", sys.platform == "linux"
# The name and folders the app's edition gives its engine (docs/EDITIONS.md); run alone, the CLI is the default edition's.
APP = os.environ.get("BYGGMOTE_APP", "Byggmöte")
FOLDER = os.environ.get("BYGGMOTE_FOLDER", APP)
CONFIG_NAME = os.environ.get("BYGGMOTE_CONFIG_NAME", "byggmote")
LOCAL_MODEL = os.environ.get("BYGGMOTE_LOCAL_MODEL", "1") != "0"
OWN_INSTRUCTIONS = os.environ.get("BYGGMOTE_OWN_INSTRUCTIONS", "1") != "0"
# The speech backend: MLX and PyTorch on the Mac, ONNX on the CPU on Windows and Linux (docs/WINDOWS.md, docs/LINUX.md).
BACKEND = "mlx" if MAC else "onnx"


class ArgError(ValueError):
    """A bad argument value: exit 2."""


def replace(src: Path, dst: Path, tries: int = 5):
    """os.replace. On Windows it fails while another process has `dst` open (a sync client, an editor): try again."""
    for i in range(tries):
        try:
            return os.replace(src, dst)
        except PermissionError:
            if not WINDOWS or i == tries - 1:
                raise
            time.sleep(0.05 * 2 ** i)


def atomic_write(p: Path, text: str):
    """Write to `.tmp` and rename; no `.tmp` is left behind on failure."""
    tmp = p.with_name(p.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        replace(tmp, p)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_json(p: Path, *keys: str) -> dict:
    """A JSON object with `keys`; ValueError naming the file otherwise."""
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"cannot read {p}: {e}") from None
    if not isinstance(obj, dict) or not all(k in obj for k in keys):
        raise ValueError(f"cannot read {p}: expected {', '.join(keys)}")
    return obj


def xdg(var: str, default: str) -> Path:
    """An XDG base folder on Linux: $XDG_… when it is an absolute path, else the spec's default."""
    v = os.environ.get(var, "")
    return Path(v) if os.path.isabs(v) else Path(default).expanduser()


def short_error(e: BaseException) -> str:
    """An error as a short sentence for the app; the raw error goes to stderr."""
    import httpx
    import socket
    import urllib.error
    x = e
    while x:
        if isinstance(x, OSError) and x.errno == errno.ENOSPC:
            return "not enough disk space"
        if isinstance(x, (ConnectionError, TimeoutError, socket.gaierror, httpx.TransportError)) or (
                isinstance(x, urllib.error.URLError) and not isinstance(x, urllib.error.HTTPError)):
            return "network unreachable"
        x = x.__cause__ or x.__context__
    if isinstance(e, PermissionError) and e.errno == errno.EPERM and MAC:  # macOS's privacy settings (#1232)
        return f"macOS does not let {APP} open {e.filename}" if e.filename else f"macOS does not let {APP} open the folder"
    if isinstance(e, PermissionError) or getattr(e, "errno", None) == errno.EROFS:
        if not e.filename:
            return "permission denied"
        p = Path(e.filename)
        return f"can't write to {p.parent if p.suffix == '.tmp' else p}"  # .tmp: an atomic write into that folder
    if isinstance(e, OSError) and e.errno and e.strerror:  # "[Errno 2] No such file…: 'x'" reads as code
        what = e.strerror[0].lower() + e.strerror[1:]
        return f"{what}: {e.filename}" if e.filename else what
    return str(e)


def _alive(pid: int) -> bool:
    if WINDOWS:  # os.kill(pid, 0) would end the process there
        import ctypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = ctypes.c_void_p
        k.GetExitCodeProcess.argtypes, k.CloseHandle.argtypes = (ctypes.c_void_p, ctypes.c_void_p), (ctypes.c_void_p,)
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5  # access denied: it exists
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return not ok or code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def sweep(prefix: str):
    """$TMPDIR/<prefix>.<pid> folders of engines that are dead."""
    for d in Path(tempfile.gettempdir()).glob(f"{prefix}.*"):
        pid = d.name.removeprefix(f"{prefix}.")
        if pid.isdigit() and not _alive(int(pid)):
            shutil.rmtree(d, ignore_errors=True)


@contextmanager
def scratch():
    """Temp files of this process, the model libraries' too, in $TMPDIR/byggmote.<pid>, removed on the way out.
    On the way in, folders left by dead engines (SIGKILL, crash) go, and NeMo's unpacked models from engines
    before this (`tmp…/model_weights.ckpt`, 2.3 GB each) that are over an hour old."""
    prev, root = tempfile.tempdir, Path(tempfile.gettempdir())
    sweep("byggmote")
    for f in root.glob("tmp*/model_weights.ckpt"):
        try:
            if time.time() - f.parent.stat().st_mtime > 3600:  # the file keeps the archive's mtime
                shutil.rmtree(f.parent, ignore_errors=True)
        except OSError:
            pass  # gone meanwhile
    d = root / f"byggmote.{os.getpid()}"
    d.mkdir(exist_ok=True)
    tempfile.tempdir = str(d)
    try:
        yield d
    finally:
        tempfile.tempdir = prev
        shutil.rmtree(d, ignore_errors=True)
