# accounts/permissions.py
from rest_framework.permissions import BasePermission


class IsSuperUser(BasePermission):
    """Allows access only to superusers"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser


class IsAdminOrSuperAdmin(BasePermission):
    """Allows access to admin or superuser"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in ['admin', 'superuser'] or request.user.is_superuser


class IsStaffOrAdmin(BasePermission):
    """Allows access to staff, admin, or superuser"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in ['gate_staff', 'admin', 'superuser'] or request.user.is_superuser


class IsDriver(BasePermission):
    """Allows access only to drivers"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == 'driver'


class IsGateStaff(BasePermission):
    """Allows access only to gate staff"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == 'gate_staff'


class IsAdmin(BasePermission):
    """Allows access only to admins (not superusers)"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == 'admin'