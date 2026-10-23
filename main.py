"""Run the NSE market-data downloader command-line application."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from nse_market_data_downloader.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
