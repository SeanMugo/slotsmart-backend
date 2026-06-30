from rest_framework import serializers
from .models import ParkingSlot, Booking, PricingRule


class ParkingSlotSerializer(serializers.ModelSerializer):
    is_available = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    
    class Meta:
        model = ParkingSlot
        fields = '__all__'
    
    def get_is_available(self, obj):
        return obj.status == 'available'
    
    def get_status_display(self, obj):
        return dict(ParkingSlot.STATUS_CHOICES).get(obj.status, obj.status)


class BookingSerializer(serializers.ModelSerializer):
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
    class Meta:
        model = PricingRule
        fields = '__all__'