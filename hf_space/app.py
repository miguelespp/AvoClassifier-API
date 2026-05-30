import json
import pathlib

import gradio as gr
import numpy as np
from huggingface_hub import snapshot_download
from PIL import Image

CATEGORIES = ["antracnosis", "sarna", "saludable"]
MODEL_REPO = "cmep121/avoclassifier"

print("Descargando modelo desde HF Hub...")
model_dir = pathlib.Path(snapshot_download(MODEL_REPO))
print(f"Modelo en: {model_dir}")

import keras

config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
model = keras.saving.deserialize_keras_object(config)
model.load_weights(str(model_dir / "model.weights.h5"))
print("Modelo cargado correctamente.")


def classify(image: Image.Image) -> dict:
    img = image.convert("RGB").resize((299, 299))
    arr = np.array(img, dtype=np.float32) / 127.5 - 1.0
    arr = np.expand_dims(arr, axis=0)
    scores = model.predict(arr, verbose=0)[0].tolist()
    return {cat: float(score) for cat, score in zip(CATEGORIES, scores)}


demo = gr.Interface(
    fn=classify,
    inputs=gr.Image(type="pil", label="Imagen de aguacate"),
    outputs=gr.Label(num_top_classes=3, label="Diagnóstico"),
    title="AvoClassifier",
    description="Detecta: Saludable · Antracnosis · Sarna",
)

demo.launch()
