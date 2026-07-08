# accounts/models.py

from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model.
    """

    ROLE_CHOICES = [
        ("driver", "Driver"),
        ("gate_staff", "Gate Staff"),
        ("admin", "Admin"),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="driver",
    )

    phone_number = models.CharField(
        max_length=15,
        blank=True,
        null=True,
    )

    wallet_balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    # ==========================================
    # WALLET HELPERS
    # ==========================================

    def has_enough_balance(self, amount):
        """
        Returns True if the wallet can fully cover the amount.
        """
        return self.wallet_balance >= amount

    def deduct_wallet(self, amount):
        """
        Deduct money from the wallet.
        Raises ValueError if insufficient funds.
        """
        amount = Decimal(amount)

        if amount > self.wallet_balance:
            raise ValueError("Insufficient wallet balance.")

        self.wallet_balance -= amount
        self.save(update_fields=["wallet_balance"])

    def credit_wallet(self, amount):
        """
        Add money to the wallet.
        """
        amount = Decimal(amount)

        self.wallet_balance += amount
        self.save(update_fields=["wallet_balance"])