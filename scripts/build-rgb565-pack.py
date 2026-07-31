#!/usr/bin/env python3
"""Build a fixed-grid MapPI3 RGB565 map pack from existing 256x256 PNG tiles.

This intentionally does not download tiles. It converts a local/approved tile cache
into one raw little-endian RGB565 file per zoom plus a MANIFEST.json with offset math.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

try:
    import numpy as np
except Exception:  # pragma: no cover - tiny Pi image may not have numpy
    np = None

TILE_SIZE = 256
BYTES_PER_TILE = TILE_SIZE * TILE_SIZE * 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MapPI3 fixed-grid RGB565 map pack from local PNG tiles")
    parser.add_argument("--source-manifest", required=True, help="PNG tile manifest JSON with levels[] x/y bounds")
    parser.add_argument("--tile-root", required=True, help="Root with {z}/{x}/{y}.png tiles")
    parser.add_argument("--out-dir", required=True, help="Output pack directory")
    parser.add_argument("--id", required=True, help="Pack id")
    parser.add_argument("--name", required=True, help="Pack display name")
    parser.add_argument("--theme", default="topo-night", help="Theme/style id")
    parser.add_argument("--min-zoom", type=int, default=None)
    parser.add_argument("--max-zoom", type=int, default=None)
    parser.add_argument("--fill-missing", choices=["checker", "black", "error"], default="checker")
    parser.add_argument(
        "--fallback-parent-tiles",
        action="store_true",
        help="When an exact z/x/y PNG is missing, synthesize it from the nearest available lower-zoom parent tile instead of using the missing-tile fill.",
    )
    parser.add_argument("--source-label", default="local pre-rendered PNG tile cache")
    parser.add_argument("--attribution", default="© OpenStreetMap contributors")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rgb565_bytes(image: Image.Image) -> bytes:
    img = image.convert("RGB").resize((TILE_SIZE, TILE_SIZE))
    if np is not None:
        arr = np.asarray(img, dtype=np.uint16)
        packed = ((arr[:, :, 0] & 0xF8) << 8) | ((arr[:, :, 1] & 0xFC) << 3) | (arr[:, :, 2] >> 3)
        return packed.astype("<u2", copy=False).tobytes()
    raw = bytearray(BYTES_PER_TILE)
    i = 0
    for r, g, b in img.getdata():
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        raw[i] = value & 0xFF
        raw[i + 1] = (value >> 8) & 0xFF
        i += 2
    return bytes(raw)


def missing_tile_bytes(z: int, x: int, y: int, mode: str) -> bytes:
    if mode == "error":
        raise FileNotFoundError(f"missing tile z{z}/{x}/{y}.png")
    if mode == "black":
        return b"\x00\x00" * (TILE_SIZE * TILE_SIZE)
    # Dim trail-night checkerboard: obvious in verification, not confused with real map.
    img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (8, 18, 13))
    px = img.load()
    for yy in range(TILE_SIZE):
        for xx in range(TILE_SIZE):
            if ((xx // 32) + (yy // 32)) % 2 == 0:
                px[xx, yy] = (20, 55, 35)
            if xx in (0, TILE_SIZE - 1) or yy in (0, TILE_SIZE - 1):
                px[xx, yy] = (120, 210, 120)
    return rgb565_bytes(img)


def parent_tile_image(tile_root: Path, z: int, x: int, y: int) -> tuple[Image.Image, dict[str, int]] | None:
    """Return a 256px tile synthesized from the nearest available lower-zoom parent.

    This is useful for making a complete fixed-grid pack from an approved overview
    cache without doing a new bulk tile download. Detail is capped by the parent
    zoom, but the native renderer still gets deterministic map pixels at every
    requested z/x/y offset.
    """
    for parent_z in range(z - 1, -1, -1):
        shift = z - parent_z
        parent_x = x >> shift
        parent_y = y >> shift
        src = tile_root / str(parent_z) / str(parent_x) / f"{parent_y}.png"
        if not src.exists():
            continue
        scale = 2 ** shift
        child_x = x - (parent_x << shift)
        child_y = y - (parent_y << shift)
        crop_w = TILE_SIZE / scale
        left = int(round(child_x * crop_w))
        top = int(round(child_y * crop_w))
        right = int(round((child_x + 1) * crop_w))
        bottom = int(round((child_y + 1) * crop_w))
        with Image.open(src) as img:
            crop = img.convert("RGB").crop((left, top, right, bottom))
            return crop.resize((TILE_SIZE, TILE_SIZE), Image.Resampling.BICUBIC), {
                "z": parent_z,
                "x": parent_x,
                "y": parent_y,
                "child_z": z,
                "child_x": x,
                "child_y": y,
            }
    return None


def load_levels(manifest: dict[str, Any], min_zoom: int | None, max_zoom: int | None) -> list[dict[str, Any]]:
    levels = list(manifest.get("levels") or [])
    if not levels:
        raise ValueError("source manifest has no levels[]")
    kept = []
    for level in levels:
        z = int(level["z"])
        if min_zoom is not None and z < min_zoom:
            continue
        if max_zoom is not None and z > max_zoom:
            continue
        x_min, x_max = int(level["x_min"]), int(level["x_max"])
        y_min, y_max = int(level["y_min"]), int(level["y_max"])
        width = x_max - x_min + 1
        height = y_max - y_min + 1
        tiles = width * height
        kept.append({**level, "z": z, "x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "width_tiles": width, "height_tiles": height, "tiles": tiles})
    if not kept:
        raise ValueError("zoom filter removed every level")
    return kept


def main() -> int:
    args = parse_args()
    source_manifest_path = Path(args.source_manifest)
    tile_root = Path(args.tile_root)
    out_dir = Path(args.out_dir)
    manifest = json.loads(source_manifest_path.read_text())
    levels = load_levels(manifest, args.min_zoom, args.max_zoom)
    out_dir.mkdir(parents=True, exist_ok=True)

    generated_levels = []
    total_tiles = 0
    total_bytes = 0
    missing_tiles = []
    fallback_parent_tiles = []
    converted_tiles = 0

    for level in levels:
        z = level["z"]
        pack_name = f"z{z}.rgb565pack"
        pack_path = out_dir / pack_name
        with pack_path.open("wb") as out:
            for y in range(level["y_min"], level["y_max"] + 1):
                for x in range(level["x_min"], level["x_max"] + 1):
                    src = tile_root / str(z) / str(x) / f"{y}.png"
                    if src.exists():
                        with Image.open(src) as img:
                            out.write(rgb565_bytes(img))
                        converted_tiles += 1
                    else:
                        fallback = parent_tile_image(tile_root, z, x, y) if args.fallback_parent_tiles else None
                        if fallback is not None:
                            img, meta = fallback
                            out.write(rgb565_bytes(img))
                            fallback_parent_tiles.append(meta)
                        else:
                            out.write(missing_tile_bytes(z, x, y, args.fill_missing))
                            missing_tiles.append({"z": z, "x": x, "y": y})
        size = pack_path.stat().st_size
        expected = level["tiles"] * BYTES_PER_TILE
        if size != expected:
            raise RuntimeError(f"{pack_path} size {size} != expected {expected}")
        checksum = sha256_file(pack_path)
        generated_levels.append({
            "z": z,
            "x_min": level["x_min"],
            "x_max": level["x_max"],
            "y_min": level["y_min"],
            "y_max": level["y_max"],
            "width_tiles": level["width_tiles"],
            "height_tiles": level["height_tiles"],
            "tiles": level["tiles"],
            "file": pack_name,
            "url": f"/map-packs/{args.id}/{pack_name}",
            "size_bytes": size,
            "sha256": checksum,
            "offset_formula": "offset = ((y - y_min) * width_tiles + (x - x_min)) * 131072",
        })
        total_tiles += level["tiles"]
        total_bytes += size

    pack_manifest = {
        "schema": "mappi3.rgb565-map-pack.v1",
        "id": args.id,
        "name": args.name,
        "theme": args.theme,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "offline_safe": True,
        "network_required": False,
        "source": args.source_label,
        "source_manifest": source_manifest_path.name,
        "source_detail_note": "Exact source PNG tiles are used where available. Parent-tile fallback, when enabled, fills higher zoom grid cells by cropping/resampling the nearest approved lower-zoom tile; coverage is complete but detail is capped by the source zoom.",
        "attribution": args.attribution or manifest.get("attribution"),
        "center": manifest.get("center"),
        "radius_miles": manifest.get("radius_miles"),
        "bbox": manifest.get("bbox"),
        "tile_format": {
            "tile_size": TILE_SIZE,
            "pixel_format": "RGB565 little-endian",
            "bytes_per_tile": BYTES_PER_TILE,
            "fixed_grid": True,
        },
        "zoom_min": min(level["z"] for level in generated_levels),
        "zoom_max": max(level["z"] for level in generated_levels),
        "levels": generated_levels,
        "tile_count": total_tiles,
        "converted_tile_count": converted_tiles,
        "fallback_parent_tile_count": len(fallback_parent_tiles),
        "fallback_parent_tiles_sample": fallback_parent_tiles[:40],
        "missing_tile_count": len(missing_tiles),
        "missing_tiles_sample": missing_tiles[:40],
        "size_bytes": total_bytes,
        "size_mib": round(total_bytes / 1024 / 1024, 3),
        "safety": "MapPI3 assists navigation; carry real map/compass/emergency tools.",
    }
    manifest_path = out_dir / "MANIFEST.json"
    manifest_path.write_text(json.dumps(pack_manifest, indent=2) + "\n")
    pack_manifest["manifest_sha256"] = sha256_file(manifest_path)
    manifest_path.write_text(json.dumps(pack_manifest, indent=2) + "\n")

    print(json.dumps({
        "ok": True,
        "out_dir": str(out_dir),
        "id": args.id,
        "levels": len(generated_levels),
        "tile_count": total_tiles,
        "converted_tile_count": converted_tiles,
        "fallback_parent_tile_count": len(fallback_parent_tiles),
        "fallback_parent_tiles_sample": fallback_parent_tiles[:40],
        "missing_tile_count": len(missing_tiles),
        "size_bytes": total_bytes,
        "size_mib": round(total_bytes / 1024 / 1024, 3),
        "manifest": str(manifest_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
