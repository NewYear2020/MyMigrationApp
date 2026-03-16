"""
Migration Agent CLI
Usage:
    uv run python main.py "SELECT * FROM patients WHERE name ILIKE 'john' LIMIT 10"
    uv run python main.py --interactive
"""
import sys
import argparse
import json

from src.migration_agent.config import OracleConfig, LLMConfig, get_oracle_connection, get_llm
from src.migration_agent.agent import run_agent


def run_single(sql: str, connection, llm, verbose: bool = False):
    """Run the migration pipeline on a single SQL query and print results."""
    print(f"\n{'='*60}")
    print(f"INPUT SQL:\n{sql}")
    print(f"{'='*60}")

    result = run_agent(sql, connection, llm)

    print(f"\nOUTPUT SQL:\n{result['translated_sql']}")
    print(f"\nSTATUS: {result['status'].upper()}")

    if result.get("error"):
        print(f"ERROR:  {result['error']}")

    if result.get("result_rows"):
        print(f"\nSAMPLE ROWS ({result['result_rows'].__len__()} returned):")
        for row in result["result_rows"][:3]:
            print(f"  {row}")

    if verbose:
        print(f"\nRETRIES: {result['retries']}")

    print(f"{'='*60}\n")
    return result


def interactive_mode(connection, llm):
    """Run in interactive mode — keep accepting SQL queries until user quits."""
    print("\nMigration Agent — Interactive Mode")
    print("Type a Vertica SQL query and press Enter to convert it.")
    print("Type 'quit' or 'exit' to stop.\n")

    while True:
        try:
            sql = input("SQL> ").strip()
            if not sql:
                continue
            if sql.lower() in ("quit", "exit"):
                print("Goodbye!")
                break
            run_single(sql, connection, llm)
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


def main():
    parser = argparse.ArgumentParser(description="Vertica → Oracle ADW SQL Migration Agent")
    parser.add_argument("sql", nargs="?", help="SQL query to convert")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("--verbose", action="store_true", help="Show extra details")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    args = parser.parse_args()

    # Load config and connect
    oracle_config = OracleConfig.from_env()
    llm_config = LLMConfig.from_env()

    print("Connecting to Oracle ADW...")
    connection = get_oracle_connection(oracle_config)
    print("Connected.")

    print(f"Loading LLM ({llm_config.provider})...")
    llm = get_llm(llm_config)
    print("LLM ready.\n")

    if args.interactive:
        interactive_mode(connection, llm)

    elif args.sql:
        result = run_single(args.sql, connection, llm, verbose=args.verbose)
        if args.json:
            print(json.dumps({
                "input": result["input_sql"],
                "output": result["translated_sql"],
                "status": result["status"],
                "retries": result["retries"],
                "error": result.get("error"),
            }, indent=2))

    else:
        # Read from stdin if no SQL provided
        if not sys.stdin.isatty():
            sql = sys.stdin.read().strip()
            run_single(sql, connection, llm, verbose=args.verbose)
        else:
            parser.print_help()

    connection.close()


if __name__ == "__main__":
    main()
