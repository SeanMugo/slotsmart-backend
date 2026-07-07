from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ParkingSlotViewSet,
    ParkingSessionViewSet,
)

router = DefaultRouter()

router.register(
    r"slots",
    ParkingSlotViewSet,
    basename="slot",
)

router.register(
    r"sessions",
    ParkingSessionViewSet,
    basename="session",
)

urlpatterns = [
    path("", include(router.urls)),
]