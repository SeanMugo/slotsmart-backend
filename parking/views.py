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
import requests
from django.conf import settings

from .models import ParkingSlot, Booking, PricingRule
from .serializers import ParkingSlotSerializer, BookingSerializer, PricingRuleSerializer
from accounts.permissions import IsDriver, IsGateStaff, IsAdminOrSuperAdmin, IsStaffOrAdmin


class ParkingSlotViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View parking slots and check availability.
    Any authenticated user can view available slots.
    """

    serializer_class = ParkingSlotSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ParkingSlot.objects.filter(status="available")

    @action(detail=False, methods=["get"])
    def available(self, request):
        """
        GET /api/slots/available/?start=...&end=...&type=...

        Returns available slots for the requested time period.
        """

        start_time = request.query_params.get("start")
        end_time = request.query_params.get("end")
        slot_type = request.query_params.get("type", "car")

        if not start_time or not end_time:
            return Response(
                {"error": "Missing start/end time parameters"},
                status=status.HTTP_400_BAD_REQUEST,
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
                {
                    "error": "Invalid date format. Use: 2026-01-20T10:00:00+00:00"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        available_slots = self.get_queryset().filter(
            slot_type=slot_type
        ).exclude(
            booking__start_time__lt=end,
            booking__end_time__gt=start,
            booking__status__in=["reserved", "active"],
        )

        result = []

        for slot in available_slots:
            slot_data = ParkingSlotSerializer(slot).data
            slot_data["current_price"] = self.calculate_price(slot, start)
            result.append(slot_data)

        return Response(result)

    def calculate_price(self, slot, booking_time):
        """Calculate price using peak/off-peak rules."""

        base_price = float(slot.base_rate)
        hour = booking_time.hour

        if 8 <= hour <= 10 or 17 <= hour <= 19:
            return round(base_price * 1.5, 2)

        if hour >= 23 or hour <= 6:
            return round(base_price * 0.7, 2)

        return round(base_price, 2)

class BookingViewSet(viewsets.ModelViewSet):
    """
    Create and manage bookings
    ✅ Anyone can create bookings (drivers, staff, admin, superuser)
    ✅ Gate Staff can check in/out
    ✅ Admins can view all bookings
    ✅ Hybrid payment: Wallet (fast) OR M-Pesa (flexible)
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """
        ✅ Role-based permissions per action
        """
        if self.action in ['check_in', 'check_out']:
            return [IsStaffOrAdmin()]
        return [IsAuthenticated()]

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
        # Ensure driver has wallet balance set
        if request.user.role == 'driver' and request.user.wallet_balance is None:
            request.user.wallet_balance = 0.00
            request.user.save()

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

        # Handle both integer and UUID slot IDs
        try:
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
        user = request.user

        # Check if user is authorized
        if user.role not in ['gate_staff', 'admin', 'superuser']:
            return Response({
                'error': 'Only gate staff, admin, or superuser can check in bookings'
            }, status=status.HTTP_403_FORBIDDEN)

        # Check if booking is already checked in
        if booking.status == 'active':
            return Response({
                'error': 'Booking is already checked in'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if booking is completed
        if booking.status == 'completed':
            return Response({
                'error': 'Booking is already completed'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if booking is overdue
        if booking.status == 'overdue':
            return Response({
                'error': 'Booking has expired and cannot be checked in'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if booking is reserved
        if booking.status != 'reserved':
            return Response({
                'error': f'Booking is {booking.status}. Only reserved bookings can be checked in.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if booking time has passed
        if timezone.now() > booking.end_time:
            booking.status = 'overdue'
            booking.save()
            return Response({
                'error': 'Booking has expired. Cannot check in.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check in the booking
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

    def call_mpesa_payment(self, phone_number, amount, booking_id, user):
        """
        Call your existing M-Pesa initiate endpoint
        """
        try:
            base_url = getattr(settings, 'BASE_URL', 'https://slotsmart-backend.onrender.com')
            mpesa_url = f"{base_url}/api/mpesa/initiate/"
            
            # We need to pass the user's auth token
            # Get token from request
            from rest_framework.request import Request
            if hasattr(self, 'request'):
                auth_header = self.request.headers.get('Authorization')
                headers = {'Authorization': auth_header} if auth_header else {}
            else:
                headers = {}
            
            payload = {
                'phone_number': phone_number,
                'amount': float(amount),
                'booking_id': booking_id
            }
            
            response = requests.post(mpesa_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'checkout_request_id': data.get('checkout_request_id'),
                    'transaction_id': data.get('transaction_id'),
                    'message': data.get('message', 'M-Pesa STK push sent')
                }
            else:
                return {
                    'success': False,
                    'error': f"M-Pesa service error: {response.status_code}",
                    'details': response.text[:500]
                }
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': 'M-Pesa request timed out. Please try again.'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'M-Pesa error: {str(e)}'
            }

    @action(detail=True, methods=['post'])
    def check_out(self, request, pk=None):
        """
        POST /api/bookings/{id}/check_out/
        ✅ Only GATE STAFF can check out vehicles
        ✅ HYBRID PAYMENT: Wallet (fast) OR M-Pesa (flexible)
        """
        booking = self.get_object()
        user = request.user

        # Check if user is authorized
        if user.role not in ['gate_staff', 'admin', 'superuser']:
            return Response({
                'error': 'Only gate staff, admin, or superuser can check out bookings'
            }, status=status.HTTP_403_FORBIDDEN)

        # Check if booking is active
        if booking.status == 'overdue':
            return Response({
                'error': 'Booking has expired. Please contact staff.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if booking.status != 'active':
            return Response({
                'error': f'Booking is {booking.status}. Only active bookings can be checked out.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Calculate actual duration and total (prevent negative)
        actual_end = timezone.now()
        duration_hours = max(0, (actual_end - booking.start_time).total_seconds() / 3600)

        # Calculate price (use current time for peak/off-peak)
        total_price = self.calculate_price(booking.slot, actual_end) * duration_hours
        total_price = round(total_price, 2)

        # Check for overstay
        penalty_amount = 0.00
        if actual_end > booking.end_time:
            overstay_seconds = (actual_end - booking.end_time).total_seconds()
            overstay_hours = max(1, int(overstay_seconds / 3600) + 1)
            penalty_rate = float(booking.price_per_hour) * 2
            penalty_amount = round(overstay_hours * penalty_rate, 2)

        final_total = total_price + penalty_amount

        # If total is 0 or negative, set minimum charge
        if final_total <= 0:
            final_total = 1.00

        # Get the user who booked
        driver = booking.user

        # Handle different user types
        if driver.role == 'driver':
            # DRIVER BOOKING - Hybrid payment
            wallet_balance = float(driver.wallet_balance or 0.00)

            # 🚀 OPTION 1: FAST TRACK - Sufficient wallet balance (Like ETC)
            if wallet_balance >= final_total:
                # Instant checkout - deduct from wallet
                driver.wallet_balance = wallet_balance - final_total
                driver.save()

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
                        'type': 'fast_track',
                        'base_price': float(total_price),
                        'penalty': float(penalty_amount),
                        'total_paid': float(final_total),
                        'remaining_balance': float(driver.wallet_balance)
                    },
                    'booking': {
                        'id': booking.id,
                        'status': booking.status,
                        'checked_out_at': booking.checked_out_at.isoformat()
                    }
                })

            # 📱 OPTION 2: FLEXIBLE PAYMENT - Insufficient balance → M-Pesa
            else:
                # Check if driver has phone number for M-Pesa
                if not driver.phone_number:
                    return Response({
                        'success': False,
                        'error': 'Insufficient wallet balance and no phone number for M-Pesa',
                        'payment_required': {
                            'amount_due': float(final_total),
                            'wallet_balance': float(wallet_balance),
                            'shortfall': float(final_total - wallet_balance)
                        },
                        'payment_options': [
                            'Add funds to wallet via top-up',
                            'Update phone number for M-Pesa'
                        ]
                    }, status=402)

                # Format phone number
                phone = driver.phone_number
                if not phone.startswith('254'):
                    phone = '254' + phone.lstrip('0')

                # Call M-Pesa
                mpesa_result = self.call_mpesa_payment(
                    phone_number=phone,
                    amount=final_total,
                    booking_id=booking.id,
                    user=driver
                )

                if mpesa_result.get('success'):
                    return Response({
                        'success': False,
                        'payment_required': True,
                        'payment_method': 'mpesa',
                        'type': 'flexible_payment',
                        'message': 'Insufficient wallet balance. M-Pesa STK push sent to your phone.',
                        'data': {
                            'checkout_request_id': mpesa_result.get('checkout_request_id'),
                            'transaction_id': mpesa_result.get('transaction_id'),
                            'amount': float(final_total),
                            'status': 'pending',
                            'wallet_balance': float(wallet_balance)
                        }
                    }, status=202)  # Accepted for processing
                else:
                    return Response({
                        'success': False,
                        'error': f'Insufficient wallet balance and M-Pesa failed: {mpesa_result.get("error", "Unknown error")}',
                        'payment_required': {
                            'amount_due': float(final_total),
                            'wallet_balance': float(wallet_balance),
                            'shortfall': float(final_total - wallet_balance)
                        },
                        'payment_options': [
                            'Add funds to wallet via top-up',
                            'Try M-Pesa again'
                        ]
                    }, status=402)

        # ADMIN/SUPERUSER BOOKING - No payment (testing mode)
        elif driver.role in ['admin', 'superuser']:
            booking.status = 'completed'
            booking.checked_out_at = actual_end
            booking.total_price = total_price
            booking.penalty_amount = penalty_amount
            booking.payment_method = 'test'
            booking.is_paid = True
            booking.save()

            return Response({
                'success': True,
                'message': 'Test booking checked out successfully (no payment)',
                'booking': {
                    'id': booking.id,
                    'status': booking.status,
                    'checked_out_at': booking.checked_out_at.isoformat()
                }
            })

        else:
            # Invalid user role
            return Response({
                'error': f'Invalid user role: {driver.role}. Only drivers, admins, and superusers can book.'
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
    ✅ View, Add, Edit, Delete slots
    """
    queryset = ParkingSlot.objects.all()
    serializer_class = ParkingSlotSerializer
    permission_classes = [IsAdminOrSuperAdmin]
    
    def perform_create(self, serializer):
        """Create new slot with admin as creator"""
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        """Update slot"""
        serializer.save(updated_by=self.request.user)
    
    def destroy(self, request, *args, **kwargs):
        """Delete slot"""
        slot = self.get_object()
        # Check if slot has active bookings
        if Booking.objects.filter(slot=slot, status__in=['reserved', 'active']).exists():
            return Response({
                'error': 'Cannot delete slot with active bookings'
            }, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


class PricingRuleViewSet(viewsets.ModelViewSet):
    """
    Manage pricing rules
    ✅ Only ADMINS and SUPERUSERS can manage pricing
    """
    queryset = PricingRule.objects.all()
    serializer_class = PricingRuleSerializer
    permission_classes = [IsAdminOrSuperAdmin]