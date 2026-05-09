from django.contrib import admin

from .models import Classification


@admin.register(Classification)
class ClassificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'predicted_category', 'confidence', 'created_at')
    list_filter = ('status', 'predicted_category')
    search_fields = ('user__email',)
    readonly_fields = ('raw_scores', 'error_message', 'created_at', 'classified_at')
    ordering = ('-created_at',)
