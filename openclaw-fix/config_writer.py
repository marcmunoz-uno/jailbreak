#!/usr/bin/env python3
"""
Atomic config writer for openclaw.json.

Prevents corruption from concurrent writes via:
  - fcntl.flock exclusive locking
  - Write to temp file + os.replace (atomic rename)
  - JSON schema validation before commit
  - Automatic backup of previous config

Usage as module:
    from config_writer import write_config, read_config, validate_config

Usage as CLI:
    python3 config_writer.py validate
    python3 config_writer.py read
    python3 config_writer.py write <json_file>
    python3 config_writer.py write -       # read JSON from stdin
"""

import fcntl
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

CONFIG_PATH = Path(os.environ.get(
    "OPENCLAW_CONFIG", os.path.expanduser("~/.openclaw/openclaw.json")
))

REQUIRED_KEYS = {
    "meta", "env", "agents", "tools", "hooks",
    "session", "channels", "gateway", "plugins",
}

MAX_BACKUPS = 5
LOCK_TIMEOUT_SECONDS = 10


class ConfigError(Exception):
    """Raised when config validation or I/O fails."""


def validate_config(data):
    """Validate that data is a dict with all required top-level keys.

    Returns list of error strings (empty = valid).
    """
    errors = []
    if not isinstance(data, dict):
        errors.append(f"Config root must be a dict, got {type(data).__name__}")
        return errors
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        errors.append(f"Missing required keys: {', '.join(sorted(missing))}")
    for key in REQUIRED_KEYS & data.keys():
        if not isinstance(data[key], dict):
            errors.append(
                f"Key '{key}' must be a dict, got {type(data[key]).__name__}"
            )
    return errors


def _acquire_lock(lock_fd, timeout=LOCK_TIMEOUT_SECONDS):
    """Try to get an exclusive lock within timeout seconds."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise ConfigError(
                    f"Could not acquire config lock within {timeout}s. "
                    "Another process may be writing."
                )
            time.sleep(0.05)


def _rotate_backups(config_path):
    """Keep up to MAX_BACKUPS numbered backups."""
    for i in range(MAX_BACKUPS, 1, -1):
        src = config_path.with_suffix(f".json.bak.{i - 1}")
        dst = config_path.with_suffix(f".json.bak.{i}")
        if src.exists():
            shutil.copy2(str(src), str(dst))
    # Current .bak becomes .bak.1
    bak = config_path.with_suffix(".json.bak")
    if bak.exists():
        shutil.copy2(str(bak), config_path.with_suffix(".json.bak.1"))


def read_config(config_path=None):
    """Read and parse the config file. Returns dict."""
    path = Path(config_path) if config_path else CONFIG_PATH
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    lock_path = path.with_suffix(".json.lock")
    lock_fd = open(lock_path, "w")
    try:
        _acquire_lock(lock_fd)
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Config is not valid JSON: {e}")
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


def write_config(data, config_path=None, skip_validation=False):
    """Atomically write config data to disk.

    Steps:
      1. Validate data against schema
      2. Acquire exclusive file lock
      3. Back up current config
      4. Write to temp file in same directory
      5. os.replace temp -> config (atomic on same filesystem)
      6. Release lock
    """
    path = Path(config_path) if config_path else CONFIG_PATH
    if not skip_validation:
        errors = validate_config(data)
        if errors:
            raise ConfigError(
                "Config validation failed:\n  " + "\n  ".join(errors)
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".json.lock")
    lock_fd = open(lock_path, "w")
    try:
        _acquire_lock(lock_fd)

        # Back up existing config
        if path.exists():
            _rotate_backups(path)
            shutil.copy2(str(path), str(path.with_suffix(".json.bak")))

        # Write to temp file in same directory (same filesystem for atomic rename)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), prefix=".openclaw_tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w") as tmp_f:
                json.dump(data, tmp_f, indent=2)
                tmp_f.write("\n")
                tmp_f.flush()
                os.fsync(tmp_f.fileno())
            # Preserve original permissions if file exists
            if path.exists():
                st = os.stat(path)
                os.chmod(tmp_path, st.st_mode)
            else:
                os.chmod(tmp_path, 0o600)
            # Atomic replace
            os.replace(tmp_path, str(path))
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


def _cli_validate(args):
    path = Path(args[0]) if args else CONFIG_PATH
    try:
        data = json.load(open(path))
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    errors = validate_config(data)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(f"OK: {path} is valid")
    return 0


def _cli_read(args):
    path = Path(args[0]) if args else None
    try:
        data = read_config(path)
        print(json.dumps(data, indent=2))
        return 0
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def _cli_write(args):
    if not args:
        print("Usage: config_writer.py write <json_file|->", file=sys.stderr)
        return 1
    source = args[0]
    dest = Path(args[1]) if len(args) > 1 else None
    try:
        if source == "-":
            data = json.load(sys.stdin)
        else:
            with open(source) as f:
                data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"ERROR: Cannot read input: {e}", file=sys.stderr)
        return 1
    try:
        write_config(data, dest)
        print(f"OK: Config written to {dest or CONFIG_PATH}")
        return 0
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 0
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    dispatch = {
        "validate": _cli_validate,
        "read": _cli_read,
        "write": _cli_write,
    }
    fn = dispatch.get(cmd)
    if not fn:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(f"Available: {', '.join(dispatch)}", file=sys.stderr)
        return 1
    return fn(rest)


if __name__ == "__main__":
    sys.exit(main())
