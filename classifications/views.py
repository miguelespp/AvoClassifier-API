import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.contrib.auth import get_user_model

_executor = ThreadPoolExecutor(max_workers=4)
from django.db.models import Avg, Count
from django.http import StreamingHttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView


class ClassificationThrottle(UserRateThrottle):
    scope = "classification"


class AdminPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

from users.permissions import IsAdminOrStaff

from .ai_service import classifier
from .models import (
    Classification,
    ClassificationStatus,
    DiseaseCategory,
    Lot,
)
from .serializers import (
    AdminClassificationSerializer,
    ClassificationCreateSerializer,
    ClassificationBulkCreateSerializer,
    ClassificationResultSerializer,
    LotSerializer,
    ClassificationLocationSerializer,
)
from .services import run_classification

User = get_user_model()


# ---------------------------------------------------------------------------
# User-facing views
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["classifications"],
    summary="Crear y listar lotes",
    description=(
        "Permite crear un nuevo lote o listar los lotes "
        "registrados por el usuario autenticado."
    ),
)
class LotListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = LotSerializer

    def get_queryset(self):
        return Lot.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        
# CRUD para el lote
@extend_schema(
    tags=["classifications"],
    summary="Consultar, editar o eliminar un lote",
)
class LotDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = LotSerializer

    def get_queryset(self):
        # Solo puede acceder a sus propios lotes
        return Lot.objects.filter(user=self.request.user)

@extend_schema(
    tags=["classifications"],
    summary="Clasificar imagen de aguacate",
    description=(
        "Sube una imagen JPG/PNG y encola la clasificación de enfermedad.\n\n"
        "**Formato de la petición:** `multipart/form-data` con el campo `image`.\n\n"
        "**Categorías posibles:** `saludable`, `antracnosis`, `sarna`.\n\n"
        "Devuelve **202 Accepted** inmediatamente con `status: pending`. "
        "Haz polling a `GET /api/classifications/{id}/` hasta que `status` "
        "sea `completed` o `failed`."
    ),
    request={"multipart/form-data": ClassificationCreateSerializer},
    responses={202: ClassificationResultSerializer},
)

class ClassificationCreateView(generics.CreateAPIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (ClassificationThrottle,)
    serializer_class = ClassificationCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()
        _executor.submit(run_classification, classification.pk)
        return Response(
            ClassificationResultSerializer(classification).data,
            status=status.HTTP_202_ACCEPTED,
        )


@extend_schema(
    tags=["classifications"],
    summary="Carga masiva de imágenes por lote",
    description=(
        "Carga múltiples imágenes, ejecuta la clasificación "
        "y devuelve los resultados completos."
    ),
)
class ClassificationBulkCreateView(generics.CreateAPIView):

    permission_classes = (IsAuthenticated,)
    serializer_class = ClassificationBulkCreateSerializer

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        lot = serializer.validated_data["lot"]
        images = serializer.validated_data["images"]

        results = []

        for image in images:

            classification = Classification.objects.create(
                user=request.user,
                lot=lot,
                image=image,
            )

            # Ejecuta la IA y espera el resultado
            run_classification(classification.pk)

            # Recarga el objeto desde la BD porque run_classification()
            # actualiza los campos en la base de datos
            classification.refresh_from_db()

            results.append(
                ClassificationResultSerializer(
                    classification,
                    context={"request": request}
                ).data
            )

        return Response(
            {
                "lot": lot.id,
                "classifications": results,
                "status": "completed"
            },
            status=status.HTTP_201_CREATED
        )
        
        
@extend_schema(
    tags=["classifications"],
    summary="Resultado de clasificación",
    description="Consulta el estado y resultado de una clasificación por ID. Útil para polling.",
    responses={200: ClassificationResultSerializer},
)
class ClassificationDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsAuthenticated,)
    def get_queryset(self):
        return Classification.objects.filter(
            user=self.request.user
        )

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ClassificationLocationSerializer

        return ClassificationResultSerializer


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
# CSV export
# ---------------------------------------------------------------------------


class _EchoBuffer:
    def write(self, value):
        return value


@extend_schema(
    tags=["classifications"],
    summary="Exportar historial en CSV",
    description="Descarga todas las clasificaciones del usuario autenticado como archivo CSV.",
    responses={200: None},
)
class ClassificationExportCSVView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        qs = (
            Classification.objects.filter(user=request.user)
            .order_by("-created_at")
            .values_list(
                "id", "status", "predicted_category", "confidence",
                "error_message", "created_at", "classified_at",
            )
        )

        header = ["id", "status", "predicted_category", "confidence",
                  "error_message", "created_at", "classified_at"]

        def rows():
            writer = csv.writer(_EchoBuffer())
            yield writer.writerow(header)
            for row in qs:
                yield writer.writerow(row)

        response = StreamingHttpResponse(rows(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="clasificaciones.csv"'
        return response


# ---------------------------------------------------------------------------
# User stats view
# ---------------------------------------------------------------------------


@extend_schema(
    tags=["classifications"],
    summary="Estadísticas propias del usuario",
    description="Devuelve un resumen de las clasificaciones del usuario autenticado.",
    responses={
        200: inline_serializer(
            name="UserStats",
            fields={
                "total": serializers.IntegerField(),
                "by_status": serializers.DictField(),
                "by_category": serializers.DictField(),
                "average_confidence": serializers.FloatField(allow_null=True),
                "recent_7_days": serializers.IntegerField(),
            },
        )
    },
)
class UserStatsView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        qs = Classification.objects.filter(user=request.user)

        by_status = dict(
            qs.values("status").annotate(count=Count("id")).values_list("status", "count")
        )
        by_category = dict(
            qs.filter(status=ClassificationStatus.COMPLETED)
            .values("predicted_category")
            .annotate(count=Count("id"))
            .values_list("predicted_category", "count")
        )
        avg_confidence = qs.filter(
            status=ClassificationStatus.COMPLETED, confidence__isnull=False
        ).aggregate(avg=Avg("confidence"))["avg"]

        seven_days_ago = timezone.now() - timedelta(days=7)
        recent = qs.filter(created_at__gte=seven_days_ago).count()

        return Response(
            {
                "total": qs.count(),
                "by_status": by_status,
                "by_category": by_category,
                "average_confidence": round(avg_confidence, 4) if avg_confidence else None,
                "recent_7_days": recent,
            }
        )


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
            description="Filtra por categoría: `saludable`, `antracnosis`, `sarna`",
            enum=["saludable", "antracnosis", "sarna"],
        ),
        OpenApiParameter("user_id", int, description="Filtra por ID de usuario"),
        OpenApiParameter("search", str, description="Filtra por email del usuario"),
        OpenApiParameter("include_deleted", bool, description="Incluir registros eliminados (soft delete)"),
    ],
    responses={200: AdminClassificationSerializer(many=True)},
)
class AdminClassificationListView(generics.ListAPIView):
    permission_classes = (IsAdminOrStaff,)
    serializer_class = AdminClassificationSerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        include_deleted = self.request.query_params.get("include_deleted", "").lower() == "true"
        base_manager = Classification.objects.with_deleted() if include_deleted else Classification.objects
        qs = base_manager.select_related("user").order_by("-created_at")

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
        summary="Eliminar clasificación (soft delete)",
        responses={204: OpenApiResponse(description="Clasificación marcada como eliminada")},
    ),
)
class AdminClassificationDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = (IsAdminOrStaff,)
    serializer_class = AdminClassificationSerializer
    queryset = Classification.objects.with_deleted().select_related("user").all()

    def perform_destroy(self, instance):
        instance.soft_delete()


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
