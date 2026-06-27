from rest_framework import serializers

from .models import Classification

MAX_IMAGE_SIZE_MB = 10
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ClassificationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classification
        fields = ("id", "image", "webhook_url")

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

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class ClassificationResultSerializer(serializers.ModelSerializer):
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
            "error_message",
            "created_at",
            "classified_at",
        )
        read_only_fields = fields


class AdminClassificationSerializer(serializers.ModelSerializer):
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
            "error_message",
            "created_at",
            "classified_at",
            "deleted_at",
        )
        read_only_fields = fields
