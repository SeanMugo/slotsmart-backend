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
    ✅ Anyone can create bookings (drivers, staff, admin, superuser)
    ✅ Gate Staff can check in/out
    ✅ Admins can view all bookings
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """
        ✅ Role-based permissions per action
        """
        if self.action in ['check_in', 'check_out']:
            return [IsStaffOrAdmin()]  # ✅ Only staff/admin can check in/out
        return [IsAuthenticated()]  # ✅ Anyone can create/view bookings

    def get_queryset(self):
        """
        ✅ Drivers see only their own bookings
        ✅ Staff, Admins, Superusers see all bookings
        """
        user = self.request.user
        
        # Staff, Admins, and Superusers can see all bookings
        if user.role in ['admin', 'super_admin', 'gate_staff']:
            return Booking.objects.all()
        
        # Drivers see only their own bookings
        return Booking.objects.filter(user=user)
    
    @transaction.atomic
    def create(self, request):
        """
        POST /api/bookings/
        ✅ ANY authenticated user can create bookings
        ✅ Accepts both integer and UUID slot IDs
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
        
        # ✅ FIX: Handle both integer and UUID slot IDs
        try:
            # Try to get slot by ID (supports both int and UUID)
            if isinstance(slot_id, int) or (isinstance(slot_id, str) and slot_id.isdigit()):
                slot = ParkingSlot.objects.get(id=int(slot_id))
            else:
                slot = ParkingSlot.objects.get(id=slot_id)
        except (ValueError, TypeError, ParkingSlot.DoesNotExist):
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
        ✅ Payment happens at checkout with wallet deduction
        """
        booking = self.get_object()
        user = request.user
        
        # 1. Check if booking is active
        if booking.status != 'active':
            return Response(
                {'error': f'Booking is {booking.status}. Only active bookings can be checked out.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 2. Calculate actual duration and total
        actual_end = timezone.now()
        duration_hours = (actual_end - booking.start_time).total_seconds() / 3600
        
        # Calculate price (use current time for peak/off-peak)
        total_price = self.calculate_price(booking.slot, actual_end) * duration_hours
        total_price = round(total_price, 2)
        
        # 3. Check for overstay
        penalty_amount = 0.00
        if actual_end > booking.end_time:
            overstay_seconds = (actual_end - booking.end_time).total_seconds()
            overstay_hours = max(1, int(overstay_seconds / 3600) + 1)
            penalty_rate = float(booking.price_per_hour) * 2
            penalty_amount = round(overstay_hours * penalty_rate, 2)
        
        final_total = total_price + penalty_amount
        
        # 4. Get the user who booked
        booker = booking.user
        
        # 5. Handle different user types
        if booker.role == 'driver':
            # ✅ DRIVER BOOKING - Payment required
            if booker.wallet_balance >= final_total:
                # ✅ SUFFICIENT BALANCE - Auto deduct
                booker.wallet_balance -= final_total
                booker.save()
                
                booking.status = 'completed'
                booking.checked_out_at = actual_end
                booking.total_price = total_price
                booking.penalty_amount = penalty_amount
                booking.payment_method = 'wallet'
                booking.is_paid = True
                booking.save()
                
                return Response({
                    'success': True,
                    'message': f'Vehicle {booking.vehicle_number} checked out',
                    'payment': {
                        'method': 'wallet',
                        'base_price': float(total_price),
                        'penalty': float(penalty_amount),
                        'total_paid': float(final_total),
                        'remaining_balance': float(booker.wallet_balance)
                    },
                    'booking': {
                        'id': booking.id,
                        'status': booking.status,
                        'checked_out_at': booking.checked_out_at.isoformat()
                    }
                })
            else:
                # ❌ INSUFFICIENT BALANCE - Payment required
                return Response({
                    'success': False,
                    'error': 'Insufficient wallet balance',
                    'payment_required': {
                        'base_price': float(total_price),
                        'penalty': float(penalty_amount),
                        'total_due': float(final_total),
                        'wallet_balance': float(booker.wallet_balance or 0.00),
                        'shortfall': float(final_total - (booker.wallet_balance or 0.00))
                    },
                    'options': [
                        'Add test money via /api/auth/add-test-money/ (if enabled)',
                        'Use M-Pesa payment'
                    ]
                }, status=402)  # 402 Payment Required
        
        elif booker.role in ['admin', 'superuser']:
            # ✅ ADMIN/SUPERUSER BOOKING - No payment (testing mode)
            booking.status = 'completed'
            booking.checked_out_at = actual_end
            booking.total_price = total_price
            booking.penalty_amount = penalty_amount
            booking.payment_method = 'test'
            booking.is_paid = True
            booking.save()
            
            return Response({
                'success': True,
                'message': f'Test booking checked out successfully (no payment)',
                'booking': {
                    'id': booking.id,
                    'status': booking.status,
                    'checked_out_at': booking.checked_out_at.isoformat()
                }
            })
        
        else:
            # ❌ Invalid user role
            return Response({
                'error': f'Invalid user role: {booker.role}. Only drivers, admins, and superusers can book.'
            }, status=status.HTTP_400_BAD_REQUEST)
    
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


class PricingRuleViewSet(viewsets.ModelViewSet):
    """
    Manage pricing rules
    ✅ Only ADMINS and SUPERUSERS can manage pricing
    """
    queryset = PricingRule.objects.all()
    serializer_class = PricingRuleSerializer
    permission_classes = [IsAdminOrSuperAdmin]