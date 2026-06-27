from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

REGISTER_URL = reverse("register")
LOGIN_URL = reverse("login")
LOGOUT_URL = reverse("logout")
PROFILE_URL = reverse("profile")
REFRESH_URL = reverse("token_refresh")


def create_user(email="test@example.com", password="testpass123", **kwargs):
    return User.objects.create_user(email=email, password=password, **kwargs)


class RegisterTests(APITestCase):
    def test_register_success(self):
        data = {
            "email": "new@example.com",
            "password": "securepass1",
            "password2": "securepass1",
            "first_name": "Ana",
            "last_name": "García",
        }
        res = self.client.post(REGISTER_URL, data)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["email"], data["email"])
        self.assertNotIn("password", res.data)

    def test_register_password_mismatch(self):
        data = {
            "email": "bad@example.com",
            "password": "pass1234",
            "password2": "different",
        }
        res = self.client.post(REGISTER_URL, data)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_email(self):
        create_user()
        data = {"email": "test@example.com", "password": "pass1234", "password2": "pass1234"}
        res = self.client.post(REGISTER_URL, data)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class LoginLogoutTests(APITestCase):
    def setUp(self):
        self.user = create_user()

    def test_login_success(self):
        res = self.client.post(LOGIN_URL, {"email": "test@example.com", "password": "testpass123"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)

    def test_login_wrong_password(self):
        res = self.client.post(LOGIN_URL, {"email": "test@example.com", "password": "wrong"})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_refresh(self):
        login = self.client.post(LOGIN_URL, {"email": "test@example.com", "password": "testpass123"})
        refresh = login.data["refresh"]
        access = login.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        res = self.client.post(LOGOUT_URL, {"refresh": refresh})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Intento de refresh debe fallar
        res2 = self.client.post(REFRESH_URL, {"refresh": refresh})
        self.assertEqual(res2.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_requires_auth(self):
        res = self.client.post(LOGOUT_URL, {"refresh": "sometoken"})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class ProfileTests(APITestCase):
    def setUp(self):
        self.user = create_user(first_name="Carlos")
        login = self.client.post(LOGIN_URL, {"email": "test@example.com", "password": "testpass123"})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_get_profile(self):
        res = self.client.get(PROFILE_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["email"], "test@example.com")

    def test_patch_profile(self):
        res = self.client.patch(PROFILE_URL, {"first_name": "Nuevo"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["first_name"], "Nuevo")

    def test_profile_requires_auth(self):
        self.client.credentials()
        res = self.client.get(PROFILE_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class AdminPermissionsTests(APITestCase):
    def setUp(self):
        self.regular_user = create_user(email="regular@example.com")
        self.staff_user = create_user(email="staff@example.com", is_staff=True)

    def _login(self, email, password="testpass123"):
        res = self.client.post(LOGIN_URL, {"email": email, "password": password})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {res.data["access"]}')

    def test_regular_user_cannot_access_admin_users(self):
        self._login("regular@example.com")
        res = self.client.get(reverse("admin_user_list"))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_user_can_access_admin_users(self):
        self._login("staff@example.com")
        res = self.client.get(reverse("admin_user_list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
