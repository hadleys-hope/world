"""Static responses with conditional caching, gzip and path containment."""

from functools import lru_cache
import gzip
import hashlib
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit


@lru_cache(maxsize=256)
def _asset(path: str, modified: int, size: int):
    body = Path(path).read_bytes()
    return (
        body,
        gzip.compress(body, compresslevel=5, mtime=0),
        '"' + hashlib.sha256(body).hexdigest() + '"',
    )


def serve_asset(handler, root: Path, prefix: str):
    """Handle only paths inside root, including URL decoding and symlink resolution."""
    rel = unquote(urlsplit(handler.path).path[len(prefix) :])
    root = Path(root).resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        handler._send(404, "text/plain", b"not found")
        return
    st = path.stat()
    body, compressed, etag = _asset(str(path), st.st_mtime_ns, st.st_size)
    encoding = handler.headers.get("Accept-Encoding", "")
    # Honour q=0 rather than sending gzip to a client which rejects it.
    accepts_gzip = False
    for part in encoding.split(","):
        pieces = [piece.strip() for piece in part.split(";")]
        if pieces[0] != "gzip":
            continue
        try:
            quality = next(
                (float(piece[2:]) for piece in pieces[1:] if piece.startswith("q=")),
                1.0,
            )
        except ValueError:
            quality = 0.0
        accepts_gzip = quality > 0
    variant = etag[:-1] + ('-gzip"' if accepts_gzip else '-identity"')
    match = handler.headers.get("If-None-Match", "")
    unchanged = (
        variant in [p.strip().removeprefix("W/") for p in match.split(",")]
        or match.strip() == "*"
    )
    handler.send_response(304 if unchanged else 200)
    handler.send_header("ETag", variant)
    handler.send_header("Cache-Control", "public, no-cache")
    handler.send_header("Vary", "Accept-Encoding")
    handler.send_header("X-Content-Type-Options", "nosniff")
    if not unchanged:
        mime = (
            {".js": "text/javascript", ".css": "text/css"}.get(path.suffix)
            or mimetypes.guess_type(path.name)[0]
            or "application/octet-stream"
        )
        handler.send_header("Content-Type", mime)
        if accepts_gzip:
            body = compressed
            handler.send_header("Content-Encoding", "gzip")
        handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if not unchanged:
        handler.wfile.write(body)
