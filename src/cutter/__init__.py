# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drive a Roland CAMM-1 GX-24 vinyl cutter directly over USB.

No printing system in the path: SVG in, HPGL out, bytes to the device node.
See README.md for the reasoning and history.md for how the design got here.
"""

__version__ = "0.1.0"

from .hpgl import HpglDocument, HpglError
from .device import Sender, DeviceError, find_devices
from .svg import SvgError

__all__ = [
    "HpglDocument",
    "HpglError",
    "Sender",
    "DeviceError",
    "find_devices",
    "SvgError",
]
