from django.urls import path

from .views import ClassificationCreateView, ClassificationDetailView, ClassificationListView

urlpatterns = [
    path('', ClassificationCreateView.as_view(), name='classification_create'),
    path('history/', ClassificationListView.as_view(), name='classification_list'),
    path('<int:pk>/', ClassificationDetailView.as_view(), name='classification_detail'),
]
