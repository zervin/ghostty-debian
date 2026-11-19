#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
root=$PWD
# shellcheck source=release.conf
source "$root/release.conf"
[[ $(uname -m) == x86_64 ]] || { echo 'Only native amd64 builds are supported' >&2; exit 1; }
work=${WORK_DIR:-$root/.work/build}
out=${OUTPUT_DIR:-$root/artifacts}
mkdir -p "$work" "$out"
work=$(realpath "$work")
out=$(realpath "$out")
[[ -z $(find "$work" "$out" -mindepth 1 -print -quit) ]] || {
    echo 'WORK_DIR and OUTPUT_DIR must both be empty; preserve previous records first' >&2; exit 1;
}
[[ $work != "$out" && $work != / && $out != / ]] || exit 1
# Only these new scratch/output directories are writable by container uid 1000.
chmod 0777 "$work" "$out"
image=ghostty-debian-builder:local
docker build --platform linux/amd64 --build-arg "DEBIAN_IMAGE=$DEBIAN_IMAGE" -t "$image" "$root"
# Use the immutable local ID, not the mutable tag, for every subsequent step.
image=$(docker image inspect --format '{{.Id}}' "$image")
docker image inspect "$image" > "$out/builder-image.json"
printf '%s\n' "$image" > "$out/builder-image-id.txt"
git rev-parse HEAD > "$work/packaging-commit.txt"
git status --porcelain > "$work/packaging-status.txt"
# GitHub release uploads reject zero-byte assets; record cleanliness explicitly.
if [[ ! -s "$work/packaging-status.txt" ]]; then
    printf 'clean\n' > "$work/packaging-status.txt"
fi
common=(--rm --platform linux/amd64 --user 1000:1000 --read-only
    --cap-drop ALL --security-opt no-new-privileges --pids-limit 2048
    --tmpfs '/tmp:rw,nosuid,nodev,size=2g'
    --mount "type=bind,src=$root,dst=/repo,readonly"
    --mount "type=bind,src=$work,dst=/work")
# Online preparation fetches through the verified source's dependency manifests.
# No home directory, token, SSH agent, or Docker socket is passed through.
docker run "${common[@]}" "$image" bash /repo/scripts/prepare.sh 2>&1 | tee "$out/prepare.log"
# Actual compilation has no network interface other than loopback.
docker run "${common[@]}" --network none \
    --mount "type=bind,src=$out,dst=/out" \
    "$image" bash /repo/scripts/compile.sh 2>&1 | tee "$out/build.log"
# Separate fresh runtime, with signed Debian apt access only for installation.
docker run --rm --platform linux/amd64 \
    --mount "type=bind,src=$root/scripts,dst=/tests,readonly" \
    --mount "type=bind,src=$out,dst=/artifacts,readonly" \
    "$DEBIAN_IMAGE" bash /tests/smoke-test.sh 2>&1 | tee "$out/smoke-test.log"
cp "$root/release.conf" "$out/release.conf"
printf 'Headless smoke passed; interactive Wayland/X11 testing is still pending.\n' > "$out/TESTING.txt"
(cd "$out" && find . -maxdepth 1 -type f -printf '%f\0' | sort -z | xargs -0 sha256sum > "$work/SHA256SUMS")
mv "$work/SHA256SUMS" "$out/SHA256SUMS"
echo "Artifacts and checksums: $out"
