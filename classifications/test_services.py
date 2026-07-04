"""
Unit tests for run_classification() and AvocadoClassifierService.
These tests mock the AI model so they don't require Keras/TensorFlow.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model

from .ai_service import CATEGORIES, AvocadoClassifierService, ClassificationResult, _UNAVAILABLE
from .models import Classification, ClassificationStatus
from .services import run_classification

User = get_user_model()


# ───────────────────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────────────────


@pytest.fixture
def user(db):
    return User.objects.create_user(email="svc@example.com", password="testpass123")


@pytest.fixture
def pending_classification(user):
    return Classification.objects.create(
        user=user,
        image="classifications/test.jpg",
        status=ClassificationStatus.PENDING,
    )


@pytest.fixture
def fresh_classifier():
    """Returns a new AvocadoClassifierService instance bypassing the singleton."""
    svc = object.__new__(AvocadoClassifierService)
    svc._model = None
    return svc


# ───────────────────────────────────────────────────────────────────
# run_classification service
# ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_run_classification_sets_completed(pending_classification):
    mock_result = ClassificationResult(
        predicted_category="saludable",
        confidence=0.95,
        raw_scores={"saludable": 0.95, "antracnosis": 0.03, "sarna": 0.02},
    )
    with patch("classifications.services._download_to_tempfile", return_value="/tmp/fake.jpg"):
        with patch("classifications.services.classifier.predict", return_value=mock_result):
            result = run_classification(pending_classification.pk)

    assert result.status == ClassificationStatus.COMPLETED
    assert result.predicted_category == "saludable"
    assert result.confidence == 0.95
    assert result.raw_scores == mock_result.raw_scores


@pytest.mark.django_db
def test_run_classification_saves_to_db(pending_classification):
    mock_result = ClassificationResult(
        predicted_category="antracnosis",
        confidence=0.80,
        raw_scores={"saludable": 0.10, "antracnosis": 0.80, "sarna": 0.10},
    )
    with patch("classifications.services._download_to_tempfile", return_value="/tmp/fake.jpg"):
        with patch("classifications.services.classifier.predict", return_value=mock_result):
            run_classification(pending_classification.pk)

    refreshed = Classification.objects.get(pk=pending_classification.pk)
    assert refreshed.status == ClassificationStatus.COMPLETED
    assert refreshed.predicted_category == "antracnosis"
    assert refreshed.classified_at is not None


@pytest.mark.django_db
def test_run_classification_sets_failed_on_predict_error(pending_classification):
    with patch("classifications.services._download_to_tempfile", return_value="/tmp/fake.jpg"):
        with patch(
            "classifications.services.classifier.predict",
            side_effect=RuntimeError("model crashed"),
        ):
            result = run_classification(pending_classification.pk)

    assert result.status == ClassificationStatus.FAILED
    assert "model crashed" in result.error_message


@pytest.mark.django_db
def test_run_classification_sets_failed_on_download_error(pending_classification):
    with patch(
        "classifications.services._download_to_tempfile",
        side_effect=IOError("storage unavailable"),
    ):
        result = run_classification(pending_classification.pk)

    assert result.status == ClassificationStatus.FAILED
    assert "storage unavailable" in result.error_message


@pytest.mark.django_db
def test_run_classification_cleans_up_temp_file(pending_classification):
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp_path = f.name

    mock_result = ClassificationResult(
        predicted_category="saludable",
        confidence=0.90,
        raw_scores={"saludable": 0.90, "antracnosis": 0.05, "sarna": 0.05},
    )
    with patch("classifications.services._download_to_tempfile", return_value=tmp_path):
        with patch("classifications.services.classifier.predict", return_value=mock_result):
            run_classification(pending_classification.pk)

    assert not os.path.exists(tmp_path)


# ───────────────────────────────────────────────────────────────────
# AvocadoClassifierService — model_status and state
# ───────────────────────────────────────────────────────────────────


def test_model_status_none(fresh_classifier):
    assert fresh_classifier.model_status["backend"] == "none"
    assert fresh_classifier.model_status["loaded"] is False
    assert fresh_classifier.model_status["categories"] == CATEGORIES


def test_model_status_heuristic(fresh_classifier):
    fresh_classifier._model = _UNAVAILABLE
    assert fresh_classifier.model_status["backend"] == "heuristic"
    assert fresh_classifier.model_status["loaded"] is False


def test_model_status_keras(fresh_classifier):
    fresh_classifier._model = MagicMock()
    assert fresh_classifier.model_status["backend"] == "keras"
    assert fresh_classifier.model_status["loaded"] is True


def test_is_model_loaded_false_when_none(fresh_classifier):
    assert fresh_classifier.is_model_loaded is False


def test_is_model_loaded_false_when_unavailable(fresh_classifier):
    fresh_classifier._model = _UNAVAILABLE
    assert fresh_classifier.is_model_loaded is False


def test_is_model_loaded_true_when_keras(fresh_classifier):
    fresh_classifier._model = MagicMock()
    assert fresh_classifier.is_model_loaded is True


def test_reload_resets_and_calls_load(fresh_classifier):
    fresh_classifier._model = MagicMock()
    with patch.object(fresh_classifier, "load") as mock_load:
        fresh_classifier.reload()

    assert fresh_classifier._model is None
    mock_load.assert_called_once()


def test_load_skips_if_already_loaded(fresh_classifier):
    fake_model = MagicMock()
    fresh_classifier._model = fake_model
    with patch.object(fresh_classifier, "_load_model") as mock_load_model:
        fresh_classifier.load()

    mock_load_model.assert_not_called()
    assert fresh_classifier._model is fake_model


# ───────────────────────────────────────────────────────────────────
# AvocadoClassifierService — predict
# ───────────────────────────────────────────────────────────────────


def test_predict_uses_highest_score_category(fresh_classifier):
    fresh_classifier._model = MagicMock()
    # antracnosis=0.1, sarna=0.2, saludable=0.7 → winner: saludable (index 2)
    mock_scores = [0.1, 0.2, 0.7]

    with patch.object(fresh_classifier, "_preprocess", return_value=MagicMock()):
        with patch.object(fresh_classifier, "_run_inference", return_value=mock_scores):
            result = fresh_classifier.predict("/tmp/fake.jpg")

    assert isinstance(result, ClassificationResult)
    assert result.predicted_category == "saludable"
    assert result.confidence == 0.7
    assert set(result.raw_scores.keys()) == set(CATEGORIES)


def test_predict_antracnosis_wins(fresh_classifier):
    fresh_classifier._model = MagicMock()
    mock_scores = [0.85, 0.10, 0.05]  # antracnosis wins

    with patch.object(fresh_classifier, "_preprocess", return_value=MagicMock()):
        with patch.object(fresh_classifier, "_run_inference", return_value=mock_scores):
            result = fresh_classifier.predict("/tmp/fake.jpg")

    assert result.predicted_category == "antracnosis"
    assert result.confidence == 0.85


# ───────────────────────────────────────────────────────────────────
# AvocadoClassifierService — _resolve_model_dir
# ───────────────────────────────────────────────────────────────────


def test_resolve_model_dir_finds_config_json(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    result = AvocadoClassifierService._resolve_model_dir(tmp_path)
    assert result == tmp_path


def test_resolve_model_dir_finds_keras_subdir(tmp_path):
    keras_dir = tmp_path / "model.keras"
    keras_dir.mkdir()
    (keras_dir / "config.json").write_text("{}")
    result = AvocadoClassifierService._resolve_model_dir(tmp_path)
    assert result == keras_dir


def test_resolve_model_dir_raises_when_empty(tmp_path):
    with pytest.raises(FileNotFoundError, match="No se encontró"):
        AvocadoClassifierService._resolve_model_dir(tmp_path)
