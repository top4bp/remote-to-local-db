from typing import Any, List, Optional

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

    try:
        cursor.execute(sql, schema, table)
        return [row.COLUMN_NAME for row in cursor.fetchall()]
    finally:
        cursor.close()


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

    try:
        cursor.execute(sql, schema, table)
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        cursor.close()


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

    try:
        cursor.execute(sql, schema, table)
        return cursor.fetchone() is not None
    finally:
        cursor.close()


def get_schema_tables(
    conn: pyodbc.Connection,
    schema: str,
) -> List[str]:
    sql = """
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = ?
          AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
    """

    cursor = conn.cursor()

    try:
        cursor.execute(sql, schema)
        return [row.TABLE_NAME for row in cursor.fetchall()]
    finally:
        cursor.close()


def create_table_like(
    source_conn: pyodbc.Connection,
    target_conn: pyodbc.Connection,
    source_schema: str,
    target_schema: str,
    table: str,
) -> None:
    create_sql = get_create_table_sql(
        source_conn=source_conn,
        source_schema=source_schema,
        target_schema=target_schema,
        table=table,
    )

    cursor = target_conn.cursor()

    try:
        cursor.execute(create_sql)
        target_conn.commit()
    finally:
        cursor.close()


def get_create_table_sql(
    source_conn: pyodbc.Connection,
    source_schema: str,
    target_schema: str,
    table: str,
) -> str:
    columns = _get_column_metadata(source_conn, source_schema, table)

    if not columns:
        raise RuntimeError(f"No columns found for source table: {source_schema}.{table}")

    column_definitions = [
        _build_column_definition(column)
        for column in columns
    ]

    return (
        f"CREATE TABLE {full_table_name(target_schema, table)} (\n"
        + ",\n".join(f"    {definition}" for definition in column_definitions)
        + "\n)"
    )


def _get_column_metadata(
    conn: pyodbc.Connection,
    schema: str,
    table: str,
) -> List[dict[str, Any]]:
    sql = """
        SELECT
            c.name AS column_name,
            ty.name AS type_name,
            SCHEMA_NAME(ty.schema_id) AS type_schema,
            ty.is_user_defined AS is_user_defined,
            c.max_length,
            c.precision,
            c.scale,
            c.is_nullable,
            c.is_identity,
            CONVERT(varchar(40), ic.seed_value) AS identity_seed,
            CONVERT(varchar(40), ic.increment_value) AS identity_increment,
            c.collation_name,
            c.is_computed,
            cc.definition AS computed_definition,
            cc.is_persisted AS computed_is_persisted,
            c.is_rowguidcol
        FROM sys.columns c
        JOIN sys.tables t ON c.object_id = t.object_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        JOIN sys.types ty ON c.user_type_id = ty.user_type_id
        LEFT JOIN sys.identity_columns ic
            ON c.object_id = ic.object_id
           AND c.column_id = ic.column_id
        LEFT JOIN sys.computed_columns cc
            ON c.object_id = cc.object_id
           AND c.column_id = cc.column_id
        WHERE s.name = ?
          AND t.name = ?
        ORDER BY c.column_id
    """

    cursor = conn.cursor()

    try:
        cursor.execute(sql, schema, table)
        column_names = [column[0] for column in cursor.description]

        return [
            dict(zip(column_names, row))
            for row in cursor.fetchall()
        ]
    finally:
        cursor.close()


def _build_column_definition(column: dict[str, Any]) -> str:
    column_name = quote_name(column["column_name"])

    if column["is_computed"]:
        definition = column["computed_definition"]

        if not definition:
            raise RuntimeError(
                f"Computed column definition is missing for {column['column_name']}"
            )

        persisted_sql = " PERSISTED" if column["computed_is_persisted"] else ""
        return f"{column_name} AS {definition}{persisted_sql}"

    type_sql = _format_data_type(column)
    collation_sql = _format_collation(column)
    identity_sql = _format_identity(column)
    rowguidcol_sql = " ROWGUIDCOL" if column["is_rowguidcol"] else ""
    nullability_sql = "NULL" if column["is_nullable"] else "NOT NULL"

    return (
        f"{column_name} {type_sql}{collation_sql}"
        f"{identity_sql}{rowguidcol_sql} {nullability_sql}"
    )


def _format_data_type(column: dict[str, Any]) -> str:
    type_name = column["type_name"]
    lower_type_name = type_name.lower()

    if column["is_user_defined"]:
        return f"{quote_name(column['type_schema'])}.{quote_name(type_name)}"

    if lower_type_name in {"varchar", "char", "varbinary", "binary"}:
        return f"{type_name}({_format_length(column['max_length'])})"

    if lower_type_name in {"nvarchar", "nchar"}:
        return f"{type_name}({_format_length(column['max_length'], unicode=True)})"

    if lower_type_name in {"decimal", "numeric"}:
        return f"{type_name}({column['precision']}, {column['scale']})"

    if lower_type_name in {"datetime2", "datetimeoffset", "time"}:
        return f"{type_name}({column['scale']})"

    if lower_type_name == "float" and column["precision"]:
        return f"{type_name}({column['precision']})"

    if lower_type_name == "timestamp":
        return "rowversion"

    return type_name


def _format_length(max_length: int, unicode: bool = False) -> str:
    if max_length == -1:
        return "max"

    if unicode:
        return str(max_length // 2)

    return str(max_length)


def _format_identity(column: dict[str, Any]) -> str:
    if not column["is_identity"]:
        return ""

    seed = column["identity_seed"] or "1"
    increment = column["identity_increment"] or "1"

    return f" IDENTITY({seed}, {increment})"


def _format_collation(column: dict[str, Any]) -> str:
    collation_name = column["collation_name"]

    if not collation_name:
        return ""

    collatable_types = {
        "char",
        "varchar",
        "text",
        "nchar",
        "nvarchar",
        "ntext",
    }

    if column["type_name"].lower() not in collatable_types:
        return ""

    return f" COLLATE {collation_name}"


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

    try:
        cursor.execute(sql, schema, table)
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()


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

    cursor = conn.cursor()

    try:
        cursor.execute(sql, schema, schema)
        conn.commit()
    finally:
        cursor.close()
