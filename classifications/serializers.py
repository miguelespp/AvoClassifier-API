from rest_framework import serializers

from .models import Classification


class ClassificationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classification
        fields = ("id", "image")

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
        )
        read_only_fields = fields
