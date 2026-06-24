# parking/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
import qrcode
from io import BytesIO
import base64
from datetime import timedelta

from .models import ParkingSlot, Booking, PricingRule
from .serializers import ParkingSlotSerializer, BookingSerializer, PricingRuleSerializer
from accounts.permissions import IsDriver, IsGateStaff, IsAdminOrSuperAdmin, IsStaffOrAdmin


class ParkingSlotViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View parking slots and check availability
    ✅ Anyone logged in can view slots
    """
    queryset = ParkingSlot.objects.filter(status='active')
    serializer_class = ParkingSlotSerializer
    permission_classes = [IsAuthenticated]  # ✅ Any logged-in user
    
    @action(detail=False, methods=['get'])
    def available(self, request):
        """
        GET /api/slots/available/?start=...&end=...&type=...
        Returns available slots for the given time range
        """
        start_time = request.query_params.get('start')
        end_time = request.query_params.get('end')
        slot_type = request.query_params.get('type', 'car')
        
        if not start_time or not end_time:
            return Response(
                {'error': 'Missing start/end time parameters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start = timezone.datetime.fromisoformat(start_time)
            end = timezone.datetime.fromisoformat(end_time)
            
            if not timezone.is_aware(start):
                start = timezone.make_aware(start)
            if not timezone.is_aware(end):
                end = timezone.make_aware(end)
                
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use: 2024-01-20T10:00:00+00:00'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        available_slots = ParkingSlot.objects.filter(
            slot_type=slot_type,
            status='active'
        ).exclude(
            booking__start_time__lt=end,
            booking__end_time__gt=start,
            booking__status__in=['reserved', 'active']
        )
        
        result = []
        for slot in available_slots:
            price = self.calculate_price(slot, start)
            slot_data = ParkingSlotSerializer(slot).data
            slot_data['current_price'] = price
            result.append(slot_data)
        
        return Response(result)
    
    def calculate_price(self, slot, booking_time):
        """Calculate price based on time and rules"""
        base_price = float(slot.base_rate)
        hour = booking_time.hour
        
        if (8 <= hour <= 10) or (17 <= hour <= 19):
            return round(base_price * 1.5, 2)
        elif hour >= 23 or hour <= 6:
            return round(base_price * 0.7, 2)
        return round(base_price, 2)


class BookingViewSet(viewsets.ModelViewSet):
    """
    Create and manage bookings
    ✅ Drivers can create bookings
    ✅ Gate Staff can check in/out
    ✅ Admins can view all bookings
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """
        ✅ Role-based permissions per action
        """
        if self.action == 'create':
            return [IsDriver()]  # ✅ Only drivers can create bookings
        elif self.action in ['check_in', 'check_out']:
            return [IsGateStaff()]  # ✅ Only gate staff can check in/out
        elif self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]  # ✅ Anyone can view their own bookings
        return [IsAuthenticated()]

    def get_queryset(self):
        """
        ✅ Users see only their own bookings
        ✅ Admins see all bookings
        """
        user = self.request.user
        if user.role in ['admin', 'super_admin']:
            return Booking.objects.all()  # Admins see all
        return Booking.objects.filter(user=user)  # Others see their own
    
    @transaction.atomic
    def create(self, request):
        """
        POST /api/bookings/
        ✅ Only DRIVERS can create bookings
        """
        slot_id = request.data.get('slot_id')
        start_time = request.data.get('start_time')
        end_time = request.data.get('end_time')
        vehicle_number = request.data.get('vehicle_number')
        
        if not all([slot_id, start_time, end_time, vehicle_number]):
            return Response(
                {'error': 'Missing required fields: slot_id, start_time, end_time, vehicle_number'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start = timezone.datetime.fromisoformat(start_time)
            end = timezone.datetime.fromisoformat(end_time)
            
            if not timezone.is_aware(start):
                start = timezone.make_aware(start)
            if not timezone.is_aware(end):
                end = timezone.make_aware(end)
                
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use: 2024-01-20T10:00:00+00:00'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if start < timezone.now():
            return Response(
                {'error': 'Start time must be in the future'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            slot = ParkingSlot.objects.select_for_update().get(id=slot_id)
        except ParkingSlot.DoesNotExist:
            return Response(
                {'error': 'Slot not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        overlap = Booking.objects.filter(
            slot=slot,
            start_time__lt=end,
            end_time__gt=start,
            status__in=['reserved', 'active']
        ).exists()
        
        if overlap:
            return Response(
                {'error': 'Slot already booked for this time'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        duration_hours = (end - start).total_seconds() / 3600
        price_per_hour = self.calculate_price(slot, start)
        total_price = round(duration_hours * price_per_hour, 2)
        
        qr_data = f"SLOTSMART|{slot.id}|{start.isoformat()}|{end.isoformat()}"
        qr = qrcode.make(qr_data)
        buffer = BytesIO()
        qr.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        booking = Booking.objects.create(
            user=request.user,
            slot=slot,
            vehicle_number=vehicle_number,
            start_time=start,
            end_time=end,
            price_per_hour=price_per_hour,
            total_price=total_price,
            qr_code=qr_base64,
            status='reserved'
        )
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def calculate_price(self, slot, booking_time):
        base_price = float(slot.base_rate)
        hour = booking_time.hour
        
        if (8 <= hour <= 10) or (17 <= hour <= 19):
            return round(base_price * 1.5, 2)
        elif hour >= 23 or hour <= 6:
            return round(base_price * 0.7, 2)
        return round(base_price, 2)
    
    @action(detail=True, methods=['post'])
    def check_in(self, request, pk=None):
        """
        POST /api/bookings/{id}/check_in/
        ✅ Only GATE STAFF can check in vehicles
        """
        booking = self.get_object()
        
        if booking.status != 'reserved':
            return Response(
                {'error': f'Booking is {booking.status}. Only reserved can be checked in.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if timezone.now() > booking.end_time:
            booking.status = 'overdue'
            booking.save()
            return Response(
                {'error': 'Booking has expired'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'active'
        booking.checked_in_at = timezone.now()
        booking.save()
        
        return Response({
            'success': True,
            'message': f'Vehicle {booking.vehicle_number} checked in',
            'data': {
                'booking_id': booking.id,
                'slot': booking.slot.slot_number,
                'valid_until': booking.end_time.isoformat()
            }
        })
    
    @action(detail=True, methods=['post'])
    def check_out(self, request, pk=None):
        """
        POST /api/bookings/{id}/check_out/
        ✅ Only GATE STAFF can check out vehicles
        """
        booking = self.get_object()
        
        if booking.status != 'active':
            return Response(
                {'error': f'Booking is {booking.status}. Only active can be checked out.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        actual_end = timezone.now()
        booking.checked_out_at = actual_end
        
        if actual_end > booking.end_time:
            overstay_seconds = (actual_end - booking.end_time).total_seconds()
            overstay_hours = max(1, int(overstay_seconds / 3600) + 1)
            penalty_rate = float(booking.price_per_hour) * 2
            booking.penalty_amount = round(overstay_hours * penalty_rate, 2)
            booking.status = 'overdue'
            message = f'Overstay detected! Penalty: ${booking.penalty_amount}'
        else:
            booking.status = 'completed'
            message = 'Check-out successful'
        
        booking.save()
        
        total = float(booking.total_price) + float(booking.penalty_amount)
        
        return Response({
            'success': True,
            'message': message,
            'data': {
                'booking_id': booking.id,
                'base_price': float(booking.total_price),
                'penalty': float(booking.penalty_amount),
                'total_paid': round(total, 2)
            }
        })
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        POST /api/bookings/{id}/cancel/
        ✅ Anyone can cancel their own booking
        """
        booking = self.get_object()
        
        if booking.status not in ['reserved', 'active']:
            return Response(
                {'error': 'Booking cannot be cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'cancelled'
        booking.save()
        
        return Response({
            'success': True,
            'message': 'Booking cancelled successfully'
        })


class AdminSlotViewSet(viewsets.ModelViewSet):
    """
    Admin-only slot management
    ✅ Only ADMINS and SUPERUSERS can manage slots
    """
    queryset = ParkingSlot.objects.all()
    serializer_class = ParkingSlotSerializer
    permission_classes = [IsAdminOrSuperAdmin]  # ✅ Only admins