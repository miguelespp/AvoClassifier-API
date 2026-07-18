from rest_framework import serializers

from .models import Classification, Lot, DiseaseCategory

MAX_IMAGE_SIZE_MB = 10
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

class ClassificationBaseSerializer(serializers.ModelSerializer):
    """
    Serializer base para ocultar información de ubicación
    cuando el fruto es saludable.
    """

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if instance.predicted_category == DiseaseCategory.SALUDABLE:
            data.pop("tree_code", None)
            data.pop("north_coordinate", None)
            data.pop("east_coordinate", None)

        return data


class ClassificationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classification
        fields = (
            "id", 
            "image", 
            "lot", 
            "tree_code",
            "north_coordinate",
            "east_coordinate",
            "webhook_url")
        
        extra_kwargs = {
            "tree_code": {"required": False},
            "north_coordinate": {"required": False},
            "east_coordinate": {"required": False},
        }

    def validate_image(self, image):
        if image.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
            raise serializers.ValidationError(
                f"La imagen no puede superar {MAX_IMAGE_SIZE_MB} MB."
            )
        content_type = getattr(image, "content_type", None)
        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError(
                "Solo se aceptan imágenes JPEG, PNG o WebP."
            )
        try:
            from PIL import Image as PilImage
            img = PilImage.open(image)
            img.verify()
            image.seek(0)
        except Exception:
            raise serializers.ValidationError(
                "El archivo no es una imagen válida o está corrupto."
            )
        return image

    def validate_lot(self, lot):
        """
        Verifica que el lote pertenezca al usuario autenticado.
        """
        request = self.context["request"]

        if lot.user != request.user:
            raise serializers.ValidationError(
                "No tienes permiso para utilizar este lote."
            )

        return lot
    
    
    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class ClassificationResultSerializer(ClassificationBaseSerializer):
    predicted_category_display = serializers.CharField(
        source="get_predicted_category_display",
        read_only=True,
    )

    class Meta:
        model = Classification
        fields = (
            "id",
            "image",
            "status",
            "predicted_category",
            "predicted_category_display",
            "confidence",
            "raw_scores",
            "tree_code",
            "north_coordinate",
            "east_coordinate",
            "error_message",
            "created_at",
            "classified_at",
        )
        read_only_fields = fields


class ClassificationLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classification
        fields = (
            "tree_code",
            "north_coordinate",
            "east_coordinate",
        )


class AdminClassificationSerializer(ClassificationBaseSerializer):
    """Extended serializer for admin — includes user info."""

    predicted_category_display = serializers.CharField(
        source="get_predicted_category_display",
        read_only=True,
    )
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = Classification
        fields = (
            "id",
            "user_id",
            "user_email",
            "image",
            "status",
            "predicted_category",
            "predicted_category_display",
            "confidence",
            "raw_scores",
            "tree_code",
            "north_coordinate",
            "east_coordinate",
            "error_message",
            "created_at",
            "classified_at",
            "deleted_at",
        )
        read_only_fields = fields
    


class LotSerializer(serializers.ModelSerializer):
    """
    Serializer para crear y listar lotes.
    """

    class Meta:
        model = Lot
        fields = (
            "id",
            "lot_name",
            "description",
            "lot_status",
            "total_images",
            "healthy_count",
            "anthracnose_count",
            "scab_count",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "lot_status",
            "total_images",
            "healthy_count",
            "anthracnose_count",
            "scab_count",
            "created_at",
            "updated_at",
        )
        

class ClassificationBulkCreateSerializer(serializers.Serializer):
    """
    Serializer para carga masiva de imágenes asociadas a un lote.
    """

    lot = serializers.PrimaryKeyRelatedField(
        queryset=Lot.objects.all()
    )

    images = serializers.ListField(
        child=serializers.ImageField(),
        allow_empty=False
    )

    def validate_lot(self, lot):
        """
        Verifica que el lote pertenezca al usuario autenticado.
        """
        request = self.context["request"]

        if lot.user != request.user:
            raise serializers.ValidationError(
                "No tienes permiso para utilizar este lote."
            )

        return lot
