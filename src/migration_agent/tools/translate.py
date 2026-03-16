"""
Translate Vertica SQL to Oracle ADW SQL.
Uses a 3-stage pipeline: pre-process (regex) → sqlglot → post-process (regex)
"""
import re
import sqlglot


def pre_process(sql: str) -> str:
    """Clean up Vertica-specific syntax before sqlglot sees it."""

    # Normalize whitespace
    sql = re.sub(r'\s+', ' ', sql).strip()

    # Redact DATEDIFF so sqlglot doesn't mangle it
    sql = re.sub(
        r'DATEDIFF\s*\(\s*MINUTE\s*,',
        '__REDACT_DATEDIFF_MINUTE__(',
        sql, flags=re.IGNORECASE
    )
    sql = re.sub(
        r'DATEDIFF\s*\(\s*HOUR\s*,',
        '__REDACT_DATEDIFF_HOUR__(',
        sql, flags=re.IGNORECASE
    )
    sql = re.sub(
        r'DATEDIFF\s*\(\s*DAY\s*,',
        '__REDACT_DATEDIFF_DAY__(',
        sql, flags=re.IGNORECASE
    )

    # Normalize AT TIME ZONE without parens: col AT TIME ZONE 'UTC'
    sql = re.sub(
        r"(\w+)\s+AT\s+TIME\s+ZONE\s+'([^']+)'",
        r"CAST(\1 AS TIMESTAMP WITH TIME ZONE) AT TIME ZONE '\2'",
        sql, flags=re.IGNORECASE
    )

    return sql


def transpile(sql: str) -> str:
    """Use sqlglot to convert from Postgres dialect to Oracle dialect."""
    try:
        results = sqlglot.transpile(sql, read="postgres", write="oracle")
        return results[0] if results else sql
    except Exception:
        return sql


def post_process(sql: str) -> str:
    """Fix things sqlglot missed or got wrong."""

    # Restore redacted DATEDIFF patterns → Oracle equivalent
    sql = re.sub(
        r'__REDACT_DATEDIFF_MINUTE__\s*\(([^,]+),([^)]+)\)',
        r'ROUND((CAST(\2 AS DATE) - CAST(\1 AS DATE)) * 1440)',
        sql, flags=re.IGNORECASE
    )
    sql = re.sub(
        r'__REDACT_DATEDIFF_HOUR__\s*\(([^,]+),([^)]+)\)',
        r'ROUND((CAST(\2 AS DATE) - CAST(\1 AS DATE)) * 24)',
        sql, flags=re.IGNORECASE
    )
    sql = re.sub(
        r'__REDACT_DATEDIFF_DAY__\s*\(([^,]+),([^)]+)\)',
        r'ROUND(CAST(\2 AS DATE) - CAST(\1 AS DATE))',
        sql, flags=re.IGNORECASE
    )

    # NOW() → CURRENT_TIMESTAMP
    sql = re.sub(r'\bNOW\s*\(\s*\)', 'CURRENT_TIMESTAMP', sql, flags=re.IGNORECASE)

    # GETDATE() → CURRENT_TIMESTAMP
    sql = re.sub(r'\bGETDATE\s*\(\s*\)', 'CURRENT_TIMESTAMP', sql, flags=re.IGNORECASE)

    # IFNULL → NVL
    sql = re.sub(r'\bIFNULL\s*\(', 'NVL(', sql, flags=re.IGNORECASE)

    # VARCHAR → VARCHAR2
    sql = re.sub(r'\bVARCHAR\b', 'VARCHAR2', sql, flags=re.IGNORECASE)

    # ILIKE → UPPER/LIKE (case-insensitive match)
    sql = re.sub(
        r"(\w+)\s+ILIKE\s+'([^']+)'",
        r"UPPER(\1) LIKE UPPER('\2')",
        sql, flags=re.IGNORECASE
    )

    return sql


def translate_sql(sql: str) -> dict:
    """
    Full 3-stage translation pipeline.
    Returns a dict with each stage's output for debugging.
    """
    pre = pre_process(sql)
    transpiled = transpile(pre)
    post = post_process(transpiled)

    return {
        "input": sql,
        "pre_processed": pre,
        "transpiled": transpiled,
        "output": post,
    }
