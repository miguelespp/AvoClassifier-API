from celery import shared_task

from .services import run_classification


@shared_task
def classify_image_task(classification_id: int) -> None:
    """Runs model inference for a Classification record asynchronously."""
    run_classification(classification_id)
