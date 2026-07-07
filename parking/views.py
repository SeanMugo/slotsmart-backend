from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.utils import timezone

from .models import ParkingSlot, ParkingSession
from .serializers import (
    ParkingSlotSerializer,
    ParkingSessionSerializer,
)
from .utils import checkout_summary


class ParkingSlotViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View all parking slots.
    """

    serializer_class = ParkingSlotSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ParkingSlot.objects.all().order_by(
            "floor",
            "slot_number",
        )


class ParkingSessionViewSet(viewsets.ModelViewSet):
    """
    Manage parking sessions.
    """

    serializer_class = ParkingSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role == "admin":
            return ParkingSession.objects.all()

        return ParkingSession.objects.filter(
            user=user
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get"])
    def active(self, request):
        """
        Return the user's active parking session.
        """

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
        Return completed parking sessions.
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
        Check a vehicle into the parking lot.
        """

        user = request.user

        if ParkingSession.objects.filter(
            user=user,
            status="active",
        ).exists():
            return Response(
                {
                    "error": "You already have an active parking session."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        slot_id = request.data.get("slot_id")
        license_plate = request.data.get("license_plate")

        if not slot_id or not license_plate:
            return Response(
                {
                    "error": "slot_id and license_plate are required."
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
                    "error": "This parking slot is not available."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = ParkingSession.objects.create(
            user=user,
            slot=slot,
            license_plate=license_plate,
            hourly_rate=slot.base_rate,
        )

        slot.status = "occupied"
        slot.save()

        serializer = self.get_serializer(session)

        return Response(
            {
                "message": "Check-in successful.",
                "session": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def check_out(self, request, pk=None):
        """
        Check a vehicle out of the parking lot.
        """

        try:
            session = self.get_queryset().get(pk=pk)

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

        session.check_out_time = timezone.now()

        summary = checkout_summary(session)

        session.duration_hours = summary["duration_hours"]
        session.amount_due = summary["amount_due"]

        session.status = "completed"
        session.save()

        slot = session.slot
        slot.status = "available"
        slot.save()

        serializer = self.get_serializer(session)

        return Response(
            {
                "message": "Check-out successful.",
                "duration_hours": session.duration_hours,
                "amount_due": session.amount_due,
                "session": serializer.data,
            },
            status=status.HTTP_200_OK,
        )