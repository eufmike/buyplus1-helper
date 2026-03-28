"""Typer CLI for the buyplus1-helper timecard tool."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .extractor import extract_sessions
from .llm_extractor import LLMExtractor, get_from_date, save_state
from .llm_extractor import _DEFAULT_MODEL as _DEFAULT_LLM_MODEL
from .llm_validator import LLMValidator
from .parser import parse_file
from .timecard import build_dataframe, export_excel, load_master, merge, save_master

_DEFAULT_LLM_CACHE = Path("data/llm_cache.json")
_DEFAULT_STATE_SUFFIX = ".state.json"

app = typer.Typer(
    name="timecard",
    help="Parse LINE chat history and maintain 曉寒's timecard.",
    add_completion=False,
)
console = Console()


@app.command()
def parse(
    chat_file: Path = typer.Argument(..., help="Path to the LINE chat export .txt file"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output CSV path (default: <stem>_timecard.csv)"
    ),
    llm_validate: bool = typer.Option(
        False, "--llm-validate", help="Use LLM to classify ambiguous 後上線 messages"
    ),
    llm_cache: Path = typer.Option(
        _DEFAULT_LLM_CACHE, "--llm-cache", help="Path to LLM result cache (JSON)"
    ),
) -> None:
    """Parse a chat file and write a timecard CSV (rule-based extractor)."""
    if not chat_file.exists():
        console.print(f"[red]File not found:[/red] {chat_file}")
        raise typer.Exit(1)

    out_path = output or chat_file.with_name(chat_file.stem + "_timecard.csv")
    validator = LLMValidator(cache_path=llm_cache) if llm_validate else None

    messages = parse_file(chat_file)
    sessions = extract_sessions(messages, source_file=chat_file.name, llm_validator=validator)
    df = build_dataframe(sessions)
    save_master(df, out_path)

    llm_note = " [dim](LLM validation on)[/dim]" if llm_validate else ""
    console.print(
        f"[green]Parsed[/green] {len(sessions)} session(s) → [bold]{out_path}[/bold]{llm_note}"
    )


@app.command()
def merge_cmd(
    input_csv: Path = typer.Argument(..., help="Parsed CSV to merge in"),
    master_csv: Path = typer.Argument(..., help="Master CSV path (created if missing)"),
) -> None:
    """Merge a parsed CSV into the master timecard (deduplicates by date+session)."""
    if not input_csv.exists():
        console.print(f"[red]File not found:[/red] {input_csv}")
        raise typer.Exit(1)

    import pandas as pd

    new_df = pd.read_csv(input_csv, encoding="utf-8-sig", dtype=str).fillna("")
    master_df = load_master(master_csv)
    merged = merge(new_df, master_df)
    save_master(merged, master_csv)

    console.print(
        f"[green]Merged[/green] → [bold]{master_csv}[/bold] ({len(merged)} total rows)"
    )


# Register with hyphenated name for CLI
app.command(name="merge")(merge_cmd)


@app.command()
def run(
    chat_file: Path = typer.Argument(..., help="Path to the LINE chat export .txt file"),
    master_csv: Path = typer.Argument(..., help="Master CSV path (created if missing)"),
    model: str = typer.Option(
        _DEFAULT_LLM_MODEL, "--model", "-m", help="Gemini model name"
    ),
    from_date: Optional[str] = typer.Option(
        None,
        "--from-date",
        help=(
            "Only process messages on/after this date (YYYY-MM-DD). "
            "Auto-detected from state file when omitted."
        ),
    ),
    rule_based: bool = typer.Option(
        False, "--rule-based", help="Use keyword rules instead of Gemini (legacy mode)"
    ),
    llm_validate: bool = typer.Option(
        False, "--llm-validate", help="[rule-based only] Validate ambiguous messages with LLM"
    ),
    llm_cache: Path = typer.Option(
        _DEFAULT_LLM_CACHE, "--llm-cache", help="[rule-based only] Path to LLM result cache"
    ),
    max_workers: int = typer.Option(
        4, "--max-workers", help="Number of parallel Gemini API calls (one per day)"
    ),
) -> None:
    """Parse a chat file and merge into the master (incremental by default).

    Uses Gemini to read all of 曉寒's messages and extract sessions directly.
    On subsequent runs with a new chat file, only the unseen portion is sent
    to the API — the overlap is detected automatically via a state file stored
    alongside the master CSV.
    """
    if not chat_file.exists():
        console.print(f"[red]File not found:[/red] {chat_file}")
        raise typer.Exit(1)

    state_path = master_csv.with_suffix(_DEFAULT_STATE_SUFFIX)
    messages = parse_file(chat_file)

    if rule_based:
        # --- Legacy rule-based path ---
        validator = LLMValidator(cache_path=llm_cache) if llm_validate else None
        sessions = extract_sessions(
            messages, source_file=chat_file.name, llm_validator=validator
        )
        llm_note = " [dim](rule-based + LLM validation)[/dim]" if llm_validate else " [dim](rule-based)[/dim]"
    else:
        # --- Full LLM path ---
        # Determine start date: CLI flag > state file > process everything
        start: Optional[date] = None
        if from_date:
            start = date.fromisoformat(from_date)
            console.print(f"[dim]Processing from {start} (--from-date)[/dim]")
        else:
            start = get_from_date(state_path)
            if start:
                console.print(f"[dim]Resuming from {start} (state file)[/dim]")
            else:
                console.print("[dim]No state file — processing full chat history[/dim]")

        extractor = LLMExtractor(model=model, max_workers=max_workers)
        with console.status(f"[bold]Calling {model}…[/bold]"):
            sessions = extractor.extract_sessions(
                messages, source_file=chat_file.name, from_date=start
            )
        llm_note = f" [dim](Gemini: {model})[/dim]"

        # Persist watermark only when at least one session was successfully extracted
        if sessions:
            last_date = max(m.date for m in messages)
            save_state(state_path, last_date)
            logger.debug("State updated: last_processed_date = %s", last_date)

    new_df = build_dataframe(sessions)
    master_df = load_master(master_csv)
    merged = merge(new_df, master_df)
    save_master(merged, master_csv)

    console.print(
        f"[green]Done[/green] — {len(sessions)} session(s) extracted, "
        f"{len(merged)} total row(s) in [bold]{master_csv}[/bold]{llm_note}"
    )


@app.command()
def show(
    master_csv: Path = typer.Argument(..., help="Master CSV path"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date YYYY-MM-DD"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD"),
) -> None:
    """Display timecard records as a rich table."""
    df = load_master(master_csv)
    if df.empty:
        console.print("[yellow]No records found.[/yellow]")
        return

    if from_date:
        df = df[df["date"] >= from_date]
    if to_date:
        df = df[df["date"] <= to_date]

    table = Table(title=f"Timecard — {master_csv.name}", show_lines=True)
    for col in df.columns:
        table.add_column(col, style="cyan" if col == "date" else "")

    for _, row in df.iterrows():
        table.add_row(*[str(v) for v in row])

    console.print(table)
    console.print(f"[dim]{len(df)} row(s)[/dim]")


@app.command()
def export(
    master_csv: Path = typer.Argument(..., help="Master CSV path"),
    format: str = typer.Option("csv", "--format", "-f", help="Output format: csv or excel"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Export the master timecard to CSV or Excel."""
    df = load_master(master_csv)
    if df.empty:
        console.print("[yellow]No records to export.[/yellow]")
        return

    if format == "excel":
        out_path = output or master_csv.with_suffix(".xlsx")
        export_excel(df, out_path)
    else:
        out_path = output or master_csv
        save_master(df, out_path)

    console.print(f"[green]Exported[/green] {len(df)} row(s) → [bold]{out_path}[/bold]")


import logging
logger = logging.getLogger(__name__)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
