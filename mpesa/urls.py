
from django.urls import path

from . import views


app_name = "mpesa"


urlpatterns = [

    # STK Push
    path(
        "test/",
        views.test_payment,
        name="test_payment",
    ),

    # Safaricom callback
    path(
        "callback/",
        views.mpesa_callback,
        name="callback",
    ),

    # Transaction status
    path(
        "transaction/<str:reference_id>/",
        views.transaction_status,
        name="transaction_status",
    ),

    # Transaction listing
    path(
        "transactions/",
        views.transaction_list,
        name="transaction_list",
    ),

]
