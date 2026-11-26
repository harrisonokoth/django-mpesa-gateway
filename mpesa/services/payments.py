
"""
M-PESA Payment Management Service.

Responsibilities:
- Create internal payment transactions.
- Initiate Safaricom STK Push.
- Store Daraja request identifiers.
- Process Safaricom STK callbacks.
- Prevent duplicate callback processing.
- Match callback details against expected payment details.
- Maintain transaction lifecycle and audit information.

Important:
A successful callback is not independent proof of payment.
Transactions remain unverified until reconciliation or
independent verification is completed.
"""

import logging
import uuid

from decimal import Decimal, InvalidOperation

from django.db import transaction as db_transaction
from django.utils import timezone

from mpesa.models import Transaction

from .daraja import (
    initiate_stk_push,
    normalize_phone_number,
    validate_amount,
    DarajaError,
    DarajaTimeoutError,
)


logger = logging.getLogger("mpesa")


# =====================================================
# CUSTOM PAYMENT EXCEPTIONS
# =====================================================

class PaymentError(Exception):
    """Base payment service exception."""


class PaymentNotFoundError(PaymentError):
    """Transaction does not exist."""


class PaymentValidationError(PaymentError):
    """Payment details failed validation."""


class PaymentCallbackError(PaymentError):
    """Invalid or incomplete Safaricom callback."""


# =====================================================
# INTERNAL HELPERS
# =====================================================

def generate_reference():
    """
    Generate a unique internal payment reference.
    """

    return f"HPDS-{uuid.uuid4().hex[:16].upper()}"


def normalize_payment_method(payment_method):
    """
    Normalize supported payment methods.
    """

    method = str(payment_method or "PAYBILL").upper().strip()

    if method not in (
        Transaction.PaymentMethod.PAYBILL,
        Transaction.PaymentMethod.BUY_GOODS,
    ):
        raise PaymentValidationError(
            "Payment method must be PAYBILL or BUY_GOODS."
        )

    return method


def normalize_metadata(metadata):
    """
    Convert Safaricom callback metadata into a dictionary.
    """

    result = {}

    if not isinstance(metadata, list):
        return result

    for item in metadata:
        if not isinstance(item, dict):
            continue

        name = item.get("Name")

        if name:
            result[name] = item.get("Value")

    return result


def get_callback_object(payload):
    """
    Accept either the complete Safaricom callback
    or the inner StkCallback object.
    """

    if not isinstance(payload, dict):
        raise PaymentCallbackError(
            "Callback payload must be a JSON object."
        )

    body = payload.get("Body", payload)

    if not isinstance(body, dict):
        raise PaymentCallbackError(
            "Invalid callback Body."
        )

    callback = body.get("stkCallback", body)

    if not isinstance(callback, dict):
        raise PaymentCallbackError(
            "Invalid STK callback structure."
        )

    return callback


def safe_decimal(value):
    """
    Safely convert callback amounts into Decimal.
    """

    try:
        result = Decimal(str(value))

        if not result.is_finite():
            return None

        return result

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return None


# =====================================================
# CREATE AND INITIATE PAYMENT
# =====================================================

def create_payment(
    phone_number,
    amount,
    account_reference=None,
    transaction_desc=None,
    payment_method="PAYBILL",
    external_reference=None,
    customer_name="",
):
    """
    Create an internal transaction and initiate STK Push.

    The database record is created BEFORE contacting
    Safaricom so the payment attempt is not lost if
    the external request fails.

    Returns:
        Transaction instance.

    Raises:
        PaymentValidationError
        DarajaError
    """

    # ---------------------------------------------
    # Validate incoming details
    # ---------------------------------------------

    try:
        phone = normalize_phone_number(phone_number)
        payment_amount = validate_amount(amount)

    except (ValueError, TypeError) as exc:
        raise PaymentValidationError(str(exc)) from exc

    method = normalize_payment_method(payment_method)

    if external_reference is not None:
        external_reference = str(
            external_reference
        ).strip()

        if not external_reference:
            external_reference = None

        elif len(external_reference) > 100:
            raise PaymentValidationError(
                "External reference cannot exceed 100 characters."
            )

    reference = generate_reference()

    account_ref = (
        account_reference
        or reference[-12:]
    )

    account_ref = str(account_ref).strip()

    if not account_ref or len(account_ref) > 12:
        raise PaymentValidationError(
            "Account reference must contain 1–12 characters."
        )

    description = (
        transaction_desc
        or "Payment"
    )

    description = str(description).strip()

    if not description or len(description) > 13:
        raise PaymentValidationError(
            "Transaction description must contain 1–13 characters."
        )

    shortcode = str(
        getattr(
            __import__("django.conf", fromlist=["settings"]).settings,
            "MPESA_SHORTCODE",
            "",
        )
    ).strip()

    if method == Transaction.PaymentMethod.BUY_GOODS:
        shortcode = str(
            getattr(
                __import__("django.conf", fromlist=["settings"]).settings,
                "MPESA_TILL_NUMBER",
                "",
            )
        ).strip()

    # ---------------------------------------------
    # Create database record first
    # ---------------------------------------------

    payment = Transaction.objects.create(
        reference_id=reference,
        external_reference=external_reference,
        phone_number=phone,
        customer_name=str(customer_name or "")[:150],
        amount=Decimal(payment_amount),
        currency="KES",
        payment_method=method,
        transaction_type=(
            Transaction.TransactionType.CUSTOMER_PAYBILL_ONLINE
            if method == Transaction.PaymentMethod.PAYBILL
            else Transaction.TransactionType.CUSTOMER_BUY_GOODS_ONLINE
        ),
        shortcode=shortcode,
        account_reference=account_ref,
        transaction_description=description,
        status=Transaction.TransactionStatus.PENDING,
    )

    # ---------------------------------------------
    # Initiate Safaricom STK Push
    # ---------------------------------------------

    try:
        response = initiate_stk_push(
            phone_number=phone,
            amount=payment_amount,
            account_reference=account_ref,
            transaction_desc=description,
            payment_method=method,
        )

        with db_transaction.atomic():
            payment = Transaction.objects.select_for_update().get(
                pk=payment.pk
            )

            payment.merchant_request_id = (
                response.get("MerchantRequestID")
            )

            payment.checkout_request_id = (
                response.get("CheckoutRequestID")
            )

            payment.daraja_response = response

            payment.customer_message = (
                response.get("CustomerMessage", "")
            )

            payment.status = (
                Transaction.TransactionStatus.PROCESSING
            )

            payment.save(
                update_fields=[
                    "merchant_request_id",
                    "checkout_request_id",
                    "daraja_response",
                    "customer_message",
                    "status",
                    "updated_at",
                ]
            )

        logger.info(
            "STK Push initiated. Reference: %s",
            payment.reference_id,
        )

        return payment

    except DarajaTimeoutError as exc:

        # A timeout is ambiguous: Safaricom might
        # have received the request despite no response.
        payment.status = Transaction.TransactionStatus.PROCESSING
        payment.error_message = str(exc)
        payment.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )

        logger.warning(
            "STK Push timed out. Reconciliation required. "
            "Reference: %s",
            payment.reference_id,
        )

        raise

    except DarajaError as exc:

        payment.status = Transaction.TransactionStatus.FAILED
        payment.error_message = str(exc)
        payment.completed_at = timezone.now()

        payment.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )

        logger.error(
            "STK Push failed. Reference: %s",
            payment.reference_id,
        )

        raise

    except Exception as exc:

        payment.status = Transaction.TransactionStatus.FAILED
        payment.error_message = (
            "Unexpected payment processing error."
        )
        payment.completed_at = timezone.now()

        payment.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )

        logger.exception(
            "Unexpected payment error. Reference: %s",
            payment.reference_id,
        )

        raise PaymentError(
            "An unexpected error occurred while initiating payment."
        ) from exc


# =====================================================
# CALLBACK PROCESSING
# =====================================================

def process_stk_callback(payload):
    """
    Process a Safaricom STK Push callback.

    Processing rules:

    1. Locate the transaction using CheckoutRequestID.
    2. Ignore duplicate processed callbacks.
    3. Save the original callback payload.
    4. Extract payment metadata.
    5. Compare amount and phone with the original request.
    6. Record callback-reported success or failure.
    7. Never independently verify payment from callback alone.

    Returns:
        Transaction instance.
    """

    callback = get_callback_object(payload)

    checkout_request_id = callback.get(
        "CheckoutRequestID"
    )

    if not checkout_request_id:
        raise PaymentCallbackError(
            "CheckoutRequestID is missing from callback."
        )

    result_code = callback.get("ResultCode")

    if result_code is None:
        raise PaymentCallbackError(
            "ResultCode is missing from callback."
        )

    try:
        result_code = int(result_code)

    except (TypeError, ValueError) as exc:
        raise PaymentCallbackError(
            "Invalid callback ResultCode."
        ) from exc

    # ---------------------------------------------
    # Find and lock the transaction
    # ---------------------------------------------

    with db_transaction.atomic():

        try:
            payment = Transaction.objects.select_for_update().get(
                checkout_request_id=checkout_request_id
            )

        except Transaction.DoesNotExist as exc:
            logger.warning(
                "Callback received for unknown CheckoutRequestID."
            )

            raise PaymentNotFoundError(
                "No transaction matches this CheckoutRequestID."
            ) from exc

        # -----------------------------------------
        # Duplicate callback protection
        # -----------------------------------------

        if payment.callback_processed:
            logger.info(
                "Duplicate callback ignored. Reference: %s",
                payment.reference_id,
            )

            return payment

        # -----------------------------------------
        # Extract callback metadata
        # -----------------------------------------

        metadata = normalize_metadata(
            callback.get("CallbackMetadata", {}).get("Item", [])
        )

        receipt_number = metadata.get(
            "MpesaReceiptNumber"
        )

        callback_amount = safe_decimal(
            metadata.get("Amount")
        )

        callback_phone = metadata.get(
            "PhoneNumber"
        )

        callback_description = callback.get(
            "ResultDesc",
            "",
        )

        payment.callback_received = True
        payment.callback_received_at = timezone.now()
        payment.callback_data = payload
        payment.callback_attempts += 1

        payment.result_code = result_code
        payment.result_description = str(
            callback_description
        )

        payment.customer_message = str(
            callback_description
        )

        # -----------------------------------------
        # Failed or cancelled payment
        # -----------------------------------------

        if result_code != 0:

            if result_code == 1032:
                payment.status = (
                    Transaction.TransactionStatus.CANCELLED
                )

            elif result_code == 1037:
                payment.status = (
                    Transaction.TransactionStatus.EXPIRED
                )

            else:
                payment.status = (
                    Transaction.TransactionStatus.FAILED
                )

            payment.error_code = str(result_code)
            payment.error_message = str(
                callback_description
            )

            payment.is_verified = False
            payment.verified_at = None

        # -----------------------------------------
        # Successful callback: validate metadata
        # -----------------------------------------

        else:

            mismatch_reasons = []

            if callback_amount is None:
                mismatch_reasons.append(
                    "Callback amount is missing or invalid."
                )

            elif callback_amount != payment.amount:
                mismatch_reasons.append(
                    "Callback amount does not match the requested amount."
                )

            if callback_phone is None:
                mismatch_reasons.append(
                    "Callback phone number is missing."
                )

            else:
                try:
                    normalized_callback_phone = (
                        normalize_phone_number(callback_phone)
                    )

                    if normalized_callback_phone != payment.phone_number:
                        mismatch_reasons.append(
                            "Callback phone number does not match the requested number."
                        )

                except ValueError:
                    mismatch_reasons.append(
                        "Callback phone number is invalid."
                    )

            if not receipt_number:
                mismatch_reasons.append(
                    "M-PESA receipt number is missing."
                )

            # -------------------------------------
            # Reject mismatched payment details
            # -------------------------------------

            if mismatch_reasons:

                payment.status = (
                    Transaction.TransactionStatus.PROCESSING
                )

                payment.error_code = "CALLBACK_MISMATCH"

                payment.error_message = " ".join(
                    mismatch_reasons
                )

                payment.is_verified = False
                payment.verified_at = None

                logger.warning(
                    "Callback mismatch. Reference: %s",
                    payment.reference_id,
                )

            else:

                # ---------------------------------
                # Record callback-reported success
                # ---------------------------------

                payment.status = (
                    Transaction.TransactionStatus.SUCCESS
                )

                payment.mpesa_receipt_number = str(
                    receipt_number
                )

                payment.error_code = ""
                payment.error_message = ""

                # A callback is not independent verification.
                payment.is_verified = False
                payment.verified_at = None

        # -----------------------------------------
        # Final callback bookkeeping
        # -----------------------------------------

        payment.callback_processed = True

        if payment.status in (
            Transaction.TransactionStatus.SUCCESS,
            Transaction.TransactionStatus.FAILED,
            Transaction.TransactionStatus.CANCELLED,
            Transaction.TransactionStatus.EXPIRED,
        ):
            payment.completed_at = timezone.now()

        payment.save()

        logger.info(
            "Callback processed. Reference: %s, Status: %s",
            payment.reference_id,
            payment.status,
        )

        return payment


# =====================================================
# TRANSACTION RETRIEVAL
# =====================================================

def get_payment(reference_id):
    """
    Retrieve a payment using its internal reference.
    """

    try:
        return Transaction.objects.get(
            reference_id=reference_id
        )

    except Transaction.DoesNotExist as exc:
        raise PaymentNotFoundError(
            "Payment transaction was not found."
        ) from exc


def get_payment_by_checkout_id(checkout_request_id):
    """
    Retrieve a payment using its Safaricom CheckoutRequestID.
    """

    try:
        return Transaction.objects.get(
            checkout_request_id=checkout_request_id
        )

    except Transaction.DoesNotExist as exc:
        raise PaymentNotFoundError(
            "No payment matches the supplied CheckoutRequestID."
        ) from exc
