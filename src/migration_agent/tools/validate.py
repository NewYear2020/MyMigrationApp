"""
Validate Oracle SQL by running EXPLAIN PLAN on Oracle ADW.
This checks syntax without actually executing the query.
"""
import oracledb


def validate_sql(sql: str, connection: oracledb.Connection) -> dict:
    """
    Run EXPLAIN PLAN on the given SQL against Oracle ADW.
    Returns success=True if valid, or success=False with the error message.
    """
    # These Oracle errors mean the SQL is syntactically valid
    # but blocked by security/access policies — treat as valid
    SYNTAX_VALID_ERRORS = (
        "ORA-28113",  # VPD policy predicate error
        "ORA-01039",  # Insufficient privileges on underlying objects
    )

    try:
        cursor = connection.cursor()
        cursor.execute(f"EXPLAIN PLAN FOR {sql}")
        cursor.close()
        return {"success": True, "error": None}
    except oracledb.DatabaseError as e:
        error_msg = str(e)
        if any(code in error_msg for code in SYNTAX_VALID_ERRORS):
            return {"success": True, "error": None}
        return {"success": False, "error": error_msg}
