from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsAdminOrStaff

from .ai_service import classifier
from .models import Classification, ClassificationStatus, DiseaseCategory  # noqa: F401
from .serializers import (
    AdminClassificationSerializer,
    ClassificationCreateSerializer,
    ClassificationResultSerializer,
)
from .services import run_classification

User = get_user_model()


# ---------------------------------------------------------------------------
# User-facing views
# ---------------------------------------------------------------------------


@extend_schema(
    tags=["classifications"],
    summary="Clasificar imagen de aguacate",
    description=(
        "Sube una imagen JPG/PNG y obtiene la clasificación de enfermedad.\n\n"
        "**Formato de la petición:** `multipart/form-data` con el campo `image`.\n\n"
        "**Categorías posibles:** `saludable`, `antracnosis`, `pudricion`.\n\n"
        "Si el procesamiento es lento, el cliente puede hacer polling a "
        "`GET /api/classifications/{id}/` usando el `id` devuelto."
    ),
    request={"multipart/form-data": ClassificationCreateSerializer},
    responses={201: ClassificationResultSerializer},
)
class ClassificationCreateView(generics.CreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ClassificationCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()

        # Ejecutar clasificación de forma síncrona
        # TODO: reemplazar por tarea Celery si el modelo es lento:
        #   classify_image_task.delay(classification.pk)
        classification = run_classification(classification.pk)

        return Response(
            ClassificationResultSerializer(classification).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["classifications"],
    summary="Resultado de clasificación",
    description="Consulta el estado y resultado de una clasificación por ID. Útil para polling.",
    responses={200: ClassificationResultSerializer},
)
class ClassificationDetailView(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ClassificationResultSerializer

    def get_queryset(self):
        return Classification.objects.filter(user=self.request.user)


@extend_schema(
    tags=["classifications"],
    summary="Historial de clasificaciones",
    description="Devuelve todas las clasificaciones del usuario autenticado, ordenadas por fecha.",
    responses={200: ClassificationResultSerializer(many=True)},
)
class ClassificationListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ClassificationResultSerializer

    def get_queryset(self):
        return Classification.objects.filter(user=self.request.user)


# ---------------------------------------------------------------------------
# Admin views — require is_staff or is_superuser
# ---------------------------------------------------------------------------


@extend_schema(
    tags=["admin-classifications"],
    summary="Listar todas las clasificaciones",
    description="Lista clasificaciones de todos los usuarios. Solo admin/staff.",
    parameters=[
        OpenApiParameter(
            "status", str,
            description="Filtra por estado: `pending`, `processing`, `completed`, `failed`",
            enum=["pending", "processing", "completed", "failed"],
        ),
        OpenApiParameter(
            "category", str,
            description="Filtra por categoría: `saludable`, `antracnosis`, `pudricion`",
            enum=["saludable", "antracnosis", "pudricion"],
        ),
        OpenApiParameter("user_id", int, description="Filtra por ID de usuario"),
        OpenApiParameter("search", str, description="Filtra por email del usuario"),
    ],
    responses={200: AdminClassificationSerializer(many=True)},
)
class AdminClassificationListView(generics.ListAPIView):
    permission_classes = (IsAdminOrStaff,)
    serializer_class = AdminClassificationSerializer

    def get_queryset(self):
        qs = Classification.objects.select_related("user").order_by("-created_at")

        status_filter = self.request.query_params.get("status")
        category = self.request.query_params.get("category")
        user_id = self.request.query_params.get("user_id")
        search = self.request.query_params.get("search")

        if status_filter:
            qs = qs.filter(status=status_filter)
        if category:
            qs = qs.filter(predicted_category=category)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if search:
            qs = qs.filter(user__email__icontains=search)

        return qs


@extend_schema(tags=["admin-classifications"])
@extend_schema_view(
    get=extend_schema(summary="Detalle de clasificación (admin)"),
    delete=extend_schema(
        summary="Eliminar clasificación",
        responses={204: OpenApiResponse(description="Clasificación eliminada")},
    ),
)
class AdminClassificationDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = (IsAdminOrStaff,)
    serializer_class = AdminClassificationSerializer
    queryset = Classification.objects.select_related("user").all()


@extend_schema(
    tags=["admin-classifications"],
    summary="Estadísticas del dashboard",
    description=(
        "Devuelve métricas globales: usuarios, clasificaciones por estado/categoría, "
        "actividad reciente y estado del modelo de IA."
    ),
    responses={
        200: inline_serializer(
            name="DashboardStats",
            fields={
                "users": inline_serializer(
                    name="UserStats",
                    fields={
                        "total": serializers.IntegerField(),
                        "active": serializers.IntegerField(),
                        "inactive": serializers.IntegerField(),
                        "staff": serializers.IntegerField(),
                    },
                ),
                "classifications": inline_serializer(
                    name="ClassificationStats",
                    fields={
                        "total": serializers.IntegerField(),
                        "by_status": serializers.DictField(),
                        "by_category": serializers.DictField(),
                        "recent_7_days": serializers.IntegerField(),
                        "average_confidence": serializers.FloatField(allow_null=True),
                    },
                ),
                "model": inline_serializer(
                    name="ModelStatus",
                    fields={
                        "backend": serializers.CharField(),
                        "loaded": serializers.BooleanField(),
                    },
                ),
            },
        )
    },
)
class AdminDashboardStatsView(APIView):
    permission_classes = (IsAdminOrStaff,)

    def get(self, request):
        # --- User stats ---
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        staff_users = User.objects.filter(is_staff=True).count()

        # --- Classification stats ---
        total_classifications = Classification.objects.count()

        by_status = dict(
            Classification.objects.values("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        by_category = dict(
            Classification.objects.filter(status=ClassificationStatus.COMPLETED)
            .values("predicted_category")
            .annotate(count=Count("id"))
            .values_list("predicted_category", "count")
        )

        # Recent activity (last 7 days)
        seven_days_ago = timezone.now() - timedelta(days=7)
        recent_classifications = Classification.objects.filter(
            created_at__gte=seven_days_ago
        ).count()

        # Average confidence for completed classifications
        avg_confidence = Classification.objects.filter(
            status=ClassificationStatus.COMPLETED,
            confidence__isnull=False,
        ).aggregate(avg=Avg("confidence"))["avg"]

        return Response(
            {
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "inactive": total_users - active_users,
                    "staff": staff_users,
                },
                "classifications": {
                    "total": total_classifications,
                    "by_status": by_status,
                    "by_category": by_category,
                    "recent_7_days": recent_classifications,
                    "average_confidence": round(avg_confidence, 4)
                    if avg_confidence
                    else None,
                },
                "model": classifier.model_status,
            }
        )


@extend_schema(
    tags=["admin-classifications"],
    summary="Recargar modelo de IA",
    description=(
        "Recarga el modelo Keras desde disco sin reiniciar el servidor. "
        "Útil tras actualizar `config.json` o `model.weights.h5` en el directorio `models/`."
    ),
    request=None,
    responses={
        200: inline_serializer(
            name="ModelReloadResponse",
            fields={
                "detail": serializers.CharField(),
                "model": serializers.DictField(),
            },
        ),
        500: OpenApiResponse(description="Error al recargar el modelo"),
    },
)
class AdminModelReloadView(APIView):
    permission_classes = (IsAdminOrStaff,)

    def post(self, request):
        try:
            classifier.reload()
            return Response(
                {
                    "detail": "Modelo recargado correctamente.",
                    "model": classifier.model_status,
                }
            )
        except Exception as exc:
            return Response(
                {"detail": f"Error al recargar el modelo: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
