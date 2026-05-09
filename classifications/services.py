import logging
from django.utils import timezone

from .ai_service import classifier
from .models import Classification, ClassificationStatus

logger = logging.getLogger(__name__)


def run_classification(classification_id: int) -> Classification:
    """
    Ejecuta la clasificación para un registro existente.

    Actualiza el campo status en cada etapa para que el cliente
    pueda hacer polling o consultar el resultado después.
    """
    classification = Classification.objects.get(pk=classification_id)

    classification.status = ClassificationStatus.PROCESSING
    classification.save(update_fields=['status'])

    try:
        result = classifier.predict(classification.image.path)

        classification.predicted_category = result.predicted_category
        classification.confidence = result.confidence
        classification.raw_scores = result.raw_scores
        classification.status = ClassificationStatus.COMPLETED
        classification.classified_at = timezone.now()
        classification.save(update_fields=[
            'predicted_category', 'confidence', 'raw_scores',
            'status', 'classified_at',
        ])
    except Exception as exc:
        logger.exception('Error al clasificar imagen id=%s', classification_id)
        classification.status = ClassificationStatus.FAILED
        classification.error_message = str(exc)
        classification.save(update_fields=['status', 'error_message'])

    return classification
