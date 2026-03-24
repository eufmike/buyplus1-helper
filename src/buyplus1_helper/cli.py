"""Typer CLI for the buyplus1-helper timecard tool."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .extractor import extract_sessions
from .parser import parse_file
from .timecard import build_dataframe, export_excel, load_master, merge, save_master

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
) -> None:
    """Parse a chat file and write a timecard CSV."""
    if not chat_file.exists():
        console.print(f"[red]File not found:[/red] {chat_file}")
        raise typer.Exit(1)

    out_path = output or chat_file.with_name(chat_file.stem + "_timecard.csv")

    messages = parse_file(chat_file)
    sessions = extract_sessions(messages, source_file=chat_file.name)
    df = build_dataframe(sessions)
    save_master(df, out_path)

    console.print(
        f"[green]Parsed[/green] {len(sessions)} session(s) → [bold]{out_path}[/bold]"
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
) -> None:
    """Parse a chat file and merge directly into the master (one-step convenience)."""
    if not chat_file.exists():
        console.print(f"[red]File not found:[/red] {chat_file}")
        raise typer.Exit(1)

    messages = parse_file(chat_file)
    sessions = extract_sessions(messages, source_file=chat_file.name)
    new_df = build_dataframe(sessions)
    master_df = load_master(master_csv)
    merged = merge(new_df, master_df)
    save_master(merged, master_csv)

    console.print(
        f"[green]Done[/green] — {len(sessions)} session(s) parsed, "
        f"{len(merged)} total row(s) in [bold]{master_csv}[/bold]"
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
