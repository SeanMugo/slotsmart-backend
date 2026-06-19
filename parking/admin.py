# parking/admin.py
from django.contrib import admin
from .models import ParkingSlot, Booking, PricingRule

@admin.register(ParkingSlot)
class ParkingSlotAdmin(admin.ModelAdmin):
    list_display = ('slot_number', 'floor', 'zone', 'slot_type', 'status', 'base_rate')
    list_filter = ('floor', 'zone', 'status', 'slot_type')
    search_fields = ('slot_number',)

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'slot', 'vehicle_number', 'status', 'total_price')
    list_filter = ('status', 'created_at')
    search_fields = ('vehicle_number', 'user__username')

@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    list_display = ('zone', 'day_of_week', 'start_hour', 'end_hour', 'multiplier', 'is_active')
    list_filter = ('is_active', 'day_of_week')