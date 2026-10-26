"""Restore externally sourced research inputs from a report specification."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python restore-inputs.py research/<project>/report-spec.json")
    root = Path.cwd().resolve()
    research = root / "research"
    manifest = Path(sys.argv[1]).resolve(strict=True)
    if not manifest.is_relative_to(research) or not manifest.is_file():
        raise ValueError("Report specification must be a file under research/")
    spec = json.loads(manifest.read_text())
    entries = spec.get("data_inputs", [])
    if spec.get("schema_version") != 2 or not isinstance(entries, list) or len(entries) > 50:
        raise ValueError("Expected a version 2 report with up to 50 external data inputs")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("External data input must be an object")
        name, url, expected = entry["path"], entry["url"], entry["sha256"]
        if not isinstance(name, str):
            raise ValueError("External data input path must be a string")
        parts = PurePosixPath(name).parts
        if len(parts) < 2 or parts[0] != "research" or any(part in {".", ".."} for part in parts) or name in seen:
            raise ValueError(f"Invalid or duplicate input path: {name}")
        seen.add(name)
        target = (root / name).resolve()
        if not target.is_relative_to(research):
            raise ValueError(f"Input path leaves research/: {name}")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"Expected an HTTPS download URL without credentials: {name}")
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError(f"Invalid SHA-256 for {name}")
        if target.exists():
            if not target.is_file() or sha256_file(target) != expected:
                raise ValueError(f"Existing input has the wrong SHA-256: {name}")
            print(f"verified {name}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.parent.resolve().is_relative_to(research):
            raise ValueError(f"Input directory leaves research/: {name}")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".terputer-", delete=False) as output:
                temporary = Path(output.name)
                digest = hashlib.sha256()
                request = urllib.request.Request(url, headers={"User-Agent": "Terputer-research-restore/1.0"})
                with urllib.request.urlopen(request, timeout=60) as source:
                    while chunk := source.read(1 << 20):
                        output.write(chunk)
                        digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError(f"Downloaded input has the wrong SHA-256: {name}")
            os.replace(temporary, target)
            print(f"restored {name}")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
