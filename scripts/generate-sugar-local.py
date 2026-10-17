"""Generate the sugar lesson artwork only with the installed local FLUX model."""
import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))
from src.core.config import settings
from src.imagegen.service import _call_local_flux
from src.imagegen.quality import inspect_generated_image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "image" / "sugar-local-art-v3"
STYLE = (
    "Richly shaded colored-pencil and opaque gouache science-book artwork, bright filled colors and visible pencil texture. "
    "Exactly four separate vignettes in a precise two-by-two grid, broad pure-white gutters and margins, no panel borders. "
    "No lettering, no numbers, no arrows, no icons, no outline-only art. "
)
PROMPTS = [
    "TOP LEFT: porcelain sugar bowl and wooden spoon. TOP RIGHT: amber soda glass with ice and sugar cubes. "
    "BOTTOM LEFT: pink cupcake, honey jar and small orange juice glass. BOTTOM RIGHT: red apple, sliced apple and whole orange.",
    "TOP LEFT: white human molar covered with sugar crystals and tiny blue oral bacteria. "
    "TOP RIGHT: human molar with a small brown enamel cavity and orange acid droplets. "
    "BOTTOM LEFT: cookies and colorful candy beside a small clock with blank dial. "
    "BOTTOM RIGHT: blue toothbrush with white toothpaste brushing a clean white molar.",
    "TOP LEFT: tall amber soda glass with ice and sugar cubes. "
    "TOP RIGHT: anatomical human stomach cutaway containing only a little blue liquid, non-graphic. "
    "BOTTOM LEFT: full-body adult in yellow shirt standing on a bathroom scale. "
    "BOTTOM RIGHT: walking adult in teal sportswear beside a balanced meal with vegetables and rice.",
    "TOP LEFT: anatomical reddish-brown liver with a few golden fat droplets. "
    "TOP RIGHT: sweet soda cup beside a blood droplet and medical glucose meter with blank display. "
    "BOTTOM LEFT: one sugar cube on a saucer beside a reassuring medical shield. "
    "BOTTOM RIGHT: colorful balanced vegetable meal, apple and walking shoes.",
    "TOP LEFT: amber soda bottle with a large blank paper label. "
    "TOP RIGHT: amber soda bottle beside a large pile of white sugar cubes. "
    "BOTTOM LEFT: wooden bowl full of sugar beside a balanced food plate. "
    "BOTTOM RIGHT: two small wooden bowls with clearly different amounts of sugar, one full and one half full.",
    "TOP LEFT: clear glass of drinking water and a cup of unsweetened tea. "
    "TOP RIGHT: amber soda bottle with blank label and a large magnifying glass. "
    "BOTTOM LEFT: fresh whole strawberries and a red apple with green leaves. "
    "BOTTOM RIGHT: three teacups with progressively less sugar beside each cup.",
]

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=int, choices=range(len(PROMPTS)))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    settings.local_imagegen_flux_width = 1024
    settings.local_imagegen_flux_height = 768
    manifest_path = OUT / "selected.json"
    selected = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    indexes = [args.scene] if args.scene is not None else range(len(PROMPTS))
    for index in indexes:
        prompt = STYLE + PROMPTS[index]
        key = hashlib.sha256((prompt + settings.local_imagegen_model).encode()).hexdigest()[:12]
        image_path = OUT / f"scene-{index}-{key}.png"
        if image_path.is_file():
            print(f"Cached local artwork: {image_path.name}", flush=True)
            selected[str(index)] = image_path.name
            manifest_path.write_text(json.dumps(selected, indent=2), encoding="utf-8")
            continue
        print(f"Generating scene {index + 1}/6 with local FLUX: {Path(settings.local_imagegen_model).name}", flush=True)
        started = time.monotonic()
        image = await _call_local_flux(prompt, quality="final")
        OUT.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(image)
        quality = inspect_generated_image(image)
        metadata = {"provider":"local", "model":settings.local_imagegen_model, "runtime":settings.local_imagegen_runtime,
                    "width":1024, "height":768, "steps":settings.local_imagegen_steps,
                    "prompt":prompt, "sha256":hashlib.sha256(image).hexdigest(),
                    "seconds":round(time.monotonic()-started, 2), "quality":quality}
        image_path.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        selected[str(index)] = image_path.name
        manifest_path.write_text(json.dumps(selected, indent=2), encoding="utf-8")
        print(f"Saved {image_path.name}: {metadata['seconds']}s; quality={quality['ok']} errors={quality['errors']}", flush=True)
    repairs = {
        "tooth-enamel-replacement.png": (
            "Friendly colored-pencil and gouache dental education artwork on clean white paper. "
            "One isolated solid human molar with natural ivory enamel and two roots. "
            "A tiny shallow tan-brown spot on its chewing surface illustrates early enamel damage. "
            "Opaque pastel shading, fine pencil texture, three dimensional form. "
            "No gums, no open mouth, no blood, no wounds, no black hole, no dramatic decay, no lettering."
        ),
        "sugar-cube-replacement.png": (
            "One small white sugar cube on an empty pale-blue porcelain saucer, isolated on pure white paper. "
            "Rich colored-pencil and opaque gouache painting, visible crystalline sugar texture, gentle soft blue shadows, "
            "realistic small proportions. No bread, no toast, no cake, no cup, no lettering."
        ),
    }
    for name, prompt in repairs.items() if args.scene is None else []:
        repair = OUT / name
        if repair.is_file():
            continue
        settings.local_imagegen_flux_width = 640
        settings.local_imagegen_flux_height = 512
        print(f"Generating inspected replacement {name} with local FLUX", flush=True)
        started = time.monotonic()
        image = await _call_local_flux(prompt, quality="final")
        repair.write_bytes(image)
        repair.with_suffix(".json").write_text(json.dumps({"provider":"local","model":settings.local_imagegen_model,
            "prompt":prompt,"sha256":hashlib.sha256(image).hexdigest(),"seconds":round(time.monotonic()-started,2),
            "quality":inspect_generated_image(image)},ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"Saved {repair.name}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
