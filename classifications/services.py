import logging
import os
import tempfile

from django.utils import timezone

from .ai_service import classifier
from .models import Classification, ClassificationStatus

logger = logging.getLogger(__name__)


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


def run_classification(classification_id: int) -> Classification:
    """
    Ejecuta la clasificación para un registro existente.

    Actualiza el campo status en cada etapa para que el cliente
    pueda hacer polling o consultar el resultado después.
    """
    classification = Classification.objects.get(pk=classification_id)

    classification.status = ClassificationStatus.PROCESSING
    classification.save(update_fields=['status'])

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
            'predicted_category', 'confidence', 'raw_scores',
            'status', 'classified_at',
        ])
    except Exception as exc:
        logger.exception('Error al clasificar imagen id=%s', classification_id)
        classification.status = ClassificationStatus.FAILED
        classification.error_message = str(exc)
        classification.save(update_fields=['status', 'error_message'])
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return classification
