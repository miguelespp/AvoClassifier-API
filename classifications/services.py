import logging
import threading

from django.utils import timezone

from .ai_service import classifier
from .models import Classification, ClassificationStatus

logger = logging.getLogger(__name__)


def _send_webhook(classification: Classification) -> None:
    """Fires a POST to classification.webhook_url in a background thread. Best-effort."""
    if not classification.webhook_url:
        return

    import json
    import urllib.request

    payload = {
        "id": classification.pk,
        "status": classification.status,
        "predicted_category": classification.predicted_category,
        "confidence": classification.confidence,
        "classified_at": classification.classified_at.isoformat() if classification.classified_at else None,
    }
    data = json.dumps(payload).encode()

    def _post():
        try:
            req = urllib.request.Request(
                classification.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            logger.warning("Webhook falló para classification id=%s", classification.pk)

    threading.Thread(target=_post, daemon=True).start()


def run_classification(classification_id: int) -> Classification:
    """
    Ejecuta la clasificación para un registro existente.

    Actualiza el campo status en cada etapa para que el cliente
    pueda hacer polling o consultar el resultado después.
    Si el registro tiene webhook_url, envía un POST al finalizar.
    """
    classification = Classification.objects.get(pk=classification_id)

    classification.status = ClassificationStatus.PROCESSING
    classification.save(update_fields=["status"])

    try:
        result = classifier.predict(classification.image.path)

        classification.predicted_category = result.predicted_category
        classification.confidence = result.confidence
        classification.raw_scores = result.raw_scores
        classification.status = ClassificationStatus.COMPLETED
        classification.classified_at = timezone.now()
        classification.save(update_fields=[
            "predicted_category", "confidence", "raw_scores",
            "status", "classified_at",
        ])
    except Exception as exc:
        logger.exception("Error al clasificar imagen id=%s", classification_id)
        classification.status = ClassificationStatus.FAILED
        classification.error_message = str(exc)
        classification.save(update_fields=["status", "error_message"])

    _send_webhook(classification)
    return classification
