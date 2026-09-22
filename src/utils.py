"""Atomic files, subprocess boundaries and content-addressed cache."""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


class ProductionError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_name(path.name + ".tmp")

    if isinstance(content, bytes):
        tmp.write_bytes(content)
    else:
        tmp.write_text(content, encoding="utf-8")

    os.replace(str(tmp), str(path))


def save(path, data):
    atomic(
        path,
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ),
    )


def read(path, default=None):
    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return default


def command(args, cwd=None):
    try:
        p = subprocess.run(
            [str(a) for a in args],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=1200,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ProductionError(
            "Local process failed: " + str(e)
        ) from e

    if p.returncode:
        stderr = p.stderr or ""
        raise ProductionError(
            Path(str(args[0])).name + ": " + stderr[-2500:]
        )

    return (p.stdout or "") + (p.stderr or "")


def probe(path):
    return json.loads(
        command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ]
        )
    )


def valid_media(path, kind=None):
    path = Path(path)

    if not path.is_file() or path.stat().st_size < 100:
        return False

    try:
        info = probe(path)

        duration = float(
            info["format"].get("duration", 0)
        )

        if duration <= 0:
            return False

        if kind is None:
            return True

        return any(
            stream.get("codec_type") == kind
            for stream in info.get("streams", [])
        )

    except (
        ProductionError,
        ValueError,
        KeyError,
        TypeError,
    ):
        return False


class Cache:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def path(
        self,
        namespace,
        key,
        suffix=".json",
    ):
        p = (
            self.root
            / namespace
            / (digest(key) + suffix)
        )

        p.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        return p

    def get(
        self,
        namespace,
        key,
        ttl=None,
    ):
        obj = read(
            self.path(namespace, key)
        )

        if (
            not isinstance(obj, dict)
            or "created" not in obj
            or "value" not in obj
        ):
            return None

        if (
            ttl is not None
            and time.time() - obj["created"] > ttl
        ):
            return None

        return obj["value"]

    def put(
        self,
        namespace,
        key,
        value,
    ):
        save(
            self.path(namespace, key),
            {
                "created": time.time(),
                "value": value,
            },
        )


class RunLock:
    """
    Cross-platform single-run file lock.

    Windows:
        uses msvcrt.locking()

    macOS/Linux:
        uses fcntl.flock()
    """

    def __init__(self, path):
        self.path = Path(path)
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.file = open(
            self.path,
            "a+b",
        )

        try:
            if os.name == "nt":
                self._lock_windows()
            else:
                self._lock_unix()

        except Exception:
            self.file.close()
            self.file = None
            raise

        return self

    def _lock_windows(self):
        import msvcrt

        self.file.seek(
            0,
            os.SEEK_END,
        )

        if self.file.tell() == 0:
            self.file.write(b"\0")
            self.file.flush()

        self.file.seek(0)

        try:
            msvcrt.locking(
                self.file.fileno(),
                msvcrt.LK_NBLCK,
                1,
            )
        except OSError as e:
            raise ProductionError(
                "Another run is active in this project."
            ) from e

    def _lock_unix(self):
        import fcntl

        try:
            fcntl.flock(
                self.file,
                fcntl.LOCK_EX
                | fcntl.LOCK_NB,
            )
        except BlockingIOError as e:
            raise ProductionError(
                "Another run is active in this project."
            ) from e

    def __exit__(self, *_):
        if self.file is None:
            return

        try:
            if os.name == "nt":
                self._unlock_windows()
            else:
                self._unlock_unix()

        finally:
            self.file.close()
            self.file = None

    def _unlock_windows(self):
        import msvcrt

        try:
            self.file.seek(0)

            msvcrt.locking(
                self.file.fileno(),
                msvcrt.LK_UNLCK,
                1,
            )
        except OSError:
            pass

    def _unlock_unix(self):
        import fcntl

        try:
            fcntl.flock(
                self.file,
                fcntl.LOCK_UN,
            )
        except OSError:
            pass