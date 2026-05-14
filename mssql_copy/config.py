import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class DatabaseConfig:
    server: str
    database: str
    username: str
    password: str
    schema: str


@dataclass(frozen=True)
class Options:
    batch_size: int
    clear_target_tables_first: bool
    trust_server_certificate: bool
    driver: str


@dataclass(frozen=True)
class AppConfig:
    source: DatabaseConfig
    target: DatabaseConfig
    options: Options
    tables: List[str]


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")

    return value


def _load_db_config(raw: dict) -> DatabaseConfig:
    username_env = raw["username_env"]
    password_env = raw["password_env"]

    return DatabaseConfig(
        server=raw["server"],
        database=raw["database"],
        username=_required_env(username_env),
        password=_required_env(password_env),
        schema=raw["schema"],
    )


def load_config(config_path: str) -> AppConfig:
    load_dotenv()

    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    options_raw = raw.get("options", {})

    return AppConfig(
        source=_load_db_config(raw["source"]),
        target=_load_db_config(raw["target"]),
        options=Options(
            batch_size=int(options_raw.get("batch_size", 1000)),
            clear_target_tables_first=bool(
                options_raw.get("clear_target_tables_first", False)
            ),
            trust_server_certificate=bool(
                options_raw.get("trust_server_certificate", True)
            ),
            driver=options_raw.get("driver", "ODBC Driver 18 for SQL Server"),
        ),
        tables=list(raw["tables"]),
    )

