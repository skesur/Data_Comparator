"""
Trains and compares several scikit-learn supervised models against
a chosen target column, and supports predicting on new input using
a previously saved model.

Task type (regression vs classification) is inferred from the
target column unless the caller overrides it: numeric + high
cardinality => regression, otherwise => classification.
"""

import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import SVC, SVR


class MLEngineError(ValueError):
    pass


REGRESSION_MODELS = {
    "LinearRegression": LinearRegression(),
    "RandomForestRegressor": RandomForestRegressor(n_estimators=100, max_depth=12, n_jobs=-1, random_state=42),
    "GradientBoostingRegressor": GradientBoostingRegressor(n_estimators=100, random_state=42),
    "SVR": SVR(),
}

CLASSIFICATION_MODELS = {
    "LogisticRegression": LogisticRegression(max_iter=1000),
    "RandomForestClassifier": RandomForestClassifier(n_estimators=100, max_depth=12, n_jobs=-1, random_state=42),
    "GradientBoostingClassifier": GradientBoostingClassifier(n_estimators=100, random_state=42),
    "SVC": SVC(),  # probability=False (default) — much faster; app only calls .predict(), never .predict_proba()
}

# On low-CPU environments (e.g. Render's free tier), SVM training time
# grows steeply with row count. Cap the training sample for SVC/SVR
# specifically — 3000 rows is plenty to compare its accuracy against
# the other models without risking a worker timeout.
_SVM_MAX_TRAIN_ROWS = 3000


def infer_task_type(series: pd.Series) -> str:
    if pd.api.types.is_numeric_dtype(series) and series.nunique() > 15:
        return "regression"
    return "classification"


def _prepare_features(df: pd.DataFrame, feature_columns: list) -> tuple[np.ndarray, list]:
    """
    One-hot encode any non-numeric feature columns, scale numeric
    ones, and return the resulting numpy array plus the final
    column order (needed later to align a single prediction row).
    """
    X = df[feature_columns].copy()

    numeric_cols = X.select_dtypes(include="number").columns.tolist()
    categorical_cols = [c for c in feature_columns if c not in numeric_cols]

    if categorical_cols:
        X = pd.get_dummies(X, columns=categorical_cols, dummy_na=False)

    X = X.fillna(X.mean(numeric_only=True)).fillna(0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    return X_scaled, X.columns.tolist(), scaler


def compare_models(
    df: pd.DataFrame,
    target_column: str,
    feature_columns: list,
    task_type: str | None = None,
    test_size: float = 0.2,
) -> dict:
    """
    Trains every candidate model for the inferred/given task type,
    evaluates on a held-out split, and returns a results dict plus
    the fitted objects needed to persist the best model.
    """
    if target_column not in df.columns:
        raise MLEngineError(f"Target column '{target_column}' not found.")
    missing = [c for c in feature_columns if c not in df.columns]
    if missing:
        raise MLEngineError(f"Feature column(s) not found: {missing}")
    if target_column in feature_columns:
        raise MLEngineError("Target column cannot also be a feature column.")

    working = df.dropna(subset=[target_column]).copy()
    if working.empty:
        raise MLEngineError("No rows remain after dropping missing target values.")

    task_type = task_type or infer_task_type(working[target_column])

    X, feature_order, scaler = _prepare_features(working, feature_columns)

    y_encoder = None
    if task_type == "classification":
        y_encoder = LabelEncoder()
        y = y_encoder.fit_transform(working[target_column].astype(str))
    else:
        y = working[target_column].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42
    )

    candidates = REGRESSION_MODELS if task_type == "regression" else CLASSIFICATION_MODELS

    results = {}
    fitted_models = {}

    for name, model in candidates.items():
        # SVM training time grows steeply with row count — subsample
        # just for this model on low-CPU hosts to avoid a request timeout.
        if name in ("SVC", "SVR") and len(X_train) > _SVM_MAX_TRAIN_ROWS:
            rng = np.random.default_rng(42)
            idx = rng.choice(len(X_train), size=_SVM_MAX_TRAIN_ROWS, replace=False)
            fit_X, fit_y = X_train[idx], y_train[idx]
        else:
            fit_X, fit_y = X_train, y_train

        start = time.perf_counter()
        model.fit(fit_X, fit_y)
        elapsed = time.perf_counter() - start

        preds = model.predict(X_test)

        if task_type == "regression":
            score = r2_score(y_test, preds)
            metrics = {
                "r2": round(float(score), 4),
                "mae": round(float(mean_absolute_error(y_test, preds)), 4),
                "rmse": round(float(np.sqrt(mean_squared_error(y_test, preds))), 4),
            }
            primary_metric = "r2"
        else:
            score = accuracy_score(y_test, preds)
            metrics = {
                "accuracy": round(float(score), 4),
                "f1_weighted": round(float(f1_score(y_test, preds, average="weighted")), 4),
            }
            primary_metric = "accuracy"

        results[name] = {
            "metrics": metrics,
            "primary_metric": primary_metric,
            "primary_score": round(float(score), 4),
            "train_time_sec": round(elapsed, 4),
        }
        fitted_models[name] = model

    best_name = max(results, key=lambda n: results[n]["primary_score"])

    return {
        "task_type": task_type,
        "results": results,
        "best_model_name": best_name,
        "best_model": fitted_models[best_name],
        "all_models": fitted_models,
        "scaler": scaler,
        "y_encoder": y_encoder,
        "feature_order": feature_order,
    }


def save_model_bundle(path, models: dict, scaler, y_encoder, feature_order, feature_columns, best_model_name):
    """
    Bundle every trained candidate model (not just the best one) plus
    everything needed to reproduce predictions into one joblib file,
    so the frontend can let the user pick which model to predict with.
    """
    joblib.dump(
        {
            "models": models,  # {model_name: fitted_model}
            "scaler": scaler,
            "y_encoder": y_encoder,
            "feature_order": feature_order,
            "feature_columns": feature_columns,
            "best_model_name": best_model_name,
        },
        path,
    )


def predict_from_bundle(path, input_row: dict, model_name: str | None = None):
    """
    Load a saved bundle and predict on a single new input row
    (dict of feature_column -> raw value), using the given model_name
    from the bundle (falls back to that run's best model if omitted).
    """
    bundle = joblib.load(path)
    models = bundle["models"]

    if model_name is None:
        model_name = bundle.get("best_model_name") or next(iter(models))
    if model_name not in models:
        raise MLEngineError(
            f"Model '{model_name}' was not part of this comparison run. "
            f"Available: {list(models)}"
        )
    model = models[model_name]

    scaler = bundle["scaler"]
    y_encoder = bundle["y_encoder"]
    feature_order = bundle["feature_order"]
    feature_columns = bundle["feature_columns"]

    row_df = pd.DataFrame([{c: input_row.get(c) for c in feature_columns}])
    numeric_cols = row_df.select_dtypes(include="number").columns.tolist()
    categorical_cols = [c for c in feature_columns if c not in numeric_cols]
    if categorical_cols:
        row_df = pd.get_dummies(row_df, columns=categorical_cols, dummy_na=False)

    # Align columns to training-time order — any missing dummy columns become 0
    row_df = row_df.reindex(columns=feature_order, fill_value=0)
    row_df = row_df.fillna(0)

    X = scaler.transform(row_df)
    prediction = model.predict(X)[0]

    if y_encoder is not None:
        prediction = y_encoder.inverse_transform([int(prediction)])[0]

    return prediction