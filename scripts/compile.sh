#!/usr/bin/env bash
# Runs as uid 1000 with --network none and a read-only container root.
set -euo pipefail
# shellcheck source=release.conf
source /repo/release.conf
umask 022
cd /work/source
[[ $(dpkg-parsechangelog -S Version) == "$DEBIAN_VERSION" ]]
[[ $(zig version) == "$ZIG_VERSION" ]]
export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH=$(dpkg-parsechangelog -S Timestamp)
export DEB_BUILD_OPTIONS
DEB_BUILD_OPTIONS=parallel=$(nproc)
dpkg-buildpackage --build=binary --no-sign
packages=(/work/*.deb)
[[ ${#packages[@]} == 1 ]]
[[ $(dpkg-deb -f "${packages[0]}" Package) == ghostty ]]
[[ $(dpkg-deb -f "${packages[0]}" Version) == "$DEBIAN_VERSION" ]]
[[ $(dpkg-deb -f "${packages[0]}" Architecture) == amd64 ]]
# Lintian's normal exit code treats errors as fatal; warnings are retained for review.
lintian --fail-on error /work/*.changes 2>&1 | tee /out/lintian.log
cp /work/*.deb /work/*.buildinfo /work/*.changes /out/
cp /work/records/* /out/
cp /work/packaging-*.txt /out/
dpkg-query -W -f='${binary:Package}\t${Version}\t${Architecture}\n' > /out/build-apt-inventory.tsv
{
    printf 'ghostty_version=%s\nupstream_tag_commit=%s\nzig_version=%s\ndebian_version=%s\nbase_image=%s\n' \
        "$GHOSTTY_VERSION" "$GHOSTTY_COMMIT" "$ZIG_VERSION" "$DEBIAN_VERSION" "$DEBIAN_IMAGE"
    printf 'source_date_epoch=%s\nnetwork_during_compile=none\nuid=%s\n' "$SOURCE_DATE_EPOCH" "$(id -u)"
    printf 'build_options=ReleaseSafe,cpu=baseline,pie=true,sentry=false,bundled-gtk4-layer-shell,emit-docs\n'
    zig version
    dpkg-buildpackage --version
    uname -a
} > /out/build-metadata.txt
dpkg-deb --info "${packages[0]}" > /out/package-info.txt
dpkg-deb --contents "${packages[0]}" > /out/package-contents.txt
mkdir /work/control
dpkg-deb -e "${packages[0]}" /work/control
# dh_makeshlibs should emit ldconfig triggers for the bundled shared library.
grep -Eq '^activate(-noawait)? ldconfig$' /work/control/triggers
cp /work/control/triggers /out/package-triggers.txt
