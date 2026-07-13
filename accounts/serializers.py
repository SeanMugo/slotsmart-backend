from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import User

User = get_user_model

class UserSerializer(serializers.ModelSerializer):
    """User details."""

    wallet_balance = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "phone_number",
            "default_vehicle",
            "wallet_balance",
            "is_active",          # <-- ADD THIS
            "created_at",
        ]

        read_only_fields = [
            "id",
            "wallet_balance",
            "is_active",          # <-- ADD THIS
            "created_at",
        ]

    def get_wallet_balance(self, obj):
        if obj.role == "driver":
            return str(obj.wallet_balance)
        return None


class UpdateProfileSerializer(serializers.ModelSerializer):
    """
    Logged-in user updates their own profile.
    """

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "default_vehicle",
        ]


class AdminUpdateUserSerializer(serializers.ModelSerializer):
    """
    Admin updates user information.
    """

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "default_vehicle",
            "role",
        ]


class RegisterSerializer(serializers.ModelSerializer):
    """
    Public registration.
    Every registered user becomes a DRIVER.
    """

    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )

    password2 = serializers.CharField(
        write_only=True,
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "password2",
            "first_name",
            "last_name",
            "phone_number",
        ]

    def validate(self, attrs):

        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {
                    "password": "Passwords do not match."
                }
            )

        return attrs

    def create(self, validated_data):

        validated_data.pop("password2")

        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email"),
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            phone_number=validated_data.get("phone_number", ""),
            role="driver",
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs["username"]
        password = attrs["password"]

        try:
            user = User.objects.get(username=username)

        except User.DoesNotExist:
            raise serializers.ValidationError(
                "Invalid username or password."
            )

        if not user.is_active:
            raise serializers.ValidationError(
                "Your account has been deactivated. Please contact an administrator."
            )

        user = authenticate(
            username=username,
            password=password,
        )

        if not user:
            raise serializers.ValidationError(
                "Invalid username or password."
            )

        attrs["user"] = user
        return attrs

class ChangePasswordSerializer(serializers.Serializer):

    old_password = serializers.CharField()

    new_password = serializers.CharField(
        validators=[validate_password],
    )

    confirm_password = serializers.CharField()

    def validate(self, attrs):

        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {
                    "confirm_password": "Passwords do not match."
                }
            )

        return attrs


class AddTestMoneySerializer(serializers.Serializer):

    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1000.00,
    )


class UpdateWalletSerializer(serializers.Serializer):

    driver_id = serializers.IntegerField()

    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    action = serializers.ChoiceField(
        choices=["add", "deduct"]
    )

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )