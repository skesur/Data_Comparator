from django.urls import path

from . import views

app_name = "comparator"

urlpatterns = [
    path("", views.index, name="index"),

    path("api/upload/", views.upload_dataset, name="upload_dataset"),
    path("api/datasets/<int:dataset_id>/", views.dataset_detail, name="dataset_detail"),
    path("api/datasets/<int:dataset_id>/full/", views.dataset_full, name="dataset_full"),
    path("api/datasets/<int:dataset_id>/download/", views.download_dataset_csv, name="download_dataset_csv"),
    path("api/datasets/<int:dataset_id>/clean/", views.clean_dataset, name="clean_dataset"),
    path("api/datasets/<int:dataset_id>/reset/", views.reset_dataset, name="reset_dataset"),
    path("api/datasets/<int:dataset_id>/visualize/", views.visualize, name="visualize"),
    path("api/datasets/<int:dataset_id>/compare/", views.compare_models_view, name="compare_models"),
    path("api/runs/<int:run_id>/predict/", views.predict_view, name="predict"),
]
