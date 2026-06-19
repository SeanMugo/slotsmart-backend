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


class ParkingSlotViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View parking slots and check availability
    """
    queryset = ParkingSlot.objects.filter(status='active')
    serializer_class = ParkingSlotSerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def available(self, request):
        """
        GET /api/slots/available/?start=2024-01-15T10:00:00&end=2024-01-15T12:00:00
        
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
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use: 2024-01-15T10:00:00'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Find available slots
        available_slots = ParkingSlot.objects.filter(
            slot_type=slot_type,
            status='active'
        ).exclude(
            booking__start_time__lt=end,
            booking__end_time__gt=start,
            booking__status__in=['reserved', 'active']
        )
        
        # Calculate dynamic pricing for each slot
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
        
        # Default pricing rules
        if (8 <= hour <= 10) or (17 <= hour <= 19):
            return round(base_price * 1.5, 2)  # Peak hour: +50%
        elif hour >= 23 or hour <= 6:
            return round(base_price * 0.7, 2)  # Off-peak: -30%
        
        return round(base_price, 2)


class BookingViewSet(viewsets.ModelViewSet):
    """
    Create and manage bookings
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Users can only see their own bookings"""
        return Booking.objects.filter(user=self.request.user)
    
    @transaction.atomic
    def create(self, request):
        """
        POST /api/bookings/
        Create a new booking
        """
        slot_id = request.data.get('slot_id')
        start_time = request.data.get('start_time')
        end_time = request.data.get('end_time')
        vehicle_number = request.data.get('vehicle_number')
        
        if not all([slot_id, start_time, end_time, vehicle_number]):
            return Response(
                {'error': 'Missing required fields'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start = timezone.datetime.fromisoformat(start_time)
            end = timezone.datetime.fromisoformat(end_time)
        except ValueError:
            return Response(
                {'error': 'Invalid date format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if start < timezone.now():
            return Response(
                {'error': 'Start time must be in the future'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get and lock the slot
        try:
            slot = ParkingSlot.objects.select_for_update().get(id=slot_id)
        except ParkingSlot.DoesNotExist:
            return Response(
                {'error': 'Slot not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check for overlapping bookings
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
        
        # Calculate price
        duration_hours = (end - start).total_seconds() / 3600
        price_per_hour = self.calculate_price(slot, start)
        total_price = round(duration_hours * price_per_hour, 2)
        
        # Generate QR code
        qr_data = f"SLOTSMART|{slot.id}|{start.isoformat()}|{end.isoformat()}"
        qr = qrcode.make(qr_data)
        buffer = BytesIO()
        qr.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        # Create booking
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
        """Calculate price based on time"""
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
        Check in a vehicle
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
        Check out and calculate final payment
        """
        booking = self.get_object()
        
        if booking.status != 'active':
            return Response(
                {'error': f'Booking is {booking.status}. Only active can be checked out.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        actual_end = timezone.now()
        booking.checked_out_at = actual_end
        
        # Check for overstay
        if actual_end > booking.end_time:
            overstay_hours = (actual_end - booking.end_time).total_seconds() / 3600
            overstay_hours = max(1, int(overstay_hours) + 1)
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
        Cancel a booking
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