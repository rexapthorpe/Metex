"""
HTTP downloader with retry, rate limiting, and size guard.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "MetexImageAcquisition/1.0 (contact@metex.com)",
    "Accept": "image/jpeg,image/png,image/webp,image/*",
})

MAX_BYTES = 15 * 1024 * 1024
TIMEOUT   = 15
MAX_RETRIES = 3


def download_image(url: str, max_bytes: int = MAX_BYTES) -> Tuple[Optional[bytes], str]:
    """
    Download image bytes from url.

    Returns (bytes, checksum) or (None, "") on failure.
    checksum is SHA-256 hex digest.
    """
    delay = 5
    for attempt in range(MAX_RETRIES):
        try:
            with _SESSION.get(url, timeout=TIMEOUT, stream=True) as r:
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", delay))
                    logger.warning("Rate limited on %s, sleeping %ds", url, wait)
                    time.sleep(wait)
                    delay *= 2
                    continue

                r.raise_for_status()

                ct = r.headers.get("Content-Type", "")
                if not any(t in ct for t in ["image/jpeg", "image/png", "image/webp", "image/"]):
                    logger.debug("Skipping non-image content-type %s for %s", ct, url)
                    return None, ""

                chunks = []
                total = 0
                for chunk in r.iter_content(chunk_size=65536):
                    total += len(chunk)
                    if total > max_bytes:
                        logger.warning("Image too large (>%d bytes): %s", max_bytes, url)
                        return None, ""
                    chunks.append(chunk)

                data = b"".join(chunks)
                if not data:
                    return None, ""

                checksum = hashlib.sha256(data).hexdigest()
                return data, checksum

        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(delay)
                delay *= 2
            else:
                logger.warning("Download failed after %d attempts for %s: %s", MAX_RETRIES, url, e)

    return None, ""
