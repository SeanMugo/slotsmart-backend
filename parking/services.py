from decimal import Decimal

from .models import WalletTransaction


def process_payment(session):
    """
    Determines how a parking session will be paid.

    Wallet Only
        - Deduct immediately.

    Hybrid
        - Reserve wallet amount.
        - Wait for successful STK callback before deducting.

    M-Pesa
        - Wait for successful STK callback.

    Returns:
    {
        success,
        payment_required,
        payment_method,
        wallet_used,
        mpesa_required,
        transaction
    }
    """

    user = session.user

    total_fee = Decimal(session.total_fee)
    wallet = Decimal(user.wallet_balance)

    # ============================
    # WALLET ONLY
    # ============================

    if wallet >= total_fee:

        # Deduct immediately
        user.wallet_balance -= total_fee
        user.save()

        session.wallet_amount = total_fee
        session.mpesa_amount = Decimal("0.00")
        session.payment_method = "wallet"
        session.payment_status = "paid"

        transaction = WalletTransaction.objects.create(
            user=user,
            parking_session=session,
            total_amount=total_fee,
            wallet_amount=total_fee,
            mpesa_amount=Decimal("0.00"),
            status="completed",
            description="Parking payment via wallet",
        )

        return {
            "success": True,
            "payment_required": False,
            "payment_method": "wallet",
            "wallet_used": total_fee,
            "mpesa_required": Decimal("0.00"),
            "transaction": transaction,
        }

    # ============================
    # HYBRID PAYMENT
    # ============================

    elif wallet > 0:

        remaining = total_fee - wallet

        # DO NOT deduct wallet yet.
        # Wait until STK callback confirms payment.

        session.wallet_amount = wallet
        session.mpesa_amount = remaining
        session.payment_method = "hybrid"
        session.payment_status = "pending"

        transaction = WalletTransaction.objects.create(
            user=user,
            parking_session=session,
            total_amount=total_fee,
            wallet_amount=wallet,
            mpesa_amount=remaining,
            status="pending",
            description="Hybrid parking payment",
        )

        return {
            "success": True,
            "payment_required": True,
            "payment_method": "hybrid",
            "wallet_used": wallet,
            "mpesa_required": remaining,
            "transaction": transaction,
        }

    # ============================
    # M-PESA ONLY
    # ============================

    session.wallet_amount = Decimal("0.00")
    session.mpesa_amount = total_fee
    session.payment_method = "mpesa"
    session.payment_status = "pending"

    transaction = WalletTransaction.objects.create(
        user=user,
        parking_session=session,
        total_amount=total_fee,
        wallet_amount=Decimal("0.00"),
        mpesa_amount=total_fee,
        status="pending",
        description="Parking payment via M-Pesa",
    )

    return {
        "success": True,
        "payment_required": True,
        "payment_method": "mpesa",
        "wallet_used": Decimal("0.00"),
        "mpesa_required": total_fee,
        "transaction": transaction,
    }