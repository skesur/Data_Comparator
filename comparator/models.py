from django.db import models


class Dataset(models.Model):
    """
    One uploaded CSV/Excel file. Tracked by browser session, not by
    logged-in user — there's no auth requirement for this tool.

    `working_file` always points at the CURRENT state of the data
    (original on upload, then overwritten in place each time a
    cleaning operation is applied), stored as parquet for fast,
    dtype-preserving reads. `original_file` is kept untouched so the
    user can always reset back to the raw upload.
    """

    session_key = models.CharField(max_length=40, db_index=True)
    original_filename = models.CharField(max_length=255)
    original_file = models.FileField(upload_to="datasets/originals/")
    working_file = models.FileField(upload_to="datasets/working/", blank=True)

    row_count = models.PositiveIntegerField(default=0)
    column_count = models.PositiveIntegerField(default=0)
    columns_meta = models.JSONField(default=dict, blank=True)
    # columns_meta shape: {"col_name": {"dtype": "float64", "nulls": 3,
    #                                    "unique": 120, "sample": [...]}}

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.session_key[:8]})"


class CleaningStep(models.Model):
    """
    Audit trail of every transformation applied to a dataset, in
    order. Lets the frontend show a history list and lets us rebuild
    the pipeline if we ever need to replay it on fresh data.
    """

    OPERATION_CHOICES = [
        ("drop_nulls", "Drop rows with nulls"),
        ("fill_nulls", "Fill nulls"),
        ("drop_column", "Drop column"),
        ("encode_categorical", "Encode categorical column"),
        ("scale_numeric", "Scale numeric column"),
        ("rename_column", "Rename column"),
        ("cast_dtype", "Cast column dtype"),
    ]

    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="steps")
    operation = models.CharField(max_length=30, choices=OPERATION_CHOICES)
    params = models.JSONField(default=dict, blank=True)
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["applied_at"]

    def __str__(self):
        return f"{self.operation} on dataset {self.dataset_id}"


class ModelComparisonRun(models.Model):
    """
    One 'train several models and compare them' run against a
    dataset for a chosen target column. Stores metrics for every
    model tried plus a pointer to the best model's serialized file
    so it can be reloaded for on-demand prediction later.
    """

    TASK_CHOICES = [
        ("regression", "Regression"),
        ("classification", "Classification"),
    ]

    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="comparison_runs")
    target_column = models.CharField(max_length=255)
    feature_columns = models.JSONField(default=list)
    task_type = models.CharField(max_length=20, choices=TASK_CHOICES)

    results = models.JSONField(default=dict, blank=True)
    # results shape: {"RandomForest": {"score": 0.91, "metric": "r2",
    #                                    "train_time_sec": 0.42}, ...}

    best_model_name = models.CharField(max_length=100, blank=True)
    best_model_file = models.FileField(upload_to="models_saved/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task_type} run on {self.target_column} ({self.dataset_id})"
