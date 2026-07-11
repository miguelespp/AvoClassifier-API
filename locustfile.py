"""
Stress tests for AvoClassifier API.

Usage:
    pip install locust

    # Contra el servidor local (python manage.py runserver):
    locust -f locustfile.py --host=http://127.0.0.1:8000

    # Contra el despliegue de Render (lo que golpea el frontend real):
    locust -f locustfile.py --host=https://avoclassifier-api.onrender.com

Then open http://localhost:8089 to configure users and ramp-up rate.

For headless runs (CI / quick benchmarks):
    locust -f locustfile.py --host=http://127.0.0.1:8000 \
           --headless -u 20 -r 2 --run-time 60s

Perfil de carga por etapas (rampa reproducible, tolerante al cold start de Render):
    STRESS_SHAPE=1 locust -f locustfile.py \
        --host=https://avoclassifier-api.onrender.com --headless
    # Con STRESS_SHAPE=1 la forma de la carga (StagedRampUp) controla el número de
    # usuarios y el spawn rate; los flags -u/-r se ignoran. Sin la env var, el
    # comportamiento clásico -u/-r se mantiene intacto.

User setup:
    Before running, create at least one regular user and one staff user
    that match REGULAR_EMAIL/PASSWORD and STAFF_EMAIL/PASSWORD below,
    or override them via environment variables:

        STRESS_USER=me@example.com STRESS_PASS=secret locust ...
"""

import io
import os
import random
import time

from locust import HttpUser, LoadTestShape, between, task
from PIL import Image as PilImage

# ---------------------------------------------------------------------------
# Credentials — override via env vars in production / CI
# ---------------------------------------------------------------------------

REGULAR_EMAIL = os.environ.get("STRESS_USER", "stress@example.com")
REGULAR_PASS = os.environ.get("STRESS_PASS", "stresspass123")
STAFF_EMAIL = os.environ.get("STRESS_STAFF_USER", "stress_admin@example.com")
STAFF_PASS = os.environ.get("STRESS_STAFF_PASS", "stresspass123")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_jpeg(width: int = 100, height: int = 100) -> io.BytesIO:
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)
    buf = io.BytesIO()
    PilImage.new("RGB", (width, height), color=(r, g, b)).save(buf, format="JPEG")
    buf.name = "test.jpg"
    buf.seek(0)
    return buf


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Regular user — simulates normal app usage
# ---------------------------------------------------------------------------

class RegularUser(HttpUser):
    """
    Simulates a regular authenticated user:
      - classify images (heaviest operation — runs sync model inference)
      - poll for classification result
      - browse history and stats
    """

    wait_time = between(1, 4)
    weight = 3  # 3x more regular users than admin users

    token: str = ""
    classification_ids: list = []

    def on_start(self):
        self.classification_ids = []
        self._login()

    def _login(self):
        with self.client.post(
            "/api/auth/login/",
            json={"email": REGULAR_EMAIL, "password": REGULAR_PASS},
            catch_response=True,
            name="/api/auth/login/",
        ) as res:
            if res.status_code == 200:
                self.token = res.json().get("access", "")
            elif res.status_code == 429:
                res.success()  # throttled logins are expected — don't count as error
            else:
                res.failure(f"Login failed: {res.status_code}")

    # --- Classify --------------------------------------------------------

    @task(4)
    def classify_image(self):
        """Upload an image and run classification (synchronous model inference)."""
        with self.client.post(
            "/api/classifications/",
            files={"image": ("test.jpg", _fake_jpeg(), "image/jpeg")},
            headers=_auth_headers(self.token),
            catch_response=True,
            name="/api/classifications/ [POST]",
        ) as res:
            if res.status_code == 202:
                cid = res.json().get("id")
                if cid:
                    self.classification_ids.append(cid)
            elif res.status_code == 429:
                res.success()  # classification throttle (30/hour) — expected
            else:
                res.failure(f"Classify failed: {res.status_code} {res.text[:200]}")

    # --- Poll result -----------------------------------------------------

    @task(6)
    def poll_classification(self):
        """Poll a known classification for its result (simulates frontend polling)."""
        if not self.classification_ids:
            return
        cid = random.choice(self.classification_ids)
        self.client.get(
            f"/api/classifications/{cid}/",
            headers=_auth_headers(self.token),
            name="/api/classifications/<id>/",
        )

    # --- Read endpoints --------------------------------------------------

    @task(5)
    def get_history(self):
        self.client.get(
            "/api/classifications/history/",
            headers=_auth_headers(self.token),
            name="/api/classifications/history/",
        )

    @task(3)
    def get_user_stats(self):
        self.client.get(
            "/api/classifications/stats/",
            headers=_auth_headers(self.token),
            name="/api/classifications/stats/",
        )

    @task(2)
    def get_profile(self):
        self.client.get(
            "/api/auth/profile/",
            headers=_auth_headers(self.token),
            name="/api/auth/profile/",
        )

    # --- Token refresh ---------------------------------------------------

    @task(1)
    def refresh_token(self):
        """Simulates a client refreshing its access token."""
        with self.client.post(
            "/api/auth/login/",
            json={"email": REGULAR_EMAIL, "password": REGULAR_PASS},
            catch_response=True,
            name="/api/auth/login/ [refresh sim]",
        ) as res:
            if res.status_code == 200:
                self.token = res.json().get("access", self.token)
            elif res.status_code == 429:
                res.success()
            else:
                res.failure(f"Token refresh failed: {res.status_code}")


# ---------------------------------------------------------------------------
# Admin user — simulates staff dashboard usage
# ---------------------------------------------------------------------------

class AdminUser(HttpUser):
    """
    Simulates a staff user browsing the admin dashboard.
    Lower weight — there are fewer admins than regular users.
    """

    wait_time = between(2, 6)
    weight = 1

    token: str = ""

    def on_start(self):
        self._login()

    def _login(self):
        with self.client.post(
            "/api/auth/login/",
            json={"email": STAFF_EMAIL, "password": STAFF_PASS},
            catch_response=True,
            name="/api/auth/login/ [admin]",
        ) as res:
            if res.status_code == 200:
                self.token = res.json().get("access", "")
            elif res.status_code == 429:
                res.success()
            else:
                res.failure(f"Admin login failed: {res.status_code}")

    @task(5)
    def get_dashboard_stats(self):
        self.client.get(
            "/api/classifications/admin/stats/",
            headers=_auth_headers(self.token),
            name="/api/classifications/admin/stats/",
        )

    @task(4)
    def list_all_classifications(self):
        page = random.randint(1, 3)
        self.client.get(
            f"/api/classifications/admin/all/?page={page}",
            headers=_auth_headers(self.token),
            name="/api/classifications/admin/all/",
        )

    @task(3)
    def list_users(self):
        self.client.get(
            "/api/auth/admin/users/",
            headers=_auth_headers(self.token),
            name="/api/auth/admin/users/",
        )

    @task(2)
    def filter_classifications_by_status(self):
        status = random.choice(["completed", "failed", "pending"])
        self.client.get(
            f"/api/classifications/admin/all/?status={status}",
            headers=_auth_headers(self.token),
            name="/api/classifications/admin/all/?status=",
        )

    @task(1)
    def export_csv(self):
        self.client.get(
            "/api/classifications/history/export/",
            headers=_auth_headers(self.token),
            name="/api/classifications/history/export/",
        )


# ---------------------------------------------------------------------------
# Load shape — perfil de rampa reproducible (opt-in via STRESS_SHAPE=1)
# ---------------------------------------------------------------------------

if os.environ.get("STRESS_SHAPE") == "1":

    class StagedRampUp(LoadTestShape):
        """
        Perfil de carga por etapas, pensado para un servicio con cold start (Render):

            1. Warm-up   — pocos usuarios para despertar el dyno sin saturarlo.
            2. Ramp-up   — subida gradual hasta la carga objetivo.
            3. Sustained — meseta a carga plena (mide throughput/latencia estable).
            4. Ramp-down — bajada suave (observa recuperación).

        Cada etapa: (duración acumulada en s, nº usuarios, spawn rate).
        Ajusta libremente los valores según el objetivo del benchmark.
        """

        stages = [
            {"duration": 30,  "users": 3,  "spawn_rate": 1},   # warm-up
            {"duration": 90,  "users": 20, "spawn_rate": 2},   # ramp-up
            {"duration": 210, "users": 20, "spawn_rate": 2},   # sustained (2 min)
            {"duration": 240, "users": 5,  "spawn_rate": 2},   # ramp-down
        ]

        def tick(self):
            run_time = self.get_run_time()
            for stage in self.stages:
                if run_time < stage["duration"]:
                    return stage["users"], stage["spawn_rate"]
            return None  # fin de la prueba
