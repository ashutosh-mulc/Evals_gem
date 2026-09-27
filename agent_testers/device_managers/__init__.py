"""
Device Managers Package — Common imports and base classes.

This module provides shared imports and the base DeviceManagerTemplate class
for all device manager implementations.

Usage:
    from agent_testers.device_managers import (
        DeviceManagerTemplate,
        AdbClient,
        logging,
        os,
        shutil,
        subprocess,
        time,
    )
"""

from __future__ import annotations

# Re-export base class
from agent_testers.device_managers.device_manager import DeviceManagerTemplate

# Re-export commonly used utilities
from utils.adb_client import AdbClient

# Re-export standard library modules commonly used
import logging
import os
import shutil
import signal
import subprocess
import time

__all__ = [
    # Base class
    "DeviceManagerTemplate",
    # Utilities
    "AdbClient",
    # Standard library (for convenience in manager files)
    "logging",
    "os",
    "shutil",
    "signal",
    "subprocess",
    "time",
]
