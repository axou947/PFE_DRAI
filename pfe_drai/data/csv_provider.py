"""CSV files: the simplest way to plug real data without writing code.

Put one file per series in data.csv_dir, named <series>.csv with two columns:
date,value. Series names are listed in pfe_drai/data/catalog.py.
"""

import pandas as pd

from ..config import resolve
from .base import DataProvider, register
from .catalog import CATALOG


@register
class CSVProvider(DataProvider):
    name = "csv"

    def fetch(self, start, end):
        folder = resolve(self.settings["data"]["csv_dir"])
        data = {}
        for name in CATALOG:
            path = folder / f"{name}.csv"
            if not path.exists():
                raise FileNotFoundError(f"Missing {path} (columns: date,value)")
            frame = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
            data[name] = frame["value"].loc[start:end].astype(float)
        return data
