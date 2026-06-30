# accounts/views.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from decimal import Decimal
import requests
from django.conf import settings

from .serializers import (
    RegisterSerializer, LoginSerializer, UserSerializer,
    ChangePasswordSerializer
)
from .permissions import IsAdminOrSuperAdmin

User = get_user_model()


# ============================================
# AUTHENTICATION VIEWS
# ============================================

class RegisterView(APIView):
    """
    POST /api/auth/register/
    Create a new user account
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()

            refresh = RefreshToken.for_user(user)

            return Response({
                'success': True,
                'message': 'User created successfully',
                'data': {
                    'user': UserSerializer(user).data,
                    'access_token': str(refresh.access_token),
                    'refresh_token': str(refresh),
                }
            }, status=status.HTTP_201_CREATED)

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """
    POST /api/auth/login/
    Login and get JWT tokens
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data['user']
            refresh = RefreshToken.for_user(user)

            return Response({
                'success': True,
                'message': 'Login successful',
                'data': {
                    'user': UserSerializer(user).data,
                    'access_token': str(refresh.access_token),
                    'refresh_token': str(refresh),
                }
            }, status=status.HTTP_200_OK)

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(APIView):
    """
    GET /api/auth/profile/ - Get current user profile
    PUT /api/auth/profile/ - Update current user profile
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get user profile with role-specific data"""
        user = request.user
        serializer = UserSerializer(user)

        response_data = serializer.data

        # Add role-specific additional info
        if user.role == 'driver':
            response_data['wallet_balance'] = str(user.wallet_balance or 0.00)

        return Response({
            'success': True,
            'data': response_data
        })

    def put(self, request):
        """Update user profile"""
        user = request.user
        serializer = UserSerializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'data': serializer.data
            })

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/
    Change user password
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)

        if serializer.is_valid():
            user = request.user

            if not user.check_password(serializer.validated_data['old_password']):
                return Response({
                    'success': False,
                    'message': 'Old password is incorrect'
                }, status=status.HTTP_400_BAD_REQUEST)

            user.set_password(serializer.validated_data['new_password'])
            user.save()

            return Response({
                'success': True,
                'message': 'Password changed successfully'
            }, status=status.HTTP_200_OK)

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Logout and blacklist refresh token
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()

            return Response({
                'success': True,
                'message': 'Logged out successfully'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class TestAuthView(APIView):
    """
    GET /api/auth/test/
    Test if authentication is working
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'success': True,
            'message': f'Welcome {request.user.username}! You are authenticated.',
            'user': UserSerializer(request.user).data
        })


# ============================================
# WALLET VIEWS
# ============================================

class TopUpWalletView(APIView):
    """
    POST /api/auth/top-up/
    Top up wallet via M-Pesa
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if user.role != 'driver':
            return Response({
                'error': 'Only drivers can top up wallet'
            }, status=status.HTTP_403_FORBIDDEN)

        amount = request.data.get('amount')
        phone = request.data.get('phone_number')

        if not amount or not phone:
            return Response({
                'error': 'Amount and phone number required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = float(amount)
            if amount <= 0:
                return Response({
                    'error': 'Amount must be greater than 0'
                }, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({
                'error': 'Invalid amount'
            }, status=status.HTTP_400_BAD_REQUEST)

        phone = str(phone)
        if not phone.startswith('254'):
            phone = '254' + phone.lstrip('0')

        try:
            base_url = getattr(settings, 'BASE_URL', 'https://slotsmart-backend.onrender.com')
            mpesa_url = f"{base_url}/api/mpesa/initiate/"

            auth_header = request.headers.get('Authorization')
            headers = {'Authorization': auth_header} if auth_header else {}

            payload = {
                'phone_number': phone,
                'amount': amount,
                'booking_id': None
            }

            response = requests.post(mpesa_url, json=payload, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                return Response({
                    'success': True,
                    'message': 'M-Pesa STK push sent. Please enter PIN to top up wallet.',
                    'data': {
                        'checkout_request_id': data.get('checkout_request_id'),
                        'amount': amount,
                        'status': 'pending'
                    }
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'error': f'M-Pesa failed: {response.text[:200]}'
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({
                'success': False,
                'error': f'M-Pesa error: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)


# ============================================
# ADMIN USER MANAGEMENT VIEWS (SIMPLE!)
# ============================================

class AdminUserListView(APIView):
    """
    GET /api/admin/users/
    List all users (Admin only)
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response({
            'success': True,
            'count': users.count(),
            'data': serializer.data
        })


class AdminUserDetailView(APIView):
    """
    GET /api/admin/users/{id}/ - Get user details (Admin only)
    DELETE /api/admin/users/{id}/ - Delete user (Admin only)
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        try:
            user = User.objects.get(id=pk)
            serializer = UserSerializer(user)
            return Response({
                'success': True,
                'data': serializer.data
            })
        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        try:
            user = User.objects.get(id=pk)

            # Don't delete superusers
            if user.is_superuser:
                return Response({
                    'error': 'Cannot delete a superuser'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Don't delete yourself
            if user.id == request.user.id:
                return Response({
                    'error': 'You cannot delete yourself'
                }, status=status.HTTP_400_BAD_REQUEST)

            username = user.username
            user.delete()

            return Response({
                'success': True,
                'message': f'User {username} deleted successfully'
            })

        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)


class AdminUserDeactivateView(APIView):
    """
    POST /api/admin/users/{id}/deactivate/ - Deactivate user (Admin only)
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(id=pk)

            # Don't deactivate superusers
            if user.is_superuser:
                return Response({
                    'error': 'Cannot deactivate a superuser'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Don't deactivate yourself
            if user.id == request.user.id:
                return Response({
                    'error': 'You cannot deactivate yourself'
                }, status=status.HTTP_400_BAD_REQUEST)

            user.is_active = False
            user.save()

            return Response({
                'success': True,
                'message': f'User {user.username} deactivated successfully'
            })

        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)


class AdminUserActivateView(APIView):
    """
    POST /api/admin/users/{id}/activate/ - Activate user (Admin only)
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(id=pk)

            # Don't activate superusers (they're always active)
            if user.is_superuser:
                return Response({
                    'error': 'Superusers are always active'
                }, status=status.HTTP_400_BAD_REQUEST)

            user.is_active = True
            user.save()

            return Response({
                'success': True,
                'message': f'User {user.username} activated successfully'
            })

        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
class AdminUserDeleteView(APIView):
    """
    POST /api/admin/users/{id}/delete/
    Delete user (Admin only)
    """
    permission_classes = [IsAdminOrSuperAdmin]
    
    def post(self, request, pk):
        try:
            user = User.objects.get(id=pk)
            
            # Don't delete superusers
            if user.is_superuser:
                return Response({
                    'error': 'Cannot delete a superuser'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Don't delete yourself
            if user.id == request.user.id:
                return Response({
                    'error': 'You cannot delete yourself'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            username = user.username
            user.delete()
            
            return Response({
                'success': True,
                'message': f'User {username} deleted successfully'
            })
        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)