"""Recover the failed local-FLUX job, keeping every attempt for inspection."""
import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
from src.imagegen import service

ART = ROOT / "image/braised-pork-recovery"
ART.mkdir(parents=True, exist_ok=True)
request = json.loads((ROOT / "apps/render/public/generated/7cbfef27-9aad-4f88-b076-84d7667f2858/image-generation-request.json").read_text(encoding="utf-8"))
original_call = service._call_local_flux
SUBJECTS = [
    "A close-up slab of raw Chinese pork belly with skin and pink cream alternating fat layers beside a finished glossy red-brown braised pork cube. Behind them a small magnified inset of loose protein fibers and water droplets, no diagram labels.",
    "Two large food preparation vignettes side by side: a knife cutting skin-on pink pork belly into large cubes on a wooden chopping board; a wide open pot with clear water, raw pork cubes, ginger and a skimmer lifting gray foam.",
    "Three large matching small black pans side by side. The first contains white rock sugar melting; the middle contains golden amber bubbling syrup; the last contains dark red-brown caramel bubbling syrup. No stage labels or numbers.",
    "One large wide black braising pot with red-brown sauce, large skin-on pork belly cubes and gentle steam over a tiny orange flame. Beside it ginger slices, star anise, cinnamon and an unbranded plain dark sauce bottle.",
    "Two large wide black woks side by side: the first holds pork belly cubes in thin pale broth; the second holds glossy deep red-brown pork cubes coated in thick reduced sauce, with golden oil highlights and steam. Both pans fully visible.",
    "A beautiful close-up shallow ceramic plate piled with glossy red-brown Chinese braised pork belly cubes, distinct translucent fat and lean layers, thick rich sauce, tiny green scallion garnish and gentle rising steam. Only the finished dish, no process diagram.",
]


async def main():
    async with httpx.AsyncClient() as client:
        for item in sorted(request["scenes"], key=lambda s: (s["scene_id"] not in {"scene_0", "scene_5"}, s["scene_id"])):
            sid = item["scene_id"]
            selected = ART / f"{sid}-clean.png"
            if selected.exists():
                assert service.inspect_generated_image(selected.read_bytes())["ok"]
                print(f"Reusing checked local artwork: {sid}", flush=True)
                continue

            async def capture(prompt, *, quality="final", attempt=0):
                data = await original_call(prompt, quality=quality, attempt=attempt)
                (ART / f"{sid}-clean-attempt-{attempt + 1}.png").write_bytes(data)
                return data

            service._call_local_flux = capture
            print(f"Generating {sid} on local FLUX", flush=True)
            item = {**item, "image_description": SUBJECTS[int(sid.split("_")[1])] + " Rich colored-pencil and gouache food illustration, opaque natural colors, detailed appetizing textures, isolated on pure white background with broad empty margins. No lettering, no typography, no labels, no numbers, no arrows, no signatures."}
            image, diagnostics = await service.generate_scene_image_result(service.SceneImageRequest(**item), client)
            diagnostics["prompt"] = service._build_prompt(service.SceneImageRequest(**item))
            (ART / f"{sid}-clean.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
            if not image:
                raise RuntimeError(f"{sid} failed quality after retries: {diagnostics}")
            selected.write_bytes(base64.b64decode(image))
            print(f"Passed {sid} attempt {diagnostics['selectedAttempt']}", flush=True)
    print("All six local paintings passed quality checks", flush=True)


asyncio.run(main())
