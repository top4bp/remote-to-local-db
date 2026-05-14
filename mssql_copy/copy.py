import pyodbc

from mssql_copy.config import AppConfig
from mssql_copy.db import (
    full_table_name,
    get_columns,
    get_identity_column,
    get_insertable_columns,
    quote_name,
    table_exists,
)


def copy_all_tables(
    source_conn: pyodbc.Connection,
    target_conn: pyodbc.Connection,
    config: AppConfig,
) -> None:
    pending_tables = list(config.tables)
    failed_errors: dict[str, Exception] = {}
    pass_number = 1

    while pending_tables:
        print(f"\n=== Copy pass {pass_number} ===")
        print(f"Pending tables: {len(pending_tables)}")

        next_pending_tables = []
        successful_tables = []

        for table in pending_tables:
            try:
                copy_table(
                    source_conn=source_conn,
                    target_conn=target_conn,
                    config=config,
                    table=table,
                )

                successful_tables.append(table)

                if table in failed_errors:
                    del failed_errors[table]

            except Exception as error:
                if _is_foreign_key_error(error):
                    print(f"Deferred table due to foreign key conflict: {table}")
                    print(f"Reason: {repr(error)}")

                    next_pending_tables.append(table)
                    failed_errors[table] = error
                else:
                    print(f"Fatal error while copying table: {table}")
                    print(f"Error type: {type(error).__name__}")
                    print(f"Error repr: {repr(error)}")
                    raise

        if successful_tables:
            print(
                f"\nPass {pass_number} finished. "
                f"Copied {len(successful_tables)} table(s), "
                f"deferred {len(next_pending_tables)} table(s)."
            )
        else:
            print(f"\nPass {pass_number} made no progress.")

        if not next_pending_tables:
            print("\nAll tables copied successfully.")
            return

        if len(next_pending_tables) == len(pending_tables):
            print("\nCould not resolve remaining foreign key dependencies.")
            print("The following tables are still blocked:")

            for table in next_pending_tables:
                print(f"\n- {table}")
                print(f"  Last error: {failed_errors[table]}")

            raise RuntimeError(
                "Copy stopped because no deferred table could be copied in the latest pass."
            )

        pending_tables = next_pending_tables
        pass_number += 1


def copy_table(
    source_conn: pyodbc.Connection,
    target_conn: pyodbc.Connection,
    config: AppConfig,
    table: str,
) -> None:
    source_schema = config.source.schema
    target_schema = config.target.schema

    source_table_ref = full_table_name(source_schema, table)
    target_table_ref = full_table_name(target_schema, table)

    print(f"\nCopying {source_table_ref} -> {target_table_ref}")

    _validate_table_exists(source_conn, source_schema, table, "source")
    _validate_table_exists(target_conn, target_schema, table, "target")

    source_columns = get_columns(source_conn, source_schema, table)
    target_insertable_columns = get_insertable_columns(
        target_conn,
        target_schema,
        table,
    )

    common_columns = [
        column
        for column in source_columns
        if column in target_insertable_columns
    ]
    
    skipped_target_columns = [
        column
        for column in source_columns
        if column not in target_insertable_columns
    ]

    if skipped_target_columns:
        print(
            "Skipping non-insertable target columns: "
            + ", ".join(skipped_target_columns)
        )

    if not common_columns:
        raise RuntimeError(
            f"No matching columns found for {source_table_ref} -> {target_table_ref}"
        )

    identity_column = get_identity_column(target_conn, target_schema, table)

    column_list_sql = ", ".join(quote_name(column) for column in common_columns)
    placeholders = ", ".join("?" for _ in common_columns)

    order_by_sql = (
        quote_name(identity_column)
        if identity_column and identity_column in common_columns
        else column_list_sql
    )

    source_sql = f"""
        SELECT {column_list_sql}
        FROM {source_table_ref}
        ORDER BY {order_by_sql}
    """

    insert_sql = f"""
        INSERT INTO {target_table_ref} ({column_list_sql})
        VALUES ({placeholders})
    """

    source_cursor = None
    target_cursor = None
    identity_insert_enabled = False

    try:
        source_cursor = source_conn.cursor()
        target_cursor = target_conn.cursor()
        target_cursor.fast_executemany = config.options.fast_executemany

        if config.options.clear_target_tables_first:
            print(f"Clearing target table {target_table_ref}")
            target_cursor.execute(f"DELETE FROM {target_table_ref}")

        if identity_column:
            print(f"Enabling IDENTITY_INSERT for {target_table_ref}")
            target_cursor.execute(f"SET IDENTITY_INSERT {target_table_ref} ON")
            identity_insert_enabled = True

        source_cursor.execute(source_sql)

        total = 0

        while True:
            rows = source_cursor.fetchmany(config.options.batch_size)

            if not rows:
                break

            try:
                target_cursor.executemany(insert_sql, rows)
            except MemoryError:
                print(
                    "MemoryError during batch insert. "
                    "Retrying this batch row-by-row without fast_executemany."
                )
            
                target_cursor.fast_executemany = False
            
                for row in rows:
                    target_cursor.execute(insert_sql, row)
            
            total += len(rows)
            
            print(f"Inserted {total} rows")
            
        if identity_insert_enabled:
            print(f"Disabling IDENTITY_INSERT for {target_table_ref}")
            target_cursor.execute(f"SET IDENTITY_INSERT {target_table_ref} OFF")
            identity_insert_enabled = False

            print(f"Reseeding identity for {target_table_ref}")
            target_cursor.execute(
                f"DBCC CHECKIDENT ('{target_schema}.{table}', RESEED)"
            )

        target_conn.commit()

        print(f"Finished {target_table_ref}")

    except Exception:
        target_conn.rollback()

        if identity_insert_enabled:
            _try_disable_identity_insert(target_conn, target_table_ref)

        raise

    finally:
        if source_cursor is not None:
            try:
                source_cursor.close()
            except Exception:
                pass

        if target_cursor is not None:
            try:
                target_cursor.close()
            except Exception:
                pass


def _validate_table_exists(
    conn: pyodbc.Connection,
    schema: str,
    table: str,
    label: str,
) -> None:
    if not table_exists(conn, schema, table):
        raise RuntimeError(f"Table does not exist in {label}: {schema}.{table}")


def _try_disable_identity_insert(
    conn: pyodbc.Connection,
    table_ref: str,
) -> None:
    cursor = None

    try:
        print(f"Trying to disable IDENTITY_INSERT after failure for {table_ref}")
        cursor = conn.cursor()
        cursor.execute(f"SET IDENTITY_INSERT {table_ref} OFF")
        conn.commit()
        print(f"IDENTITY_INSERT disabled after failure for {table_ref}")
    except Exception as error:
        print(
            f"Warning: could not disable IDENTITY_INSERT for {table_ref}: {repr(error)}"
        )
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass


def _is_foreign_key_error(error: Exception) -> bool:
    error_text = str(error)

    return (
        "FOREIGN KEY constraint" in error_text
        or "conflicted with the FOREIGN KEY" in error_text
        or "(547)" in error_text
    )
