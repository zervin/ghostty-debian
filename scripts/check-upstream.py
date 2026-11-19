#!/usr/bin/env python3
"""Propose reviewed stable Ghostty inputs; never change the pinned Zig compiler."""

import argparse
import base64
from datetime import datetime, timezone
from email.utils import format_datetime
import json
import os
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

UPSTREAM = "repos/ghostty-org/ghostty"
VERSION = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
SHA = r"[0-9a-f]{40}"


def version_tuple(value):
    match = re.fullmatch(VERSION, value)
    if not match:
        raise ValueError(f"Not a stable semantic version: {value!r}")
    return tuple(map(int, match.groups()))


def trust_guard(environ):
    # Locally this tool is usable without Actions. In Actions only trusted main runs apply.
    if environ.get("GITHUB_ACTIONS") == "true":
        if (environ.get("GITHUB_EVENT_NAME") not in {"schedule", "workflow_dispatch"}
                or environ.get("GITHUB_REF") != "refs/heads/main"):
            raise ValueError("Upstream checker requires a scheduled/manual run on main")


def github_api(path):
    request = Request("https://api.github.com/" + path, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ghostty-debian-upstream-checker",
        **({"Authorization": "Bearer " + os.environ["GH_TOKEN"]}
           if os.environ.get("GH_TOKEN") else {}),
    })
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def read_config(text):
    config = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z_]+)=([^\s]+)", line)
        if not match or match[1] in config:
            raise ValueError("Malformed or duplicate release.conf input")
        config[match[1]] = match[2]
    version_tuple(config["GHOSTTY_VERSION"])
    version_tuple(config["ZIG_VERSION"])
    if not re.fullmatch(SHA, config["GHOSTTY_COMMIT"]):
        raise ValueError("Invalid pinned Ghostty commit")
    if not re.fullmatch(re.escape(config["GHOSTTY_VERSION"]) + r"-[0-9]+personal[0-9]+\.deb13u[0-9]+",
                        config["DEBIAN_VERSION"]):
        raise ValueError("Pinned Ghostty and Debian versions disagree")
    return config


def discover(config, api=None):
    api = api or github_api
    stable = []
    page = 1
    while True:
        tags = api(f"{UPSTREAM}/tags?per_page=100&page={page}")
        if not isinstance(tags, list):
            raise ValueError("Unexpected tags API response")
        for tag in tags:
            # Upstream stable tags use vX.Y.Z, not vt-*, tip, or prereleases.
            if re.fullmatch("v" + VERSION, tag["name"]):
                stable.append((version_tuple(tag["name"][1:]), tag))
        if len(tags) < 100:
            break
        page += 1
    if not stable:
        raise ValueError("No stable upstream tags found")
    _, latest = max(stable, key=lambda item: item[0])
    version = latest["name"][1:]
    if version_tuple(version) <= version_tuple(config["GHOSTTY_VERSION"]):
        return {"update_available": False, "version": version}

    ref = api(f"{UPSTREAM}/git/ref/tags/{latest['name']}")
    obj = ref["object"]
    if (ref.get("ref") != "refs/tags/" + latest["name"] or obj["type"] != "tag"
            or not re.fullmatch(SHA, obj["sha"])):
        raise ValueError("New stable release must have an annotated tag")
    tag = api(f"{UPSTREAM}/git/tags/{obj['sha']}")
    verification = tag.get("verification", {})
    if verification.get("verified") is not True or verification.get("reason") != "valid":
        raise ValueError("New stable tag does not have valid GitHub signature verification")
    commit = tag["object"]["sha"]
    if (tag.get("sha") != obj["sha"] or tag.get("tag") != latest["name"]
            or tag["object"]["type"] != "commit" or not re.fullmatch(SHA, commit)
            or commit != latest["commit"]["sha"]):
        raise ValueError("Tag name/object/commit mismatch; refusing update")
    contents = api(f"{UPSTREAM}/contents/build.zig.zon?ref={commit}")
    if contents.get("encoding") != "base64" or contents.get("type") != "file":
        raise ValueError("Expected build.zig.zon file contents")
    zon = base64.b64decode(contents["content"]).decode("utf-8")
    minima = re.findall(r'^\s*\.minimum_zig_version\s*=\s*"([^"\n]+)"\s*,', zon, re.M)
    if len(minima) != 1:
        raise ValueError("Cannot determine a unique upstream minimum Zig version")
    minimum = minima[0]
    if version_tuple(config["ZIG_VERSION"]) < version_tuple(minimum):
        raise ValueError(f"Ghostty {version} requires Zig >= {minimum}; pinned Zig "
                         f"{config['ZIG_VERSION']} is incompatible. Review compiler inputs "
                         "manually; no files were changed.")
    return {"update_available": True, "version": version, "commit": commit,
            "tag": latest["name"], "minimum_zig_version": minimum,
            "zig_version": config["ZIG_VERSION"],
            "debian_version": f"{version}-1personal1.deb13u1",
            "url": f"https://release.files.ghostty.org/{version}/ghostty-{version}.tar.gz"}


def update_files(root, candidate):
    if not candidate["update_available"]:
        return
    config_path = root / "release.conf"
    changelog_path = root / "debian/changelog"
    text = config_path.read_text()
    config = read_config(text)
    if version_tuple(candidate["version"]) <= version_tuple(config["GHOSTTY_VERSION"]):
        raise ValueError("Candidate is no longer newer than pinned inputs")
    replacements = {"GHOSTTY_VERSION": candidate["version"],
                    "GHOSTTY_COMMIT": candidate["commit"],
                    "DEBIAN_VERSION": candidate["debian_version"],
                    "GHOSTTY_URL": candidate["url"]}
    for key, value in replacements.items():
        if key not in config:
            raise ValueError(f"Missing {key} in release.conf")
        text = re.sub(r"^" + key + r"=.*$", lambda _: f"{key}={value}", text, flags=re.M)
    changelog = changelog_path.read_text()
    maintainer = re.search(r"^ -- ([^\n]+? <[^<>\n]+>)  ", changelog, re.M)
    if not maintainer:
        raise ValueError("Cannot preserve existing changelog maintainer")
    date = format_datetime(datetime.now(timezone.utc))
    entry = (f"ghostty ({candidate['debian_version']}) trixie; urgency=medium\n\n"
             f"  * Independent personal package of the signed Ghostty {candidate['version']} release.\n\n"
             f" -- {maintainer[1]}  {date}\n\n")
    config_path.write_text(text)
    changelog_path.write_text(entry + changelog)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="emit candidate JSON without writing")
    mode.add_argument("--update", action="store_true", help="update release.conf and debian/changelog")
    parser.add_argument("--expected-version", help="fail if the candidate changed since the check job")
    args = parser.parse_args()
    trust_guard(os.environ)
    root = Path(__file__).resolve().parents[1]
    candidate = discover(read_config((root / "release.conf").read_text()))
    if args.expected_version and candidate["version"] != args.expected_version:
        raise ValueError("Upstream candidate changed since check; rerun the workflow")
    if args.update:
        update_files(root, candidate)
    print(json.dumps(candidate, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        print(f"Upstream check failed: {error}", file=sys.stderr)
        sys.exit(1)
