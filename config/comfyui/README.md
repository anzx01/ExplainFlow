# ComfyUI scene image workflow

`scene-image-api.json` is an API-format workflow template. ExplainFlow replaces
the `__EXPLAINFLOW_*__` tokens for each scene before submitting it to ComfyUI.
The workflow must accept a positive prompt, a negative prompt, seed, width, height,
and produce a PNG through a `SaveImage` node.

The local checkpoint is currently `E:/MYLLM/meinapastel-v5/meinaPastelV5_bakedVAE.safetensors`.
Optional SD 1.5 LoRAs can be enabled through `COMFYUI_LORA` and
`COMFYUI_LORA_STRENGTH`; put compatible files in `E:/MYLLM/loras` or
`D:/ck/ComfyUI/models/loras`. Do not load Flux LoRAs on this SD 1.5 checkpoint.
The only LoRAs found on this machine so far are Flux realism LoRAs and are
incompatible with the current checkpoint.

Do not use the FreeVideo video workflow here: it produces video frames and cannot
provide stable raster artwork for stroke tracing.
