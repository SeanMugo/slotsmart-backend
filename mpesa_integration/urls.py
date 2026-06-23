from django.urls import path
from .views import MpesaSTKPushView, MpesaCallbackView

urlpatterns = [
    path('initiate/', MpesaSTKPushView.as_view(), name='mpesa-initiate'),
    path('callback/', MpesaCallbackView.as_view(), name='mpesa-callback'),
]