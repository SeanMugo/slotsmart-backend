# mpesa_integration/views.py
import base64
import traceback
from datetime import datetime

import requests
from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MpesaTransaction
from .serializers import MpesaSTKPushSerializer


class MpesaAuth:
    @staticmethod
    def get_access_token():
        """
        Gets M-Pesa access token using consumer key/secret.
        """
        consumer_key = settings.MPESA_CONSUMER_KEY
        consumer_secret = settings.MPESA_CONSUMER_SECRET
        api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

        try:
            response = requests.get(api_url, auth=(consumer_key, consumer_secret), timeout=30)
            if response.status_code == 200:
                return response.json().get('access_token')
            else:
                print(f"❌ Access token error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"❌ Access token exception: {e}")
            return None


class MpesaSTKPushView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # 1. Validate input
            serializer = MpesaSTKPushSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({"error": "Invalid input", "details": serializer.errors}, status=400)

            phone = serializer.validated_data['phone_number']
            amount = serializer.validated_data['amount']
            user = request.user

            # 2. Get access token (hardcoded fallback if needed)
            # ✅ Step 1: Try to get token normally
            access_token = MpesaAuth.get_access_token()
            
            # ✅ Step 2: If that fails, use this hardcoded token (replace with your actual token from shell)
            if not access_token:
                print("⚠️ Using hardcoded access token (remove this in production!)")
                access_token = "Yjd4KF36mxEP1COZGt7yXAU8N4Aw"  

            if not access_token:
                return Response({"error": "Could not authenticate with M-Pesa"}, status=500)

            # 3. Prepare STK Push
            api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            password_str = settings.MPESA_SHORTCODE + settings.MPESA_PASSKEY + timestamp
            password = base64.b64encode(password_str.encode()).decode('utf-8')

            payload = {
                "BusinessShortCode": int(settings.MPESA_SHORTCODE),
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": int(amount),
                "PartyA": phone,
                "PartyB": int(settings.MPESA_SHORTCODE),
                "PhoneNumber": phone,
                "CallBackURL": "https://uplifting-armhole-fling.ngrok-free.dev/api/mpesa/callback/",
                "AccountReference": user.username[:20],
                "TransactionDesc": "Parking payment"
            }

            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            print("\n=== SENDING PAYLOAD ===")
            print(payload)
            print("========================")

            response = requests.post(api_url, json=payload, headers=headers, timeout=30)

            print("\n=== M-PESA RESPONSE ===")
            print(f"Status: {response.status_code}")
            print(f"Body: {response.text}")
            print("========================")

            if response.status_code == 200:
                data = response.json()
                if data.get('ResponseCode') != '0':
                    return Response({
                        "error": data.get('ResponseDescription', 'M-Pesa error'),
                        "code": data.get('ResponseCode')
                    }, status=400)

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
                }, status=200)
            else:
                return Response({
                    "error": "M-Pesa service error",
                    "status_code": response.status_code,
                    "details": response.text[:500]
                }, status=500)

        except Exception as e:
            print("\n=== ERROR ===")
            traceback.print_exc()
            print("=============")
            return Response({"error": str(e)}, status=500)


class MpesaCallbackView(APIView):
    permission_classes = []

    def post(self, request):
        try:
            print("\n=== M-PESA CALLBACK RECEIVED ===")
            data = request.data
            print(f"Callback data: {data}")

            result_code = data.get('Body', {}).get('stkCallback', {}).get('ResultCode')
            checkout_request_id = data.get('Body', {}).get('stkCallback', {}).get('CheckoutRequestID')
            result_desc = data.get('Body', {}).get('stkCallback', {}).get('ResultDesc')

            if not checkout_request_id:
                print("❌ No checkout_request_id in callback")
                return Response({"error": "Invalid callback"}, status=400)

            transaction = MpesaTransaction.objects.get(checkout_request_id=checkout_request_id)
            transaction.status = 'success' if result_code == 0 else 'failed'
            transaction.save()

            print(f"✅ Transaction {transaction.id} updated to {transaction.status}")
            return Response({"message": "Callback processed"}, status=200)

        except MpesaTransaction.DoesNotExist:
            print(f"❌ Transaction not found for ID: {checkout_request_id}")
            return Response({"error": "Transaction not found"}, status=404)
        except Exception as e:
            print("Callback error:", str(e))
            traceback.print_exc()
            return Response({"error": "Callback error"}, status=500)