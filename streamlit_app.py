"""
Streamlit UI for Vertica → Oracle ADW SQL Migration Agent.
Wraps the existing translate → validate → execute → rewrite pipeline.
"""
import sys
import os
import pandas as pd

import streamlit as st

# Make sure the src package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from migration_agent.config import OracleConfig, LLMConfig, get_oracle_connection, get_llm
from migration_agent.tools.translate import translate_sql
from migration_agent.agent import run_agent


# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Vertica → Oracle ADW Migrator",
    page_icon="🔄",
    layout="wide",
)

st.title("🔄 Vertica → Oracle ADW SQL Migrator")
st.caption("Paste a Vertica query. The agent iterates until the query executes successfully on Oracle ADW.")


# ── Sidebar: connection status ────────────────────────────────────────────────
with st.sidebar:
    st.header("Connection")

    @st.cache_resource(show_spinner="Connecting to Oracle ADW…")
    def load_resources():
        oracle_cfg = OracleConfig.from_env()
        llm_cfg = LLMConfig.from_env()
        conn = get_oracle_connection(oracle_cfg)
        llm = get_llm(llm_cfg)
        return conn, llm, oracle_cfg, llm_cfg

    try:
        conn, llm, oracle_cfg, llm_cfg = load_resources()
        st.success(f"Oracle ADW: **{oracle_cfg.dsn}**")
        st.success(f"LLM: **{llm_cfg.provider}**")
    except Exception as e:
        st.error(f"Connection failed: {e}")
        st.stop()

    st.divider()
    mode = st.radio(
        "Pipeline mode",
        ["Translate only", "Translate + Validate + Execute (full agent)"],
        index=1,
    )


# ── Main input area ───────────────────────────────────────────────────────────
default_sql = """\
SELECT
    provider_key,
    clinician_specialty,
    practice_state_or_us_territory,
    IFNULL(years_in_medicare, 0)        AS years_in_medicare,
    IFNULL(final_score, 0)              AS final_score,
    payment_adjustment_percentage
FROM qpp_experience_2022
WHERE clinician_specialty ILIKE '%surgery%'
  AND practice_state_or_us_territory ILIKE 'ca'
ORDER BY final_score DESC
LIMIT 10;"""

vertica_sql = st.text_area(
    "Vertica SQL",
    value=default_sql,
    height=180,
    placeholder="SELECT … FROM … WHERE …",
)

run_btn = st.button("Translate & Run", type="primary", disabled=not vertica_sql.strip())


# ── Run pipeline ──────────────────────────────────────────────────────────────
if run_btn and vertica_sql.strip():
    col_in, col_out = st.columns(2)

    with col_in:
        st.subheader("Input (Vertica SQL)")
        st.code(vertica_sql.strip(), language="sql")

    # ── Translate-only mode ───────────────────────────────────────────────────
    if mode == "Translate only":
        with st.spinner("Translating…"):
            result = translate_sql(vertica_sql.strip())

        with col_out:
            st.subheader("Oracle ADW SQL")
            st.code(result["output"], language="sql")

        st.info("Translation complete — no DB validation in this mode.")
        st.divider()
        st.text_area("Copy translated SQL", value=result["output"], height=120, key="copy_box")

    # ── Full agent mode ───────────────────────────────────────────────────────
    else:
        spinner_msg = st.empty()
        with spinner_msg.container():
            st.spinner("Running migration agent — iterating until query succeeds…")

        with st.spinner("Running migration agent — iterating until query succeeds on Oracle ADW…"):
            try:
                final = run_agent(vertica_sql.strip(), conn, llm)
            except Exception as e:
                st.error("The agent encountered an unexpected error. Please check your query and try again.")
                st.stop()

        status = final.get("status", "unknown")
        retries = final.get("retries", 0)

        with col_out:
            st.subheader("Oracle ADW SQL")
            st.code(final["translated_sql"], language="sql")

        # ── Pipeline step badges ──────────────────────────────────────────────
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Translated", "✅")
        c2.metric("Validated", "✅" if final.get("validated") else "❌")
        c3.metric("Executed", "✅" if final.get("executed") else "❌")
        c4.metric("LLM rewrites", retries)

        # ── Results or friendly failure message ───────────────────────────────
        st.divider()

        if status == "success":
            st.success("Query executed successfully on Oracle ADW.")

            rows = final.get("result_rows") or []
            cols = final.get("result_columns") or None

            if rows:
                st.subheader("Query Results")
                df = pd.DataFrame(rows, columns=cols)
                st.dataframe(df, use_container_width=True)
                st.caption(f"{len(rows)} row(s) returned (capped at 10 by the agent).")
            else:
                st.info("Query executed with no rows returned.")
        else:
            st.warning(
                "The agent was unable to produce a fully validated query after exhausting all retries. "
                "Please review the translated SQL above and adjust your input query."
            )

        # ── Copy box always shown ─────────────────────────────────────────────
        st.divider()
        st.text_area("Copy translated SQL", value=final["translated_sql"], height=120, key="copy_box")
