# accounts/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Convert User objects to JSON and back"""
    wallet_balance = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'phone_number', 'wallet_balance', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_wallet_balance(self, obj):
        """Only return wallet balance for drivers"""
        if obj.role == 'driver':
            return str(obj.wallet_balance) if obj.wallet_balance is not None else "0.00"
        return None  # Hide for non-drivers


class RegisterSerializer(serializers.ModelSerializer):
    """Handle user registration with password confirmation"""
    
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password]
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True
    )
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'password2',
            'first_name', 'last_name', 'phone_number', 'role'
        ]
    
    def validate(self, attrs):
        """Check that passwords match"""
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({
                "password": "Password fields didn't match."
            })
        return attrs
    
    def create(self, validated_data):
        """Create the user with hashed password"""
        # Remove password2 from data
        validated_data.pop('password2')
        
        # Create user with hashed password
        user = User.objects.create_user(**validated_data)
        
        # Set initial wallet balance for drivers
        if user.role == 'driver':
            user.wallet_balance = 0.00
            user.save()
        
        return user


class LoginSerializer(serializers.Serializer):
    """Handle user login"""
    
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')
        
        # Try to authenticate user
        user = authenticate(username=username, password=password)
        
        if not user:
            raise serializers.ValidationError(
                "Invalid username or password"
            )
        
        if not user.is_active:
            raise serializers.ValidationError(
                "User account is disabled"
            )
        
        attrs['user'] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    """Handle password change"""
    
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(
        required=True,
        validators=[validate_password]
    )
    confirm_password = serializers.CharField(required=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({
                "confirm_password": "Passwords don't match"
            })
        return attrs


class AddTestMoneySerializer(serializers.Serializer):
    """Handle adding test money to driver wallet"""
    
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        default=1000.00,
        min_value=0.01
    )
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value


class UpdateWalletSerializer(serializers.Serializer):
    """Handle wallet balance updates (Admin only)"""
    
    driver_id = serializers.IntegerField(required=True)
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True
    )
    action = serializers.ChoiceField(
        choices=['add', 'deduct'],
        required=True
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default=""
    )
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value