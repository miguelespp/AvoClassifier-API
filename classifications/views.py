from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Classification
from .serializers import ClassificationCreateSerializer, ClassificationResultSerializer
from .services import run_classification


class ClassificationCreateView(generics.CreateAPIView):
    """
    POST /api/classifications/
    Sube una imagen y dispara la clasificación.

    Cuando el modelo de IA esté integrado la respuesta tendrá status=completed.
    Mientras tanto devuelve status=failed con el error de NotImplementedError.

    Si el procesamiento es lento, mover run_classification() a una tarea
    asíncrona (Celery) y que el cliente haga polling al endpoint de detalle.
    """

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


class ClassificationDetailView(generics.RetrieveAPIView):
    """
    GET /api/classifications/<id>/
    Consulta el resultado de una clasificación (útil para polling).
    """

    permission_classes = (IsAuthenticated,)
    serializer_class = ClassificationResultSerializer

    def get_queryset(self):
        return Classification.objects.filter(user=self.request.user)


class ClassificationListView(generics.ListAPIView):
    """
    GET /api/classifications/history/
    Historial de clasificaciones del usuario autenticado.
    """

    permission_classes = (IsAuthenticated,)
    serializer_class = ClassificationResultSerializer

    def get_queryset(self):
        return Classification.objects.filter(user=self.request.user)
