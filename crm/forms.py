"""Django forms for authentication, customer management, catalog, staff, and tickets."""

from django import forms
from django.contrib.auth import authenticate

from crm.models import Customer, Product, SupportTicket, User


class LoginForm(forms.Form):
    """Login form supporting institutional Email or Staff Code plus password."""

    identifier = forms.CharField(
        max_length=150,
        label="Email Address or Staff Code",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. manager@uiventures.ui.edu.ng or UIV-STF-002",
                "autocomplete": "username",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        ),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        identifier = cleaned_data.get("identifier")
        password = cleaned_data.get("password")

        if identifier and password:
            self.user_cache = authenticate(
                self.request, username=identifier, password=password
            )
            if self.user_cache is None:
                raise forms.ValidationError(
                    "Invalid credentials. Check your email/staff code and password."
                )
            if not self.user_cache.is_active:
                raise forms.ValidationError(
                    "This account has been deactivated. Contact the system administrator."
                )
        return cleaned_data

    def get_user(self):
        return self.user_cache


class CustomerForm(forms.ModelForm):
    """Create or update a registered UI Ventures customer."""

    class Meta:
        model = Customer
        fields = ["full_name", "phone", "email", "category"]
        widgets = {
            "full_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. Adebayo Oluwaseun"}
            ),
            "phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. 08031234567"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "e.g. student@ui.edu.ng"}
            ),
            "category": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        qs = Customer.objects.filter(phone=phone)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A customer with this phone number already exists.")
        return phone


class ProductForm(forms.ModelForm):
    """Create or update a UI Ventures retail catalog item."""

    class Meta:
        model = Product
        fields = [
            "sku_code",
            "product_name",
            "category",
            "unit_price",
            "stock_qty",
            "reorder_level",
        ]
        widgets = {
            "sku_code": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. BK-104"}
            ),
            "product_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Product title"}
            ),
            "category": forms.Select(attrs={"class": "form-select"}),
            "unit_price": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0.01"}
            ),
            "stock_qty": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "reorder_level": forms.NumberInput(
                attrs={"class": "form-control", "min": "0"}
            ),
        }

    def clean_sku_code(self):
        return self.cleaned_data["sku_code"].strip().upper()


class SupportTicketCreateForm(forms.ModelForm):
    """Create a support ticket (customer field hidden when submitted by a Customer user)."""

    class Meta:
        model = SupportTicket
        fields = ["customer", "category", "subject", "description"]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Brief summary of the issue or feedback",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Provide receipt number, product SKU, or detailed context...",
                }
            ),
        }

    def __init__(self, *args, for_customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        if for_customer is not None:
            self.fields["customer"].required = False
            self.fields["customer"].widget = forms.HiddenInput()
        else:
            self.fields["customer"].queryset = Customer.objects.order_by("full_name")


class SupportTicketUpdateForm(forms.ModelForm):
    """Staff workflow form for assigning, progressing, and resolving support tickets."""

    class Meta:
        model = SupportTicket
        fields = ["assigned_to", "status", "resolution_note"]
        widgets = {
            "assigned_to": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "resolution_note": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Record investigation details or customer resolution...",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(
            role__in=[User.Role.ADMIN, User.Role.MANAGER, User.Role.ATTENDANT],
            is_active=True,
        ).order_by("full_name")
        self.fields["assigned_to"].required = False


class StaffCreateForm(forms.ModelForm):
    """Admin form to register a new staff member with role assignment."""

    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Minimum 8 characters"}
        ),
    )

    class Meta:
        model = User
        fields = ["staff_code", "full_name", "email", "role", "is_active"]
        widgets = {
            "staff_code": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. UIV-STF-010"}
            ),
            "full_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Full Name"}
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "name@uiventures.ui.edu.ng",
                }
            ),
            "role": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [
            (User.Role.ADMIN, "Admin"),
            (User.Role.MANAGER, "Manager"),
            (User.Role.ATTENDANT, "Attendant"),
        ]
        self.fields["staff_code"].required = True

    def clean_staff_code(self):
        code = (self.cleaned_data.get("staff_code") or "").strip().upper()
        if not code:
            raise forms.ValidationError("Staff code is required for staff accounts.")
        return code

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = user.email.lower()
        user.is_staff = user.role in {User.Role.ADMIN, User.Role.MANAGER}
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class StaffUpdateForm(forms.ModelForm):
    """Admin form to edit an existing staff account's profile, role, or status."""

    new_password = forms.CharField(
        required=False,
        min_length=8,
        label="Reset Password (Optional)",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Leave blank to keep current password",
            }
        ),
    )

    class Meta:
        model = User
        fields = ["staff_code", "full_name", "email", "role", "is_active"]
        widgets = {
            "staff_code": forms.TextInput(attrs={"class": "form-control"}),
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [
            (User.Role.ADMIN, "Admin"),
            (User.Role.MANAGER, "Manager"),
            (User.Role.ATTENDANT, "Attendant"),
        ]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = user.email.lower()
        user.is_staff = user.role in {User.Role.ADMIN, User.Role.MANAGER}
        new_pw = self.cleaned_data.get("new_password")
        if new_pw:
            user.set_password(new_pw)
        if commit:
            user.save()
        return user
