"""
File → DataFrame parsing, and DataFrame ↔ working-file persistence.

The 'working file' for a Dataset is stored as parquet on disk. Parquet
round-trips dtypes exactly (unlike CSV, which turns everything back
into strings on read), so a column we've already cast to int/float/
category stays that way across requests.
"""

import numpy as np
import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def read_uploaded_file(django_file) -> pd.DataFrame:
    """
    Read an uploaded CSV or Excel file into a DataFrame.
    Raises ValueError for unsupported types or unreadable files.
    """
    name = django_file.name.lower()

    if name.endswith(".csv"):
        try:
            return pd.read_csv(django_file)
        except UnicodeDecodeError:
            django_file.seek(0)
            return pd.read_csv(django_file, encoding="latin-1")
    elif name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(django_file)
    else:
        raise ValueError(
            f"Unsupported file type: '{name}'. Upload a .csv, .xlsx, or .xls file."
        )


def build_columns_meta(df: pd.DataFrame) -> dict:
    """
    Compute per-column metadata used by the frontend to render the
    column picker, dtype badges, and null-count warnings.
    """
    meta = {}
    for col in df.columns:
        series = df[col]
        dtype = str(series.dtype)

        # Grab a small JSON-safe sample of non-null values for the UI preview
        sample_values = series.dropna().head(5).tolist()
        sample_values = [_json_safe(v) for v in sample_values]

        meta[col] = {
            "dtype": dtype,
            "nulls": int(series.isna().sum()),
            "unique": int(series.nunique(dropna=True)),
            "is_numeric": bool(pd.api.types.is_numeric_dtype(series)),
            "sample": sample_values,
        }
    return meta


def _json_safe(value):
    """Convert numpy/pandas scalar types into plain Python types for JSON."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def dataframe_preview(df: pd.DataFrame, n_rows: int = 25) -> list:
    """First n_rows of the DataFrame as a list of JSON-safe dict records."""
    preview = df.head(n_rows).copy()
    for col in preview.columns:
        if pd.api.types.is_datetime64_any_dtype(preview[col]):
            preview[col] = preview[col].astype(str)
    records = preview.to_dict(orient="records")
    return [{k: _json_safe(v) if not pd.isna(v) else None for k, v in row.items()} for row in records]


# Hard ceiling on "view all rows" — protects the browser tab from trying
# to render an enormous table. Well above what anyone scrolls through by hand.
MAX_FULL_VIEW_ROWS = 5000


def dataframe_full(df: pd.DataFrame, max_rows: int = MAX_FULL_VIEW_ROWS) -> dict:
    """
    Up to max_rows of the DataFrame as JSON-safe records, plus whether
    the result was truncated — used by the "view all rows" button.
    """
    truncated = len(df) > max_rows
    return {
        "rows": dataframe_preview(df, n_rows=max_rows),
        "returned_count": min(len(df), max_rows),
        "truncated": truncated,
    }
