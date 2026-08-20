#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Bootstrap a Raspberry Pi to drive the GX-24.
#
# Idempotent: safe to re-run. Everything that needs sudo is announced before it
# happens. Run from the repo root:
#
#     ./scripts/setup-pi.sh
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO/.venv"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32mok\033[0m   %s\n' "$*"; }
warn() { printf '    \033[33mwarn\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31merror\033[0m %s\n\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Linux" ] || die "This targets Linux. On macOS there is no usblp driver and no device node to write to."

# --------------------------------------------------------------------------
say "System packages"
# python3-venv is separate on Debian; libudev/avahi are already present on Pi OS.
sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-pip git
ok "python3-venv, python3-pip, git"

# --------------------------------------------------------------------------
say "Python environment"
# Raspberry Pi OS (Bookworm and later) marks the system Python as
# externally-managed, so pip refuses to install into it. A venv is not optional.
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
  ok "created $VENV"
else
  ok "$VENV already exists"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -e "$REPO"
ok "installed cutter $("$VENV/bin/cutter" --version | awk '{print $2}')"

# --------------------------------------------------------------------------
say "Kernel module"
# CUPS ships a modprobe blacklist for usblp so its own USB backend can claim
# printers. If CUPS was ever installed, that file is why /dev/usb/lp0 never
# appears -- and since this project does not use CUPS at all, the blacklist is
# pure obstacle.
if grep -rqs '^blacklist usblp' /etc/modprobe.d/ 2>/dev/null; then
  warn "usblp is blacklisted by:"
  grep -rls '^blacklist usblp' /etc/modprobe.d/ | sed 's/^/         /'
  warn "That blacklist ships with CUPS. This project does not use CUPS."
  warn "To undo it:  sudo rm <that file> && sudo modprobe usblp"
fi

if ! lsmod | grep -q '^usblp'; then
  sudo modprobe usblp 2>/dev/null || warn "could not load usblp"
fi
lsmod | grep -q '^usblp' && ok "usblp loaded" || warn "usblp not loaded"

# Load it at boot.
if [ ! -f /etc/modules-load.d/usblp.conf ]; then
  echo usblp | sudo tee /etc/modules-load.d/usblp.conf >/dev/null
  ok "usblp will load at boot"
fi

# --------------------------------------------------------------------------
say "Device permissions"
sudo cp "$REPO/config/99-roland-gx24.rules" /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
ok "udev rule installed"

if id -nG "$USER" | tr ' ' '\n' | grep -qx lp; then
  ok "$USER is already in the 'lp' group"
else
  sudo usermod -aG lp "$USER"
  warn "added $USER to 'lp' -- you must log out and back in for this to apply"
fi

# --------------------------------------------------------------------------
say "Looking for the cutter"
if [ -n "$(ls /dev/usb/lp* 2>/dev/null || true)" ]; then
  for d in /dev/usb/lp*; do ok "$d  $(ls -l "$d" | awk '{print $1, $3, $4}')"; done
  echo
  echo "    Roland USB IDs seen on this machine:"
  lsusb | grep -i roland | sed 's/^/      /' || echo "      (none reported by lsusb -- check the name in: lsusb)"
else
  warn "No /dev/usb/lp* found."
  warn "Check: cutter powered on, USB cable seated, then 'dmesg | tail -20'"
fi

# --------------------------------------------------------------------------
say "Done"
cat <<EOF

    Verify:      $VENV/bin/cutter info
    First cut:   $VENV/bin/cutter pattern registration --force 110 --dry-run
                 (read it, then drop --dry-run)

    If anything looks wrong: ./scripts/diagnose.sh
EOF
