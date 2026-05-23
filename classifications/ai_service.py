"""
Capa de servicio para el modelo de clasificación de enfermedades en palta.

Estrategia de carga:
  1. Se intenta cargar el modelo Keras 3.x desde settings.AI_MODEL_DIR.
  2. Si Keras / TensorFlow no están disponibles (p.ej. Python 3.14 donde TF aún no
     corre), el modelo se marca como 'UNAVAILABLE' y la inferencia cae en el modo
     heurístico basado en estadísticas de color de la imagen.
  3. Cuando TF/Keras esté disponible, no se necesita cambiar nada: el clasificador
     detectará el modelo cargado y usará _run_inference() real.

Categorías (deben coincidir con DiseaseCategory en classifications/models.py):
  - antracnosis → manchas oscuras/marrones por Colletotrichum
  - sarna       → roña/sarna del fruto
  - saludable   → fruto sin enfermedad visible
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Orden alfabético de carpetas de entrenamiento: antracnosis / sarna / saludable
CATEGORIES: list[str] = ["antracnosis", "sarna", "saludable"]

# Sentinel para indicar que el backend ML no pudo cargarse
_UNAVAILABLE = "UNAVAILABLE"


@dataclass
class ClassificationResult:
    predicted_category: str
    confidence: float  # probabilidad de la categoría ganadora (0.0–1.0)
    raw_scores: dict[str, float]  # probabilidad por cada categoría


class AvocadoClassifierService:
    """
    Wrapper del modelo de IA. Mantiene el modelo en memoria entre llamadas.
    Se instancia una sola vez (singleton) para evitar recargas.

    Modos de operación
    ------------------
    - **keras**     : modelo Keras 3.x cargado desde AI_MODEL_DIR. Inferencia real.
    - **heuristic** : Keras/TF no disponibles. Inferencia por estadísticas de color.
    - **none**      : load() todavía no fue llamado.
    """

    _instance: Optional["AvocadoClassifierService"] = None
    _model = None  # None → no cargado; _UNAVAILABLE → sin backend ML; objeto → listo

    def __new__(cls) -> "AvocadoClassifierService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def load(self) -> None:
        """
        Carga el modelo en memoria.
        Llamado automáticamente desde ClassificationsConfig.ready() al iniciar Django.
        Es seguro llamarlo varias veces: sólo carga una vez.
        """
        if self._model is not None:
            return
        logger.info("Cargando modelo de clasificación de palta…")
        self._model = self._load_model()
        if self._model is _UNAVAILABLE:
            logger.warning(
                "Backend ML no disponible. Se usará inferencia heurística por color. "
                "Instalar keras/tensorflow cuando Python 3.14 sea soportado."
            )
        else:
            logger.info("Modelo Keras cargado correctamente desde AI_MODEL_DIR.")

    def reload(self) -> None:
        """Descarga y recarga el modelo. Útil para hot-reload en desarrollo."""
        self._model = None
        self.load()

    # ------------------------------------------------------------------
    # Propiedades de estado
    # ------------------------------------------------------------------

    @property
    def is_model_loaded(self) -> bool:
        """True sólo cuando el modelo Keras real está en memoria."""
        return self._model is not None and self._model is not _UNAVAILABLE

    @property
    def model_status(self) -> dict:
        """
        Diccionario descriptivo del estado actual del servicio.

        Ejemplo (Keras disponible):
            {'loaded': True, 'backend': 'keras', 'categories': [...]}
        Ejemplo (sin TF):
            {'loaded': False, 'backend': 'heuristic', 'categories': [...]}
        Ejemplo (antes de load()):
            {'loaded': False, 'backend': 'none', 'categories': [...]}
        """
        if self._model is None:
            backend = "none"
        elif self._model is _UNAVAILABLE:
            backend = "heuristic"
        else:
            backend = "keras"

        return {
            "loaded": self.is_model_loaded,
            "backend": backend,
            "categories": CATEGORIES,
        }

    # ------------------------------------------------------------------
    # Método principal
    # ------------------------------------------------------------------

    def predict(self, image_path: str) -> ClassificationResult:
        """
        Clasifica una imagen y devuelve el resultado.

        Args:
            image_path: Ruta absoluta (o relativa al CWD) al archivo de imagen.

        Returns:
            ClassificationResult con la categoría predicha, confianza y scores crudos.

        Raises:
            RuntimeError: Si load() aún no fue llamado.
        """
        if self._model is None:
            self.load()  # carga diferida: primer predict activa la carga

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
    # Implementaciones internas
    # ------------------------------------------------------------------

    def _load_model(self):
        """
        Carga el modelo Keras 3.x en formato directorio (config.json + model.weights.h5).

        Búsqueda del modelo en settings.AI_MODEL_DIR:
          1. Si el directorio contiene directamente config.json → lo carga.
          2. Si no, busca el primer subdirectorio *.keras y lo carga.

        Se usa deserialize_keras_object + load_weights en lugar de
        keras.saving.load_model porque éste último falla en Windows cuando
        el path termina en .keras pero es un directorio (no un zip).
        """
        try:
            import json
            import pathlib

            import keras
            from django.conf import settings

            base = pathlib.Path(settings.AI_MODEL_DIR)
            model_dir = self._resolve_model_dir(base)
            logger.info("Cargando modelo desde: %s", model_dir)

            config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
            model = keras.saving.deserialize_keras_object(config)
            model.load_weights(str(model_dir / "model.weights.h5"))
            return model

        except (ImportError, ModuleNotFoundError) as exc:
            logger.warning(
                "keras/tensorflow no disponibles (%s). "
                "Se activa el modo heurístico de respaldo.",
                exc,
            )
            return _UNAVAILABLE

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error inesperado al cargar el modelo Keras: %s. "
                "Se activa el modo heurístico de respaldo.",
                exc,
                exc_info=True,
            )
            return _UNAVAILABLE

    @staticmethod
    def _resolve_model_dir(base):
        """
        Resuelve el directorio concreto del modelo dentro de base.

        Prioridad:
          1. base contiene config.json → es el propio directorio del modelo.
          2. base tiene un único subdirectorio *.keras → lo usa.
          3. Lanza FileNotFoundError si no encuentra ninguno.
        """
        import pathlib

        base = pathlib.Path(base)
        if (base / "config.json").exists():
            return base
        candidates = sorted(base.glob("*.keras"))
        if candidates:
            return candidates[0]
        raise FileNotFoundError(
            f"No se encontró ningún modelo Keras en '{base}'. "
            "Debe contener config.json o un subdirectorio *.keras."
        )

    def _preprocess(self, image_path: str):
        """
        Carga una imagen desde disco y la convierte en un array numpy listo
        para ser consumido por el modelo.

        Transformaciones aplicadas:
          1. Abrir con PIL y convertir a RGB (descarta canal alfa si existe).
          2. Redimensionar a 299×299 (tamaño esperado por el modelo).
          3. Convertir a float32 y aplicar preprocess_input de InceptionV3: [0,255] → [-1, 1].
          4. Agregar dimensión de batch → shape final (1, 299, 299, 3).

        Returns:
            numpy.ndarray de shape (1, 299, 299, 3) y dtype float32.
        """
        import numpy as np
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        img = img.resize((299, 299), Image.LANCZOS)
        arr = np.array(img, dtype=np.float32)
        arr = arr / 127.5 - 1.0  # preprocess_input de InceptionV3: rango [-1, 1]
        return np.expand_dims(arr, axis=0)  # (1, 299, 299, 3)

    def _run_inference(self, tensor) -> list[float]:
        """
        Ejecuta la inferencia sobre el tensor preprocesado.

        - Si el modelo Keras está cargado: pasa el tensor por la red y devuelve
          las probabilidades softmax directamente del modelo.
        - Si el backend es 'heuristic': delega a _heuristic_scores().

        Returns:
            Lista de float con una probabilidad por categoría (suma ≈ 1.0).
            El orden coincide con CATEGORIES = ['antracnosis', 'sarna', 'saludable'].
        """
        if self._model is _UNAVAILABLE:
            logger.debug("Usando inferencia heurística (sin modelo ML).")
            return self._heuristic_scores(tensor)

        # Inferencia real con Keras
        # model.predict devuelve un array de shape (batch, num_classes)
        predictions = self._model.predict(tensor, verbose=0)
        return [float(p) for p in predictions[0].tolist()]

    # ------------------------------------------------------------------
    # Heurística de respaldo (sin modelo ML)
    # ------------------------------------------------------------------

    def _heuristic_scores(self, tensor) -> list[float]:
        """
        Inferencia de respaldo basada en estadísticas de color de la imagen.
        Se usa ÚNICAMENTE cuando Keras/TF no está disponible.

        Lógica:
          - Saludable    : dominancia del canal verde (G > R y G > B).
          - Antracnosis  : señal marrón/amarillenta (R+G altos, B bajo).
          - Pudrición    : alta desviación estándar + tonos oscuros.

        Los scores crudos se normalizan con softmax para obtener probabilidades.

        ADVERTENCIA: Esta heurística es puramente ilustrativa; no reemplaza al
        modelo entrenado. Los resultados no deben usarse en producción.

        Args:
            tensor: numpy.ndarray de shape (1, 299, 299, 3), valores en [0, 1].

        Returns:
            Lista de 3 floats (probabilidades sumadas ≈ 1.0) en el orden
            [antracnosis, sarna, saludable].
        """
        import numpy as np

        img = tensor[0]  # (299, 299, 3)

        r_mean = float(np.mean(img[:, :, 0]))
        g_mean = float(np.mean(img[:, :, 1]))
        b_mean = float(np.mean(img[:, :, 2]))
        std = float(np.std(img))

        # Scores crudos (sin normalizar) — orden debe coincidir con CATEGORIES
        # antracnosis: tono marrón/amarillo (R+G altos, B bajo)
        score_antracnosis = (r_mean + g_mean) * 0.7 - b_mean * 0.5 - g_mean * 0.3 + 0.05

        # sarna: alta varianza + tonos oscuros
        score_sarna = (
            std * 2.0 - g_mean * 0.5 + (1.0 - r_mean - g_mean - b_mean) * 0.3 + 0.05
        )

        # saludable: dominancia del verde
        score_saludable = g_mean * 1.5 - r_mean * 0.5 - b_mean * 0.3 + 0.1

        raw = np.array(
            [score_antracnosis, score_sarna, score_saludable], dtype=np.float32
        )

        # Softmax estable numéricamente
        exp = np.exp(raw - np.max(raw))
        probs = exp / exp.sum()

        return probs.tolist()


# Instancia global (singleton) — importar desde aquí en el resto del proyecto
classifier = AvocadoClassifierService()
