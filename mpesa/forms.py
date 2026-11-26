
from django import forms


class STKPushForm(forms.Form):
    phone = forms.CharField(
        max_length=13,
        label="Phone Number",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "0712345678",
        }),
    )

    amount = forms.IntegerField(
        min_value=1,
        label="Amount (KES)",
    )

    reference = forms.CharField(
        max_length=12,
        label="Account Reference",
        initial="HPDS-TEST",
    )

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip().replace(" ", "")

        if phone.startswith("+"):
            phone = phone[1:]

        if phone.startswith("0") and len(phone) == 10:
            phone = "254" + phone[1:]
        elif phone.startswith("7") and len(phone) == 9:
            phone = "254" + phone
        elif phone.startswith("1") and len(phone) == 9:
            phone = "254" + phone

        if not (
            len(phone) == 12
            and phone.startswith("254")
            and phone.isdigit()
        ):
            raise forms.ValidationError(
                "Enter a valid Kenyan phone number."
            )

        return phone
