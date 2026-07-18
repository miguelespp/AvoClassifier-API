from django.urls import path

from .views import (
    AdminClassificationDetailView,
    AdminClassificationListView,
    AdminDashboardStatsView,
    AdminModelReloadView,
    ClassificationCreateView,
    ClassificationDetailView,
    ClassificationExportCSVView,
    ClassificationListView,
    ClassificationBulkCreateView,
    LotDetailView,
    LotListCreateView,
    UserStatsView,
)

urlpatterns = [
    
    # User endpoints
    path("", ClassificationCreateView.as_view(), name="classification_create"),
    path("history/", ClassificationListView.as_view(), name="classification_list"),
    path("stats/", UserStatsView.as_view(), name="user_stats"),
    path("history/export/", ClassificationExportCSVView.as_view(), name="classification_export_csv"),
    path("<int:pk>/", ClassificationDetailView.as_view(), name="classification_detail"),
    path("lots/", LotListCreateView.as_view(), name="lot_list_create"), # Lotes ---> POST (para crear) y GET (para listar): http://127.0.0.1:8000/api/classifications/lots/
    path("lots/<int:pk>/", LotDetailView.as_view(), name="lot_detail"), # Detalle de lote
    path("bulk/", ClassificationBulkCreateView.as_view(), name="classification_bulk_create"), # Carga masiva de imágenes asociadas a un lote
    
    # Admin endpoints
    path(
        "admin/all/",
        AdminClassificationListView.as_view(),
        name="admin_classification_list",
    ),
    path(
        "admin/all/<int:pk>/",
        AdminClassificationDetailView.as_view(),
        name="admin_classification_detail",
    ),
    path("admin/stats/", AdminDashboardStatsView.as_view(), name="admin_stats"),
    path(
        "admin/model/reload/", AdminModelReloadView.as_view(), name="admin_model_reload"
    ),
]
