from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class MpesaTransaction(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
    )

    parking_session = models.ForeignKey(
        "parking.ParkingSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mpesa_transactions",
    )

    phone_number = models.CharField(
        max_length=15,
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    merchant_request_id = models.CharField(
        max_length=100,
        unique=True,
    )

    checkout_request_id = models.CharField(
        max_length=100,
        unique=True,
    )

    mpesa_receipt = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    response_code = models.IntegerField(
        null=True,
        blank=True,
    )

    response_description = models.TextField(
        blank=True,
    )

    # Time Safaricom says the payment happened
    transaction_date = models.DateTimeField(
        null=True,
        blank=True,
    )

    # Raw callback for debugging (very useful)
    callback_data = models.JSONField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "mpesa_transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"KES {self.amount} - "
            f"{self.status}"
        )