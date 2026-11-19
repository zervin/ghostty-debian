#!/usr/bin/env python3
"""Emit only validated release identifiers from the reviewed configuration."""
from pathlib import Path
import os
import re


def identifiers(config: str) -> tuple[str, str]:
    lines = [line.split("=", 1) for line in config.splitlines() if line and not line.startswith("#")]
    values = dict(lines)
    version = values["DEBIAN_VERSION"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-[0-9]+personal[0-9]+\.deb13u[0-9]+", version):
        raise ValueError("Unexpected Debian version")
    if values["GHOSTTY_VERSION"] != version.split("-", 1)[0]:
        raise ValueError("Upstream/Debian version mismatch")
    return version, "ghostty-" + version


if __name__ == "__main__":
    version, tag = identifiers(Path("release.conf").read_text())
    output = f"version={version}\ntag={tag}\n"
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write(output)
    else:
        print(output, end="")
