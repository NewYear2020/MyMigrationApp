"""
Execute Oracle SQL with a safety row limit (smoke test).
Adds FETCH FIRST 10 ROWS ONLY to avoid pulling large datasets.
"""
import re
import oracledb


def execute_sql(sql: str, connection: oracledb.Connection, row_limit: int = 10) -> dict:
    """
    Execute SQL with a row limit as a smoke test.
    Returns success=True with sample rows, or success=False with error.
    """
    # Add row limit if not already present
    if not re.search(r'FETCH\s+FIRST', sql, re.IGNORECASE):
        limited_sql = f"{sql.rstrip(';')} FETCH FIRST {row_limit} ROWS ONLY"
    else:
        limited_sql = sql

    try:
        cursor = connection.cursor()
        cursor.execute(limited_sql)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description] if cursor.description else []
        cursor.close()
        return {
            "success": True,
            "error": None,
            "rows": rows,
            "columns": columns,
            "row_count": len(rows),
        }
    except oracledb.DatabaseError as e:
        return {
            "success": False,
            "error": str(e),
            "rows": [],
            "columns": [],
            "row_count": 0,
        }
