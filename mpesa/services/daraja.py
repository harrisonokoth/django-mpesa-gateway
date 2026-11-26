
"""
Safaricom Daraja API integration service.

Responsibilities:
- OAuth authentication
- Access token caching
- STK Push initiation
- PayBill and Buy Goods support
- STK transaction status queries
- Daraja API error handling

Business transaction management is handled separately.
"""

import base64
import logging
import re

from decimal import Decimal, InvalidOperation
from datetime import datetime

import requests

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


logger = logging.getLogger("mpesa")


# =====================================================
# CUSTOM EXCEPTIONS
# =====================================================

class DarajaError(Exception):
    """Base Daraja integration exception."""


class DarajaConfigurationError(DarajaError):
    """Invalid or missing Daraja configuration."""


class DarajaAuthenticationError(DarajaError):
    """Daraja OAuth authentication failure."""


class DarajaRequestError(DarajaError):
    """Daraja API request failure."""


class DarajaTimeoutError(DarajaRequestError):
    """Daraja API request timeout."""


# =====================================================
# CONFIGURATION
# =====================================================

REQUEST_TIMEOUT = 30

TOKEN_CACHE_PREFIX = "mpesa_daraja_token"


def get_environment():
    environment = getattr(
        settings,
        "MPESA_ENVIRONMENT",
        "sandbox",
    )

    environment = environment.lower().strip()

    if environment not in ("sandbox", "production"):
        raise DarajaConfigurationError(
            "MPESA_ENVIRONMENT must be sandbox or production."
        )

    return environment


def get_base_url():
    environment = get_environment()

    if environment == "production":
        return "https://api.safaricom.co.ke"

    return "https://sandbox.safaricom.co.ke"


def get_setting(name, default=""):
    return str(
        getattr(settings, name, default) or ""
    ).strip()


def validate_oauth_configuration():
    """
    Validate only OAuth-related configuration.

    Callback URLs and payment settings are deliberately
    excluded so OAuth can be tested independently.
    """

    consumer_key = get_setting("MPESA_CONSUMER_KEY")
    consumer_secret = get_setting("MPESA_CONSUMER_SECRET")

    if not consumer_key:
        raise DarajaConfigurationError(
            "MPESA_CONSUMER_KEY is missing."
        )

    if not consumer_secret:
        raise DarajaConfigurationError(
            "MPESA_CONSUMER_SECRET is missing."
        )

    get_environment()

    return consumer_key, consumer_secret


def validate_stk_configuration(payment_method="PAYBILL"):
    """
    Validate configuration required for STK Push.
    """

    validate_oauth_configuration()

    shortcode = get_setting("MPESA_SHORTCODE")
    passkey = get_setting("MPESA_PASSKEY")
    callback_url = get_setting("MPESA_CALLBACK_URL")

    if not shortcode:
        raise DarajaConfigurationError(
            "MPESA_SHORTCODE is missing."
        )

    if not passkey:
        raise DarajaConfigurationError(
            "MPESA_PASSKEY is missing."
        )

    if not callback_url:
        raise DarajaConfigurationError(
            "MPESA_CALLBACK_URL is missing."
        )

    if not callback_url.startswith("https://"):
        raise DarajaConfigurationError(
            "The Daraja callback URL must use HTTPS."
        )

    if "yourdomain.com" in callback_url.lower():
        raise DarajaConfigurationError(
            "Replace the placeholder callback URL."
        )

    if payment_method == "BUY_GOODS":
        till_number = get_setting("MPESA_TILL_NUMBER")

        if not till_number:
            raise DarajaConfigurationError(
                "MPESA_TILL_NUMBER is required for Buy Goods."
            )

    return True


# =====================================================
# RESPONSE HANDLING
# =====================================================

def parse_response(response):
    try:
        return response.json()

    except ValueError:
        return {
            "raw_response": response.text[:2000]
        }


def raise_for_daraja_error(response, operation):
    """
    Convert HTTP failures into meaningful Daraja exceptions.
    """

    if response.ok:
        return

    data = parse_response(response)

    logger.error(
        "Daraja %s failed. HTTP status: %s",
        operation,
        response.status_code,
    )

    error_message = (
        data.get("errorMessage")
        or data.get("error_description")
        or data.get("ResponseDescription")
        or data.get("message")
        or data.get("raw_response")
        or "Unknown Safaricom API error."
    )

    error_code = (
        data.get("errorCode")
        or data.get("requestId")
        or response.status_code
    )

    message = (
        f"Daraja {operation} failed: "
        f"{error_message} "
        f"(Code: {error_code})"
    )

    if response.status_code in (401, 403):
        raise DarajaAuthenticationError(message)

    raise DarajaRequestError(message)


# =====================================================
# OAUTH AUTHENTICATION
# =====================================================

def get_access_token(force_refresh=False):
    """
    Retrieve a Safaricom OAuth access token.

    The token is cached until shortly before expiry.
    """

    consumer_key, consumer_secret = (
        validate_oauth_configuration()
    )

    environment = get_environment()

    cache_key = (
        f"{TOKEN_CACHE_PREFIX}_{environment}_"
        f"{consumer_key[:12]}"
    )

    if not force_refresh:
        cached_token = cache.get(cache_key)

        if cached_token:
            return cached_token

    url = (
        f"{get_base_url()}"
        "/oauth/v1/generate"
    )

    try:
        response = requests.get(
            url,
            params={
                "grant_type": "client_credentials"
            },
            auth=(
                consumer_key,
                consumer_secret,
            ),
            headers={
                "Accept": "application/json"
            },
            timeout=REQUEST_TIMEOUT,
        )

        raise_for_daraja_error(
            response,
            "OAuth authentication",
        )

        data = parse_response(response)

        access_token = data.get("access_token")

        if not access_token:
            raise DarajaAuthenticationError(
                "Safaricom did not return an access token."
            )

        expires_in = int(
            data.get("expires_in", 3600)
        )

        cache_timeout = max(
            60,
            expires_in - 120,
        )

        cache.set(
            cache_key,
            access_token,
            timeout=cache_timeout,
        )

        logger.info(
            "Daraja OAuth authentication successful."
        )

        return access_token

    except requests.Timeout as exc:
        raise DarajaTimeoutError(
            "Safaricom OAuth request timed out."
        ) from exc

    except requests.ConnectionError as exc:
        raise DarajaRequestError(
            "Unable to connect to Safaricom OAuth."
        ) from exc

    except requests.RequestException as exc:
        raise DarajaRequestError(
            f"OAuth communication error: {exc}"
        ) from exc


# =====================================================
# TIMESTAMP AND PASSWORD GENERATION
# =====================================================

def get_daraja_timestamp():
    """
    Generate the Daraja-required timestamp.

    Format: YYYYMMDDHHMMSS
    """

    return timezone.localtime().strftime(
        "%Y%m%d%H%M%S"
    )


def generate_stk_password(timestamp=None):
    """
    Generate the Base64 STK password.

    Password = Base64(
        BusinessShortCode + Passkey + Timestamp
    )
    """

    shortcode = get_setting("MPESA_SHORTCODE")
    passkey = get_setting("MPESA_PASSKEY")

    if not shortcode or not passkey:
        raise DarajaConfigurationError(
            "Shortcode and passkey are required."
        )

    timestamp = timestamp or get_daraja_timestamp()

    raw_password = (
        f"{shortcode}{passkey}{timestamp}"
    )

    encoded_password = base64.b64encode(
        raw_password.encode("utf-8")
    ).decode("utf-8")

    return encoded_password


# =====================================================
# INPUT VALIDATION
# =====================================================

def normalize_phone_number(phone_number):
    """
    Normalize Kenyan phone numbers to 254XXXXXXXXX.
    """

    phone = re.sub(
        r"[\s\-\(\)]",
        "",
        str(phone_number),
    )

    if phone.startswith("+"):
        phone = phone[1:]

    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]

    elif phone.startswith("7") and len(phone) == 9:
        phone = "254" + phone

    elif phone.startswith("1") and len(phone) == 9:
        phone = "254" + phone

    if not re.fullmatch(r"254[17]\d{8}", phone):
        raise ValueError(
            "Enter a valid Kenyan Safaricom-compatible "
            "phone number, e.g. 254712345678."
        )

    return phone


def validate_amount(amount):
    """
    Validate STK Push amount.

    Daraja STK Push accepts whole-number amounts.
    """

    try:
        value = Decimal(str(amount))

    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(
            "Enter a valid payment amount."
        )

    if not value.is_finite() or value <= 0:
        raise ValueError(
            "Payment amount must be greater than zero."
        )

    if value != value.to_integral_value():
        raise ValueError(
            "STK Push amount must be a whole number."
        )

    return int(value)


# =====================================================
# STK PUSH
# =====================================================

def initiate_stk_push(
    phone_number,
    amount,
    account_reference=None,
    transaction_desc=None,
    payment_method="PAYBILL",
):
    """
    Initiate an STK Push request.

    payment_method:
        PAYBILL
        BUY_GOODS

    Returns the raw Safaricom response dictionary.

    This function does not create or update database
    transactions. That responsibility belongs to
    the payment service layer.
    """

    payment_method = payment_method.upper().strip()

    if payment_method not in ("PAYBILL", "BUY_GOODS"):
        raise ValueError(
            "Payment method must be PAYBILL or BUY_GOODS."
        )

    validate_stk_configuration(payment_method)

    phone = normalize_phone_number(phone_number)
    payment_amount = validate_amount(amount)

    shortcode = get_setting("MPESA_SHORTCODE")
    callback_url = get_setting("MPESA_CALLBACK_URL")

    reference = (
        account_reference
        or get_setting(
            "MPESA_ACCOUNT_REFERENCE",
            "Payment",
        )
    )

    description = (
        transaction_desc
        or get_setting(
            "MPESA_TRANSACTION_DESC",
            "Payment",
        )
    )

    reference = str(reference).strip()
    description = str(description).strip()

    if not reference or len(reference) > 12:
        raise ValueError(
            "Account reference must contain 1–12 characters."
        )

    if not description or len(description) > 13:
        raise ValueError(
            "Transaction description must contain 1–13 characters."
        )

    # PayBill and Buy Goods use different transaction types.
    if payment_method == "PAYBILL":

        transaction_type = "CustomerPayBillOnline"
        party_b = shortcode

    else:

        transaction_type = "CustomerBuyGoodsOnline"
        party_b = get_setting("MPESA_TILL_NUMBER")

    timestamp = get_daraja_timestamp()
    password = generate_stk_password(timestamp)

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": transaction_type,
        "Amount": payment_amount,
        "PartyA": phone,
        "PartyB": party_b,
        "PhoneNumber": phone,
        "CallBackURL": callback_url,
        "AccountReference": reference,
        "TransactionDesc": description,
    }

    access_token = get_access_token()

    url = (
        f"{get_base_url()}"
        "/mpesa/stkpush/v1/processrequest"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        raise_for_daraja_error(
            response,
            "STK Push",
        )

        data = parse_response(response)

        if not data.get("CheckoutRequestID"):
            raise DarajaRequestError(
                "Safaricom response did not contain "
                "a CheckoutRequestID."
            )

        logger.info(
            "STK Push accepted. Payment method: %s",
            payment_method,
        )

        return data

    except requests.Timeout as exc:
        raise DarajaTimeoutError(
            "STK Push request timed out. "
            "Check transaction status before retrying "
            "to avoid duplicate payments."
        ) from exc

    except requests.ConnectionError as exc:
        raise DarajaRequestError(
            "Unable to connect to Safaricom STK Push."
        ) from exc

    except requests.RequestException as exc:
        raise DarajaRequestError(
            f"STK Push communication error: {exc}"
        ) from exc


# =====================================================
# STK TRANSACTION STATUS QUERY
# =====================================================

def query_stk_status(checkout_request_id):
    """
    Query the status of an STK Push transaction.

    This returns Safaricom's query response.
    It does not automatically mark a database
    transaction as successful or verified.
    """

    validate_stk_configuration("PAYBILL")

    checkout_request_id = str(
        checkout_request_id
    ).strip()

    if not checkout_request_id:
        raise ValueError(
            "CheckoutRequestID is required."
        )

    shortcode = get_setting("MPESA_SHORTCODE")

    timestamp = get_daraja_timestamp()
    password = generate_stk_password(timestamp)

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }

    access_token = get_access_token()

    url = (
        f"{get_base_url()}"
        "/mpesa/stkpushquery/v1/query"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        raise_for_daraja_error(
            response,
            "STK status query",
        )

        return parse_response(response)

    except requests.Timeout as exc:
        raise DarajaTimeoutError(
            "STK status query timed out."
        ) from exc

    except requests.ConnectionError as exc:
        raise DarajaRequestError(
            "Unable to connect to Safaricom "
            "for transaction status query."
        ) from exc

    except requests.RequestException as exc:
        raise DarajaRequestError(
            f"STK status query communication error: {exc}"
        ) from exc
