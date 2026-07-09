from rest_framework import serializers


class MpesaSTKPushSerializer(serializers.Serializer):
    phone_number = serializers.CharField(
        max_length=15,
    )

    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    parking_session_id = serializers.IntegerField()

    def validate_phone_number(self, value):
        """
        Accepts Kenyan phone numbers in the following formats:

        0722123456
        254722123456
        +254722123456

        Returns the number in the format required by Safaricom:
        254722123456
        """

        value = value.strip().replace(" ", "")

        # Convert +2547XXXXXXXX -> 2547XXXXXXXX
        if value.startswith("+254"):
            value = value[1:]

        # Convert 07XXXXXXXX -> 2547XXXXXXXX
        elif value.startswith("07"):
            value = "254" + value[1:]

        # Validate prefix
        if not value.startswith("254"):
            raise serializers.ValidationError(
                "Enter a valid Kenyan phone number."
            )

        # Validate length
        if len(value) != 12:
            raise serializers.ValidationError(
                "Phone number must contain exactly 12 digits."
            )

        # Validate digits only
        if not value.isdigit():
            raise serializers.ValidationError(
                "Phone number must contain digits only."
            )

        return value