from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class ParkingSlot(models.Model):
    """A physical parking space."""

    SLOT_TYPES = [
        ("car", "Car"),
        ("motorbike", "Motorbike"),
        ("ev", "Electric Vehicle"),
    ]

    ZONES = [
        ("A", "Zone A - Premium"),
        ("B", "Zone B - Standard"),
        ("C", "Zone C - Economy"),
    ]

    STATUS_CHOICES = [
        ("available", "Available"),
        ("occupied", "Occupied"),
        ("maintenance", "Maintenance"),
    ]

    slot_number = models.CharField(max_length=10, unique=True)

    floor = models.PositiveIntegerField()

    zone = models.CharField(
        max_length=1,
        choices=ZONES,
    )

    slot_type = models.CharField(
        max_length=20,
        choices=SLOT_TYPES,
    )

    has_charger = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="available",
    )

    base_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "parking_slots"
        ordering = ["floor", "slot_number"]

    def __str__(self):
        return self.slot_number


class ParkingSession(models.Model):
    """Represents one parking visit."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
    ]

    PAYMENT_STATUS = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    PAYMENT_METHOD = [
        ("wallet", "Wallet"),
        ("mpesa", "M-Pesa"),
        ("hybrid", "Wallet + M-Pesa"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="parking_sessions",
    )

    slot = models.ForeignKey(
        ParkingSlot,
        on_delete=models.PROTECT,
        related_name="sessions",
    )

    license_plate = models.CharField(max_length=20)

    check_in_time = models.DateTimeField(auto_now_add=True)

    check_out_time = models.DateTimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    hourly_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
    )

    duration_hours = models.PositiveIntegerField(
        default=0,
    )

    # ==========================
    # PAYMENT DETAILS
    # ==========================

    total_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    wallet_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    mpesa_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS,
        default="pending",
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "parking_sessions"
        ordering = ["-check_in_time"]

    def save(self, *args, **kwargs):
        self.license_plate = self.license_plate.upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.license_plate} - {self.slot.slot_number}"


class WalletTransaction(models.Model):
    """
    Records every wallet/M-Pesa payment.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="wallet_transactions",
    )

    parking_session = models.ForeignKey(
        ParkingSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    wallet_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    mpesa_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    mpesa_receipt = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    description = models.CharField(
        max_length=255,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wallet_transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"KES {self.total_amount}"
        )


class PricingRule(models.Model):
    """
    Future feature.
    Not used in Version 1.
    """

    zone = models.CharField(
        max_length=1,
        null=True,
        blank=True,
    )

    day_of_week = models.IntegerField()

    start_hour = models.TimeField()

    end_hour = models.TimeField()

    multiplier = models.DecimalField(
        max_digits=3,
        decimal_places=1,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pricing_rules"

    def __str__(self):
        zone = self.zone or "All Zones"
        return f"{zone} x{self.multiplier}"