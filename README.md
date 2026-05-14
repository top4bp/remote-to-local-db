# MSSQL DB Copy

A small Python CLI tool for copying data from one Microsoft SQL Server database to another.

It supports:

- different source and target servers
- different ports
- different users and passwords
- different schemas
- configured table list
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

## Run

```bash
python -m mssql_copy --config config.yml
```


