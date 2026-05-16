from django.contrib.auth import get_user_model
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .permissions import IsAdminOrStaff
from .serializers import (
    AdminCreateUserSerializer,
    AdminUserSerializer,
    RegisterSerializer,
    UserSerializer,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Public / authenticated views
# ---------------------------------------------------------------------------


@extend_schema(tags=["auth"])
class RegisterView(generics.CreateAPIView):
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

    @extend_schema(
        summary="Registrar nuevo usuario",
        description="Crea una cuenta de usuario. No requiere autenticación.",
        responses={201: UserSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["auth"],
    summary="Iniciar sesión",
    description="Devuelve `access` (30 min) y `refresh` (7 días) JWT tokens.",
)
class LoginView(TokenObtainPairView):
    permission_classes = (AllowAny,)


@extend_schema(tags=["auth"])
class ProfileView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Obtener perfil",
        description="Devuelve los datos del usuario autenticado.",
        responses={200: UserSerializer},
    )
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    @extend_schema(
        summary="Actualizar perfil",
        description="Actualiza `first_name` o `last_name`. El email no se puede cambiar.",
        request=UserSerializer,
        responses={200: UserSerializer},
    )
    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Admin views — require is_staff or is_superuser
# ---------------------------------------------------------------------------


@extend_schema(tags=["admin-users"])
@extend_schema_view(
    get=extend_schema(
        summary="Listar usuarios",
        description="Lista todos los usuarios del sistema. Solo admin/staff.",
        parameters=[
            OpenApiParameter("search", str, description="Filtra por email, nombre o apellido"),
            OpenApiParameter("active", str, description="Filtra por estado: `true` o `false`"),
            OpenApiParameter("staff", str, description="Filtra por rol staff: `true` o `false`"),
        ],
        responses={200: AdminUserSerializer(many=True)},
    ),
    post=extend_schema(
        summary="Crear usuario",
        description="Crea un nuevo usuario. Permite asignar rol staff desde el inicio.",
        request=AdminCreateUserSerializer,
        responses={201: AdminUserSerializer},
    ),
)
class AdminUserListView(generics.ListCreateAPIView):
    permission_classes = (IsAdminOrStaff,)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AdminCreateUserSerializer
        return AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.all().order_by("-created_at")

        search = self.request.query_params.get("search")
        active = self.request.query_params.get("active")
        staff = self.request.query_params.get("staff")

        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        if active is not None:
            qs = qs.filter(is_active=(active.lower() == "true"))
        if staff is not None:
            qs = qs.filter(is_staff=(staff.lower() == "true"))

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["admin-users"])
@extend_schema_view(
    get=extend_schema(summary="Detalle de usuario"),
    patch=extend_schema(summary="Actualizar usuario", description="Permite cambiar `is_active`, `is_staff`, nombres."),
    delete=extend_schema(
        summary="Eliminar usuario",
        responses={
            204: OpenApiResponse(description="Usuario eliminado"),
            400: OpenApiResponse(description="No puedes eliminar tu propio usuario"),
        },
    ),
)
class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAdminOrStaff,)
    serializer_class = AdminUserSerializer
    queryset = User.objects.all()

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            return Response(
                {"detail": "No puedes eliminar tu propio usuario."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["admin-users"],
    summary="Activar / desactivar usuario",
    description="Alterna el campo `is_active` del usuario. No se puede aplicar al propio usuario.",
    request=None,
    responses={
        200: AdminUserSerializer,
        400: OpenApiResponse(description="No puedes desactivar tu propio usuario"),
        404: OpenApiResponse(description="Usuario no encontrado"),
    },
)
class AdminUserToggleActiveView(APIView):
    permission_classes = (IsAdminOrStaff,)

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(
                {"detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if user == request.user:
            return Response(
                {"detail": "No puedes desactivar tu propio usuario."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        return Response(AdminUserSerializer(user).data)


@extend_schema(
    tags=["admin-users"],
    summary="Cambiar contraseña de usuario",
    description="Permite al admin reiniciar la contraseña de cualquier usuario. Mínimo 8 caracteres.",
    request=inline_serializer(
        name="ChangePasswordRequest",
        fields={"password": serializers.CharField(min_length=8)},
    ),
    responses={
        200: inline_serializer(
            name="ChangePasswordResponse",
            fields={"detail": serializers.CharField()},
        ),
        400: OpenApiResponse(description="Contraseña muy corta"),
        404: OpenApiResponse(description="Usuario no encontrado"),
    },
)
class AdminUserChangePasswordView(APIView):
    permission_classes = (IsAdminOrStaff,)

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(
                {"detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        password = request.data.get("password", "")
        if len(password) < 8:
            return Response(
                {"detail": "La contraseña debe tener al menos 8 caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(password)
        user.save()
        return Response({"detail": "Contraseña actualizada correctamente."})
