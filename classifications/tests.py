import io

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from PIL import Image as PilImage
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Classification, ClassificationStatus

User = get_user_model()

LOGIN_URL = reverse("login")
CREATE_URL = reverse("classification_create")
STATS_URL = reverse("user_stats")
EXPORT_URL = reverse("classification_export_csv")
ADMIN_LIST_URL = reverse("admin_classification_list")


def create_user(email="user@example.com", password="testpass123", **kw):
    return User.objects.create_user(email=email, password=password, **kw)


def _fake_jpeg():
    """Returns an in-memory JPEG file object."""
    buf = io.BytesIO()
    img = PilImage.new("RGB", (100, 100), color=(100, 200, 50))
    img.save(buf, format="JPEG")
    buf.name = "test.jpg"
    buf.seek(0)
    return buf


def _fake_text_as_jpg():
    """Returns a text file disguised as image."""
    buf = io.BytesIO(b"this is not an image")
    buf.name = "fake.jpg"
    buf.seek(0)
    return buf


class ImageValidationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = create_user()
        login = self.client.post(LOGIN_URL, {"email": "user@example.com", "password": "testpass123"})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_upload_valid_jpeg(self):
        res = self.client.post(CREATE_URL, {"image": _fake_jpeg()}, format="multipart")
        # 201 o 500 si el modelo falla — lo importante es que pasa validación
        self.assertNotEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_corrupt_file_rejected(self):
        res = self.client.post(CREATE_URL, {"image": _fake_text_as_jpg()}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class UserStatsTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = create_user(email="stats@example.com")
        login = self.client.post(LOGIN_URL, {"email": "stats@example.com", "password": "testpass123"})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
        Classification.objects.create(
            user=self.user,
            image="classifications/test.jpg",
            status=ClassificationStatus.COMPLETED,
            predicted_category="saludable",
            confidence=0.95,
        )

    def test_stats_returns_correct_total(self):
        # pylint: disable=protected-access
        res = self.client.get(STATS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["total"], 1)
        self.assertIn("by_status", res.data)
        self.assertIn("by_category", res.data)
        self.assertIn("average_confidence", res.data)

    def test_stats_requires_auth(self):
        self.client.credentials()  # limpia credenciales
        res = self.client.get(STATS_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class CSVExportTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = create_user(email="csv@example.com")
        login = self.client.post(LOGIN_URL, {"email": "csv@example.com", "password": "testpass123"})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
        Classification.objects.create(
            user=self.user,
            image="classifications/test.jpg",
            status=ClassificationStatus.COMPLETED,
            predicted_category="antracnosis",
        )

    def test_export_returns_csv(self):
        res = self.client.get(EXPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", res["Content-Type"])
        self.assertIn("clasificaciones.csv", res["Content-Disposition"])

    def test_export_requires_auth(self):
        self.client.credentials()
        res = self.client.get(EXPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class SoftDeleteTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.staff = create_user(email="staff@example.com", is_staff=True)
        login = self.client.post(LOGIN_URL, {"email": "staff@example.com", "password": "testpass123"})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
        self.classification = Classification.objects.create(
            user=self.staff,
            image="classifications/test.jpg",
            status=ClassificationStatus.COMPLETED,
        )

    def test_delete_soft_deletes(self):
        url = reverse("admin_classification_detail", kwargs={"pk": self.classification.pk})
        res = self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        # No visible en el manager normal
        self.assertFalse(Classification.objects.filter(pk=self.classification.pk).exists())

        # Pero existe en with_deleted
        self.assertTrue(Classification.objects.with_deleted().filter(pk=self.classification.pk).exists())

    def test_admin_list_excludes_deleted_by_default(self):
        self.classification.soft_delete()
        res = self.client.get(ADMIN_LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in res.data["results"]]
        self.assertNotIn(self.classification.pk, ids)

    def test_admin_list_includes_deleted_with_param(self):
        self.classification.soft_delete()
        res = self.client.get(ADMIN_LIST_URL + "?include_deleted=true")
        ids = [r["id"] for r in res.data["results"]]
        self.assertIn(self.classification.pk, ids)
