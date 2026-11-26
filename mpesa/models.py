
import uuid

from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class Transaction(models.Model):
    """
    Stores M-PESA payment transactions initiated through the gateway.

    Supports:
    - PayBill STK Push
    - Buy Goods / Till payments
    - Payment callback processing
    - Transaction verification
    - External application references
    """

    class PaymentMethod(models.TextChoices):
        PAYBILL = "PAYBILL", "PayBill"
        BUY_GOODS = "BUY_GOODS", "Buy Goods / Till"

    class TransactionStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        SUCCESS = "SUCCESS", "Successful"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"

    class TransactionType(models.TextChoices):
        CUSTOMER_PAYBILL_ONLINE = (
            "CustomerPayBillOnline",
            "Customer PayBill Online",
        )
        CUSTOMER_BUY_GOODS_ONLINE = (
            "CustomerBuyGoodsOnline",
            "Customer Buy Goods Online",
        )

    # ==========================================
    # INTERNAL IDENTIFICATION
    # ==========================================

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    reference_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique internal payment reference.",
    )

    external_reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Reference supplied by an integrating application.",
    )

    # ==========================================
    # CUSTOMER INFORMATION
    # ==========================================

    phone_number = models.CharField(
        max_length=15,
        db_index=True,
        help_text="Customer phone number in international format.",
    )

    customer_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
    )

    # ==========================================
    # PAYMENT INFORMATION
    # ==========================================

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )

    currency = models.CharField(
        max_length=3,
        default="KES",
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.PAYBILL,
        db_index=True,
    )

    transaction_type = models.CharField(
        max_length=50,
        choices=TransactionType.choices,
        default=TransactionType.CUSTOMER_PAYBILL_ONLINE,
    )

    shortcode = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Business shortcode used for the transaction.",
    )

    account_reference = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    transaction_description = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    # ==========================================
    # SAFARICOM DARAJA IDENTIFIERS
    # ==========================================

    merchant_request_id = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        db_index=True,
    )

    checkout_request_id = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        unique=True,
    )

    mpesa_receipt_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
    )

    result_code = models.IntegerField(
        blank=True,
        null=True,
    )

    result_description = models.TextField(
        blank=True,
        default="",
    )

    customer_message = models.TextField(
        blank=True,
        default="",
    )

    # ==========================================
    # TRANSACTION STATUS
    # ==========================================

    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
        db_index=True,
    )

    is_verified = models.BooleanField(
        default=False,
        help_text="Indicates whether payment was independently verified.",
    )

    verified_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    # ==========================================
    # CALLBACK AND API DATA
    # ==========================================

    callback_received = models.BooleanField(
        default=False,
    )

    callback_received_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    callback_data = models.JSONField(
        blank=True,
        null=True,
        help_text="Safaricom callback payload for reconciliation.",
    )

    daraja_response = models.JSONField(
        blank=True,
        null=True,
        help_text="Initial Daraja STK Push response.",
    )

    verification_response = models.JSONField(
        blank=True,
        null=True,
        help_text="Response from transaction verification.",
    )

    callback_processed = models.BooleanField(
        default=False,
    )

    callback_attempts = models.PositiveIntegerField(
        default=0,
    )

    # ==========================================
    # ERROR HANDLING
    # ==========================================

    error_code = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    error_message = models.TextField(
        blank=True,
        default="",
    )

    # ==========================================
    # TIMESTAMPS
    # ==========================================

    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    completed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    expires_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    # ==========================================
    # MODEL CONFIGURATION
    # ==========================================

    class Meta:
        verbose_name = "M-PESA Transaction"
        verbose_name_plural = "M-PESA Transactions"

        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="mpesa_status_created_idx",
            ),
            models.Index(
                fields=["phone_number", "created_at"],
                name="mpesa_phone_created_idx",
            ),
            models.Index(
                fields=["payment_method", "status"],
                name="mpesa_method_status_idx",
            ),
        ]

    # ==========================================
    # STRING REPRESENTATION
    # ==========================================

    def __str__(self):
        return (
            f"{self.reference_id} | "
            f"KES {self.amount} | "
            f"{self.get_status_display()}"
        )

    # ==========================================
    # HELPER PROPERTIES
    # ==========================================

    @property
    def is_successful(self):
        return (
            self.status == self.TransactionStatus.SUCCESS
            and self.is_verified
        )

    @property
    def is_pending(self):
        return self.status in [
            self.TransactionStatus.PENDING,
            self.TransactionStatus.PROCESSING,
        ]

    @property
    def is_completed(self):
        return self.status in [
            self.TransactionStatus.SUCCESS,
            self.TransactionStatus.FAILED,
            self.TransactionStatus.CANCELLED,
            self.TransactionStatus.EXPIRED,
        ]

    def mark_completed(self):
        """Record when a transaction reaches a terminal status."""

        if self.is_completed and not self.completed_at:
            self.completed_at = timezone.now()

        elif not self.is_completed:
            self.completed_at = None

        self.save(
            update_fields=[
                "completed_at",
                "updated_at",
            ]
        )

    def mark_verified(self):
        """
        Mark a transaction as verified.

        Call only after independent verification confirms
        the payment details against trusted Daraja data.
        """

        if self.status != self.TransactionStatus.SUCCESS:
            raise ValueError(
                "Only successful transactions can be verified."
            )

        self.is_verified = True
        self.verified_at = timezone.now()

        self.save(
            update_fields=[
                "is_verified",
                "verified_at",
                "updated_at",
            ]
        )
