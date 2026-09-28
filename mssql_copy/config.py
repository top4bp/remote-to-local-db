import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

import yaml
from dotenv import load_dotenv


INCLUDE_TABLES_MODE = "include_tables"
COPY_ALL_FROM_SCHEMA_MODE = "copy_all_from_schema"
SUPPORTED_COPY_MODES = {INCLUDE_TABLES_MODE, COPY_ALL_FROM_SCHEMA_MODE}


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
    encrypt: bool
    driver: str
    fast_executemany: bool


@dataclass(frozen=True)
class AppConfig:
    source: DatabaseConfig
    target: DatabaseConfig
    options: Options
    copy_mode: str
    tables: List[str]
    exclude_tables: List[str]


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


def _load_table_list(raw: dict, key: str) -> List[str]:
    values = raw.get(key, [])

    if values is None:
        return []

    if not isinstance(values, list):
        raise RuntimeError(f"Config value '{key}' must be a list.")

    return [str(value) for value in values]


def load_config(config_path: str) -> AppConfig:
    load_dotenv()

    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    if raw is None:
        raise RuntimeError(f"Config file is empty: {config_path}")

    copy_mode = raw.get("mode", INCLUDE_TABLES_MODE)

    if copy_mode not in SUPPORTED_COPY_MODES:
        supported_modes = ", ".join(sorted(SUPPORTED_COPY_MODES))
        raise RuntimeError(
            f"Unsupported copy mode '{copy_mode}'. Supported modes: {supported_modes}"
        )

    tables = _load_table_list(raw, "tables")
    exclude_tables = _load_table_list(raw, "exclude_tables")

    if copy_mode == INCLUDE_TABLES_MODE and not tables:
        raise RuntimeError(
            "Config value 'tables' must contain at least one table "
            "when mode is 'include_tables'."
        )

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
            encrypt=bool(
                options_raw.get("encrypt", False)
            ),

            driver=options_raw.get("driver", "ODBC Driver 18 for SQL Server"),
            fast_executemany=bool(options_raw.get("fast_executemany", False)),
        ),
        copy_mode=copy_mode,
        tables=tables,
        exclude_tables=exclude_tables,
    )

