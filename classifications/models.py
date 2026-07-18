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



class LotStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "En proceso"
    COMPLETED = "completed", "Completado"



class Lot(models.Model):
    """
    Agrupa múltiples clasificaciones realizadas en una misma sesión
    de análisis por lote.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lots",
    )

    # Información del lote
    lot_name = models.CharField(
        max_length=100,
        verbose_name="Nombre del lote",
    )

    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Descripción",
    )

    # Estado del lote
    lot_status = models.CharField(
        max_length=20,
        choices=LotStatus.choices,
        default=LotStatus.IN_PROGRESS,
        verbose_name="Estado del lote",
    )
    
    # Cantidad total de imágenes del lote
    total_images = models.PositiveIntegerField(
        default=0
    )
    
    # Resumen estadístico del lote
    healthy_count = models.PositiveIntegerField(default=0)
    anthracnose_count = models.PositiveIntegerField(default=0)
    scab_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lote"
        verbose_name_plural = "Lotes"
        
        constraints = [
            models.UniqueConstraint(
                fields=["user", "lot_name"],
                name="unique_lot_per_user",
            )
        ]
        
    def __str__(self):
        return self.lot_name



class Classification(models.Model):
    """
    Representa el resultado del análisis de una imagen individual.
    Puede pertenecer a un lote o ser un análisis independiente.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="classifications",
    )
    
    lot = models.ForeignKey(
        "Lot",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="classifications",
    )
    
    # Imagen a analizar
    image = models.ImageField(upload_to="classifications/%Y/%m/%d/")
    
    # Resultado de la IA
    status = models.CharField(
        max_length=20,
        choices=ClassificationStatus.choices,
        default=ClassificationStatus.PENDING,
    )
    
    predicted_category = models.CharField(
        max_length=30,
        choices=DiseaseCategory.choices,
        blank=True,
    )
    confidence = models.FloatField(null=True, blank=True)
    raw_scores = models.JSONField(null=True, blank=True)

     # Información del árbol inspeccionado donde se identifica el fruto (solo si existe enfermedad)
    tree_code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Código del árbol",
    )

    north_coordinate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coordenada Norte (m)",
    )

    east_coordinate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coordenada Este (m)",
    )    
    
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
        



