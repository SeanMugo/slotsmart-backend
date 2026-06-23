from rest_framework import serializers

class MpesaSTKPushSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_phone_number(self, value):
        if not value.startswith('254'):
            raise serializers.ValidationError("Phone number must start with 254")
        if len(value) != 12:
            raise serializers.ValidationError("Phone number must be 12 digits")
        return value