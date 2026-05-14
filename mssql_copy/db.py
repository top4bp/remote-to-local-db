from typing import List, Optional

import pyodbc

from mssql_copy.config import DatabaseConfig, Options


def quote_name(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def full_table_name(schema: str, table: str) -> str:
    return f"{quote_name(schema)}.{quote_name(table)}"


def connect(config: DatabaseConfig, options: Options) -> pyodbc.Connection:
    trust_cert = "yes" if options.trust_server_certificate else "no"
    encrypt = "yes" if options.encrypt else "no"

    connection_string = (
        f"DRIVER={{{options.driver}}};"
        f"SERVER={config.server};"
        f"DATABASE={config.database};"
        f"UID={config.username};"
        f"PWD={config.password};"
        f"TrustServerCertificate={trust_cert};"
	f"Encrypt={encrypt};"
    )

    return pyodbc.connect(connection_string)


def get_columns(
    conn: pyodbc.Connection,
    schema: str,
    table: str,
) -> List[str]:
    sql = """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ?
          AND TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
    """

    cursor = conn.cursor()
    cursor.execute(sql, schema, table)

    return [row.COLUMN_NAME for row in cursor.fetchall()]


def get_identity_column(
    conn: pyodbc.Connection,
    schema: str,
    table: str,
) -> Optional[str]:
    sql = """
        SELECT c.name
        FROM sys.columns c
        JOIN sys.tables t ON c.object_id = t.object_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE s.name = ?
          AND t.name = ?
          AND c.is_identity = 1
    """

    cursor = conn.cursor()
    cursor.execute(sql, schema, table)

    row = cursor.fetchone()

    return row[0] if row else None


def table_exists(
    conn: pyodbc.Connection,
    schema: str,
    table: str,
) -> bool:
    sql = """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = ?
          AND TABLE_NAME = ?
          AND TABLE_TYPE = 'BASE TABLE'
    """

    cursor = conn.cursor()
    cursor.execute(sql, schema, table)

    return cursor.fetchone() is not None


    
def get_insertable_columns(
    conn: pyodbc.Connection,
    schema: str,
    table: str,
) -> List[str]:
    sql = """
        SELECT c.name
        FROM sys.columns c
        JOIN sys.tables t ON c.object_id = t.object_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        JOIN sys.types ty ON c.user_type_id = ty.user_type_id
        WHERE s.name = ?
          AND t.name = ?
          AND c.is_computed = 0
          AND c.generated_always_type = 0
          AND ty.name NOT IN ('timestamp', 'rowversion')
        ORDER BY c.column_id
    """

    cursor = conn.cursor()
    cursor.execute(sql, schema, table)

    return [row[0] for row in cursor.fetchall()]    
    
def ensure_schema_exists(
    conn: pyodbc.Connection,
    schema: str,
) -> None:
    sql = """
        IF NOT EXISTS (
            SELECT 1
            FROM sys.schemas
            WHERE name = ?
        )
        BEGIN
            DECLARE @sql nvarchar(max);
            SET @sql = N'CREATE SCHEMA ' + QUOTENAME(?);
            EXEC sp_executesql @sql;
        END
    """

    cursor = None

    try:
        cursor = conn.cursor()
        cursor.execute(sql, schema, schema)
        conn.commit()
    finally:
        if cursor is not None:
            cursor.close()    
