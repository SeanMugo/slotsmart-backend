# accounts/urls.py
from django.urls import path
from .views import (
    RegisterView, LoginView, ProfileView, ChangePasswordView,
    LogoutView, TestAuthView, TopUpWalletView,
    AdminUserListView, AdminUserDetailView,
    AdminUserDeactivateView, AdminUserActivateView
)

urlpatterns = [
    # ============================================
    # AUTHENTICATION
    # ============================================
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/profile/', ProfileView.as_view(), name='profile'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/test/', TestAuthView.as_view(), name='test_auth'),
    
    # ============================================
    # WALLET
    # ============================================
    path('auth/top-up/', TopUpWalletView.as_view(), name='top-up'),
    
    # ============================================
    # ADMIN USER MANAGEMENT (Just 4 endpoints)
    # ============================================
    path('admin/users/', AdminUserListView.as_view(), name='admin-users'),  # GET - List users
    path('admin/users/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),  # GET - Details, DELETE - Delete
    path('admin/users/<int:pk>/deactivate/', AdminUserDeactivateView.as_view(), name='admin-user-deactivate'),  # POST - Deactivate
    path('admin/users/<int:pk>/activate/', AdminUserActivateView.as_view(), name='admin-user-activate'),  # POST - Activate
]