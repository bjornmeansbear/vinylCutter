# SPDX-License-Identifier: AGPL-3.0-or-later
"""Talking to the GX-24 over USB printer class.

The GX-24 enumerates as a USB printer-class device. On Linux the `usblp`
kernel module claims it and exposes a character device at /dev/usb/lp0, which
accepts HPGL as raw bytes. That node is the machine's actual interface -- there
is no printing system in the path, and nothing here depends on CUPS.

macOS has no usblp equivalent, so there is no device node to write to. This
module detects that and says so rather than failing obscurely; on a Mac you use
--dry-run to inspect output and let the Pi do the cutting.

Flow control
------------
The GX-24's input buffer is small, and blasting a large file at the device node
in one write is a known way to lose commands mid-job -- the symptom is a cut
that starts correctly then jumps to the origin partway through. So writes are
chunked with a pause between them, which lets the machine drain. This is
open-loop: USB printer class is bidirectional in principle and the GX-24 answers
HPGL status queries, but reading back reliably is firmware-dependent, so the
conservative default is simply to write slower than the machine consumes.
"""

from __future__ import annotations

import platform
import sys
import time
from dataclasses import dataclass
from glob import glob
from pathlib import Path

#: Where usblp puts printer-class devices, most likely first.
DEVICE_GLOBS = ("/dev/usb/lp*", "/dev/lp*")

#: Bytes per write. Deliberately small -- the cost is a few milliseconds and
#: the benefit is not silently truncating someone's job.
DEFAULT_CHUNK_BYTES = 1024

#: Seconds to pause between chunks.
DEFAULT_CHUNK_DELAY = 0.05


class DeviceError(RuntimeError):
    """Raised when the cutter cannot be reached or written to."""


def find_devices() -> list[str]:
    """Return candidate device nodes, most likely first."""
    found: list[str] = []
    for pattern in DEVICE_GLOBS:
        found.extend(sorted(glob(pattern)))
    return found


def default_device() -> str | None:
    """The device we would use if none is specified."""
    devices = find_devices()
    return devices[0] if devices else None


def platform_note() -> str | None:
    """Explain, if relevant, why no device is going to show up here."""
    if platform.system() == "Darwin":
        return (
            "macOS has no usblp driver, so a USB cutter never appears as a "
            "device node. Generate HPGL here with --dry-run and send it from "
            "the Pi."
        )
    if platform.system() == "Windows":
        return "Windows is not supported; this targets Linux device nodes."
    return None


@dataclass
class Sender:
    """Writes an HPGL stream to the cutter in paced chunks."""

    device: str | None = None
    chunk_bytes: int = DEFAULT_CHUNK_BYTES
    chunk_delay: float = DEFAULT_CHUNK_DELAY
    dry_run: bool = False
    #: Called with (bytes_sent, bytes_total) after each chunk.
    progress: callable | None = None

    def __post_init__(self) -> None:
        if self.dry_run:
            return
        if self.device is None:
            self.device = default_device()
        if self.device is None:
            note = platform_note()
            hint = f" {note}" if note else (
                " Check that the cutter is powered on and connected, then look "
                "for it with: dmesg | tail, ls /dev/usb/"
            )
            raise DeviceError(f"No cutter device found.{hint}")

    def send(self, hpgl: str) -> int:
        """Send an HPGL stream. Returns the number of bytes written.

        HPGL is ASCII by definition, so a non-ASCII character means something
        upstream produced text the cutter cannot parse -- better to fail here
        than to have the machine choke on a byte it will silently drop.
        """
        try:
            payload = hpgl.encode("ascii")
        except UnicodeEncodeError as exc:
            raise DeviceError(
                f"HPGL contains a non-ASCII character at position {exc.start}; "
                "the cutter cannot parse it."
            ) from exc

        total = len(payload)

        if self.dry_run:
            sys.stdout.write(hpgl)
            return total

        path = Path(self.device)
        if not path.exists():
            raise DeviceError(f"{self.device} does not exist.")

        sent = 0
        try:
            # Unbuffered binary write: we are pacing this ourselves and do not
            # want Python's buffering to undo the chunking.
            with open(path, "wb", buffering=0) as fh:
                for i in range(0, total, self.chunk_bytes):
                    chunk = payload[i : i + self.chunk_bytes]
                    fh.write(chunk)
                    sent += len(chunk)
                    if self.progress:
                        self.progress(sent, total)
                    if self.chunk_delay and sent < total:
                        time.sleep(self.chunk_delay)
        except PermissionError as exc:
            raise DeviceError(
                f"Permission denied writing to {self.device}. Install the udev "
                "rule in config/99-roland-gx24.rules and add yourself to the "
                "'lp' group, then re-plug the cutter."
            ) from exc
        except OSError as exc:
            raise DeviceError(f"Write to {self.device} failed: {exc}") from exc

        return sent
