#!/usr/bin/env bash
# kaushal's installer: links ~/.local/bin/kaushal and the login unit, then
# gives every agent the skills and tools. No root. From a checkout (kosha's
# copy) it installs that; otherwise it clones its newest release first:
#
#   curl -fsSL https://raw.githubusercontent.com/Theyashsawarkar/kaushal/main/install.sh | bash
set -euo pipefail
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null ||
  { echo "kaushal needs Python 3.11 or newer" >&2; exit 1; }
here=$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd || true)
if [ -n "$here" ] && [ -f "$here/bin/kaushal" ]; then
  src=$here
else
  command -v git >/dev/null || { echo "kaushal needs git" >&2; exit 1; }
  src="${XDG_DATA_HOME:-$HOME/.local/share}/kaushal"
  if [ -d "$src/.git" ]; then
    git -C "$src" fetch -q --tags origin
  else
    git clone -q https://github.com/Theyashsawarkar/kaushal "$src"
  fi
  latest=$(git -C "$src" tag -l 'v*' --sort=-v:refname | head -1)
  [ -n "$latest" ] && git -C "$src" -c advice.detachedHead=false checkout -q "$latest"
fi
mkdir -p "$HOME/.local/bin"
ln -sfn "$src/bin/kaushal" "$HOME/.local/bin/kaushal"
# Synced again at every login: new agents, new vesha profiles, new skills.
units="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$units"
ln -sfn "$src/systemd/kaushal.service" "$units/kaushal.service"
systemctl --user daemon-reload 2>/dev/null || true
"$src/bin/kaushal" sync
echo "kaushal installed: $HOME/.local/bin/kaushal"
echo "to sync at every login: systemctl --user enable kaushal (Vayu starts it for you)"
