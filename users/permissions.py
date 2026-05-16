"""Custom DRF permissions for AvoClassifier."""

from rest_framework.permissions import (  # noqa: F401 (re-export)
    BasePermission,
    IsAdminUser,
)


class IsAdminOrStaff(BasePermission):
    """Allows access only to admin users (is_staff=True or is_superuser=True)."""

    message = "Se requieren permisos de administrador."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )
