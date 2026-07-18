import logging
import threading
import os
import tempfile

from django.utils import timezone

from .ai_service import classifier
from .models import Classification, ClassificationStatus, DiseaseCategory, LotStatus

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
def _download_to_tempfile(image_field) -> str:
    """
    Copia la imagen del storage (local o remoto) a un archivo temporal local
    y devuelve su ruta.

    Es necesario porque image.path solo existe en FileSystemStorage; en backends
    remotos como Google Cloud Storage / Firebase, acceder a .path lanza
    "This backend doesn't support absolute paths". El clasificador (PIL y/o
    gradio_client) necesita una ruta de archivo local legible.
    """
    suffix = os.path.splitext(image_field.name)[1] or '.jpg'
    image_field.open('rb')
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in image_field.chunks():
                tmp.write(chunk)
            return tmp.name
    finally:
        image_field.close()

def _update_lot_statistics(classification: Classification):
    """
    Recalcula las estadísticas del lote al que pertenece
    la clasificación.
    """
    if classification.lot is None:
        return

    lot = classification.lot
    lot.lot_status = LotStatus.IN_PROGRESS

    completed = lot.classifications.filter(
        status=ClassificationStatus.COMPLETED
    )

    lot.total_images = lot.classifications.count()

    lot.healthy_count = completed.filter(
        predicted_category=DiseaseCategory.SALUDABLE
    ).count()

    lot.anthracnose_count = completed.filter(
        predicted_category=DiseaseCategory.ANTRACNOSIS
    ).count()

    lot.scab_count = completed.filter(
        predicted_category=DiseaseCategory.SARNA
    ).count()

    if lot.total_images > 0 and completed.count() == lot.total_images:
        lot.lot_status = LotStatus.COMPLETED

    lot.save()

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

    tmp_path = None
    try:
        tmp_path = _download_to_tempfile(classification.image)
        result = classifier.predict(tmp_path)

        classification.predicted_category = result.predicted_category
        classification.confidence = result.confidence
        classification.raw_scores = result.raw_scores
        classification.status = ClassificationStatus.COMPLETED
        classification.classified_at = timezone.now()
        classification.save(update_fields=[
            "predicted_category", "confidence", "raw_scores",
            "status", "classified_at",
        ])
        _update_lot_statistics(classification)
        
    except Exception as exc:
        logger.exception("Error al clasificar imagen id=%s", classification_id)
        classification.status = ClassificationStatus.FAILED
        classification.error_message = str(exc)
        classification.save(update_fields=['status', 'error_message'])
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    _send_webhook(classification)
    return classification
