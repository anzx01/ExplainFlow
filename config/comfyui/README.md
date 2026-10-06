# ComfyUI scene image workflow

Export a ComfyUI API-format workflow JSON to `scene-image-api.json` in this directory.
The workflow must accept a positive prompt, a negative prompt, seed, width, height,
and produce a PNG through a `SaveImage` node. The API adapter uses DeepSeek for the
prompt text and ComfyUI for image generation.

Do not use the FreeVideo video workflow here: it produces video frames and cannot
provide stable raster artwork for stroke tracing.
