"""
Cleaning/transformation operations. Every function takes a DataFrame
and a params dict, returns a NEW DataFrame (never mutates in place),
so the caller can persist the result as the dataset's new working
state and log the operation as a CleaningStep.
"""

import pandas as pd
from sklearn.preprocessing import LabelEncoder, MinMaxScaler, StandardScaler


class CleaningError(ValueError):
    """Raised when a requested cleaning operation can't be applied."""


def drop_nulls(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    columns = params.get("columns")  # None = check all columns
    subset = columns if columns else None
    return df.dropna(subset=subset).reset_index(drop=True)


def fill_nulls(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    column = params.get("column")
    strategy = params.get("strategy", "mean")  # mean | median | mode | constant
    out = df.copy()

    if column not in out.columns:
        raise CleaningError(f"Column '{column}' not found.")

    series = out[column]

    if strategy == "mean":
        if not pd.api.types.is_numeric_dtype(series):
            raise CleaningError("Mean fill requires a numeric column.")
        out[column] = series.fillna(series.mean())
    elif strategy == "median":
        if not pd.api.types.is_numeric_dtype(series):
            raise CleaningError("Median fill requires a numeric column.")
        out[column] = series.fillna(series.median())
    elif strategy == "mode":
        mode_val = series.mode(dropna=True)
        out[column] = series.fillna(mode_val.iloc[0] if not mode_val.empty else None)
    elif strategy == "constant":
        out[column] = series.fillna(params.get("value"))
    else:
        raise CleaningError(f"Unknown fill strategy '{strategy}'.")

    return out


def drop_column(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    column = params.get("column")
    if column not in df.columns:
        raise CleaningError(f"Column '{column}' not found.")
    return df.drop(columns=[column])


def rename_column(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    old_name = params.get("old_name")
    new_name = params.get("new_name")
    if old_name not in df.columns:
        raise CleaningError(f"Column '{old_name}' not found.")
    if not new_name:
        raise CleaningError("New column name cannot be empty.")
    return df.rename(columns={old_name: new_name})


def encode_categorical(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Label-encode a categorical column in place (adds `<column>_encoded`).
    For a handful of categories, one-hot is offered via `method`.
    """
    column = params.get("column")
    method = params.get("method", "label")  # label | onehot
    out = df.copy()

    if column not in out.columns:
        raise CleaningError(f"Column '{column}' not found.")

    if method == "label":
        encoder = LabelEncoder()
        non_null_mask = out[column].notna()
        out.loc[non_null_mask, f"{column}_encoded"] = encoder.fit_transform(
            out.loc[non_null_mask, column].astype(str)
        )
    elif method == "onehot":
        dummies = pd.get_dummies(out[column], prefix=column, dummy_na=False)
        out = pd.concat([out, dummies], axis=1)
    else:
        raise CleaningError(f"Unknown encoding method '{method}'.")

    return out


def scale_numeric(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    column = params.get("column")
    method = params.get("method", "standard")  # standard | minmax
    out = df.copy()

    if column not in out.columns:
        raise CleaningError(f"Column '{column}' not found.")
    if not pd.api.types.is_numeric_dtype(out[column]):
        raise CleaningError("Scaling requires a numeric column.")

    scaler = StandardScaler() if method == "standard" else MinMaxScaler()
    non_null_mask = out[column].notna()
    values = out.loc[non_null_mask, [column]].values
    out.loc[non_null_mask, f"{column}_scaled"] = scaler.fit_transform(values).flatten()

    return out


def cast_dtype(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    column = params.get("column")
    target_dtype = params.get("dtype")  # "int64" | "float64" | "str" | "category" | "datetime64[ns]"
    out = df.copy()

    if column not in out.columns:
        raise CleaningError(f"Column '{column}' not found.")

    try:
        if target_dtype == "datetime64[ns]":
            out[column] = pd.to_datetime(out[column], errors="coerce")
        else:
            out[column] = out[column].astype(target_dtype)
    except (ValueError, TypeError) as exc:
        raise CleaningError(f"Could not cast '{column}' to {target_dtype}: {exc}")

    return out


OPERATIONS = {
    "drop_nulls": drop_nulls,
    "fill_nulls": fill_nulls,
    "drop_column": drop_column,
    "rename_column": rename_column,
    "encode_categorical": encode_categorical,
    "scale_numeric": scale_numeric,
    "cast_dtype": cast_dtype,
}


def apply_operation(df: pd.DataFrame, operation: str, params: dict) -> pd.DataFrame:
    if operation not in OPERATIONS:
        raise CleaningError(f"Unknown operation '{operation}'.")
    return OPERATIONS[operation](df, params)
