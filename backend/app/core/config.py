"""All KnowHub settings in one place.

Values come from environment variables (docker compose loads them from the repo-root
.env; see .env.example for every key with comments). Nothing else in the codebase
reads os.environ or hardcodes GCP names, hosts or buckets.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_JWT_SECRET = "change-me"

# Used when MODEL / LLM_API_BASE are left empty in .env.
DEFAULT_MODELS = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-sonnet-5",
    "gemini": "gemini-2.5-flash",
    "vertex": "gemini-2.5-flash",
    "ollama": "llama3.2",
}

DEFAULT_API_BASES = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "ollama": "http://localhost:11434",
    # vertex builds its host from the project and location instead
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,  # tests and code can use the field names directly
        protected_namespaces=(),  # "model" is a field here, not a pydantic internal
    )

    # --- app ---
    app_env: Literal["local", "dev", "stage", "prod"] = "local"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # --- database ---
    database_url: str = "postgresql+asyncpg://knowhub:knowhub@postgres:5432/knowhub"
    db_pool_size: int = 5

    # --- auth ---
    jwt_secret: str = INSECURE_JWT_SECRET
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 14
    password_reset_ttl_min: int = 30

    # --- gcp ---
    gcp_project_id: str = "knowhub-local"
    gcp_region: str = "us-central1"

    # --- storage ---
    storage_backend: Literal["gcs"] = "gcs"
    gcs_endpoint_url: str = ""  # set → fake-gcs-server; empty → real GCS
    gcs_public_endpoint_url: str = ""  # browser-reachable emulator URL (signed URLs, media)
    # one bucket holds both, separated by prefix: raw/ (originals) and media/ (processed)
    gcs_bucket: str = "knowhub-data"
    gcs_raw_prefix: str = "raw"
    gcs_media_prefix: str = "media"
    signed_url_ttl_min: int = 15
    media_public_base_url: str = ""

    # --- pub/sub ---
    pubsub_emulator_host: str = ""  # set → emulator (read by the client library too)
    pubsub_topic_video_uploaded: str = "video-uploaded"
    pubsub_topic_transcode_events: str = "transcode-events"
    pubsub_topic_video_published: str = "video-published"
    pubsub_topic_video_metadata_changed: str = "video-metadata-changed"
    pubsub_topic_analytics_events: str = "analytics-events"

    # --- transcoder ---
    transcoder_backend: Literal["ffmpeg", "gcp"] = "ffmpeg"
    transcoder_location: str = "us-central1"

    # --- analytics ---
    analytics_backend: Literal["postgres", "bigquery"] = "postgres"
    bq_dataset: str = "knowhub_analytics"
    bq_events_table: str = "events"

    # --- ai ---
    # One switch. Each provider brings its own key and its own default model; MODEL and
    # LLM_API_BASE override those when you want a specific model or an OpenAI-compatible
    # gateway (Ollama, vLLM, LiteLLM, a company proxy).
    provider: Literal["openai", "anthropic", "gemini", "vertex", "ollama", "none"] = Field(
        default="ollama", validation_alias=AliasChoices("PROVIDER", "AI_PROVIDER")
    )
    model: str = Field(default="", validation_alias=AliasChoices("MODEL", "AI_TEXT_MODEL"))
    llm_api_base: str = Field(default="", validation_alias=AliasChoices("LLM_API_BASE", "OLLAMA_BASE_URL"))
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    ai_embedding_model: str = "nomic-embed-text"
    ai_embedding_dim: int = 768
    # where the Vertex models live; empty falls back to GCP_REGION ("global" is allowed)
    vertex_location: str = ""
    ai_enhance_max_chars: int = 5000

    @property
    def ai_model(self) -> str:
        """MODEL from .env, or the provider's default."""
        return self.model.strip() or DEFAULT_MODELS.get(self.provider, "")

    @property
    def ai_base_url(self) -> str:
        """LLM_API_BASE from .env, or the provider's own endpoint."""
        return (self.llm_api_base or DEFAULT_API_BASES.get(self.provider, "")).rstrip("/")

    @property
    def ai_api_key(self) -> str:
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
        }.get(self.provider, "").strip()

    @property
    def ai_key_setting(self) -> str:
        """The .env key to name when the provider rejects us for lack of one."""
        return {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }.get(self.provider, "")

    @property
    def ai_location(self) -> str:
        return self.vertex_location or self.gcp_region

    # --- engagement ---
    # how long after posting a comment can still be edited
    comment_edit_window_seconds: int = 60

    # --- limits ---
    max_video_bytes: int = 5 * 1024**3
    max_video_seconds: int = 7200
    max_short_seconds: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"

    @property
    def pubsub_topics(self) -> list[str]:
        return [
            self.pubsub_topic_video_uploaded,
            self.pubsub_topic_transcode_events,
            self.pubsub_topic_video_published,
            self.pubsub_topic_video_metadata_changed,
            self.pubsub_topic_analytics_events,
        ]

    @property
    def buckets(self) -> list[str]:
        return [self.gcs_bucket]

    def raw_object(self, *parts: str) -> str:
        """raw/users/{user_id}/videos/{video_id}/source.mp4"""
        return "/".join([self.gcs_raw_prefix, *parts])

    def media_object(self, *parts: str) -> str:
        """media/videos/{video_id}/v1/hls/master.m3u8"""
        return "/".join([self.gcs_media_prefix, *parts])

    @model_validator(mode="after")
    def _check_secrets_and_env(self) -> Settings:
        # An empty JWT_SECRET only shows up at the first login, as PyJWT's
        # "HMAC key must not be empty". Refuse to start instead.
        if not self.jwt_secret.strip():
            raise ValueError(
                "JWT_SECRET is empty, so access tokens cannot be signed. Set it in .env, "
                "e.g. JWT_SECRET=$(openssl rand -hex 32)"
            )
        # Pointing a cloud provider at a local model name gives a puzzling 404 from the
        # provider, so say it here instead. An explicit LLM_API_BASE means the person is
        # deliberately using an OpenAI-compatible gateway (Ollama, vLLM, a proxy), so the
        # model name is theirs to choose.
        local_models = ("llama", "mistral", "qwen", "phi", "gemma", "deepseek")
        if (
            self.provider in ("openai", "anthropic", "gemini", "vertex")
            and not self.llm_api_base
            and self.ai_model.startswith(local_models)
        ):
            raise ValueError(
                f"PROVIDER={self.provider} but MODEL is '{self.ai_model}', which is a local model. "
                f"Use one of that provider's models (default: {DEFAULT_MODELS[self.provider]}), "
                "or set LLM_API_BASE if you are pointing at a compatible gateway"
            )
        if self.app_env != "local":
            if self.jwt_secret == INSECURE_JWT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be a random value of at least 32 characters outside local")
            if self.gcs_endpoint_url or self.pubsub_emulator_host:
                raise ValueError("emulator endpoints must not be set outside local")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
