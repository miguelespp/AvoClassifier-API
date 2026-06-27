from django.conf import settings
from django.db import models
from django.utils import timezone


class DiseaseCategory(models.TextChoices):
    SALUDABLE = "saludable", "Saludable"
    ANTRACNOSIS = "antracnosis", "Antracnosis"
    SARNA = "sarna", "Sarna"


class ClassificationStatus(models.TextChoices):
    PENDING = "pending", "Pendiente"
    PROCESSING = "processing", "Procesando"
    COMPLETED = "completed", "Completado"
    FAILED = "failed", "Fallido"


class ClassificationManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def with_deleted(self):
        return super().get_queryset()

    def deleted(self):
        return super().get_queryset().filter(deleted_at__isnull=False)


class Classification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="classifications",
    )
    image = models.ImageField(upload_to="classifications/%Y/%m/%d/")
    status = models.CharField(
        max_length=20,
        choices=ClassificationStatus.choices,
        default=ClassificationStatus.PENDING,
    )

    # Resultado de la IA
    predicted_category = models.CharField(
        max_length=30,
        choices=DiseaseCategory.choices,
        blank=True,
    )
    confidence = models.FloatField(null=True, blank=True)
    raw_scores = models.JSONField(null=True, blank=True)

    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    classified_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Webhook para notificación async (opcional)
    webhook_url = models.URLField(blank=True)

    objects = ClassificationManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Classification {self.pk} - {self.user.email} [{self.status}]"

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])
