import base64
import io
import json
import pathlib

import gradio as gr
import numpy as np
from fastapi import Request
from fastapi.responses import JSONResponse
from huggingface_hub import snapshot_download
from PIL import Image

CATEGORIES = ["antracnosis", "sarna", "saludable"]
MODEL_REPO = "cmep121/avoclassifier"

print("Descargando modelo desde HF Hub...")
model_dir = pathlib.Path(snapshot_download(MODEL_REPO))

import keras

config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
model = keras.saving.deserialize_keras_object(config)
model.load_weights(str(model_dir / "model.weights.h5"))
print("Modelo cargado correctamente.")


def _run(image: Image.Image) -> dict:
    img = image.convert("RGB").resize((299, 299))
    arr = np.array(img, dtype=np.float32) / 127.5 - 1.0
    arr = np.expand_dims(arr, axis=0)
    scores = model.predict(arr, verbose=0)[0].tolist()
    return {cat: float(score) for cat, score in zip(CATEGORIES, scores)}


# ── Gradio UI ─────────────────────────────────────────────────────────────────

demo = gr.Interface(
    fn=_run,
    inputs=gr.Image(type="pil", label="Imagen de aguacate"),
    outputs=gr.Label(num_top_classes=3, label="Diagnóstico"),
    title="AvoClassifier",
    description="Detecta: Saludable · Antracnosis · Sarna",
)


# ── Endpoint REST custom montado en el FastAPI interno de Gradio ──────────────

@demo.app.post("/classify")
async def classify_endpoint(request: Request):
    """
    Endpoint para el backend Django.
    Acepta JSON: {"image": "<base64>"} para evitar CSRF de Gradio.
    """
    body = await request.json()
    img_bytes = base64.b64decode(body["image"])
    image = Image.open(io.BytesIO(img_bytes))
    scores = _run(image)
    predicted = max(scores, key=scores.get)
    return JSONResponse({
        "predicted_category": predicted,
        "confidence": scores[predicted],
        "raw_scores": scores,
    })


demo.launch()
