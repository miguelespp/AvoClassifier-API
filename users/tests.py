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
CHANGE_PASSWORD_URL = reverse("change_password")
ADMIN_USER_LIST_URL = reverse("admin_user_list")


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


class ChangePasswordTests(APITestCase):
    def setUp(self):
        self.user = create_user()
        login = self.client.post(LOGIN_URL, {"email": "test@example.com", "password": "testpass123"})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_change_password_success(self):
        res = self.client.post(CHANGE_PASSWORD_URL, {
            "current_password": "testpass123",
            "new_password": "newpassword456",
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpassword456"))

    def test_change_password_wrong_current(self):
        res = self.client.post(CHANGE_PASSWORD_URL, {
            "current_password": "wrongpassword",
            "new_password": "newpassword456",
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_too_short(self):
        res = self.client.post(CHANGE_PASSWORD_URL, {
            "current_password": "testpass123",
            "new_password": "short",
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_requires_auth(self):
        self.client.credentials()
        res = self.client.post(CHANGE_PASSWORD_URL, {
            "current_password": "testpass123",
            "new_password": "newpassword456",
        })
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class AdminUserCRUDTests(APITestCase):
    def setUp(self):
        self.staff = create_user(email="staff@example.com", is_staff=True)
        self.client.force_authenticate(user=self.staff)
        self.target = create_user(email="target@example.com", first_name="Target")

    def test_list_users_includes_all(self):
        res = self.client.get(ADMIN_USER_LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        emails = [u["email"] for u in res.data["results"]]
        self.assertIn("target@example.com", emails)

    def test_create_user(self):
        res = self.client.post(ADMIN_USER_LIST_URL, {
            "email": "created@example.com",
            "password": "pass12345",
            "first_name": "Nuevo",
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="created@example.com").exists())

    def test_get_user_detail(self):
        url = reverse("admin_user_detail", kwargs={"pk": self.target.pk})
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["email"], "target@example.com")

    def test_patch_user_detail(self):
        url = reverse("admin_user_detail", kwargs={"pk": self.target.pk})
        res = self.client.patch(url, {"first_name": "Modificado"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["first_name"], "Modificado")

    def test_delete_user(self):
        url = reverse("admin_user_detail", kwargs={"pk": self.target.pk})
        res = self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.target.pk).exists())

    def test_cannot_delete_self(self):
        url = reverse("admin_user_detail", kwargs={"pk": self.staff.pk})
        res = self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_search_filter(self):
        res = self.client.get(ADMIN_USER_LIST_URL + "?search=target")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        emails = [u["email"] for u in res.data["results"]]
        self.assertIn("target@example.com", emails)
        self.assertNotIn("staff@example.com", emails)

    def test_filter_by_active(self):
        self.target.is_active = False
        self.target.save()
        res = self.client.get(ADMIN_USER_LIST_URL + "?active=false")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        emails = [u["email"] for u in res.data["results"]]
        self.assertIn("target@example.com", emails)
        self.assertNotIn("staff@example.com", emails)


class AdminUserToggleActiveTests(APITestCase):
    def setUp(self):
        self.staff = create_user(email="staff@example.com", is_staff=True)
        self.client.force_authenticate(user=self.staff)
        self.target = create_user(email="target@example.com")

    def test_toggle_deactivates_active_user(self):
        url = reverse("admin_user_toggle_active", kwargs={"pk": self.target.pk})
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

    def test_toggle_activates_inactive_user(self):
        self.target.is_active = False
        self.target.save()
        url = reverse("admin_user_toggle_active", kwargs={"pk": self.target.pk})
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_cannot_toggle_self(self):
        url = reverse("admin_user_toggle_active", kwargs={"pk": self.staff.pk})
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_toggle_nonexistent_user(self):
        url = reverse("admin_user_toggle_active", kwargs={"pk": 99999})
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class AdminUserChangePasswordTests(APITestCase):
    def setUp(self):
        self.staff = create_user(email="staff@example.com", is_staff=True)
        self.client.force_authenticate(user=self.staff)
        self.target = create_user(email="target@example.com")

    def test_admin_change_password_success(self):
        url = reverse("admin_user_change_password", kwargs={"pk": self.target.pk})
        res = self.client.post(url, {"password": "newadminpass123"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password("newadminpass123"))

    def test_admin_change_password_too_short(self):
        url = reverse("admin_user_change_password", kwargs={"pk": self.target.pk})
        res = self.client.post(url, {"password": "short"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_change_password_user_not_found(self):
        url = reverse("admin_user_change_password", kwargs={"pk": 99999})
        res = self.client.post(url, {"password": "validpassword123"})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
