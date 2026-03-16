"""
Migration Agent — LangGraph state machine.
Orchestrates: translate → validate → execute → rewrite (if needed)
"""
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from migration_agent.tools.translate import translate_sql
from migration_agent.tools.validate import validate_sql
from migration_agent.tools.execute import execute_sql
from migration_agent.tools.rewrite import rewrite_sql


# --- State: what gets passed between each step ---

class MigrationState(TypedDict):
    input_sql: str           # Original Vertica SQL
    translated_sql: str      # After translation
    validated: bool          # Did EXPLAIN PLAN pass?
    executed: bool           # Did smoke test pass?
    error: Optional[str]     # Last error message
    retries: int             # How many rewrites attempted
    status: str              # final status: success / needs_review
    result_rows: list        # Sample rows from execution
    result_columns: list     # Column names from execution
    connection: object       # Oracle DB connection
    llm: object              # LLM instance


MAX_RETRIES = 5


# --- Nodes (each step in the pipeline) ---

def translate_node(state: MigrationState) -> MigrationState:
    """Step 1: Convert Vertica SQL to Oracle SQL."""
    result = translate_sql(state["input_sql"])
    return {**state, "translated_sql": result["output"]}


def validate_node(state: MigrationState) -> MigrationState:
    """Step 2: Check if Oracle SQL is syntactically valid."""
    result = validate_sql(state["translated_sql"], state["connection"])
    return {
        **state,
        "validated": result["success"],
        "error": result["error"],
    }


def execute_node(state: MigrationState) -> MigrationState:
    """Step 3: Run SQL with row limit as smoke test."""
    result = execute_sql(state["translated_sql"], state["connection"])
    return {
        **state,
        "executed": result["success"],
        "error": result["error"],
        "result_rows": result.get("rows", []),
        "result_columns": result.get("columns", []),
    }


def rewrite_node(state: MigrationState) -> MigrationState:
    """Step 4: Ask LLM to fix broken SQL."""
    try:
        result = rewrite_sql(state["translated_sql"], state["error"], state["llm"])
        return {
            **state,
            "translated_sql": result["rewritten_sql"],
            "retries": state["retries"] + 1,
            "validated": False,
            "executed": False,
            "error": None,
        }
    except Exception as e:
        # LLM unavailable — mark as needs_review instead of crashing
        return {
            **state,
            "retries": state["retries"] + 1,
            "status": "needs_review",
            "error": f"LLM rewrite failed: {e}",
        }


def finalize_node(state: MigrationState) -> MigrationState:
    """Final step: mark as success or needs_review."""
    if state.get("executed"):
        status = "success"
    elif state.get("validated"):
        status = "success"
    else:
        status = "needs_review"
    return {**state, "status": status}


# --- Routing logic ---

def after_validate(state: MigrationState) -> str:
    if state["validated"]:
        return "execute"
    elif state["retries"] < MAX_RETRIES:
        return "rewrite"
    else:
        return "finalize"


def after_execute(state: MigrationState) -> str:
    if state["executed"]:
        return "finalize"
    elif state["retries"] < MAX_RETRIES:
        return "rewrite"
    else:
        return "finalize"


def after_rewrite(state: MigrationState) -> str:
    return "validate"


# --- Build the graph ---

def create_agent():
    graph = StateGraph(MigrationState)

    graph.add_node("translate", translate_node)
    graph.add_node("validate", validate_node)
    graph.add_node("execute", execute_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("translate")

    graph.add_edge("translate", "validate")
    graph.add_conditional_edges("validate", after_validate)
    graph.add_conditional_edges("execute", after_execute)
    graph.add_conditional_edges("rewrite", after_rewrite)
    graph.add_edge("finalize", END)

    return graph.compile()


def run_agent(sql: str, connection, llm) -> dict:
    """Run the full migration pipeline on a single SQL query."""
    agent = create_agent()
    initial_state = {
        "input_sql": sql,
        "translated_sql": "",
        "validated": False,
        "executed": False,
        "error": None,
        "retries": 0,
        "status": "pending",
        "result_rows": [],
        "result_columns": [],
        "connection": connection,
        "llm": llm,
    }
    final_state = agent.invoke(initial_state)
    return final_state
