from django.urls import path

from .views import (
    AdminClassificationDetailView,
    AdminClassificationListView,
    AdminDashboardStatsView,
    AdminModelReloadView,
    ClassificationCreateView,
    ClassificationDetailView,
    ClassificationListView,
)

urlpatterns = [
    # User endpoints
    path("", ClassificationCreateView.as_view(), name="classification_create"),
    path("history/", ClassificationListView.as_view(), name="classification_list"),
    path("<int:pk>/", ClassificationDetailView.as_view(), name="classification_detail"),
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
