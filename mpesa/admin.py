
import json

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):

    # ==========================================
    # LIST DISPLAY
    # ==========================================

    list_display = (
        "reference_id",
        "customer_display",
        "amount_display",
        "payment_method",
        "status_badge",
        "verification_badge",
        "mpesa_receipt_number",
        "created_at",
    )

    list_display_links = (
        "reference_id",
    )

    # ==========================================
    # FILTERS
    # ==========================================

    list_filter = (
        "status",
        "payment_method",
        "transaction_type",
        "is_verified",
        "callback_received",
        "callback_processed",
        "created_at",
    )

    # ==========================================
    # SEARCH
    # ==========================================

    search_fields = (
        "reference_id",
        "external_reference",
        "phone_number",
        "customer_name",
        "merchant_request_id",
        "checkout_request_id",
        "mpesa_receipt_number",
        "account_reference",
    )

    # ==========================================
    # ORDERING AND PAGINATION
    # ==========================================

    ordering = (
        "-created_at",
    )

    list_per_page = 25

    date_hierarchy = "created_at"

    show_full_result_count = True

    # ==========================================
    # FORM LAYOUT
    # ==========================================

    fieldsets = (
        (
            "Transaction Identification",
            {
                "fields": (
                    "id",
                    "reference_id",
                    "external_reference",
                )
            },
        ),
        (
            "Customer Information",
            {
                "fields": (
                    "phone_number",
                    "customer_name",
                )
            },
        ),
        (
            "Payment Details",
            {
                "fields": (
                    "amount",
                    "currency",
                    "payment_method",
                    "transaction_type",
                    "shortcode",
                    "account_reference",
                    "transaction_description",
                )
            },
        ),
        (
            "Safaricom Transaction Identifiers",
            {
                "fields": (
                    "merchant_request_id",
                    "checkout_request_id",
                    "mpesa_receipt_number",
                )
            },
        ),
        (
            "Payment Result",
            {
                "fields": (
                    "status",
                    "result_code",
                    "result_description",
                    "customer_message",
                    "error_code",
                    "error_message",
                )
            },
        ),
        (
            "Verification",
            {
                "fields": (
                    "is_verified",
                    "verified_at",
                )
            },
        ),
        (
            "Callback Processing",
            {
                "fields": (
                    "callback_received",
                    "callback_received_at",
                    "callback_processed",
                    "callback_attempts",
                )
            },
        ),
        (
            "API and Safaricom Responses",
            {
                "classes": (
                    "collapse",
                ),
                "fields": (
                    "daraja_response",
                    "callback_data",
                    "verification_response",
                )
            },
        ),
        (
            "Transaction Timeline",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                    "completed_at",
                    "expires_at",
                )
            },
        ),
    )

    # ==========================================
    # READ-ONLY FIELDS
    # ==========================================

    readonly_fields = (
        "id",
        "reference_id",
        "merchant_request_id",
        "checkout_request_id",
        "mpesa_receipt_number",
        "result_code",
        "result_description",
        "customer_message",
        "is_verified",
        "verified_at",
        "callback_received",
        "callback_received_at",
        "callback_processed",
        "callback_attempts",
        "daraja_response",
        "callback_data",
        "verification_response",
        "created_at",
        "updated_at",
        "completed_at",
    )

    # ==========================================
    # SAFE ADMIN BEHAVIOUR
    # ==========================================

    def has_delete_permission(self, request, obj=None):
        """
        Prevent accidental deletion of financial records.
        """

        return False

    def has_add_permission(self, request):
        """
        Transactions should be created by payment services,
        not manually through Django Admin.
        """

        return False

    # ==========================================
    # DISPLAY HELPERS
    # ==========================================

    @admin.display(
        description="Customer",
        ordering="phone_number",
    )
    def customer_display(self, obj):
        if obj.customer_name:
            return format_html(
                "{}<br><small>{}</small>",
                obj.customer_name,
                obj.phone_number,
            )

        return obj.phone_number

    @admin.display(
        description="Amount",
        ordering="amount",
    )
    def amount_display(self, obj):
        return f"{obj.currency} {obj.amount:,.2f}"

    @admin.display(
        description="Payment Status",
        ordering="status",
    )
    def status_badge(self, obj):

        colors = {
            "PENDING": "#d97706",
            "PROCESSING": "#2563eb",
            "SUCCESS": "#15803d",
            "FAILED": "#dc2626",
            "CANCELLED": "#64748b",
            "EXPIRED": "#7c3aed",
        }

        color = colors.get(obj.status, "#64748b")

        return format_html(
            '<span style="'
            'background:{};'
            'color:white;'
            'padding:4px 9px;'
            'border-radius:12px;'
            'font-size:11px;'
            'font-weight:600;'
            '">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(
        description="Verification",
        boolean=True,
        ordering="is_verified",
    )
    def verification_badge(self, obj):
        return obj.is_verified

    # ==========================================
    # ADMIN ACTIONS
    # ==========================================

    actions = (
        "mark_for_reconciliation",
    )

    @admin.action(
        description="Mark selected transactions for reconciliation"
    )
    def mark_for_reconciliation(self, request, queryset):

        count = queryset.filter(
            status=Transaction.TransactionStatus.SUCCESS,
            is_verified=False,
        ).count()

        self.message_user(
            request,
            (
                f"{count} successful but unverified transaction(s) "
                "identified for reconciliation. No payment status "
                "or verification records were changed."
            ),
        )
