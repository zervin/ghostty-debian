#!/usr/bin/env bash
# Runs only inside the credential-free preparation container.
set -euo pipefail
# shellcheck source=release.conf
source /repo/release.conf
umask 022
mkdir -p /work/home /work/inputs /work/zig-cache /work/records
cd /work/inputs
fetch() { curl --fail --show-error --silent --location --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 3 "$1" --output "$2"; }
fetch "$GHOSTTY_URL" ghostty.tar.gz
fetch "$GHOSTTY_URL.minisig" ghostty.tar.gz.minisig
fetch "$ZIG_URL" zig.tar.xz
fetch "$ZIG_URL.minisig" zig.tar.xz.minisig
minisign -Vm ghostty.tar.gz -x ghostty.tar.gz.minisig -P "$GHOSTTY_KEY" | tee /work/records/ghostty-signature.txt
minisign -Vm zig.tar.xz -x zig.tar.xz.minisig -P "$ZIG_KEY" | tee /work/records/zig-signature.txt
sha256sum ghostty.tar.gz zig.tar.xz > /work/records/verified-inputs.sha256
cp ./*.minisig /work/records/
mkdir /work/source /work/zig
tar --extract --gzip --file ghostty.tar.gz --directory /work/source --strip-components=1 --no-same-owner
tar --extract --xz --file zig.tar.xz --directory /work/zig --strip-components=1 --no-same-owner
[[ $(zig version) == "$ZIG_VERSION" ]]
# A valid signature alone must not permit replaying a different signed release.
[[ $(< /work/source/VERSION) == "$GHOSTTY_VERSION" ]]
# Fetch through the signed manifests into default zig-pkg local storage. Bare
# fetch produces unusable recompressed archives with Zig 0.17.1; never reuse them.
[[ ! -e /work/source/zig-pkg ]]
[[ -z $(find "$ZIG_GLOBAL_CACHE_DIR" -mindepth 1 -print -quit) ]]
(cd /work/source && zig build --fetch=all)
(cd /work/source && find zig-pkg -type f -print0 | sort -z | xargs -0 sha256sum) > /work/records/dependency-packages.sha256
cp -a /repo/debian /work/source/debian
cp /repo/LICENSE /work/source/debian/packaging-LICENSE
# Record fetched archives as well as the local package files used by the build.
(cd /work/zig-cache && find p -type f -print0 | sort -z | xargs -0 sha256sum) > /work/records/dependency-cache.sha256
