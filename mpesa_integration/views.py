from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from .models import MpesaTransaction
from .serializers import MpesaSTKPushSerializer
import requests
import base64
from datetime import datetime

class MpesaAuth:
    @staticmethod
    def get_access_token():
        consumer_key = settings.MPESA_CONSUMER_KEY
        consumer_secret = settings.MPESA_CONSUMER_SECRET
        api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        
        response = requests.get(api_url, auth=(consumer_key, consumer_secret))
        if response.status_code == 200:
            return response.json().get('access_token')
        return None

class MpesaSTKPushView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MpesaSTKPushSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        phone = serializer.validated_data['phone_number']
        amount = serializer.validated_data['amount']
        user = request.user

        access_token = MpesaAuth.get_access_token()
        if not access_token:
            return Response({"error": "Could not authenticate with M-Pesa"}, status=500)

        api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password_str = settings.MPESA_SHORTCODE + settings.MPESA_PASSKEY + timestamp
        password = base64.b64encode(password_str.encode()).decode('utf-8')

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        payload = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": settings.MPESA_SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": "https://your-ngrok-url.ngrok.io/api/mpesa/callback/",
            "AccountReference": user.username,
            "TransactionDesc": f"Parking payment for {user.username}"
        }

        response = requests.post(api_url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            transaction = MpesaTransaction.objects.create(
                user=user,
                phone_number=phone,
                amount=amount,
                merchant_request_id=data.get('MerchantRequestID'),
                checkout_request_id=data.get('CheckoutRequestID'),
                status='pending',
                response_code=data.get('ResponseCode'),
                response_description=data.get('ResponseDescription')
            )
            return Response({
                "success": True,
                "message": "STK Push sent. Please check your phone.",
                "transaction_id": transaction.id,
                "checkout_request_id": data.get('CheckoutRequestID')
            })
        else:
            return Response({"error": "Could not initiate M-Pesa payment"}, status=500)


class MpesaCallbackView(APIView):
    permission_classes = []

    def post(self, request):
        data = request.data
        print("Callback received:", data)

        result_code = data.get('Body', {}).get('stkCallback', {}).get('ResultCode')
        checkout_request_id = data.get('Body', {}).get('stkCallback', {}).get('CheckoutRequestID')

        try:
            transaction = MpesaTransaction.objects.get(checkout_request_id=checkout_request_id)
            if result_code == 0:
                transaction.status = 'success'
            else:
                transaction.status = 'failed'
            transaction.save()
            return Response({"message": "Callback processed"})
        except MpesaTransaction.DoesNotExist:
            return Response({"error": "Transaction not found"}, status=404)