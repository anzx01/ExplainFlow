"""Prepare Diffusers CLIP weights for stable-diffusion.cpp Flux loading."""
from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path


SOURCE = Path(r"E:\MYLLM\flux1-schnell-fp8\extracted\clip\model.safetensors")
OUTPUT = SOURCE.with_name("clip-text-model.safetensors")


def main() -> None:
    if OUTPUT.is_file() and OUTPUT.stat().st_size > 10_000_000:
        print(f"ready: {OUTPUT}")
        return
    with SOURCE.open("rb") as source:
        header_length = struct.unpack("<Q", source.read(8))[0]
        header = json.loads(source.read(header_length))
        renamed = {"__metadata__": header.get("__metadata__", {})}
        renamed.update(
            {f"text_model.{name}": value for name, value in header.items() if name != "__metadata__"}
        )
        encoded = json.dumps(renamed, separators=(",", ":")).encode("utf-8")
        encoded += b" " * ((8 - len(encoded) % 8) % 8)
        with OUTPUT.open("wb") as target:
            target.write(struct.pack("<Q", len(encoded)))
            target.write(encoded)
            shutil.copyfileobj(source, target, length=16 * 1024 * 1024)
    print(f"created: {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
