from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Local development uses the on-machine generator; production overrides
    # IMAGEGEN_PROVIDER through its environment template.
    # CORS
    cors_allowed_origins: str = Field(
        default="http://localhost:3010,http://127.0.0.1:3010",
        env="CORS_ALLOWED_ORIGINS",
    )

    # LLM
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.deepseek.com/v1", env="OPENAI_BASE_URL")
    llm_model: str = Field(default="deepseek-chat", env="LLM_MODEL")
    coder_model: str = Field(default="deepseek-coder", env="CODER_MODEL")
    remotion_codegen_mode: str = Field(default="compiler", env="REMOTION_CODEGEN_MODE")
    remotion_llm_repair: bool = Field(default=False, env="REMOTION_LLM_REPAIR")
    llm_preflight_timeout_s: float = Field(default=8.0, env="LLM_PREFLIGHT_TIMEOUT_S")
    llm_preflight_ttl_s: float = Field(default=60.0, env="LLM_PREFLIGHT_TTL_S")
    llm_max_retries: int = Field(default=3, env="LLM_MAX_RETRIES")
    llm_retry_base_delay_s: float = Field(default=1.0, env="LLM_RETRY_BASE_DELAY_S")
    llm_json_max_tokens: int = Field(default=8192, env="LLM_JSON_MAX_TOKENS")
    llm_json_parse_retries: int = Field(default=2, env="LLM_JSON_PARSE_RETRIES")

    # Image generation. Local Flux is the default; Ark remains opt-in.
    imagegen_provider: str = Field(default="comfyui", env="IMAGEGEN_PROVIDER")
    comfyui_base_url: str = Field(default="http://127.0.0.1:8188", env="COMFYUI_BASE_URL")
    comfyui_workflow: str = Field(default=r"", env="COMFYUI_WORKFLOW")
    comfyui_timeout_s: float = Field(default=600, env="COMFYUI_TIMEOUT_S")
    comfyui_checkpoint: str = Field(default="meinaPastelV5_bakedVAE.safetensors", env="COMFYUI_CHECKPOINT")
    comfyui_lora: str = Field(default="", env="COMFYUI_LORA")
    comfyui_lora_strength: float = Field(default=0.8, env="COMFYUI_LORA_STRENGTH")
    comfyui_lora_trigger: str = Field(default="doodle, messy, stickfigure, crayola, crayons, colored chalk, scribble", env="COMFYUI_LORA_TRIGGER")
    comfyui_client_id: str = Field(default="explainflow", env="COMFYUI_CLIENT_ID")
    comfyui_checkpoint: str = Field(default="meinaPastelV5_bakedVAE.safetensors", env="COMFYUI_CHECKPOINT")
    comfyui_client_id: str = Field(default="explainflow", env="COMFYUI_CLIENT_ID")
    local_imagegen_runtime: str = Field(default=r"D:\ck\04-第三方库与二进制依赖\stable-diffusion-cpp-bin\vulkan\sd-cli.exe", env="LOCAL_IMAGEGEN_RUNTIME")
    local_imagegen_model: str = Field(default=r"E:\MYLLM\flux1-schnell-fp8\gguf\flux1-schnell-Q5_K_S.gguf", env="LOCAL_IMAGEGEN_MODEL")
    local_imagegen_vae: str = Field(default=r"E:\MYLLM\flux1-schnell-fp8\extracted\vae\diffusion_pytorch_model.safetensors", env="LOCAL_IMAGEGEN_VAE")
    local_imagegen_clip_l: str = Field(default=r"E:\MYLLM\flux1-schnell-fp8\extracted\clip\clip-text-model.safetensors", env="LOCAL_IMAGEGEN_CLIP_L")
    local_imagegen_t5xxl: str = Field(default=r"E:\MYLLM\flux1-schnell-fp8\extracted\t5\t5xxl-relative-q8_0.gguf", env="LOCAL_IMAGEGEN_T5XXL")
    local_imagegen_backend: str = Field(default="diffusion=Vulkan0,te=cpu,vae=cpu", env="LOCAL_IMAGEGEN_BACKEND")
    local_imagegen_offload_to_cpu: bool = Field(default=True, env="LOCAL_IMAGEGEN_OFFLOAD_TO_CPU")
    local_imagegen_diffusion_flash_attention: bool = Field(default=True, env="LOCAL_IMAGEGEN_DIFFUSION_FLASH_ATTENTION")
    local_imagegen_vae_tiling: bool = Field(default=True, env="LOCAL_IMAGEGEN_VAE_TILING")
    local_imagegen_vae_tile_size: str = Field(default="128x128", env="LOCAL_IMAGEGEN_VAE_TILE_SIZE")
    local_imagegen_width: int = Field(default=1024, env="LOCAL_IMAGEGEN_WIDTH")
    local_imagegen_height: int = Field(default=1024, env="LOCAL_IMAGEGEN_HEIGHT")
    local_imagegen_preview_width: int = Field(default=512, env="LOCAL_IMAGEGEN_PREVIEW_WIDTH")
    local_imagegen_preview_height: int = Field(default=512, env="LOCAL_IMAGEGEN_PREVIEW_HEIGHT")
    local_imagegen_steps: int = Field(default=4, env="LOCAL_IMAGEGEN_STEPS")
    local_imagegen_guidance: float = Field(default=3.5, env="LOCAL_IMAGEGEN_GUIDANCE")
    local_imagegen_lora_dir: str = Field(default=r"E:\MYLLM\loras", env="LOCAL_IMAGEGEN_LORA_DIR")
    local_imagegen_lora: str = Field(default="", env="LOCAL_IMAGEGEN_LORA")
    local_imagegen_lora_strength: float = Field(default=0.65, env="LOCAL_IMAGEGEN_LORA_STRENGTH")
    local_imagegen_lora_trigger: str = Field(default="ChalkBoardDrawing", env="LOCAL_IMAGEGEN_LORA_TRIGGER")
    local_imagegen_flux_width: int = Field(default=768, env="LOCAL_IMAGEGEN_FLUX_WIDTH")
    local_imagegen_flux_height: int = Field(default=768, env="LOCAL_IMAGEGEN_FLUX_HEIGHT")
    local_imagegen_flux_preview_width: int = Field(default=512, env="LOCAL_IMAGEGEN_FLUX_PREVIEW_WIDTH")
    local_imagegen_flux_preview_height: int = Field(default=512, env="LOCAL_IMAGEGEN_FLUX_PREVIEW_HEIGHT")
    local_imagegen_max_attempts: int = Field(default=3, env="LOCAL_IMAGEGEN_MAX_ATTEMPTS")
    local_imagegen_timeout_s: float = Field(default=600, env="LOCAL_IMAGEGEN_TIMEOUT_S")

    # Optional Volcengine Ark / Seedream provider.
    ark_api_key: str = Field(default="", env="ARK_API_KEY")
    ark_base_url: str = Field(default="https://ark.cn-beijing.volces.com/api/v3", env="ARK_BASE_URL")
    seedream_model: str = Field(default="doubao-seedream-5-0-260128", env="SEEDREAM_MODEL")

    # TTS
    tts_voice: str = Field(default="zh-CN-XiaoxiaoNeural", env="TTS_VOICE")

    # Server
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8010, env="API_PORT")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()
