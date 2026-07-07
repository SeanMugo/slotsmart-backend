# parking/admin.py

from django.contrib import admin
from .models import (
    ParkingSlot,
    ParkingSession,
    PricingRule,
)


@admin.register(ParkingSlot)
class ParkingSlotAdmin(admin.ModelAdmin):
    list_display = (
        "slot_number",
        "floor",
        "zone",
        "slot_type",
        "status",
        "base_rate",
    )

    list_filter = (
        "floor",
        "zone",
        "status",
        "slot_type",
    )

    search_fields = (
        "slot_number",
    )


@admin.register(ParkingSession)
class ParkingSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "license_plate",
        "slot",
        "status",
        "amount_due",
        "check_in_time",
        "check_out_time",
    )

    list_filter = (
        "status",
        "check_in_time",
    )

    search_fields = (
        "license_plate",
        "user__username",
        "slot__slot_number",
    )


@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    list_display = (
        "zone",
        "day_of_week",
        "start_hour",
        "end_hour",
        "multiplier",
        "is_active",
    )

    list_filter = (
        "is_active",
        "day_of_week",
    )