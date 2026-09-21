import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_local_defaults_are_valid():
    settings = make()
    assert settings.is_local
    assert settings.buckets == ["knowhub-data"]
    assert settings.raw_object("users", "u1", "source.mp4") == "raw/users/u1/source.mp4"
    assert len(settings.pubsub_topics) == 5


def test_cors_origins_are_split():
    settings = make(cors_origins="http://a.test, http://b.test,")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_empty_jwt_secret_is_rejected_everywhere():
    """An empty secret used to pass config and fail later as PyJWT's
    "HMAC key must not be empty" on the first login."""
    for value in ("", "   "):
        with pytest.raises(ValidationError, match="JWT_SECRET is empty"):
            make(app_env="local", jwt_secret=value)


def test_non_local_requires_strong_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        make(app_env="prod", jwt_secret="change-me", gcs_endpoint_url="", pubsub_emulator_host="")


def test_non_local_rejects_emulators():
    with pytest.raises(ValidationError, match="emulator"):
        make(app_env="prod", jwt_secret="x" * 40, gcs_endpoint_url="http://gcs:4443")


def test_env_vars_are_read(monkeypatch):
    monkeypatch.setenv("GCS_BUCKET", "other-raw")
    monkeypatch.setenv("AI_PROVIDER", "none")
    settings = make()
    assert settings.gcs_bucket == "other-raw"
    assert settings.ai_provider == "none"
