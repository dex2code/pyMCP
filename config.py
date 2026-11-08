from __future__ import annotations

from typing import Literal
from pathlib import Path
import os
import yaml

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    model_validator,
)
from pydantic.networks import IPvAnyAddress
from dotenv import load_dotenv


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mcp_name: str = Field(min_length=1, max_length=32)
    mcp_transport: Literal["stdio", "streamable-http"] = "stdio"
    host: IPvAnyAddress
    port: int = Field(ge=1, le=65535)
    path: str = Field(pattern=r"^/", min_length=1, max_length=32)
    api_key: SecretStr | None = Field(default=None, min_length=8)

    @model_validator(mode="after")
    def _require_api_key_for_network_transport(self) -> "AppConfig":
        if self.mcp_transport != "stdio" and self.api_key is None:
            raise ValueError(
                f"api_key is required when mcp_transport={self.mcp_transport!r}"
            )
        return self


def load_config(
    yaml_path: str | Path = "config.yaml",
    env_path: str | Path | None = ".env",
    api_key_env: str = "API_KEY",
) -> AppConfig:

    if env_path is not None:
        env_path_obj = Path(env_path)
        if not env_path_obj.is_file():
            raise FileNotFoundError(f".env file not found: {env_path_obj}")
        load_dotenv(env_path_obj, override=False)

    raw_api_key = (os.environ.get(api_key_env) or "").strip()

    yaml_path_obj = Path(yaml_path)
    if not yaml_path_obj.is_file():
        raise FileNotFoundError(f"YAML config file not found: {yaml_path_obj}")

    try:
        with yaml_path_obj.open("r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {yaml_path_obj}: {e}") from e

    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, dict):
        raise ValueError(
            f"YAML config must be a mapping, got {type(raw_config).__name__}"
        )

    if raw_api_key:
        raw_config["api_key"] = raw_api_key

    return AppConfig.model_validate(raw_config)
