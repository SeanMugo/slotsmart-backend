from rest_framework import serializers
from .models import ParkingSlot, Booking, PricingRule


class ParkingSlotSerializer(serializers.ModelSerializer):
    """Convert ParkingSlot to JSON"""
    is_available = serializers.SerializerMethodField()
    
    class Meta:
        model = ParkingSlot
        fields = '__all__'
    
    def get_is_available(self, obj):
        return obj.status == 'active'


class BookingSerializer(serializers.ModelSerializer):
    """Convert Booking to JSON"""
    user_details = serializers.SerializerMethodField()
    slot_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ['id', 'user', 'qr_code', 'created_at', 'penalty_amount']
    
    def get_user_details(self, obj):
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'email': obj.user.email
        }
    
    def get_slot_details(self, obj):
        return {
            'id': obj.slot.id,
            'slot_number': obj.slot.slot_number,
            'floor': obj.slot.floor,
            'zone': obj.slot.zone
        }


class PricingRuleSerializer(serializers.ModelSerializer):
    """Convert PricingRule to JSON"""
    class Meta:
        model = PricingRule
        fields = '__all__'