#!/usr/bin/env python3
"""Preserve discoverable upstream and dependency notices without flattening paths."""
import os
from pathlib import Path
import shutil

out = Path("debian/bundled-licenses")
out.mkdir(parents=True, exist_ok=True)
for label, root in (("source", Path(".")), ("zig-cache", Path(os.environ["ZIG_GLOBAL_CACHE_DIR"]) / "p")):
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {"debian", ".zig-cache", "zig-out", ".git"})
        for name in sorted(files):
            lower = name.lower()
            if not (any(word in lower for word in ("license", "copying", "copyright", "notice")) or lower in {"ofl", "ofl.txt"}):
                continue
            source = Path(directory) / name
            if source.is_symlink() or not source.is_file():
                continue
            target = out / label / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
