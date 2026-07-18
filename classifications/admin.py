from django.contrib import admin
from django.utils.html import format_html

from .models import Classification, ClassificationStatus

# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------


def reprocess_classifications(modeladmin, request, queryset):
    """Admin action to reprocess failed classifications."""
    from .services import run_classification

    failed = queryset.filter(status=ClassificationStatus.FAILED)
    count = 0
    for c in failed:
        try:
            run_classification(c.pk)
            count += 1
        except Exception:
            pass
    modeladmin.message_user(request, f"{count} clasificación(es) reprocesada(s).")


reprocess_classifications.short_description = "Reprocesar clasificaciones fallidas"


def delete_failed_classifications(modeladmin, request, queryset):
    deleted, _ = queryset.filter(status=ClassificationStatus.FAILED).delete()
    modeladmin.message_user(
        request, f"{deleted} clasificación(es) fallida(s) eliminada(s)."
    )


delete_failed_classifications.short_description = "Eliminar clasificaciones fallidas"


# ---------------------------------------------------------------------------
# Admin class
# ---------------------------------------------------------------------------


@admin.register(Classification)
class ClassificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_link",
        "status_badge",
        "predicted_category",
        "confidence_display",
        "created_at",
        "classified_at",
    )
    list_filter = ("status", "predicted_category")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    readonly_fields = (
        "raw_scores",
        "error_message",
        "created_at",
        "classified_at",
        "image_preview",
    )
    ordering = ("-created_at",)
    actions = [reprocess_classifications, delete_failed_classifications]
    date_hierarchy = "created_at"
    list_per_page = 25

    fieldsets = (
        (
            "Información general",
            {
                "fields": (
                    "user",
                    "image",
                    "image_preview",
                    "status",
                    "created_at",
                    "classified_at",
                ),
            },
        ),
        (
            "Resultado de la IA",
            {
                "fields": ("predicted_category", "confidence", "raw_scores"),
            },
        ),
        (
            "Errores",
            {
                "fields": ("error_message",),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Usuario", ordering="user__email")
    def user_link(self, obj):
        return format_html(
            '<a href="/admin/users/user/{}/change/">{}</a>',
            obj.user.pk,
            obj.user.email,
        )

    @admin.display(description="Estado")
    def status_badge(self, obj):
        colors = {
            "pending": "#f59e0b",
            "processing": "#3b82f6",
            "completed": "#10b981",
            "failed": "#ef4444",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Confianza")
    def confidence_display(self, obj):
        if obj.confidence is None:
            return "-"
        pct = obj.confidence * 100
        color = "#10b981" if pct >= 70 else "#f59e0b" if pct >= 50 else "#ef4444"
        return format_html(
            '<span style="color:{};font-weight:bold">{}%</span>',
            color,
            f"{pct:.1f}",
        )

    @admin.display(description="Vista previa")
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width:200px;max-height:200px;border-radius:8px" />',
                obj.image.url,
            )
        return "(sin imagen)"
