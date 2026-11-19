#!/usr/bin/env bash
# Run after preparation, inside the --network none compile container. Requires Zig.
set -euo pipefail
source_dir=$(realpath "${1:-/work/source}")
expected=$(python3 - "$source_dir/build.zig.zon" <<'PY'
from pathlib import Path
import re
import sys
text = Path(sys.argv[1]).read_text()
match = re.search(r'\.libxev\s*=\s*\.\{[^}]*\.hash\s*=\s*"([A-Za-z0-9_.-]+)"', text)
if not match:
    raise SystemExit('Cannot identify libxev hash in verified manifest; review upstream changes')
print(match[1])
PY
)
dependency="$source_dir/zig-pkg/$expected"
# This known wrapped upstream archive must have its manifest directly at root.
grep -Fq ".hash = \"$expected\"" "$source_dir/build.zig.zon"
[[ -f "$dependency/build.zig.zon" && ! -L $dependency ]]
zig=${ZIG:-zig}
# Zig compiles a helper into this cache; /tmp is intentionally mounted noexec.
verification=$(mktemp -d "${source_dir%/*}/cache-verification.XXXXXX")
trap 'rm -rf "$verification"' EXIT
# A fresh cache and unrelated cwd ensure directory-name lookups cannot stand in
# for computing the local directory's package hash. No dependency URLs are used.
actual=$(cd "$verification" && ZIG_GLOBAL_CACHE_DIR="$verification/cache" "$zig" fetch "$dependency")
printf 'expected=%s\ncomputed=%s\n' "$expected" "$actual"
[[ $actual == "$expected" ]]
echo 'PASS: prefetched libxev root and recomputed package hash match signed manifest'
