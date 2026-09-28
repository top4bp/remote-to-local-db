# MSSQL DB Copy

A small Python CLI tool for copying data from one Microsoft SQL Server database to another.

It supports:

- different source and target servers
- different ports
- different users and passwords
- different schemas
- configured table list
- copy all tables from a source schema with optional exclusions
- automatic target table creation when a configured table is missing
- identity columns via `SET IDENTITY_INSERT`
- batched inserts
- environment variable based credentials

## Requirements

- Python 3.10+
- Microsoft ODBC Driver for SQL Server
- Access to both MSSQL databases

```bash
sudo apt install -y unixodbc unixodbc-dev
sudo apt install odbcinst
sudo ACCEPT_EULA=Y apt install -y msodbcsql18
```
```bash
```

## Setup

Clone the repository:

```bash
git clone <repo-url>
cd mssql-db-copy
```

Setup environment
```bash
python3 -m venv .venv
pip install -r requirements.txt
source .venv/bin/activate
cp config.example.yml config.yml

```

Modify config
```bash
nano config.yml
```

## Copy modes

### Include specific tables

This is the default/existing behavior. The tool copies only the tables listed under `tables`, creates missing target tables, and retries deferred tables across multiple passes when foreign-key dependencies block inserts.

```yaml
mode: include_tables

tables:
  - Users
  - Orders
  - OrderItems
```

If `mode` is omitted, `include_tables` is used.

### Copy all tables from a schema

Use this mode to discover every base table in `source.schema` and copy it to `target.schema`. Missing target tables are still created automatically, and the same multi-pass dependency retry behavior is used.

```yaml
mode: copy_all_from_schema

exclude_tables:
  - flyway_schema_history
  - SomeLargeAuditTable
```

`exclude_tables` is optional. Table names should match the names in the source schema.

## Run

```bash
python -m mssql_copy --config config.yml
```


