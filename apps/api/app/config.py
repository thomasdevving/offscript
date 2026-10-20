"""Runtime configuration, loaded from environment variables (see `.env.example`)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = API_ROOT.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", str(REPO_ROOT / ".env")), extra="ignore")

    environment: Literal["local", "test", "azure"] = "local"
    log_level: str = "INFO"

    # --- Microsoft Foundry ---------------------------------------------------
    # When `foundry_project_endpoint` and `foundry_model` are set, agents call the Foundry
    # deployment through Microsoft Agent Framework's FoundryChatClient (Entra ID auth via
    # DefaultAzureCredential: managed identity in Azure, `az login` locally).
    # Otherwise agents run on the clearly-labelled deterministic policy client.
    foundry_project_endpoint: str | None = None
    foundry_model: str | None = None
    agent_mode: Literal["auto", "foundry", "policy"] = "auto"
    foundry_timeout_s: float = 25.0
    foundry_max_output_tokens: int = 1200
    agent_max_tool_calls: int = 6

    # --- Simulation ----------------------------------------------------------
    default_rollouts: int = 200
    max_rollouts: int = 500
    simulation_horizon_s: float = 10.0
    simulation_time_budget_s: float = 20.0
    max_concurrent_analyses: int = 2

    # --- Workflow ------------------------------------------------------------
    max_strategy_revisions: int = 2
    max_explanation_retries: int = 1

    # --- Storage / web ------------------------------------------------------
    data_dir: Path = Field(default=API_ROOT / "data")
    scenarios_dir: Path = Field(default=REPO_ROOT / "scenarios")
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    use_analysis_cache: bool = True

    # --- Telemetry -----------------------------------------------------------
    applicationinsights_connection_string: str | None = None

    @property
    def foundry_configured(self) -> bool:
        return bool(self.foundry_project_endpoint and self.foundry_model)

    @property
    def effective_agent_mode(self) -> Literal["foundry", "policy"]:
        if self.agent_mode == "policy":
            return "policy"
        if self.agent_mode == "foundry":
            return "foundry"
        return "foundry" if self.foundry_configured else "policy"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
