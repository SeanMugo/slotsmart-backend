# parking/utils.py

from math import ceil
from decimal import Decimal
from django.utils import timezone


def calculate_duration_hours(check_in_time, check_out_time=None):
    """
    Calculate parking duration.

    Any fraction of an hour is rounded UP.

    Examples:
        15 mins  -> 1 hour
        61 mins  -> 2 hours
        2h 15m   -> 3 hours
    """

    if check_out_time is None:
        check_out_time = timezone.now()

    seconds = (check_out_time - check_in_time).total_seconds()

    hours = seconds / 3600

    return max(1, ceil(hours))


def calculate_amount(hourly_rate, duration_hours):
    """
    Calculate total parking fee.
    """

    return Decimal(hourly_rate) * Decimal(duration_hours)


def calculate_parking_fee(session):
    """
    Calculates parking duration and total fee.
    Used during checkout.
    """

    duration = calculate_duration_hours(
        session.check_in_time,
        session.check_out_time or timezone.now(),
    )

    total_fee = calculate_amount(
        session.hourly_rate,
        duration,
    )

    return {
        "duration_hours": duration,
        "total_fee": total_fee,
    }