# accounts/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):

    ROLE_CHOICES = [
        ('driver', 'Driver'),
        ('gate_staff', 'Gate Staff'),
        ('admin', 'Admin'),
        ('super_admin', 'Super Admin'),
    ]
    
    # Role field - determines what user can do
    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default='driver'
    )
    
    # Contact information
    phone_number = models.CharField(
        max_length=15, 
        blank=True, 
        null=True
    )
    
    # Wallet for parking payments
    wallet_balance = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        """String representation of the user"""
        return f"{self.username} ({self.role})"
    
    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
        ]