import io

import pytest
from PIL import Image as PilImage


@pytest.fixture
def fake_jpeg():
    """Returns a factory that produces in-memory JPEG file objects."""
    def _make(color=(100, 200, 50)):
        buf = io.BytesIO()
        img = PilImage.new("RGB", (100, 100), color=color)
        img.save(buf, format="JPEG")
        buf.name = "test.jpg"
        buf.seek(0)
        return buf
    return _make
