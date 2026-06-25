# accounts/urls.py
from django.urls import path
from . import views
from .test_money import AddTestMoneyView

urlpatterns = [
    # Authentication endpoints
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('test/', views.TestAuthView.as_view(), name='test'),
    path('auth/add-test-money/', AddTestMoneyView.as_view(), name='add_test_money'),
]