from django.urls import path
from .views import (
    RegisterView, LoginView, ProfileView, ChangePasswordView,
    LogoutView, TestAuthView, TopUpWalletView,
    AdminUserListView, AdminUserDetailView,
    AdminUserDeactivateView, AdminUserActivateView, AdminUserDeleteView
)

urlpatterns = [
    # Authentication (no 'auth/' prefix here)
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('test/', TestAuthView.as_view(), name='test_auth'),
    
    # Wallet
    path('top-up/', TopUpWalletView.as_view(), name='top-up'),
    
    # Admin
    path('admin/users/', AdminUserListView.as_view(), name='admin-users'),
    path('admin/users/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('admin/users/<int:pk>/deactivate/', AdminUserDeactivateView.as_view(), name='admin-user-deactivate'),
    path('admin/users/<int:pk>/activate/', AdminUserActivateView.as_view(), name='admin-user-activate'),
    path('admin/users/<int:pk>/delete/', AdminUserDeleteView.as_view(), name='admin-user-delete'),
]