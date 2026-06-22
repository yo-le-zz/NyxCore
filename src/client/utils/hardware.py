"""Hardware fingerprint utility — cross-platform."""
from __future__ import annotations

import hashlib
import platform
import socket
import uuid


def get_hardware_id() -> str:
    """Return a stable hardware ID derived from MAC address + hostname."""
    mac = uuid.getnode()
    hostname = socket.gethostname()
    raw = f"{mac}-{hostname}-{platform.system()}-{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:48]


def get_os_info() -> str:
    return f"{platform.system()} {platform.release()} ({platform.machine()})"


def get_hostname() -> str:
    return socket.gethostname()
