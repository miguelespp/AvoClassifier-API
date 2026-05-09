"""
Capa de servicio para el modelo de clasificación de enfermedades en palta.

Para integrar el modelo real:
  1. Implementar _load_model() con la carga del modelo (torch, tensorflow, etc.)
  2. Implementar _preprocess(image_path) con el preprocesamiento requerido
  3. Implementar _run_inference(tensor) con la inferencia
  4. Ajustar CATEGORIES con los nombres reales de las 3 clases

El resto del flujo (guardar resultado, manejar errores, actualizar status) ya está listo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# TODO: reemplazar con los nombres reales de las 3 categorías de enfermedad
CATEGORIES: list[str] = ['category_a', 'category_b', 'category_c']


@dataclass
class ClassificationResult:
    predicted_category: str
    confidence: float          # score de la categoría ganadora (0.0 - 1.0)
    raw_scores: dict[str, float]  # score por cada categoría


class AvocadoClassifierService:
    """
    Wrapper del modelo de IA. Mantiene el modelo en memoria entre llamadas.
    Instanciar una sola vez (singleton) para evitar recargas.
    """

    _instance: Optional['AvocadoClassifierService'] = None
    _model = None

    def __new__(cls) -> 'AvocadoClassifierService':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self) -> None:
        """Carga el modelo en memoria. Llamar al iniciar la aplicación (AppConfig.ready)."""
        if self._model is not None:
            return
        logger.info('Cargando modelo de clasificación de palta...')
        self._model = self._load_model()
        logger.info('Modelo cargado correctamente.')

    # ------------------------------------------------------------------
    # Método principal
    # ------------------------------------------------------------------

    def predict(self, image_path: str) -> ClassificationResult:
        """
        Clasifica una imagen y devuelve el resultado.

        Args:
            image_path: Ruta absoluta al archivo de imagen en disco.

        Returns:
            ClassificationResult con la categoría predicha y los scores.

        Raises:
            RuntimeError: Si el modelo no fue cargado o la inferencia falla.
        """
        if self._model is None:
            raise RuntimeError('El modelo no está cargado. Llamar a load() primero.')

        tensor = self._preprocess(image_path)
        scores = self._run_inference(tensor)

        predicted_idx = scores.index(max(scores))
        raw_scores = dict(zip(CATEGORIES, scores))

        return ClassificationResult(
            predicted_category=CATEGORIES[predicted_idx],
            confidence=scores[predicted_idx],
            raw_scores=raw_scores,
        )

    # ------------------------------------------------------------------
    # Métodos a implementar cuando llegue el modelo real
    # ------------------------------------------------------------------

    def _load_model(self):
        # TODO: cargar pesos del modelo
        # Ejemplo PyTorch:
        #   import torch
        #   model = MyModelClass()
        #   model.load_state_dict(torch.load(settings.AI_MODEL_PATH))
        #   model.eval()
        #   return model
        raise NotImplementedError('Implementar _load_model con el modelo real.')

    def _preprocess(self, image_path: str):
        # TODO: aplicar transformaciones requeridas por el modelo
        # Ejemplo:
        #   from PIL import Image
        #   import torchvision.transforms as T
        #   transform = T.Compose([T.Resize((224, 224)), T.ToTensor(), ...])
        #   return transform(Image.open(image_path).convert('RGB')).unsqueeze(0)
        raise NotImplementedError('Implementar _preprocess.')

    def _run_inference(self, tensor) -> list[float]:
        # TODO: ejecutar inferencia y devolver lista de scores por categoría
        # Ejemplo PyTorch:
        #   import torch
        #   with torch.no_grad():
        #       output = self._model(tensor)
        #       return torch.softmax(output, dim=1).squeeze().tolist()
        raise NotImplementedError('Implementar _run_inference.')


# Instancia global (singleton)
classifier = AvocadoClassifierService()
