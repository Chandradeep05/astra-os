"""
File hashing for duplicate prevention and watcher change detection.
SHA-256 in 64KB chunks — handles large files without loading into memory.
"""
import hashlib


def sha256_file(path: str, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hash of a file, reading in 64KB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
