#!/usr/bin/env python3
"""
MapPI3 Offline RAG / Reference Paragraph Search for PiSugar Whisplay
====================================================================

Architecture: "Embedding + Reference Database Search"

This script does NOT generate advice. It finds the single closest matching
paragraph from local reference documents and displays that paragraph directly.
That makes it suitable for survival manuals, app help, first-aid red flags,
trail notes, and other offline references where exact source text matters.

Default dependencies: Python standard library only.
Optional dependencies:
  - Ollama running locally or on a LAN host with an embedding model such as all-minilm
  - PiSugar Whisplay Python library OR ST7789/Pillow stack for LCD output
  - whisper.cpp / external STT command later, if voice input is enabled

Quick install checklist, safest first:

  # On the machine that will provide embeddings, e.g. NukeBox/Oracle/Pi if capable:
  # Ollama model name may vary by registry. If `all-minilm` is unavailable, use
  # another small embedding model and pass --model NAME.
  ollama pull all-minilm

  # Optional display stack on the Pi, depending on current Whisplay install:
  # Use official PiSugar Whisplay install first; this script auto-detects it.
  # If using raw ST7789 fallback, install the distro/library package used by
  # Whisplay on this image plus Pillow.

  # Recommended run on MapPI3 Pi, using NukeBox/Oracle Ollama if Pi is too small:
  python3 mappi3_offline_rag_whisplay.py \
    --docs /opt/mappi3/app/docs /var/lib/mappi3/manuals /var/lib/mappi3/field-ai \
    --ollama http://100.82.165.23:11434 \
    --model all-minilm

Safety note: This is an offline reference lookup tool. It does not replace a map,
compass, emergency beacon, first-aid training, poison control, or professional care.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import textwrap
import time
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib import request, error

APP_NAME = "MapPI3 Offline RAG"
DEFAULT_DB = "/var/lib/mappi3/rag/reference_vectors.sqlite3"
DEFAULT_MODEL = "all-minilm"
DEFAULT_OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
SUPPORTED_EXTS = {".md", ".markdown", ".txt", ".rst"}
MAX_PARAGRAPH_CHARS = 1400
MIN_PARAGRAPH_CHARS = 30

# ---------------------------------------------------------------------------
# Text loading / chunking
# ---------------------------------------------------------------------------

def iter_text_files(paths: Sequence[str]) -> Iterable[Path]:
    """Yield readable local text files from files or directories."""
    seen = set()
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.exists():
            continue
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                yield rp
        elif p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTS:
                    rp = child.resolve()
                    if rp not in seen:
                        seen.add(rp)
                        yield rp


def clean_text(s: str) -> str:
    """Normalize markdown-ish text without destroying source wording."""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # Drop huge code fences from embedding chunks; manuals can keep prose around them.
    s = re.sub(r"```.*?```", "\n", s, flags=re.S)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def paragraph_chunks(text: str, source: str) -> Iterable[Tuple[str, str]]:
    """Split documents into paragraph-sized chunks and preserve source labels.

    Markdown manuals often use headings with only short paragraphs underneath.
    Treat headings as section boundaries so "Mushroom safety" and "Fire safety"
    become separate searchable references instead of one giant document blob.
    """
    text = clean_text(text)
    # Put a blank line before each Markdown heading, then split on blank lines.
    # This stays conservative: source wording is preserved inside each section.
    text = re.sub(r"\n(#{1,6}\s+)", r"\n\n\1", text)
    rough = re.split(r"\n\s*\n", text)
    buf: List[str] = []
    for part in rough:
        part = re.sub(r"[ \t]+", " ", part).strip()
        if not part:
            continue
        # Keep Markdown sections independent even if short. This improves exact
        # paragraph/manual lookup and avoids mixing unrelated safety topics.
        if part.startswith("#") and buf:
            chunk = "\n\n".join(buf).strip()
            if len(chunk) >= MIN_PARAGRAPH_CHARS:
                yield source, chunk
            buf = []
        if len(part) > MAX_PARAGRAPH_CHARS:
            # Split very long manual sections by sentence-ish boundaries.
            sentences = re.split(r"(?<=[.!?])\s+", part)
            for sent in sentences:
                if len(" ".join(buf + [sent])) > MAX_PARAGRAPH_CHARS and buf:
                    chunk = " ".join(buf).strip()
                    if len(chunk) >= MIN_PARAGRAPH_CHARS:
                        yield source, chunk
                    buf = []
                buf.append(sent)
            continue
        if len("\n\n".join(buf + [part])) > MAX_PARAGRAPH_CHARS and buf:
            chunk = "\n\n".join(buf).strip()
            if len(chunk) >= MIN_PARAGRAPH_CHARS:
                yield source, chunk
            buf = []
        buf.append(part)
    if buf:
        chunk = "\n\n".join(buf).strip()
        if len(chunk) >= MIN_PARAGRAPH_CHARS:
            yield source, chunk

# ---------------------------------------------------------------------------
# Ollama embeddings
# ---------------------------------------------------------------------------

def ollama_embed(text: str, host: str, model: str, timeout: float = 30.0) -> List[float]:
    """Return one embedding vector from Ollama. Supports /api/embed and fallback /api/embeddings."""
    host = host.rstrip("/")
    payload = json.dumps({"model": model, "input": text}).encode("utf-8")
    req = request.Request(host + "/api/embed", data=payload, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        emb = data.get("embeddings")
        if isinstance(emb, list) and emb and isinstance(emb[0], list):
            return [float(x) for x in emb[0]]
    except Exception:
        pass

    # Older Ollama endpoint shape.
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    req = request.Request(host + "/api/embeddings", data=payload, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    emb = data.get("embedding")
    if not isinstance(emb, list):
        raise RuntimeError(f"Ollama did not return an embedding for model={model!r}")
    return [float(x) for x in emb]

# ---------------------------------------------------------------------------
# Tiny SQLite vector store
# ---------------------------------------------------------------------------

def vector_to_blob(vec: Sequence[float]) -> str:
    """Store vector as compact JSON text. Good enough for small offline manuals."""
    return json.dumps([round(float(x), 7) for x in vec], separators=(",", ":"))


def blob_to_vector(blob: str) -> List[float]:
    return [float(x) for x in json.loads(blob)]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else -1.0


def db_connect(path: str) -> sqlite3.Connection:
    db_path = Path(path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chunks ("
        "id TEXT PRIMARY KEY, source TEXT, text TEXT, embedding TEXT, model TEXT, updated REAL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source)")
    return conn


def chunk_id(source: str, text: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"\0")
    h.update(source.encode())
    h.update(b"\0")
    h.update(text.encode())
    return h.hexdigest()[:32]


def tokenize(text: str) -> List[str]:
    """Tiny tokenizer for no-internet/no-Ollama fallback search."""
    stop = {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
        "how", "i", "if", "in", "is", "it", "of", "on", "or", "should", "the",
        "to", "what", "when", "where", "with", "you", "your",
    }
    return [t for t in re.findall(r"[a-z0-9][a-z0-9'-]{2,}", text.lower()) if t not in stop]


def keyword_score(query: str, text: str) -> float:
    """Small BM25-ish score using only the Python stdlib.

    This is the field fallback: lower quality than MiniLM embeddings, but it keeps
    MapPI3 useful when NukeBox/Ollama/internet are unavailable.
    """
    q = tokenize(query)
    if not q:
        return 0.0
    words = tokenize(text)
    if not words:
        return 0.0
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    unique_hits = sum(1 for t in set(q) if t in counts)
    freq_hits = sum(min(counts.get(t, 0), 3) for t in q)
    phrase_bonus = 1.5 if query.lower().strip() in text.lower() else 0.0
    length_penalty = math.log(20 + len(words))
    return (unique_hits * 2.0 + freq_hits + phrase_bonus) / length_penalty


def build_index(conn: sqlite3.Connection, docs: Sequence[str], host: str, model: str, rebuild: bool = False) -> int:
    if rebuild:
        conn.execute("DELETE FROM chunks WHERE model=?", (model,))
        conn.commit()
    added = 0
    embedding_disabled = False
    warned_embedding = False
    for file_path in iter_text_files(docs):
        try:
            raw = file_path.read_text(errors="ignore")
        except Exception as exc:
            print(f"WARN: could not read {file_path}: {exc}", file=sys.stderr)
            continue
        source = str(file_path)
        for src, text in paragraph_chunks(raw, source):
            cid = chunk_id(src, text, model)
            if conn.execute("SELECT 1 FROM chunks WHERE id=?", (cid,)).fetchone():
                continue
            emb_blob = ""
            if not embedding_disabled:
                try:
                    emb_blob = vector_to_blob(ollama_embed(text[:MAX_PARAGRAPH_CHARS], host, model))
                except Exception as exc:
                    embedding_disabled = True
                    if not warned_embedding:
                        print(
                            "WARN: embedding service unavailable; indexing keyword-only "
                            f"fallback chunks. Reason: {exc}",
                            file=sys.stderr,
                        )
                        warned_embedding = True
            conn.execute(
                "INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?)",
                (cid, src, text, emb_blob, model, time.time()),
            )
            added += 1
            if added % 10 == 0:
                conn.commit()
                print(f"Indexed {added} new paragraphs...", file=sys.stderr)
    conn.commit()
    return added


def search_top1(conn: sqlite3.Connection, query: str, host: str, model: str) -> Tuple[float, str, str]:
    best = (-1.0, "", "No reference paragraphs indexed yet.")
    rows = list(conn.execute("SELECT source, text, embedding FROM chunks WHERE model=?", (model,)))
    try:
        qvec = ollama_embed(query, host, model)
    except Exception:
        qvec = []
    for source, text, emb_blob in rows:
        if qvec and emb_blob:
            score = cosine(qvec, blob_to_vector(emb_blob))
        else:
            score = keyword_score(query, text)
        if score > best[0]:
            best = (score, source, text)
    return best

# ---------------------------------------------------------------------------
# Whisplay / display fallback
# ---------------------------------------------------------------------------

class Display:
    """LCD abstraction. Uses Whisplay if available, else console."""

    def __init__(self, width: int = 240, height: int = 280):
        self.width = width
        self.height = height
        self.mode = "console"
        self._whisplay = None
        self._image_libs = None
        self._try_whisplay()

    def _try_whisplay(self) -> None:
        # Whisplay upstream APIs differ between installs. Try common import names,
        # but never fail the RAG loop if display libraries are absent.
        for mod_name in ("whisplay", "pisugar_whisplay"):
            try:
                mod = __import__(mod_name)
                self._whisplay = mod
                self.mode = mod_name
                return
            except Exception:
                continue
        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore
            self._image_libs = (Image, ImageDraw, ImageFont)
        except Exception:
            self._image_libs = None

    def show(self, title: str, body: str) -> None:
        wrapped_title = titlewrap(title, 28)
        wrapped_body = "\n".join(textwrap.wrap(body, width=30))
        text = (wrapped_title + "\n" + "-" * 28 + "\n" + wrapped_body)[:1200]

        # Console is always printed for logs/debugging.
        print("\n" + "=" * 60)
        print(text)
        print("=" * 60 + "\n")

        if self._whisplay is not None:
            # Prefer simple helper functions if the installed library exposes them.
            for attr in ("display_text", "show_text", "draw_text", "text"):
                fn = getattr(self._whisplay, attr, None)
                if callable(fn):
                    try:
                        fn(text)
                        return
                    except Exception:
                        pass

        # Raw ST7789 fallback intentionally omitted unless the exact Whisplay image
        # driver API is present. Console fallback keeps this safe on every install.


def titlewrap(s: str, width: int) -> str:
    return "\n".join(textwrap.wrap(s, width=width)) or APP_NAME

# ---------------------------------------------------------------------------
# Input loop: console now, button/audio hooks later
# ---------------------------------------------------------------------------

def read_query_console() -> Optional[str]:
    try:
        q = input("Ask MapPI3 reference search> ").strip()
    except EOFError:
        return None
    if q.lower() in {"q", "quit", "exit"}:
        return None
    return q


def read_query_voice_placeholder() -> Optional[str]:
    """Future hook: call whisper.cpp or another ultra-light STT command."""
    cmd = os.environ.get("MAPPI3_STT_COMMAND", "").strip()
    if not cmd:
        return read_query_console()
    try:
        out = subprocess.check_output(cmd, shell=True, text=True, timeout=20)
        return out.strip() or None
    except Exception as exc:
        print(f"STT failed, falling back to console: {exc}", file=sys.stderr)
        return read_query_console()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--docs", nargs="+", default=["/opt/mappi3/app/docs", "/var/lib/mappi3/manuals", "/var/lib/mappi3/field-ai"], help="Reference files/directories to index")
    ap.add_argument("--db", default=DEFAULT_DB, help="SQLite vector database path")
    ap.add_argument("--ollama", default=DEFAULT_OLLAMA, help="Ollama base URL, e.g. http://127.0.0.1:11434 or http://nukebox:11434")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Ollama embedding model name")
    ap.add_argument("--rebuild", action="store_true", help="Rebuild this model's index from scratch")
    ap.add_argument("--once", help="Run one query and exit")
    ap.add_argument("--voice", action="store_true", help="Use MAPPI3_STT_COMMAND placeholder for voice-to-text, else console")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    display = Display()
    display.show(APP_NAME, "Booting offline reference search. Indexing local paragraphs...")

    conn = db_connect(args.db)
    try:
        added = build_index(conn, args.docs, args.ollama, args.model, args.rebuild)
    except error.URLError as exc:
        display.show("Ollama unavailable", f"Could not reach {args.ollama}. Start Ollama and pull {args.model}, or point --ollama to NukeBox/Oracle. Error: {exc}")
        return 2
    except Exception as exc:
        display.show("Index failed", str(exc))
        return 3

    total = conn.execute("SELECT COUNT(*) FROM chunks WHERE model=?", (args.model,)).fetchone()[0]
    display.show(APP_NAME, f"Ready. Paragraphs indexed: {total}. New this run: {added}. Ask a question or type quit.")

    if args.once:
        q = args.once.strip()
        score, source, text = search_top1(conn, q, args.ollama, args.model)
        display.show(f"Match {score:.3f} | {Path(source).name}", text)
        return 0

    while True:
        q = read_query_voice_placeholder() if args.voice else read_query_console()
        if not q:
            display.show(APP_NAME, "Reference search stopped.")
            return 0
        try:
            score, source, text = search_top1(conn, q, args.ollama, args.model)
            display.show(f"Match {score:.3f} | {Path(source).name}", text)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            display.show("Search error", str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
