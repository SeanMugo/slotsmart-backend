from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.permissions import IsGateStaffOrAdmin

from .models import ParkingSlot, ParkingSession
from .serializers import (
    ParkingSlotSerializer,
    ParkingSessionSerializer,
)
from .utils import calculate_parking_fee
from .services import process_payment

User = get_user_model()


class ParkingSlotViewSet(viewsets.ModelViewSet):
    """
    View and edit parking slots.
    """

    serializer_class = ParkingSlotSerializer

    def get_permissions(self):
        """
        Everyone can view parking slots.
        Only Admins can edit them.
        """

        if self.action in [
            "update",
            "partial_update",
            "destroy",
            "create",
        ]:
            if (
                self.request.user.is_authenticated
                and self.request.user.role == "admin"
            ):
                return [IsAuthenticated()]

            return [IsAuthenticated()]

        return [IsAuthenticated()]

    def get_queryset(self):
        return ParkingSlot.objects.all().order_by(
            "floor",
            "slot_number",
        )
    def perform_update(self, serializer):
        """
        Prevent editing occupied parking slots.
        """

        slot = self.get_object()

        if slot.status == "occupied":
            raise serializers.ValidationError(
                "Occupied parking slots cannot be edited."
            )

        serializer.save()


    def perform_destroy(self, instance):
        """
        Prevent deleting occupied parking slots.
        """

        if instance.status == "occupied":
            raise serializers.ValidationError(
                "Occupied parking slots cannot be deleted."
            )

        instance.delete()

class ParkingSessionViewSet(viewsets.ModelViewSet):
    """
    Manage parking sessions.
    """

    serializer_class = ParkingSessionSerializer

    def get_permissions(self):
        """
        Only Gate Staff/Admin can perform
        check-in and check-out.
        """

        if self.action in ["check_in", "check_out"]:
            return [IsGateStaffOrAdmin()]

        return [IsAuthenticated()]

    def get_queryset(self):

        user = self.request.user

        # Admin sees everything
        if user.role == "admin":
            return ParkingSession.objects.all()

        # Gate Staff sees everything
        if user.role == "gate_staff":
            return ParkingSession.objects.all()

        # Drivers only see their own sessions
        return ParkingSession.objects.filter(user=user)

    @action(detail=False, methods=["get"])
    def active(self, request):
        """
        Return active parking sessions.
        """

        if request.user.role in ["admin", "gate_staff"]:

            sessions = ParkingSession.objects.filter(
                status="active"
            )

            serializer = self.get_serializer(
                sessions,
                many=True,
            )

            return Response(serializer.data)

        session = ParkingSession.objects.filter(
            user=request.user,
            status="active",
        ).first()

        if session is None:
            return Response(
                {
                    "message": "No active parking session."
                }
            )

        serializer = self.get_serializer(session)

        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def history(self, request):
        """
        Parking history.
        """

        sessions = self.get_queryset().filter(
            status="completed"
        ).order_by("-check_in_time")

        serializer = self.get_serializer(
            sessions,
            many=True,
        )

        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def check_in(self, request):
        """
        Gate Staff checks a driver into parking.
        """

        driver_id = request.data.get("driver_id")
        slot_id = request.data.get("slot_id")
        license_plate = request.data.get("license_plate")

        if not all([driver_id, slot_id, license_plate]):
            return Response(
                {
                    "error": "driver_id, slot_id and license_plate are required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            driver = User.objects.get(
                id=driver_id,
                role="driver",
            )

        except User.DoesNotExist:
            return Response(
                {
                    "error": "Driver not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if ParkingSession.objects.filter(
            user=driver,
            status="active",
        ).exists():
            return Response(
                {
                    "error": "Driver already has an active parking session."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            slot = ParkingSlot.objects.get(id=slot_id)

        except ParkingSlot.DoesNotExist:
            return Response(
                {
                    "error": "Parking slot not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if slot.status != "available":
            return Response(
                {
                    "error": "Parking slot is not available."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = ParkingSession.objects.create(
            user=driver,
            slot=slot,
            license_plate=license_plate,
            hourly_rate=slot.base_rate,
        )

        slot.status = "occupied"
        slot.save()

        serializer = self.get_serializer(session)

        return Response(
            {
                "message": "Vehicle checked in successfully.",
                "session": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def check_out(self, request, pk=None):
        """
        Gate Staff checks a vehicle out.
        """

        try:
            session = ParkingSession.objects.get(pk=pk)

        except ParkingSession.DoesNotExist:
            return Response(
                {
                    "error": "Parking session not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if session.status != "active":
            return Response(
                {
                    "error": "This parking session has already been completed."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Record checkout time
        session.check_out_time = timezone.now()

        # Calculate parking duration and fee
        summary = calculate_parking_fee(session)

        session.duration_hours = summary["duration_hours"]
        session.total_fee = summary["total_fee"]

        # Determine payment flow
        payment = process_payment(session)

        session.save()

        # Wallet payment only
        if not payment["payment_required"]:

            session.status = "completed"
            session.payment_status = "paid"
            session.save()

            slot = session.slot
            slot.status = "available"
            slot.save()

            serializer = self.get_serializer(session)

            return Response(
                {
                    "success": True,
                    "message": "Payment completed successfully using wallet.",
                    "payment_method": "wallet",
                    "duration_hours": session.duration_hours,
                    "total_fee": session.total_fee,
                    "session": serializer.data,
                }
            )

        # Hybrid or M-Pesa payment required
        serializer = self.get_serializer(session)

        return Response(
            {
                "success": True,
                "payment_required": True,
                "payment_method": payment["payment_method"],
                "wallet_used": payment["wallet_used"],
                "mpesa_required": payment["mpesa_required"],
                "duration_hours": session.duration_hours,
                "total_fee": session.total_fee,
                "session": serializer.data,
            }
        )