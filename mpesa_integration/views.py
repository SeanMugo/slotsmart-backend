# mpesa_integration/views.py
import traceback
from datetime import datetime

import requests

from django.conf import settings

from rest_framework import status
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from parking.models import ParkingSession

from .models import MpesaTransaction
from .serializers import MpesaSTKPushSerializer
from .services import send_stk_push


class MpesaAuth:
    @staticmethod
    def get_access_token():
        """
        Generate Safaricom OAuth Access Token.
        """

        consumer_key = settings.MPESA_CONSUMER_KEY
        consumer_secret = settings.MPESA_CONSUMER_SECRET

        api_url = (
            "https://sandbox.safaricom.co.ke/"
            "oauth/v1/generate?grant_type=client_credentials"
        )

        try:
            response = requests.get(
                api_url,
                auth=(consumer_key, consumer_secret),
                timeout=30,
            )

            if response.status_code == 200:
                return response.json().get("access_token")

            print(
                f"Access Token Error:"
                f" {response.status_code}"
            )
            print(response.text)

            return None

        except Exception as e:
            print(e)
            return None


class MpesaSTKPushView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = MpesaSTKPushSerializer(
            data=request.data
        )

        if not serializer.is_valid():

            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone = serializer.validated_data[
            "phone_number"
        ]

        amount = serializer.validated_data[
            "amount"
        ]

        parking_session_id = serializer.validated_data[
            "parking_session_id"
        ]

        try:

            parking_session = ParkingSession.objects.get(
                id=parking_session_id,
            )

        except ParkingSession.DoesNotExist:

            return Response(
                {
                    "error": "Parking session not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        user = parking_session.user

        result = send_stk_push(
            user=user,
            parking_session=parking_session,
            phone_number=phone,
            amount=amount,
        )

        if not result["success"]:

            return Response(
                {
                    "error": result["error"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "success": True,
                "message": (
                    "STK Push sent successfully. "
                    "Complete payment on your phone."
                ),
                "transaction_id": result[
                    "transaction"
                ].id,
                "checkout_request_id": result[
                    "transaction"
                ].checkout_request_id,
            }
        )
    
class MpesaCallbackView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        try:

            print("\n========== M-PESA CALLBACK ==========")
            print(request.data)

            callback = (
                request.data
                .get("Body", {})
                .get("stkCallback", {})
            )

            checkout_request_id = callback.get(
                "CheckoutRequestID"
            )

            result_code = callback.get(
                "ResultCode"
            )

            result_description = callback.get(
                "ResultDesc"
            )

            if not checkout_request_id:

                return Response(
                    {
                        "error": "CheckoutRequestID missing."
                    },
                    status=400,
                )

            try:

                transaction = MpesaTransaction.objects.get(
                    checkout_request_id=checkout_request_id
                )

            except MpesaTransaction.DoesNotExist:

                return Response(
                    {
                        "error": "Transaction not found."
                    },
                    status=404,
                )

            transaction.response_code = result_code
            transaction.response_description = (
                result_description
            )
            transaction.callback_data = request.data

            # ===================================
            # PAYMENT FAILED
            # ===================================

            if str(result_code) != "0":

                transaction.status = "failed"
                transaction.save()

                session = transaction.parking_session

                if session:
                    session.payment_status = "failed"
                    session.save()

                return Response(
                    {
                        "message": "Payment failed."
                    }
                )

            # ===================================
            # PAYMENT SUCCESS
            # ===================================

            callback_items = (
                callback.get(
                    "CallbackMetadata",
                    {}
                )
                .get("Item", [])
            )

            receipt = None
            transaction_date = None

            for item in callback_items:

                name = item.get("Name")

                if name == "MpesaReceiptNumber":
                    receipt = item.get("Value")

                elif name == "TransactionDate":

                    value = str(item.get("Value"))

                    try:

                        transaction_date = datetime.strptime(
                            value,
                            "%Y%m%d%H%M%S",
                        )

                    except Exception:
                        pass

            transaction.status = "success"
            transaction.mpesa_receipt = receipt
            transaction.transaction_date = transaction_date

            transaction.save()

            session = transaction.parking_session

            if session:

                session.payment_status = "paid"
                session.status = "completed"
                session.save()

                slot = session.slot
                slot.status = "available"
                slot.save()

            print(
                f"Payment complete "
                f"{transaction.checkout_request_id}"
            )

            return Response(
                {
                    "message": "Callback processed."
                }
            )

        except Exception:

            traceback.print_exc()

            return Response(
                {
                    "error": "Callback processing failed."
                },
                status=500,
            )