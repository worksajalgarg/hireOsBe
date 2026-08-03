"""Runtime settings loaded from environment (.env via python-dotenv)."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = 8000
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    resume_max_upload_mb: int = Field(default=10, ge=1, le=50)
    cors_origins: str = "http://localhost:3000"
    # Empty = official OpenAI. OpenRouter: https://openrouter.ai/api/v1
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    # Cap completion size (OpenRouter free/low credit accounts reject high defaults).
    openai_max_tokens: int = Field(default=512, ge=64, le=8192)
    # mock | openrouter | gemini | local
    llm_mode: str = "mock"
    gemini_model: str = "gemini-2.0-flash-lite"
    # When true, gemini/openrouter/local failures fall back to mock so the pipeline can finish
    llm_fallback_to_mock: bool = True
    # Docling: force OCR on every PDF page (slower; useful for scanned resumes)
    docling_force_full_page_ocr: bool = False
    # Local transformers instruct model (LLM_MODE=local)
    local_llm_model: str = "Qwen/Qwen2.5-3B-Instruct"
    local_llm_max_new_tokens: int = Field(default=2048, ge=64, le=8192)
    # auto | mps | cuda | cpu
    local_llm_device: str = "auto"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    # Allow PORT from env without renaming; pydantic-settings maps field names.
    if "PORT" in os.environ and "port" not in os.environ:
        os.environ.setdefault("port", os.environ["PORT"])
    return Settings()
