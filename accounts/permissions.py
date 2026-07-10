from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """
    Allows access only to Admin users.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == "admin"
        )


class IsGateStaff(BasePermission):
    """
    Allows access only to Gate Staff.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == "gate_staff"
        )


class IsDriver(BasePermission):
    """
    Allows access only to Drivers.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == "driver"
        )


class IsGateStaffOrAdmin(BasePermission):

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in ["gate_staff", "admin"]
        )