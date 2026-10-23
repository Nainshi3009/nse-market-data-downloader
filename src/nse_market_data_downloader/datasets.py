"""Known NSE market-data page locations."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class DatasetSpec:
    """Identifier and published NSE page for a requested dataset."""

    dataset_id: str
    page_url: str


DATASETS: Mapping[str, DatasetSpec] = MappingProxyType(
    {
        "top-gainers-losers": DatasetSpec(
            "top-gainers-losers",
            "https://www.nseindia.com/market-data/top-gainers-losers",
        ),
        "upper-band-hitters": DatasetSpec(
            "upper-band-hitters",
            "https://www.nseindia.com/market-data/upper-band-hitters",
        ),
        "volume-gainers-spurts": DatasetSpec(
            "volume-gainers-spurts",
            "https://www.nseindia.com/market-data/volume-gainers-spurts",
        ),
        "52-week-high-equity-market": DatasetSpec(
            "52-week-high-equity-market",
            "https://www.nseindia.com/market-data/52-week-high-equity-market",
        ),
    }
)
