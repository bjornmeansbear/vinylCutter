#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Turn on USB ethernet gadget mode on a Raspberry Pi Zero's SD card, so the Pi
# appears as a network device when plugged into a computer over USB. No monitor,
# no keyboard, no WiFi needed.
#
# Run this on the Mac with the SD card inserted, before first boot:
#
#     ./scripts/enable-usb-gadget.sh
#
# Idempotent. Backs up anything it edits. Only touches the FAT boot partition.
#
set -euo pipefail

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32mok\033[0m   %s\n' "$*"; }
warn() { printf '    \033[33mwarn\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31merror\033[0m %s\n\n' "$*" >&2; exit 1; }

# --------------------------------------------------------------------------
say "Finding the boot partition"

# Raspberry Pi OS names it 'bootfs' (Bookworm and later) or 'boot' (older).
BOOT=""
for candidate in /Volumes/bootfs /Volumes/boot; do
  [ -d "$candidate" ] && { BOOT="$candidate"; break; }
done

if [ -z "$BOOT" ]; then
  echo
  echo "    No /Volumes/bootfs or /Volumes/boot found. Currently mounted:"
  ls -1 /Volumes 2>/dev/null | sed 's/^/      /'
  echo
  die "Insert the SD card. If it is in and you still see nothing, the card may
       not be flashed yet -- write Raspberry Pi OS Lite with Raspberry Pi Imager
       first, then re-insert it."
fi
ok "$BOOT"

CONFIG="$BOOT/config.txt"
CMDLINE="$BOOT/cmdline.txt"
[ -f "$CONFIG" ]  || die "$CONFIG not found -- is this really a Pi boot partition?"
[ -f "$CMDLINE" ] || die "$CMDLINE not found -- is this really a Pi boot partition?"

STAMP=$(date +%Y%m%d%H%M%S)

# --------------------------------------------------------------------------
say "config.txt -- enable the dwc2 USB controller"

if grep -q '^dtoverlay=dwc2' "$CONFIG"; then
  ok "dtoverlay=dwc2 already present"
else
  cp "$CONFIG" "$CONFIG.bak.$STAMP"
  # Append under [all] so it applies regardless of any model-specific sections
  # already in the file.
  printf '\n[all]\ndtoverlay=dwc2\n' >> "$CONFIG"
  ok "added dtoverlay=dwc2  (backup: config.txt.bak.$STAMP)"
fi

# --------------------------------------------------------------------------
say "cmdline.txt -- load the ethernet gadget module"

# cmdline.txt MUST stay a single line; a stray newline makes the Pi unbootable.
if grep -q 'modules-load=dwc2,g_ether' "$CMDLINE"; then
  ok "modules-load=dwc2,g_ether already present"
else
  cp "$CMDLINE" "$CMDLINE.bak.$STAMP"
  # Insert immediately after rootwait, which is where the Pi docs put it.
  python3 - "$CMDLINE" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1])
line = p.read_text().strip()
if "rootwait" in line:
    line = line.replace("rootwait", "rootwait modules-load=dwc2,g_ether", 1)
else:
    line = line + " modules-load=dwc2,g_ether"
p.write_text(line + "\n")
PY
  ok "added modules-load=dwc2,g_ether  (backup: cmdline.txt.bak.$STAMP)"
fi

# Guard against the classic footgun.
if [ "$(wc -l < "$CMDLINE" | tr -d ' ')" -gt 1 ]; then
  warn "cmdline.txt has more than one line. It must be exactly one."
  warn "Restore from cmdline.txt.bak.$STAMP and edit by hand."
fi

# --------------------------------------------------------------------------
say "SSH"

if [ -f "$BOOT/ssh" ] || [ -f "$BOOT/ssh.txt" ]; then
  ok "ssh already enabled"
else
  touch "$BOOT/ssh"
  ok "created empty 'ssh' file to enable sshd on first boot"
fi

if [ -f "$BOOT/userconf.txt" ]; then
  ok "userconf.txt present -- a user account is preconfigured"
else
  warn "No userconf.txt. Raspberry Pi OS has no default 'pi' user any more."
  warn "If you did not set a username and password in Raspberry Pi Imager,"
  warn "you will not be able to log in. Re-flash with Imager's gear icon set,"
  warn "or create userconf.txt:"
  warn "    echo \"pi:\$(openssl passwd -6 'yourpassword')\" > $BOOT/userconf.txt"
fi

# --------------------------------------------------------------------------
say "Done"
cat <<EOF

    1. Eject the card:   diskutil unmountDisk \$(df "$BOOT" | tail -1 | awk '{print \$1}' | sed 's/s[0-9]*$//')
    2. Put it in the Pi.
    3. Plug USB into the port labelled 'USB', NOT 'PWR IN'.
       On a Pi Zero that is the INNER micro-USB, nearer the HDMI socket.
       The PWR IN port cannot carry data -- this is the single most common
       reason gadget mode "does not work".
    4. Wait ~90 seconds for first boot.
    5. Check your Mac sees it:

           ifconfig | grep -A3 '^en'          # look for a new interface
           ping raspberrypi.local
           ssh <youruser>@raspberrypi.local

EOF
