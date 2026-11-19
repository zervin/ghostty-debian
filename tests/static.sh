#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for script in scripts/*.sh tests/*.sh; do bash -n "$script"; done
shellcheck -x scripts/*.sh tests/*.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/release-metadata.py
if command -v dpkg-parsechangelog >/dev/null; then
    dpkg-parsechangelog -l debian/changelog -S Version
fi
echo 'PASS: static checks (not a build or runtime test)'
