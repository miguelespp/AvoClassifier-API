from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AdminUserChangePasswordView,
    AdminUserDetailView,
    AdminUserListView,
    AdminUserToggleActiveView,
    ChangePasswordView,
    LoginView,
    ProfileView,
    RegisterView,
)

urlpatterns = [
    # Auth
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("change-password/", ChangePasswordView.as_view(), name="change_password"),
    # Admin - Users
    path("admin/users/", AdminUserListView.as_view(), name="admin_user_list"),
    path(
        "admin/users/<int:pk>/", AdminUserDetailView.as_view(), name="admin_user_detail"
    ),
    path(
        "admin/users/<int:pk>/toggle-active/",
        AdminUserToggleActiveView.as_view(),
        name="admin_user_toggle_active",
    ),
    path(
        "admin/users/<int:pk>/change-password/",
        AdminUserChangePasswordView.as_view(),
        name="admin_user_change_password",
    ),
]
