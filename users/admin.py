from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import (
    format_html,  # noqa: F401 — available for future custom columns
)

from .models import User

# ---------------------------------------------------------------------------
# Computed column
# ---------------------------------------------------------------------------


def _classification_count(obj):
    return obj.classifications.count()


_classification_count.short_description = "Clasificaciones"


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------


def activate_users(modeladmin, request, queryset):
    queryset.update(is_active=True)
    modeladmin.message_user(request, f"{queryset.count()} usuario(s) activado(s).")


activate_users.short_description = "Activar usuarios seleccionados"


def deactivate_users(modeladmin, request, queryset):
    queryset.exclude(pk=request.user.pk).update(is_active=False)
    modeladmin.message_user(request, "Usuarios desactivados (excepto el tuyo).")


deactivate_users.short_description = "Desactivar usuarios seleccionados"


def make_staff(modeladmin, request, queryset):
    queryset.update(is_staff=True)
    modeladmin.message_user(request, f"{queryset.count()} usuario(s) ahora son staff.")


make_staff.short_description = "Otorgar permisos de staff"


def remove_staff(modeladmin, request, queryset):
    queryset.exclude(pk=request.user.pk).update(is_staff=False)
    modeladmin.message_user(request, "Permisos de staff removidos.")


remove_staff.short_description = "Remover permisos de staff"


# ---------------------------------------------------------------------------
# Admin class
# ---------------------------------------------------------------------------


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_active_badge",
        "is_staff",
        "is_superuser",
        _classification_count,
        "created_at",
    )
    list_display_links = ("email",)
    list_filter = ("is_staff", "is_active", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("-created_at",)
    actions = [activate_users, deactivate_users, make_staff, remove_staff]
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Información personal", {"fields": ("first_name", "last_name")}),
        (
            "Permisos",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Fechas",
            {
                "fields": ("last_login", "created_at"),
                "classes": ("collapse",),
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                    "is_staff",
                ),
            },
        ),
    )

    @admin.display(description="Activo", boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active
