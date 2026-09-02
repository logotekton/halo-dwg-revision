"""Runtime configuration for the halo_engine sidecar.

All fields are overridable via ``HALO_ENGINE_*`` environment variables
(e.g. ``HALO_ENGINE_DATA_DIR``, ``HALO_ENGINE_DEV``, ``HALO_ENGINE_TOKEN``),
which is how CLI-provided values reach a uvicorn ``--reload`` worker that
re-imports the app factory in a fresh process.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Sidecar settings. See ``docs/PLAN.md`` §3 for the handshake protocol."""

    model_config = SettingsConfigDict(env_prefix="HALO_ENGINE_", extra="ignore")

    data_dir: Path = Path.home() / ".halo-cad" / "engine"
    dev: bool = False
    log_dir: Path | None = None
    token: str | None = None
