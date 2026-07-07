from django.urls import path
from .views import (
    LoginView,
    LogoutView,
    ProfileView,
    ChangePasswordView,

    AdminCreateUserView,
    AdminListUsersView,
    AdminUserDetailView,
    AdminActivateUserView,
    AdminDeactivateUserView,
)

urlpatterns = [
    # Authentication
    path('login/', LoginView.as_view(), name='login'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('logout/', LogoutView.as_view(), name='logout'),

    # Admin User Management
    path('admin/users/', AdminListUsersView.as_view(), name='admin-users'),
    path('admin/users/create/', AdminCreateUserView.as_view(), name='admin-user-create'),
    path('admin/users/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('admin/users/<int:pk>/activate/', AdminActivateUserView.as_view(), name='admin-user-activate'),
    path('admin/users/<int:pk>/deactivate/', AdminDeactivateUserView.as_view(), name='admin-user-deactivate'),
]