"""PoliWatch CLI entry point."""

import asyncio

import typer

app = typer.Typer(help="PoliWatch — Congressional trade accountability tool")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="API host"),
    port: int = typer.Option(8000, help="API port"),
) -> None:
    """Start the FastAPI server."""
    import uvicorn

    uvicorn.run("poliwatch.api.main:app", host=host, port=port, reload=False)


@app.command()
def ingest(
    backfill: bool = typer.Option(False, "--backfill", help="Fetch all historical data"),
    once: bool = typer.Option(True, "--once/--schedule", help="Run once or on schedule"),
) -> None:
    """Run data ingestion."""
    from poliwatch.ingestion.scheduler import run_full_ingest

    asyncio.run(run_full_ingest(backfill=backfill))


@app.command()
def dashboard() -> None:
    """Launch the Streamlit dashboard (requires streamlit in PATH)."""
    import subprocess
    import sys
    from pathlib import Path

    dashboard_path = Path(__file__).parent / "dashboard" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(dashboard_path)], check=True)


if __name__ == "__main__":
    app()
