"""
Rewrite broken Oracle SQL using an LLM.
Called when validate or execute fails — passes the error + SQL to the AI for fixing.
"""
from langchain_core.messages import HumanMessage, SystemMessage


SYSTEM_PROMPT = """You are an expert SQL migration assistant specializing in converting
Vertica SQL to Oracle ADW SQL.

You will be given:
1. A SQL query that was converted from Vertica to Oracle
2. An error message from Oracle when it tried to run the query

Your job is to fix the SQL so it runs correctly on Oracle ADW.

Common fixes:
- ORA-00904: Invalid identifier → check column names, quote reserved words
- ORA-01722: Invalid number → wrap with TO_NUMBER() or add NULLIF to avoid divide by zero
- ORA-01843: Invalid month → use TO_DATE() with explicit format like TO_DATE(col, 'YYYY-MM-DD')
- ORA-12899: Value too large → check VARCHAR2 column sizes
- ORA-00923: FROM keyword not found → check SELECT syntax
- ILIKE → use UPPER(col) LIKE UPPER('value')
- LIMIT n → use FETCH FIRST n ROWS ONLY
- NOW() or GETDATE() → use CURRENT_TIMESTAMP
- IFNULL → use NVL
- VARCHAR → use VARCHAR2

Return ONLY the fixed SQL query. No explanation, no markdown, no code blocks. Just the SQL."""


def rewrite_sql(sql: str, error: str, llm) -> dict:
    """
    Ask the LLM to fix the broken SQL.
    Returns the rewritten SQL and whether it looks valid.
    """
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"""Fix this Oracle SQL query.

Original SQL:
{sql}

Oracle Error:
{error}

Return only the fixed SQL:""")
    ]

    response = llm.invoke(messages)
    fixed_sql = response.content.strip()

    # Strip markdown code blocks if LLM wrapped the SQL in them
    if fixed_sql.startswith("```"):
        lines = fixed_sql.split("\n")
        fixed_sql = "\n".join(lines[1:-1]).strip()

    return {
        "original_sql": sql,
        "error": error,
        "rewritten_sql": fixed_sql,
    }
