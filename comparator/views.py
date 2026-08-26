import json
import os
import tempfile

import pandas as pd
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import CleaningStep, Dataset, ModelComparisonRun
from .services import cleaner, ml_engine, parser, visualizer


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

def _get_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _load_working_df(dataset: Dataset) -> pd.DataFrame:
    dataset.working_file.open("rb")
    try:
        df = pd.read_parquet(dataset.working_file)
    finally:
        dataset.working_file.close()
    return df


def _save_working_df(dataset: Dataset, df: pd.DataFrame):
    """Overwrite the dataset's working parquet file with a new DataFrame state."""
    buffer_path = os.path.join(tempfile.gettempdir(), f"dataset_{dataset.id}_working.parquet")
    df.to_parquet(buffer_path, index=False)

    with open(buffer_path, "rb") as f:
        content = ContentFile(f.read())
        # Delete old file before saving new one under the same name pattern
        if dataset.working_file:
            dataset.working_file.delete(save=False)
        dataset.working_file.save(f"dataset_{dataset.id}.parquet", content, save=False)

    os.remove(buffer_path)

    dataset.row_count = len(df)
    dataset.column_count = len(df.columns)
    dataset.columns_meta = parser.build_columns_meta(df)
    dataset.save()


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


# --------------------------------------------------------------------
# Page
# --------------------------------------------------------------------

@require_GET
def index(request):
    return render(request, "comparator/index.html")


# --------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------

@csrf_exempt
@require_POST
def upload_dataset(request):
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return _json_error("No file was provided.")

    try:
        df = parser.read_uploaded_file(uploaded_file)
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f"Could not parse file: {exc}")

    if df.empty:
        return _json_error("The uploaded file has no rows.")

    session_key = _get_session_key(request)

    dataset = Dataset.objects.create(
        session_key=session_key,
        original_filename=uploaded_file.name,
        original_file=uploaded_file,
    )

    # Reset file pointer isn't needed again — we already parsed df above
    _save_working_df(dataset, df)

    return JsonResponse({
        "ok": True,
        "dataset_id": dataset.id,
        "filename": dataset.original_filename,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "columns_meta": dataset.columns_meta,
        "preview": parser.dataframe_preview(df),
    })


# --------------------------------------------------------------------
# Preview / metadata
# --------------------------------------------------------------------

@require_GET
def dataset_detail(request, dataset_id):
    dataset = get_object_or_404(Dataset, id=dataset_id, session_key=_get_session_key(request))
    df = _load_working_df(dataset)

    return JsonResponse({
        "ok": True,
        "dataset_id": dataset.id,
        "filename": dataset.original_filename,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "columns_meta": dataset.columns_meta,
        "preview": parser.dataframe_preview(df),
        "steps": list(dataset.steps.values("operation", "params", "applied_at")),
    })


@require_GET
def dataset_full(request, dataset_id):
    """Return up to MAX_FULL_VIEW_ROWS rows for the 'view all rows' button."""
    dataset = get_object_or_404(Dataset, id=dataset_id, session_key=_get_session_key(request))
    df = _load_working_df(dataset)
    full = parser.dataframe_full(df)
    return JsonResponse({"ok": True, **full})


@require_GET
def download_dataset_csv(request, dataset_id):
    """Download the dataset's current (possibly cleaned) state as a CSV file."""
    dataset = get_object_or_404(Dataset, id=dataset_id, session_key=_get_session_key(request))
    df = _load_working_df(dataset)

    base_name = os.path.splitext(dataset.original_filename or "dataset")[0]
    filename = f"{base_name}_cleaned.csv"

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    df.to_csv(response, index=False)
    return response


# --------------------------------------------------------------------
# Cleaning
# --------------------------------------------------------------------

@csrf_exempt
@require_POST
def clean_dataset(request, dataset_id):
    dataset = get_object_or_404(Dataset, id=dataset_id, session_key=_get_session_key(request))

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body.")

    operation = payload.get("operation")
    params = payload.get("params", {})

    if not operation:
        return _json_error("'operation' is required.")

    df = _load_working_df(dataset)

    try:
        new_df = cleaner.apply_operation(df, operation, params)
    except cleaner.CleaningError as exc:
        return _json_error(str(exc))

    _save_working_df(dataset, new_df)
    CleaningStep.objects.create(dataset=dataset, operation=operation, params=params)

    return JsonResponse({
        "ok": True,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "columns_meta": dataset.columns_meta,
        "preview": parser.dataframe_preview(new_df),
    })


@csrf_exempt
@require_POST
def reset_dataset(request, dataset_id):
    """Discard all cleaning steps and restore the original uploaded file."""
    dataset = get_object_or_404(Dataset, id=dataset_id, session_key=_get_session_key(request))

    try:
        df = parser.read_uploaded_file(dataset.original_file)
    except Exception as exc:
        return _json_error(f"Could not reload original file: {exc}")

    _save_working_df(dataset, df)
    dataset.steps.all().delete()

    return JsonResponse({
        "ok": True,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "columns_meta": dataset.columns_meta,
        "preview": parser.dataframe_preview(df),
    })


# --------------------------------------------------------------------
# Visualization
# --------------------------------------------------------------------

@csrf_exempt
@require_POST
def visualize(request, dataset_id):
    dataset = get_object_or_404(Dataset, id=dataset_id, session_key=_get_session_key(request))

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body.")

    chart_type = payload.get("chart_type")
    builder = visualizer.CHART_BUILDERS.get(chart_type)
    if not builder:
        return _json_error(f"Unknown chart_type '{chart_type}'. Choose from {list(visualizer.CHART_BUILDERS)}.")

    df = _load_working_df(dataset)

    # Build kwargs from payload, excluding chart_type itself
    kwargs = {k: v for k, v in payload.items() if k != "chart_type"}

    try:
        figure_json = builder(df, **kwargs)
    except visualizer.VisualizationError as exc:
        return _json_error(str(exc))
    except TypeError as exc:
        return _json_error(f"Missing or invalid parameters for '{chart_type}': {exc}")

    return JsonResponse({"ok": True, "figure": json.loads(figure_json)})


# --------------------------------------------------------------------
# ML: compare models
# --------------------------------------------------------------------

@csrf_exempt
@require_POST
def compare_models_view(request, dataset_id):
    dataset = get_object_or_404(Dataset, id=dataset_id, session_key=_get_session_key(request))

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body.")

    target_column = payload.get("target_column")
    feature_columns = payload.get("feature_columns", [])
    task_type = payload.get("task_type")  # optional override

    if not target_column or not feature_columns:
        return _json_error("'target_column' and 'feature_columns' are required.")

    df = _load_working_df(dataset)

    try:
        outcome = ml_engine.compare_models(df, target_column, feature_columns, task_type)
    except ml_engine.MLEngineError as exc:
        return _json_error(str(exc))

    run = ModelComparisonRun.objects.create(
        dataset=dataset,
        target_column=target_column,
        feature_columns=feature_columns,
        task_type=outcome["task_type"],
        results=outcome["results"],
        best_model_name=outcome["best_model_name"],
    )

    # Persist bundles for ALL trained candidate models (not just the best
    # one), so the Predict panel can let the user choose which to use.
    bundle_path = os.path.join(tempfile.gettempdir(), f"model_bundle_{run.id}.joblib")
    ml_engine.save_model_bundle(
        bundle_path,
        outcome["all_models"],
        outcome["scaler"],
        outcome["y_encoder"],
        outcome["feature_order"],
        feature_columns,
        outcome["best_model_name"],
    )
    with open(bundle_path, "rb") as f:
        run.best_model_file.save(f"run_{run.id}.joblib", ContentFile(f.read()), save=True)
    os.remove(bundle_path)

    return JsonResponse({
        "ok": True,
        "run_id": run.id,
        "task_type": run.task_type,
        "results": run.results,
        "best_model_name": run.best_model_name,
    })


# --------------------------------------------------------------------
# ML: predict with a saved run's chosen model
# --------------------------------------------------------------------

@csrf_exempt
@require_POST
def predict_view(request, run_id):
    run = get_object_or_404(ModelComparisonRun, id=run_id, dataset__session_key=_get_session_key(request))

    if not run.best_model_file:
        return _json_error("No trained model is stored for this run.")

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body.")

    input_row = payload.get("input", {})
    model_name = payload.get("model_name")  # optional — defaults to the run's best model
    missing = [c for c in run.feature_columns if c not in input_row]
    if missing:
        return _json_error(f"Missing input value(s) for: {missing}")

    try:
        prediction = ml_engine.predict_from_bundle(run.best_model_file.path, input_row, model_name)
    except ml_engine.MLEngineError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f"Prediction failed: {exc}")

    if hasattr(prediction, "item"):
        prediction = prediction.item()

    return JsonResponse({
        "ok": True,
        "prediction": prediction,
        "model_used": model_name or run.best_model_name,
    })