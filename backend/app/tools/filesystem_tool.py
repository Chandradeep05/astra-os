"""
ASTRA OS — Filesystem Tool
============================
Safe local file operations for the agent:
  - Read files (safe)
  - List directory contents (safe)
  - Write files to a sandboxed output folder (risky — requires approval)

Writes are restricted to a dedicated 'agent_output' directory to prevent
the agent from modifying system files or the project codebase.
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Sandboxed output directory — the ONLY place the agent can write files
AGENT_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "agent_output")


def _ensure_output_dir():
    """Create the agent output directory if it doesn't exist."""
    os.makedirs(AGENT_OUTPUT_DIR, exist_ok=True)


class FileReadTool:
    """Read the contents of a local file. Safe operation."""

    def __init__(self):
        self.name = "read_file"
        self.description = (
            "Read the contents of a file on the local filesystem. "
            "Provide the full file path. Returns the file content as text. "
            "Useful for reading config files, logs, documents, or code files."
        )

    async def execute(self, file_path: str) -> str:
        """Read a file and return its contents."""
        try:
            path = Path(file_path).resolve()

            if not path.exists():
                return f"Error: File not found: {file_path}"

            if not path.is_file():
                return f"Error: Not a file: {file_path}"

            # Limit file size to 50KB to avoid blowing up context
            size = path.stat().st_size
            if size > 50_000:
                return f"Error: File too large ({size:,} bytes). Max 50KB for safety."

            content = path.read_text(encoding="utf-8", errors="replace")
            return f"Contents of {path.name} ({size:,} bytes):\n\n{content}"

        except PermissionError:
            return f"Error: Permission denied reading {file_path}"
        except Exception as e:
            logger.error(f"File read error: {e}")
            return f"Error reading file: {str(e)}"


class ListDirectoryTool:
    """List the contents of a directory. Safe operation."""

    def __init__(self):
        self.name = "list_directory"
        self.description = (
            "List files and subdirectories in a given directory path. "
            "Returns file names, sizes, and types. "
            "Useful for exploring the filesystem structure."
        )

    async def execute(self, directory_path: str) -> str:
        """List directory contents."""
        try:
            path = Path(directory_path).resolve()

            if not path.exists():
                return f"Error: Directory not found: {directory_path}"

            if not path.is_dir():
                return f"Error: Not a directory: {directory_path}"

            entries = []
            for item in sorted(path.iterdir()):
                try:
                    if item.is_file():
                        size = item.stat().st_size
                        entries.append(f"  📄 {item.name} ({size:,} bytes)")
                    elif item.is_dir():
                        child_count = sum(1 for _ in item.iterdir()) if os.access(str(item), os.R_OK) else "?"
                        entries.append(f"  📁 {item.name}/ ({child_count} items)")
                except PermissionError:
                    entries.append(f"  🔒 {item.name} (access denied)")

            if not entries:
                return f"Directory '{path}' is empty."

            # Cap at 50 entries to avoid huge outputs
            if len(entries) > 50:
                entries = entries[:50]
                entries.append(f"  ... and {len(list(path.iterdir())) - 50} more items")

            return f"Contents of {path}:\n\n" + "\n".join(entries)

        except PermissionError:
            return f"Error: Permission denied accessing {directory_path}"
        except Exception as e:
            logger.error(f"Directory listing error: {e}")
            return f"Error listing directory: {str(e)}"


class FileWriteTool:
    """
    Write content to a file in the sandboxed agent_output directory.
    RISKY operation — requires human approval.
    """

    def __init__(self):
        self.name = "write_file"
        self.description = (
            "Write text content to a file. For safety, files are written to the "
            "'agent_output/' directory only. Provide a filename (not a full path) "
            "and the content to write. Useful for saving reports, notes, or generated code."
        )

    async def execute(self, filename: str, content: str) -> str:
        """Write content to a file in the sandboxed output directory."""
        try:
            _ensure_output_dir()

            # Sanitize filename — strip path components to prevent directory traversal
            safe_name = Path(filename).name
            if not safe_name:
                return "Error: Invalid filename."

            # Block obviously dangerous extensions
            dangerous_ext = {".exe", ".bat", ".cmd", ".ps1", ".sh", ".vbs", ".msi"}
            if Path(safe_name).suffix.lower() in dangerous_ext:
                return f"Error: Writing {Path(safe_name).suffix} files is blocked for security."

            output_path = Path(AGENT_OUTPUT_DIR) / safe_name

            output_path.write_text(content, encoding="utf-8")
            size = output_path.stat().st_size

            logger.info(f"Agent wrote file: {output_path} ({size:,} bytes)")
            return f"Successfully wrote {safe_name} ({size:,} bytes) to agent_output/"

        except Exception as e:
            logger.error(f"File write error: {e}")
            return f"Error writing file: {str(e)}"
