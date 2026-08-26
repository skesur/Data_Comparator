from django.contrib import admin

from .models import CleaningStep, Dataset, ModelComparisonRun


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("id", "original_filename", "row_count", "column_count", "session_key", "created_at")
    list_filter = ("created_at",)
    search_fields = ("original_filename", "session_key")
    readonly_fields = ("columns_meta", "row_count", "column_count", "created_at", "updated_at")


@admin.register(CleaningStep)
class CleaningStepAdmin(admin.ModelAdmin):
    list_display = ("id", "dataset", "operation", "applied_at")
    list_filter = ("operation",)


@admin.register(ModelComparisonRun)
class ModelComparisonRunAdmin(admin.ModelAdmin):
    list_display = ("id", "dataset", "target_column", "task_type", "best_model_name", "created_at")
    list_filter = ("task_type",)
    readonly_fields = ("results",)
