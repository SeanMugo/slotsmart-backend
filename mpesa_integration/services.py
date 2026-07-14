import base64
from datetime import datetime

import requests

from django.conf import settings

from .models import MpesaTransaction


def send_stk_push(
    *,
    user,
    parking_session,
    phone_number,
    amount,
):
    """
    Send an STK Push to the supplied phone number.

    Returns:
    {
        success,
        transaction,
        error
    }
    """

    # Local import to avoid circular import
    from .views import MpesaAuth

    access_token = MpesaAuth.get_access_token()

    if not access_token:
        return {
            "success": False,
            "error": "Unable to authenticate with Safaricom.",
        }

    timestamp = datetime.now().strftime(
        "%Y%m%d%H%M%S"
    )

    password = base64.b64encode(
        (
            settings.MPESA_SHORTCODE
            + settings.MPESA_PASSKEY
            + timestamp
        ).encode()
    ).decode()

    callback_url = (
        f"{settings.BASE_URL}/api/mpesa/callback/"
    )

    payload = {
        "BusinessShortCode": int(settings.MPESA_SHORTCODE),
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": int(settings.MPESA_SHORTCODE),
        "PhoneNumber": phone_number,
        "CallBackURL": callback_url,
        "AccountReference": f"PS{parking_session.id}",
        "TransactionDesc": "Parking Payment",
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers=headers,
            timeout=30,
        )

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }

    if response.status_code != 200:
        return {
            "success": False,
            "error": response.text,
        }

    data = response.json()

    if data.get("ResponseCode") != "0":
        return {
            "success": False,
            "error": data.get("ResponseDescription"),
        }

    transaction = MpesaTransaction.objects.create(
        user=user,
        parking_session=parking_session,
        phone_number=phone_number,
        amount=amount,
        merchant_request_id=data.get("MerchantRequestID"),
        checkout_request_id=data.get("CheckoutRequestID"),
        status="pending",
        response_code=data.get("ResponseCode"),
        response_description=data.get("ResponseDescription"),
    )

    return {
        "success": True,
        "transaction": transaction,
    }