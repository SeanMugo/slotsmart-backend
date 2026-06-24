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
        consumer_key = settings.MPESA_CONSUMER_KEY
        consumer_secret = settings.MPESA_CONSUMER_SECRET
        api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        
        try:
            response = requests.get(api_url, auth=(consumer_key, consumer_secret), timeout=30)
            if response.status_code == 200:
                return response.json().get('access_token')
            else:
                print(f"Access token error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Access token exception: {e}")
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

            # 2. Get access token
            access_token = MpesaAuth.get_access_token()
            if not access_token:
                return Response({"error": "Could not authenticate with M-Pesa"}, status=500)

            # 3. Prepare STK Push
            api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            password_str = settings.MPESA_SHORTCODE + settings.MPESA_PASSKEY + timestamp
            password = base64.b64encode(password_str.encode()).decode('utf-8')

            payload = {
                "BusinessShortCode": settings.MPESA_SHORTCODE,
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": int(amount),
                "PartyA": phone,
                "PartyB": settings.MPESA_SHORTCODE,
                "PhoneNumber": phone,
                "CallBackURL": "https://your-ngrok-url.ngrok-free.dev/api/mpesa/callback/",
                "AccountReference": user.username,
                "TransactionDesc": f"Parking payment for {user.username}"
            }

            # 4. Send to M-Pesa
            response = requests.post(api_url, json=payload, headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }, timeout=30)

            # 5. Log response (this will show in terminal)
            print("\n=== M-PESA RESPONSE ===")
            print(f"Status: {response.status_code}")
            print(f"Body: {response.text}")
            print("========================")

            # 6. Handle response
            if response.status_code == 200:
                data = response.json()
                
                # Check if M-Pesa returned an error code
                if data.get('ResponseCode') != '0':
                    return Response({
                        "error": "M-Pesa declined the request",
                        "code": data.get('ResponseCode'),
                        "message": data.get('ResponseDescription', 'Unknown error')
                    }, status=400)

                # Save transaction
                transaction = MpesaTransaction.objects.create(
                    user=user,
                    phone_number=phone,
                    amount=amount,
                    merchant_request_id=data.get('MerchantRequestID', ''),
                    checkout_request_id=data.get('CheckoutRequestID', ''),
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
                # Non-200 response from M-Pesa
                return Response({
                    "error": "M-Pesa service error",
                    "status_code": response.status_code,
                    "details": response.text[:500]
                }, status=500)

        except requests.exceptions.Timeout:
            print("⏰ M-Pesa request timed out")
            return Response({"error": "M-Pesa request timed out"}, status=504)
        except requests.exceptions.ConnectionError:
            print("🔌 Could not connect to M-Pesa")
            return Response({"error": "Could not connect to M-Pesa"}, status=503)
        except Exception as e:
            # 👇 THIS captures ANY other error and prints it to terminal
            print("\n" + "="*50)
            print("🚨 UNEXPECTED ERROR IN M-PESA VIEW:")
            traceback.print_exc()  # ← Full error traceback
            print("="*50 + "\n")
            
            # Return a clean error to the user (server stays up)
            return Response({
                "error": "Something went wrong processing your payment",
                "details": str(e) if settings.DEBUG else None
            }, status=500)


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
            print("\n" + "="*50)
            print("🚨 UNEXPECTED ERROR IN CALLBACK:")
            traceback.print_exc()
            print("="*50 + "\n")
            return Response({"error": "Callback error"}, status=500)