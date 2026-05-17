from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.deepseek.com/v1", env="OPENAI_BASE_URL")
    llm_model: str = Field(default="deepseek-chat", env="LLM_MODEL")
    coder_model: str = Field(default="deepseek-coder", env="CODER_MODEL")
    remotion_codegen_mode: str = Field(default="compiler", env="REMOTION_CODEGEN_MODE")
    remotion_llm_repair: bool = Field(default=False, env="REMOTION_LLM_REPAIR")
    llm_preflight_timeout_s: float = Field(default=8.0, env="LLM_PREFLIGHT_TIMEOUT_S")
    llm_preflight_ttl_s: float = Field(default=60.0, env="LLM_PREFLIGHT_TTL_S")

    # Image generation (Volcengine Ark / Seedream)
    ark_api_key: str = Field(default="", env="ARK_API_KEY")
    ark_base_url: str = Field(default="https://ark.cn-beijing.volces.com/api/v3", env="ARK_BASE_URL")
    seedream_model: str = Field(default="doubao-seedream-5-0-260128", env="SEEDREAM_MODEL")

    # TTS
    tts_voice: str = Field(default="zh-CN-XiaoxiaoNeural", env="TTS_VOICE")

    # Server
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
