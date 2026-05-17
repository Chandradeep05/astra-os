"""
ASTRA OS — System Info Tool
=============================
Gives the agent awareness of its environment:
  - Current date and time
  - Platform/OS information
  - Disk usage
  - Working directory

All operations are read-only and safe (no system modifications).
"""

import platform
import os
import shutil
from datetime import datetime


class SystemInfoTool:
    """Provides current system information. Safe, read-only operation."""

    def __init__(self):
        self.name = "system_info"
        self.description = (
            "Get current system information including date/time, OS, disk usage, "
            "and working directory. Useful when you need to know the current time, "
            "check available disk space, or understand the platform you're running on."
        )

    async def execute(self, info_type: str = "all") -> str:
        """
        Get system information.
        info_type: 'time', 'platform', 'disk', 'all' (default)
        """
        parts = []

        if info_type in ("time", "all"):
            now = datetime.now()
            parts.append(
                f"📅 Date & Time:\n"
                f"   Date: {now.strftime('%A, %B %d, %Y')}\n"
                f"   Time: {now.strftime('%I:%M:%S %p')}\n"
                f"   Timezone: {datetime.now().astimezone().tzname()}\n"
                f"   ISO: {now.isoformat()}"
            )

        if info_type in ("platform", "all"):
            parts.append(
                f"💻 Platform:\n"
                f"   OS: {platform.system()} {platform.release()}\n"
                f"   Version: {platform.version()}\n"
                f"   Machine: {platform.machine()}\n"
                f"   Python: {platform.python_version()}"
            )

        if info_type in ("disk", "all"):
            try:
                usage = shutil.disk_usage(os.path.expanduser("~"))
                total_gb = usage.total / (1024 ** 3)
                used_gb = usage.used / (1024 ** 3)
                free_gb = usage.free / (1024 ** 3)
                pct = (usage.used / usage.total) * 100
                parts.append(
                    f"💾 Disk Usage:\n"
                    f"   Total: {total_gb:.1f} GB\n"
                    f"   Used:  {used_gb:.1f} GB ({pct:.1f}%)\n"
                    f"   Free:  {free_gb:.1f} GB"
                )
            except Exception:
                parts.append("💾 Disk Usage: Unable to determine")

        if info_type in ("cwd", "all"):
            parts.append(f"📂 Working Directory: {os.getcwd()}")

        if not parts:
            return f"Unknown info_type '{info_type}'. Use: time, platform, disk, cwd, or all."

        return "\n\n".join(parts)
