#!/usr/bin/env bash
# Fresh Debian base, not the builder image. Deliberately headless.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
packages=(/artifacts/ghostty_*_amd64.deb)
[[ ${#packages[@]} == 1 && -f ${packages[0]} ]]
apt-get install -y --no-install-recommends "${packages[0]}" ncurses-bin desktop-file-utils
version=$(dpkg-deb -f "${packages[0]}" Version)
[[ $(dpkg-query -W -f='${Version}' ghostty) == "$version" ]]
ghostty +version | tee /tmp/ghostty-version.txt
upstream=${version%%-*}
grep -Fq "Ghostty $upstream" /tmp/ghostty-version.txt
# Test CLI as a non-root user with a new home and no display server.
useradd --create-home smoke
printf 'font-size = 12\n' > /tmp/valid.ghostty
runuser -u smoke -- ghostty +validate-config --config-file=/tmp/valid.ghostty
printf 'this-option-does-not-exist = true\n' > /tmp/invalid.ghostty
if runuser -u smoke -- ghostty +validate-config --config-file=/tmp/invalid.ghostty; then
    echo 'Invalid config unexpectedly accepted' >&2; exit 1
fi
infocmp -x xterm-ghostty
ldd /usr/bin/ghostty | tee /tmp/ghostty-ldd.txt
if grep -q 'not found' /tmp/ghostty-ldd.txt; then
    echo 'Unresolved runtime library' >&2; exit 1
fi
grep -F '/usr/bin/../lib/ghostty/libgtk4-layer-shell.so' /tmp/ghostty-ldd.txt
# Validate application entries; KDE service-menu entries use a different schema.
while IFS= read -r desktop; do desktop-file-validate "$desktop"; done < <(dpkg -L ghostty | grep '^/usr/share/applications/.*\.desktop$')
files=$(dpkg -L ghostty)
for resource in '/usr/share/icons/' '/usr/share/man/' '/usr/share/bash-completion/' '/usr/share/fish/' '/usr/share/zsh/' '/usr/share/doc/ghostty/bundled-licenses/'; do
    grep -Fq "$resource" <<< "$files"
done
dpkg-query -W -f='${binary:Package}\t${Version}\t${Architecture}\n'
apt-get purge -y ghostty
[[ ! -e /usr/bin/ghostty ]]
[[ ! -e /usr/lib/ghostty/libgtk4-layer-shell.so ]]
if dpkg-query -W -f='${db:Status-Status}' ghostty 2>/dev/null | grep -q installed; then
    exit 1
fi
echo 'PASS: install, version, config, terminfo, resources, private shared-library lookup, purge'
