"""
Configuration — reads .env file and sets up Oracle + LLM connections.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class OracleConfig:
    dsn: str
    user: str
    password: str
    wallet_path: str = ""
    wallet_password: str = ""

    @classmethod
    def from_env(cls) -> "OracleConfig":
        return cls(
            dsn=os.environ["ORACLE_DSN"],
            user=os.environ["ORACLE_USER"],
            password=os.environ["ORACLE_PASSWORD"],
            wallet_path=os.environ.get("ORACLE_WALLET_PATH", ""),
            wallet_password=os.environ.get("ORACLE_WALLET_PASSWORD", ""),
        )


@dataclass
class LLMConfig:
    provider: str       # "openai", "anthropic", or "oci_genai"
    model: str = ""

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            provider=os.environ.get("LLM_PROVIDER", "openai"),
            model=os.environ.get("LLM_MODEL", ""),
        )


def get_oracle_connection(config: OracleConfig):
    """Create and return an Oracle ADW connection."""
    import oracledb

    if config.wallet_path:
        # Tell Oracle driver where to find tnsnames.ora and the wallet
        os.environ["TNS_ADMIN"] = config.wallet_path
        connection = oracledb.connect(
            user=config.user,
            password=config.password,
            dsn=config.dsn,
            config_dir=config.wallet_path,
            wallet_location=config.wallet_path,
            wallet_password=config.wallet_password or None,
        )
    else:
        connection = oracledb.connect(
            user=config.user,
            password=config.password,
            dsn=config.dsn,
        )
    return connection


def get_llm(config: LLMConfig):
    """Create and return an LLM instance based on the provider in .env."""

    if config.provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=config.model or "gpt-4o",
            api_key=os.environ["OPENAI_API_KEY"],
        )

    elif config.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=config.model or "claude-sonnet-4-6",
            api_key=os.environ["ANTHROPIC_API_KEY"],
        )

    elif config.provider == "oci_genai":
        from migration_agent.llm.oci_genai import ChatOCIGenAI, OCIGenAIConfig
        oci_config = OCIGenAIConfig(
            config_file=os.path.expanduser(os.environ.get("OCI_CONFIG_FILE", "~/.oci/config")),
            config_profile=os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT"),
            endpoint=os.environ.get("OCI_GENAI_ENDPOINT", ""),
            endpoint_id=os.environ.get("OCI_GENAI_ENDPOINT_ID", ""),
            compartment_id=os.environ.get("OCI_COMPARTMENT_ID", ""),
            model_id=os.environ.get("OCI_GENAI_MODEL_ID", ""),
        )
        return ChatOCIGenAI(config=oci_config)

    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}. Use openai, anthropic, or oci_genai.")
