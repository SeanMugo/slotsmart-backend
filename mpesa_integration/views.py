# mpesa_integration/views.py
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

        try:
            response = requests.get(api_url, auth=(consumer_key, consumer_secret), timeout=30)
            print("=== ACCESS TOKEN RESPONSE ===")
            print("Status:", response.status_code)
            print("Response:", response.text[:200])  # Print first 200 chars
            print("==============================")
            
            if response.status_code == 200:
                return response.json().get('access_token')
            else:
                print("Failed to get access token:", response.text)
                return None
        except Exception as e:
            print("Access token error:", str(e))
            return None


class MpesaSTKPushView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            print("\n=== NEW STK PUSH REQUEST ===")
            print("User:", request.user.username)
            print("Data:", request.data)

            serializer = MpesaSTKPushSerializer(data=request.data)
            if not serializer.is_valid():
                print("Serializer errors:", serializer.errors)
                return Response(serializer.errors, status=400)

            phone = serializer.validated_data['phone_number']
            amount = serializer.validated_data['amount']
            user = request.user

            # 1. Get Access Token
            access_token = MpesaAuth.get_access_token()
            if not access_token:
                return Response({"error": "Could not authenticate with M-Pesa"}, status=500)

            # 2. Prepare STK Push Request
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
                "CallBackURL": "https://uplifting-armhole-fling.ngrok-free.dev/api/mpesa/callback/",
                "AccountReference": user.username,
                "TransactionDesc": f"Parking payment for {user.username}"
            }

            print("\n=== STK PUSH PAYLOAD ===")
            print(payload)
            print("=========================")

            # 3. Send request to M-Pesa
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)

            print("\n=== M-PESA STK PUSH RESPONSE ===")
            print("Status Code:", response.status_code)
            print("Response Text:", response.text)
            print("=================================")

            if response.status_code == 200:
                data = response.json()
                
                # Check if M-Pesa returned an error code
                if data.get('ResponseCode') != '0':
                    print("M-Pesa returned error:", data)
                    return Response({
                        "error": data.get('ResponseDescription', 'M-Pesa error'),
                        "response_code": data.get('ResponseCode')
                    }, status=400)

                # Save transaction
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
                print("M-Pesa error response:", response.text)
                return Response({
                    "error": "M-Pesa payment initiation failed",
                    "details": response.text
                }, status=500)

        except requests.exceptions.Timeout:
            print("Request timed out")
            return Response({"error": "M-Pesa request timed out"}, status=504)
        except requests.exceptions.ConnectionError as e:
            print("Connection error:", str(e))
            return Response({"error": "Could not connect to M-Pesa: " + str(e)}, status=503)
        except Exception as e:
            import traceback
            print("\n=== UNEXPECTED EXCEPTION ===")
            traceback.print_exc()
            print("=============================")
            return Response({"error": str(e)}, status=500)


class MpesaCallbackView(APIView):
    permission_classes = []

    def post(self, request):
        try:
            print("\n=== M-PESA CALLBACK RECEIVED ===")
            print("Full callback data:", request.data)
            print("=================================")

            data = request.data
            result_code = data.get('Body', {}).get('stkCallback', {}).get('ResultCode')
            checkout_request_id = data.get('Body', {}).get('stkCallback', {}).get('CheckoutRequestID')
            result_desc = data.get('Body', {}).get('stkCallback', {}).get('ResultDesc')

            print(f"Result Code: {result_code}")
            print(f"Checkout Request ID: {checkout_request_id}")
            print(f"Result Description: {result_desc}")

            if not checkout_request_id:
                print("Missing checkout_request_id in callback")
                return Response({"error": "Invalid callback data"}, status=400)

            transaction = MpesaTransaction.objects.get(checkout_request_id=checkout_request_id)
            print(f"Found transaction: {transaction.id}")

            if result_code == 0:
                transaction.status = 'success'
                print("✅ Transaction marked as SUCCESS")
            else:
                transaction.status = 'failed'
                print("❌ Transaction marked as FAILED")

            transaction.save()
            return Response({"message": "Callback processed successfully"}, status=200)

        except MpesaTransaction.DoesNotExist:
            print(f"Transaction not found for: {checkout_request_id}")
            return Response({"error": "Transaction not found"}, status=404)
        except Exception as e:
            import traceback
            print("Callback error:", str(e))
            traceback.print_exc()
            return Response({"error": str(e)}, status=500)