
"""
Django views for the M-PESA Gateway.

Responsibilities:
- Homepage
- STK Push payment interface
- Safaricom callback endpoint
- Transaction status lookup
"""

import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .forms import STKPushForm
from .models import Transaction

from .services.daraja import DarajaError

from .services.payments import (
    create_payment,
    process_stk_callback,
    get_payment,
    PaymentError,
    PaymentNotFoundError,
    PaymentValidationError,
)


logger = logging.getLogger("mpesa")


# =====================================================
# HOMEPAGE
# =====================================================

@require_GET
def home(request):
    """
    Display the gateway homepage.
    """

    return render(
        request,
        "mpesa/home.html",
    )


# =====================================================
# STK PUSH PAYMENT PAGE
# =====================================================

def test_payment(request):
    """
    Display the STK Push test form and process payments.

    Uses the payment service layer rather than communicating
    directly with Safaricom from the view.
    """

    form = STKPushForm(request.POST or None)

    context = {
        "form": form,
        "success": False,
        "error": None,
        "payment": None,
        "result": None,
    }

    if request.method == "POST":

        if form.is_valid():

            try:
                payment = create_payment(
                    phone_number=form.cleaned_data["phone"],
                    amount=form.cleaned_data["amount"],
                    account_reference=form.cleaned_data["reference"],
                    transaction_desc="Payment",
                    payment_method="PAYBILL",
                )

                context.update({
                    "success": True,
                    "payment": payment,
                    "result": payment.daraja_response,
                })

                logger.info(
                    "Payment form submitted. Reference: %s",
                    payment.reference_id,
                )

            except (DarajaError, PaymentError, ValueError) as exc:

                context["error"] = str(exc)

                logger.warning(
                    "Payment initiation failed: %s",
                    exc,
                )

            except Exception:

                context["error"] = (
                    "An unexpected error occurred. "
                    "Please check the application logs."
                )

                logger.exception(
                    "Unexpected error in STK Push payment view."
                )

    return render(
        request,
        "mpesa/test_payment.html",
        context,
    )


# =====================================================
# SAFARICOM CALLBACK
# =====================================================

@csrf_exempt
@require_POST
def mpesa_callback(request):
    """
    Receive and process Safaricom STK Push callbacks.

    Safaricom sends JSON containing:
        Body
          └── stkCallback
                ├── MerchantRequestID
                ├── CheckoutRequestID
                ├── ResultCode
                ├── ResultDesc
                └── CallbackMetadata

    The payment service matches the callback against
    the original transaction and records its outcome.

    IMPORTANT:
    Callback receipt alone is not independent payment
    verification.
    """

    try:

        payload = json.loads(
            request.body.decode("utf-8")
        )

        payment = process_stk_callback(payload)

        logger.info(
            "Safaricom callback processed. "
            "Reference: %s, Status: %s",
            payment.reference_id,
            payment.status,
        )

        return JsonResponse({
            "ResultCode": 0,
            "ResultDesc": "Callback processed successfully.",
        })

    except (json.JSONDecodeError, UnicodeDecodeError):

        logger.warning(
            "Invalid JSON received at M-PESA callback endpoint."
        )

        return JsonResponse(
            {
                "ResultCode": 1,
                "ResultDesc": "Invalid JSON payload.",
            },
            status=400,
        )

    except PaymentNotFoundError as exc:

        logger.error(
            "Safaricom callback could not be matched: %s",
            exc,
        )

        # Acknowledge the callback to avoid repeated delivery.
        # The unmatched callback must be investigated.
        return JsonResponse({
            "ResultCode": 0,
            "ResultDesc": "Callback received for reconciliation.",
        })

    except PaymentError as exc:

        logger.error(
            "M-PESA callback processing error: %s",
            exc,
        )

        return JsonResponse({
            "ResultCode": 0,
            "ResultDesc": "Callback received for manual review.",
        })

    except Exception:

        logger.exception(
            "Unexpected error while processing Safaricom callback."
        )

        return JsonResponse(
            {
                "ResultCode": 1,
                "ResultDesc": "Callback processing error.",
            },
            status=500,
        )


# =====================================================
# TRANSACTION STATUS LOOKUP
# =====================================================

@require_GET
def transaction_status(request, reference_id):
    """
    Return transaction details using the internal reference.

    This endpoint is intended for local testing.
    External API authentication will be introduced later.
    """

    try:

        payment = get_payment(reference_id)

    except PaymentNotFoundError:

        return JsonResponse(
            {
                "success": False,
                "message": "Transaction not found.",
            },
            status=404,
        )

    return JsonResponse({
        "success": True,
        "transaction": {
            "reference": payment.reference_id,
            "external_reference": payment.external_reference,
            "phone_number": payment.phone_number,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "payment_method": payment.payment_method,
            "status": payment.status,
            "receipt_number": payment.mpesa_receipt_number,
            "is_verified": payment.is_verified,
            "callback_received": payment.callback_received,
            "created_at": payment.created_at.isoformat(),
            "completed_at": (
                payment.completed_at.isoformat()
                if payment.completed_at
                else None
            ),
        },
    })


# =====================================================
# TRANSACTION LIST
# =====================================================

@require_GET
def transaction_list(request):
    """
    Display recent transactions.

    This page is intended for local development.
    Production access will be protected through
    authentication and permissions.
    """

    transactions = Transaction.objects.all()[:100]

    return render(
        request,
        "mpesa/transactions.html",
        {
            "transactions": transactions,
        },
    )
