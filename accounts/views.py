from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from .permissions import IsAdmin

from rest_framework_simplejwt.tokens import RefreshToken

from django.contrib.auth import get_user_model

from .serializers import (
    UserSerializer,
    UpdateProfileSerializer,
    AdminUpdateUserSerializer,
    LoginSerializer,
    ChangePasswordSerializer,
)

User = get_user_model()


# ==========================================
# LOGIN
# ==========================================

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():

            user = serializer.validated_data["user"]

            refresh = RefreshToken.for_user(user)

            return Response(
                {
                    "success": True,
                    "message": "Login successful.",
                    "user": UserSerializer(user).data,
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                }
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


# ==========================================
# LOGOUT
# ==========================================

class LogoutView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        try:

            refresh_token = request.data.get("refresh")

            token = RefreshToken(refresh_token)

            token.blacklist()

            return Response(
                {
                    "success": True,
                    "message": "Logged out successfully.",
                }
            )

        except Exception:

            return Response(
                {
                    "success": False,
                    "message": "Invalid refresh token.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


# ==========================================
# PROFILE
# ==========================================

class ProfileView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        serializer = UserSerializer(request.user)

        return Response(serializer.data)

    def put(self, request):

        serializer = UpdateProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():

            serializer.save()

            return Response(
                {
                    "success": True,
                    "message": "Profile updated successfully.",
                    "user": UserSerializer(request.user).data,
                }
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )
# ==========================================
# DRIVERS
# ==========================================

class DriverListView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        drivers = (
            User.objects.filter(
                role="driver",
                is_active=True,
            )
            .order_by("first_name", "last_name")
        )

        data = [
            {
                "id": driver.id,
                "name": (
                    f"{driver.first_name} {driver.last_name}".strip()
                    or driver.username
                ),
                "default_vehicle": driver.default_vehicle,
            }
            for driver in drivers
        ]

        return Response(data)

# ==========================================
# CHANGE PASSWORD
# ==========================================

class ChangePasswordView(APIView):
    

    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = ChangePasswordSerializer(
            data=request.data
        )

        if serializer.is_valid():

            user = request.user

            if not user.check_password(
                serializer.validated_data["old_password"]
            ):

                return Response(
                    {
                        "error": "Old password is incorrect."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.set_password(
                serializer.validated_data["new_password"]
            )

            user.save()

            return Response(
                {
                    "success": True,
                    "message": "Password changed successfully.",
                }
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

# ==========================================
# ADMIN USER MANAGEMENT
# ==========================================

class AdminCreateUserView(APIView):
    """
    Admin creates Drivers, Gate Staff and Admins.
    """

    permission_classes = [IsAdmin]

    def post(self, request):

        data = request.data.copy()

        role = data.get("role")

        if role not in ["driver", "gate_staff", "admin"]:
            return Response(
                {"error": "Invalid role."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        username = data.get("username")

        if User.objects.filter(username=username).exists():
            return Response(
                {"error": "Username already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email=data.get("email")).exists():
            return Response(
                {"error": "Email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        password = data.get("password")

        if not password:
            return Response(
                {"error": "Password is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.create_user(
            username=username,
            email=data.get("email", ""),
            password=password,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            phone_number=data.get("phone_number", ""),
            default_vehicle=data.get("default_vehicle", ""),
            role=role,
        )

        serializer = UserSerializer(user)

        return Response(
            {
                "message": "User created successfully.",
                "user": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class AdminListUsersView(APIView):
    """
    List all users.
    """

    permission_classes = [IsAdmin]

    def get(self, request):

        users = User.objects.all().order_by("username")

        serializer = UserSerializer(users, many=True)

        return Response(serializer.data)


class AdminUserDetailView(APIView):
    """
    Retrieve, update or delete a user.
    """

    permission_classes = [IsAdmin]

    def get_object(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):

        user = self.get_object(pk)

        if user is None:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(UserSerializer(user).data)

    def put(self, request, pk):

        user = self.get_object(pk)

        if user is None:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminUpdateUserSerializer(
            user,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():

            serializer.save()

            return Response(
                {
                    "message": "User updated successfully.",
                    "user": UserSerializer(user).data,
                }
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, pk):

        user = self.get_object(pk)

        if user is None:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user == request.user:
            return Response(
                {
                    "error": "You cannot delete your own account."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.delete()

        return Response(
            {
                "message": "User deleted successfully."
            }
        )


class AdminActivateUserView(APIView):
    """
    Activate a user.
    """

    permission_classes = [IsAdmin]

    def post(self, request, pk):

        try:
            user = User.objects.get(pk=pk)

        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.is_active = True
        user.save()

        return Response(
            {
                "message": "User activated successfully."
            }
        )


class AdminDeactivateUserView(APIView):
    """
    Deactivate a user.
    """

    permission_classes = [IsAdmin]

    def post(self, request, pk):

        try:
            user = User.objects.get(pk=pk)

        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user == request.user:
            return Response(
                {
                    "error": "You cannot deactivate your own account."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = False
        user.save()

        return Response(
            {
                "message": "User deactivated successfully."
            }
        )
    