"""Transcript parser service configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Matches the floor `api` and `ai` already apply to this same secret.
MINIMUM_PRODUCTION_TOKEN_LENGTH = 32


class Settings(BaseSettings):
    service_name: str = "transcript-parser"
    environment: str = "development"
    transcript_parser_port: int = 8010
    internal_service_token: str | None = None
    max_upload_bytes: int = 5 * 1024 * 1024
    parse_timeout_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def resolved_internal_service_token(self) -> str:
        return (self.internal_service_token or "").strip()

    def validate_production_settings(self) -> None:
        """Refuse to run a production parser with no boundary in front of it.

        `/parse` accepts an uploaded PDF from anything that can reach the port,
        and `require_internal_service_token` returns early when no token is
        configured. That early return is right for a developer running this
        alone and wrong in production, where the way it happens is an env var
        that quietly fails to arrive -- nothing errors and nothing looks
        different.

        `api` already refuses to start without a 32+ character token for this
        exact secret, and `ai` enforces the same rule on the other side of the
        same boundary. This service was the one that would start without any
        token at all, which made it the soft spot between two hard ones.
        """
        if self.environment != "production":
            return
        token = self.resolved_internal_service_token()
        if not token:
            raise RuntimeError(
                "INTERNAL_SERVICE_TOKEN is required in production: without it "
                "/parse accepts uploads from anything that can reach the port."
            )
        if len(token) < MINIMUM_PRODUCTION_TOKEN_LENGTH:
            raise RuntimeError(
                "INTERNAL_SERVICE_TOKEN must be at least "
                f"{MINIMUM_PRODUCTION_TOKEN_LENGTH} characters in production."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
