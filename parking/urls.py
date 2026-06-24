from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ParkingSlotViewSet, BookingViewSet

router = DefaultRouter()
router.register(r'slots', ParkingSlotViewSet, basename='slot')
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'admin/slots', AdminSlotViewSet, basename='admin-slot')

urlpatterns = [
    path('', include(router.urls)),
]