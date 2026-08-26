# Data Comparator

A Django + vanilla JS tool: upload a CSV/Excel file, clean it with pandas,
visualize it with Plotly, then train and compare several scikit-learn
supervised models and predict on new input.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py makemigrations comparator
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/

(Optional) create an admin user to inspect stored datasets/runs at `/admin/`:
```bash
python manage.py createsuperuser
```

## How it works

1. **Upload** (`/api/upload/`) — parses the file with pandas, stores the
   original upload plus a "working" copy as parquet (preserves dtypes
   across requests, unlike CSV).
2. **Clean** (`/api/datasets/<id>/clean/`) — applies one operation at a
   time (drop nulls, fill nulls, drop/rename column, encode categorical,
   scale numeric, cast dtype) to the working copy and logs it as a
   `CleaningStep`. `/reset/` restores the original upload.
3. **Visualize** (`/api/datasets/<id>/visualize/`) — builds a Plotly
   figure server-side (histogram, scatter, line, bar, box, correlation
   heatmap) and returns it as JSON for `Plotly.newPlot()` on the frontend.
4. **Compare models** (`/api/datasets/<id>/compare/`) — picks a target +
   feature columns, auto-detects regression vs. classification, trains
   4 candidate models per task type, and returns metrics for each plus
   the best one. The winning model (+ scaler + encoders) is serialized
   with joblib as a `ModelComparisonRun.best_model_file`.
5. **Predict** (`/api/runs/<run_id>/predict/`) — reloads that joblib
   bundle and predicts on a single new input row.

## Project layout

```
config/            Django project settings/urls
comparator/
  models.py         Dataset, CleaningStep, ModelComparisonRun
  views.py           JSON API endpoints
  urls.py
  admin.py
  services/
    parser.py         file → DataFrame, preview/metadata helpers
    cleaner.py         cleaning/transform operations
    visualizer.py      Plotly figure builders (cyan/purple dark theme)
    ml_engine.py        model training, comparison, predict-from-bundle
templates/comparator/index.html   single-page wizard UI
static/comparator/                CSS + vanilla JS
```

No DRF, no auth system — datasets are scoped to the browser session
(`request.session.session_key`), which keeps things simple since there's
no login requirement for this tool.
