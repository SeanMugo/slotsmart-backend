from rest_framework import serializers

from .models import (
    ParkingSlot,
    ParkingSession,
    PricingRule,
)


class ParkingSlotSerializer(serializers.ModelSerializer):
    is_available = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = ParkingSlot
        fields = "__all__"

    def get_is_available(self, obj):
        return obj.status == "available"

    def get_status_display(self, obj):
        return dict(ParkingSlot.STATUS_CHOICES).get(
            obj.status,
            obj.status,
        )


class ParkingSessionSerializer(serializers.ModelSerializer):
    user_details = serializers.SerializerMethodField()
    slot_details = serializers.SerializerMethodField()

    class Meta:
        model = ParkingSession
        fields = "__all__"
        read_only_fields = [
            "id",
            "user",
            "check_in_time",
            "check_out_time",
            "duration_hours",
            "amount_due",
            "created_at",
            "updated_at",
        ]

    def get_user_details(self, obj):
        return {
            "id": obj.user.id,
            "username": obj.user.username,
            "email": obj.user.email,
        }

    def get_slot_details(self, obj):
        return {
            "id": obj.slot.id,
            "slot_number": obj.slot.slot_number,
            "floor": obj.slot.floor,
            "zone": obj.slot.zone,
            "slot_type": obj.slot.slot_type,
            "hourly_rate": obj.slot.base_rate,
        }

    def validate_license_plate(self, value):
        value = value.strip().upper()

        if len(value) < 6:
            raise serializers.ValidationError(
                "Enter a valid license plate."
            )

        return value


class PricingRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingRule
        fields = "__all__"