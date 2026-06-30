from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.indexes import GistIndex

User = get_user_model()


class ParkingSlot(models.Model):
    """A physical parking spot"""
    
    SLOT_TYPES = [
        ('car', 'Car'),
        ('bike', 'Bike'),
        ('ev', 'EV Charging'),
    ]
    
    ZONES = [
        ('A', 'Zone A - Premium'),
        ('B', 'Zone B - Standard'),
        ('C', 'Zone C - Economy'),
    ]
    
    # Basic info
    slot_number = models.CharField(max_length=10, unique=True)
    floor = models.IntegerField()
    zone = models.CharField(max_length=2, choices=ZONES)
    slot_type = models.CharField(max_length=10, choices=SLOT_TYPES)
    
    # Features
    has_charger = models.BooleanField(default=False)
    
    # Status
    status = models.CharField(max_length=20, default='active')
    
    # Pricing
    base_rate = models.DecimalField(max_digits=6, decimal_places=2)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.slot_number} (Floor {self.floor}, {self.zone})"
    
    class Meta:
        db_table = 'parking_slots'  # Optional
        indexes = [
            models.Index(fields=['floor', 'status']),
            models.Index(fields=['zone', 'slot_type']),
        ]


class Booking(models.Model):
    """A parking reservation"""
    
    STATUS_CHOICES = [
        ('reserved', 'Reserved'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('overdue', 'Overdue'),
    ]
    
    # Relationships
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    slot = models.ForeignKey(ParkingSlot, on_delete=models.PROTECT)
    
    # Vehicle info
    vehicle_number = models.CharField(max_length=20)
    
    # Time
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='reserved')
    
    # Pricing
    price_per_hour = models.DecimalField(max_digits=6, decimal_places=2)
    total_price = models.DecimalField(max_digits=8, decimal_places=2)
    penalty_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    
    # QR Code
    qr_code = models.TextField(blank=True, null=True)
    
    # Check-in/out
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Booking #{self.id} - {self.slot.slot_number} ({self.status})"
    
    class Meta:
        db_table = 'bookings'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['start_time']),
            models.Index(fields=['slot', 'start_time', 'end_time']),
        ]


class PricingRule(models.Model):
    """Dynamic pricing rules"""
    
    zone = models.CharField(max_length=2, null=True, blank=True)
    day_of_week = models.IntegerField()  # 0=Monday
    start_hour = models.TimeField()
    end_hour = models.TimeField()
    multiplier = models.DecimalField(max_digits=3, decimal_places=1)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        zone_str = self.zone or "All Zones"
        return f"{zone_str} - Day {self.day_of_week}: {self.start_hour}-{self.end_hour} (x{self.multiplier})"
    
    class Meta:
        db_table = 'pricing_rules'