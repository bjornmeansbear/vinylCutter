#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Report everything relevant about whether this machine can see the cutter.
#
# Read-only, no sudo, changes nothing. Run it after plugging the GX-24 in; the
# output is meant to be pasted somewhere for help if the answer is not obvious.
#
#     ./scripts/diagnose.sh
#
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

hr()  { printf '\n\033[1m--- %s %s\033[0m\n' "$*" "$(printf '%.0s-' $(seq 1 $((60 - ${#1}))))"; }

hr "system"
uname -srm
[ -f /etc/os-release ] && . /etc/os-release && echo "$PRETTY_NAME"
[ -f /proc/device-tree/model ] && tr -d '\0' < /proc/device-tree/model && echo

hr "usb devices"
if command -v lsusb >/dev/null; then
  lsusb
  echo
  if lsusb | grep -qi roland; then
    echo "Roland device found:"
    lsusb | grep -i roland
  else
    echo "No device reporting as Roland."
    echo "The GX-24 may report under a generic name -- look for anything that"
    echo "appeared only after you plugged the cutter in."
  fi
else
  echo "lsusb not installed:  sudo apt-get install usbutils"
fi

hr "usblp kernel module"
if ! command -v lsmod >/dev/null; then
  echo "lsmod not available -- this section only applies on Linux."
elif lsmod | grep -q '^usblp'; then
  lsmod | grep '^usblp'
else
  echo "NOT LOADED. Try: sudo modprobe usblp"
fi

if grep -rqs '^blacklist usblp' /etc/modprobe.d/ 2>/dev/null; then
  echo
  echo "BLACKLISTED by:"
  grep -rls '^blacklist usblp' /etc/modprobe.d/ | sed 's/^/  /'
  echo "That file ships with CUPS so its USB backend can claim printers."
  echo "This project does not use CUPS. Remove the file and modprobe usblp."
fi

hr "device nodes"
if ls /dev/usb/lp* >/dev/null 2>&1; then
  ls -l /dev/usb/lp*
else
  echo "No /dev/usb/lp* present."
  ls -l /dev/lp* 2>/dev/null || echo "No /dev/lp* either."
fi

hr "permissions"
echo "user:   $USER"
echo "groups: $(id -nG)"
if id -nG | tr ' ' '\n' | grep -qx lp; then
  echo "        'lp' present"
else
  echo "        'lp' MISSING -- sudo usermod -aG lp $USER, then log out and back in"
fi
[ -f /etc/udev/rules.d/99-roland-gx24.rules ] \
  && echo "udev rule installed" \
  || echo "udev rule NOT installed -- run ./scripts/setup-pi.sh"

hr "recent kernel messages"
# dmesg is root-only when kernel.dmesg_restrict=1.
if dmesg 2>/dev/null | tail -25; then :; else
  echo "(restricted -- run: sudo dmesg | tail -25)"
fi

hr "cutter cli"
if [ -x "$REPO/.venv/bin/cutter" ]; then
  "$REPO/.venv/bin/cutter" info
elif command -v cutter >/dev/null; then
  cutter info
else
  echo "Not installed. Run ./scripts/setup-pi.sh"
fi

echo
