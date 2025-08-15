from django import forms
from django.forms import TextInput, ClearableFileInput
from django.utils.timezone import localdate
from django.utils import timezone

from .models import (
    # core
    Company, Branch, Village, Center, Group, Role, UserProfile, Staff,
    Product, Client, LoanApplication, LoanApproval, Disbursement,
    BusinessSetting, FieldSchedule, FieldReport, WeeklyReport, MonthlyReport, Column, Cadre,
    # new business tables
    AccountHead, Voucher, Posting, RecoveryPosting,
    # ⇣ auto-generated CSV models stay below ⇣
    AccCashbook, AccCashbookold, AccHeads, Aadhar, Accfundloancols, Accfundloans,
    Accountmaster, Arrear, Cheque, Codes, Contacts, Dayend, Equity2,
    Equityshare31032014, Equityshare31032015, Gr, Groups, MXAgent, MXCode,
    MXMember, MXSavings, Massposting, MasterBranch, MasterCategories, MasterFs,
    MasterLoanpurposes, MasterLoantypes, MasterMonth, MasterSectors, MasterSetup,
    MasterWeeks, MXAgriment, MXLoancols, MXLoans, MXSalaries, Pdc, RptDaybook,
    Securitydeposit, Staffloans, Transefer, Cobarower, Collectionrpt, Fund,
    Loancols, Loans, Loansmfi41110, Mloanschedule, Mloancols, Mloans, Mlogin,
    Mmisc, Mrecvisit, Msetup, Msurity, MasterBusinessmode, Memberdeposits,
    Members, Memberskaikaluru, Pbdet, Rptincome, RptGrcollectionsheet,
    RptOutstanding, RptPassbook, RptPassbookcommon, RptTb, RptDisRegister,
    RptHigh, RptSavings, RptSumsheet, Savings, Setup, Setupn, Share, Share1,
    Smtavail, Temp, Users,
    # feature models (added)
    KYCDocument, AlertRule,
    # HRPM (added)
    Appointment, SalaryStatement,
    # Separated permissions entity (added)
    UserPermission,
    # validators
    phone_validator, aadhar_validator
)

ACTIVE_SENTINELS = ("active", "1", 1, True)

# Accept UI format and ISO (to avoid “Enter a valid date” if backend normalized)
DATE_INPUT_FORMATS = ["%d/%m/%Y", "%Y-%m-%d"]


class ExcludeRawCSVDataForm(forms.ModelForm):
    class Meta:
        exclude = ["raw_csv_data"]

    def __init__(self, *args, **kwargs):
        self.extra_fields = kwargs.pop("extra_fields", [])
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            # 🗓 joining_date: prefill today, readonly, flatpickr, dd/mm/yyyy
            if name == "joining_date":
                today_str = localdate().strftime("%d/%m/%Y")
                if (
                    not self.data.get(name)
                    and not self.initial.get(name)
                    and not getattr(self.instance, name)
                ):
                    field.initial = today_str
                    self.initial[name] = today_str

                field.widget.attrs.update({
                    "readonly": "readonly",
                    "class": "form-control",
                    "placeholder": "dd/mm/yyyy",
                    "autocomplete": "off",
                    "style": "pointer-events: none; background-color: #e9ecef;",
                    "data-no-flatpickr": "true",
                    "pattern": r"\d{2}/\d{2}/\d{4}",
                    "maxlength": "10",
                })
                # Accept both dd/mm/YYYY and ISO
                if hasattr(field, "input_formats"):
                    field.input_formats = DATE_INPUT_FORMATS

            # 🆔 Aadhaar formatting (12 digits, spaced) — supports multiple field names
            elif name in ("adharno", "aadhar", "aadhaar"):
                field.widget.attrs.update({
                    "placeholder": "0000 0000 0000",
                    "maxlength": "14",
                    "class": "form-control aadhar-input",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                    "pattern": r"\d{4}\s\d{4}\s\d{4}",
                    "title": "Enter Aadhar in 0000 0000 0000 format using only digits",
                    "oninput": "this.value=this.value.replace(/[^0-9 ]/g,'').replace(/(\\d{4})\\s?(\\d{0,4})\\s?(\\d{0,4})/, '$1 $2 $3').trim()",
                })

            elif name in ("phone", "mobile", "contact1", "housecontactno"):
                css = field.widget.attrs.get("class", "form-control")
                field.widget.attrs.update({
                    "class": f"{css} phone-input".strip(),
                    "placeholder": "10-digit number",
                    "maxlength": "10",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                    "pattern": r"\d{10}",
                    "title": "Enter 10-digit phone number using only digits",
                    "oninput": "this.value=this.value.replace(/\\D/g,'')",
                })

            # 🆔 Code handling (extended to alternate identifier fields)
            elif name in ("code", "voucher_no", "smtcode", "empcode", "staffcode", "VCode"):
                field.widget.attrs.setdefault("class", "form-control autocode")
                if not self.instance.pk:
                    field.widget.attrs["readonly"] = "readonly"
                    field.widget.attrs.setdefault("placeholder", "auto")
                else:
                    field.widget.attrs.pop("readonly", None)

            # 🖼 File/Image Fields
            elif isinstance(field, (forms.ImageField, forms.FileField)):
                field.widget = ClearableFileInput(attrs={"class": "form-control"})

            # 🗓 Other DateFields
            elif isinstance(field, forms.DateField):
                field.input_formats = DATE_INPUT_FORMATS
                field.widget = TextInput(attrs={
                    "class": "date-field form-control",
                    "placeholder": "dd/mm/yyyy",
                    "data-flatpickr": "true",
                    "autocomplete": "off",
                    "pattern": r"\d{2}/\d{2}/\d{4}",
                    "maxlength": "10",
                })

            # 🧩 Default styling
            elif not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-control")

        # 🔒 Hide status-like fields and default them to active
        for name in ("status", "is_active", "active"):
            if name in self.fields:
                f = self.fields[name]
                f.required = False
                f.widget = forms.HiddenInput()
                # choose sane default
                if name == "status":
                    # Prefer 'active' from choices when present
                    val = "active"
                    try:
                        for v, _ in getattr(f, "choices", []) or []:
                            if v in ACTIVE_SENTINELS:
                                val = v
                                break
                    except Exception:
                        pass
                    f.initial = val
                    self.initial.setdefault(name, val)
                else:
                    # boolean/int conventions
                    val = True if isinstance(f, forms.BooleanField) else "1"
                    f.initial = val
                    self.initial.setdefault(name, val)

        # ➕ Inject extra fields from Column model (Company ID 1)
        for col in self.extra_fields:
            field_kwargs = {
                "label": col.label,
                "required": col.required,
                "widget": TextInput(attrs={"class": "form-control"}),
            }

            if col.field_type == "date":
                field_cls = forms.DateField
                field_kwargs["widget"] = TextInput(attrs={
                    "class": "date-field form-control",
                    "placeholder": "dd/mm/yyyy",
                    "data-flatpickr": "true",
                    "autocomplete": "off",
                    "pattern": r"\d{2}/\d{2}/\d{4}",
                    "maxlength": "10",
                })
                field_kwargs["input_formats"] = DATE_INPUT_FORMATS

            elif col.field_type == "number":
                field_cls = forms.DecimalField

            elif col.field_type == "file":
                field_cls = forms.FileField
                field_kwargs["widget"] = ClearableFileInput(attrs={"class": "form-control"})

            else:
                field_cls = forms.CharField

            self.fields[f"extra__{col.field_name}"] = field_cls(**field_kwargs)

        # ⏯️ Client-side gating only: mark required fields so JS disables Save until filled
        for nm, f in self.fields.items():
            if not isinstance(f.widget, forms.HiddenInput):
                if getattr(f, "required", False) or isinstance(f, forms.DateField):
                    f.widget.attrs.setdefault("data-required", "true")

    def clean(self):
        cleaned = super().clean()
        # Ensure active defaults even if field omitted from POST
        if "status" in self.fields and cleaned.get("status") in (None, "",):
            cleaned["status"] = self.initial.get("status", "active")
        if "is_active" in self.fields and cleaned.get("is_active") in (None, ""):
            cleaned["is_active"] = True
        if "active" in self.fields and cleaned.get("active") in (None, ""):
            cleaned["active"] = 1
        return cleaned


# ─────────  CORE DOMAIN FORMS  ─────────
class CompanyForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Company
        fields = "__all__"


class BranchForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Branch
        fields = "__all__"


class VillageForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Village
        fields = "__all__"


class CenterForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Center
        fields = "__all__"


class GroupForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Group
        fields = "__all__"


class RoleForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Role
        exclude = ExcludeRawCSVDataForm.Meta.exclude + ["permissions"]


class UserProfileForm(ExcludeRawCSVDataForm):
    # Free-text username (shadow to auth_user)
    user = forms.CharField(
        required=False,
        widget=TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter a unique username",
            "autocomplete": "off",
        }),
        help_text="Type a username; a Django user will be created or linked.",
        label="Username",
    )
    # Write-only password (saved to auth_user)
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            "class": "form-control password-input",
            "placeholder": "Set / Reset password",
            "autocomplete": "new-password",
        }),
        help_text="Leave blank to keep existing password.",
    )

    class Meta(ExcludeRawCSVDataForm.Meta):
        model = UserProfile
        exclude = ExcludeRawCSVDataForm.Meta.exclude + ["user",
            "is_admin","is_master","is_data_entry","is_accounting",
            "is_recovery_agent","is_auditor","is_manager"
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Allow ANY staff from company 1 so existing inactive/linked values never 404 as “invalid choice”
        base_qs = Staff.objects.filter(extra_data__company_id=1)

        # Always include current staff on edit
        if getattr(self.instance, "pk", None) and getattr(self.instance, "staff_id", None):
            base_qs = base_qs | Staff.objects.filter(pk=self.instance.staff_id)

        # Also include posted staff id so validation runs even if filtered out
        try:
            posted_id = (self.data.get("staff") or "").strip()
            if posted_id:
                base_qs = base_qs | Staff.objects.filter(pk=posted_id)
        except Exception:
            pass

        if "staff" in self.fields:
            self.fields["staff"].queryset = base_qs.distinct().order_by("name")
            # nicer message than “Select a valid choice…”
            self.fields["staff"].error_messages["invalid_choice"] = \
                "Selected staff is not available."

        # Only 'is_reports' is visible here; default True & locked
        if "is_reports" in self.fields:
            self.fields["is_reports"].initial = True
            try:
                self.fields["is_reports"].disabled = True
            except Exception:
                pass

        # Branch hidden; filled from chosen staff
        if "branch" in self.fields:
            self.fields["branch"].required = False
            self.fields["branch"].widget = forms.HiddenInput()

        # Pre-fill username from FK if present
        try:
            if getattr(self.instance, "user_id", None) and "user" in self.fields:
                self.fields["user"].initial = self.instance.user.username
        except Exception:
            pass

        # Field order
        try:
            want_first = ["staff", "user", "password"]
            ordered = [f for f in want_first if f in self.fields] + \
                      [f for f in self.fields if f not in want_first]
            self.order_fields(ordered)
        except Exception:
            pass

    def clean_staff(self):
        """
        Keep your rules:
        - allow current staff on edit
        - require active + not already linked for new links
        """
        staff = self.cleaned_data.get("staff")
        if not staff:
            return staff

        # allow current on edit
        if getattr(self.instance, "pk", None) and self.instance.staff_id == staff.id:
            return staff

        # active?
        if str(getattr(staff, "status", "")).strip().lower() not in {"active", "1", "true"}:
            raise forms.ValidationError("Selected staff is inactive.")

        # not linked?
        if UserProfile.objects.filter(staff_id=staff.id).exists():
            raise forms.ValidationError("Selected staff is already linked to a user profile.")

        return staff

    def clean(self):
        cleaned = super().clean()
        # set branch from staff if missing
        try:
            if not cleaned.get("branch") and cleaned.get("staff"):
                st = cleaned["staff"]
                if getattr(st, "branch_id", None):
                    self.cleaned_data["branch"] = st.branch
        except Exception:
            pass
        if "is_reports" in self.fields:
            cleaned["is_reports"] = True
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        # enforce branch from staff again
        try:
            if not getattr(instance, "branch_id", None) and getattr(instance, "staff_id", None):
                instance.branch = instance.staff.branch
        except Exception:
            pass
        if hasattr(instance, "is_reports") and not instance.is_reports:
            instance.is_reports = True
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class StaffForm(ExcludeRawCSVDataForm):
    adharno  = forms.CharField(
        validators=[aadhar_validator],
        widget=TextInput(attrs={"placeholder": "0000 0000 0000"})
    )
    contact1 = forms.CharField(validators=[phone_validator], required=False)
    housecontactno = forms.CharField(validators=[phone_validator], required=False)

    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Staff
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Camera + upload for staff photo
        if "photo" in self.fields:
            self.fields["photo"].widget = ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
                "capture": "environment"  # mobile rear camera
            })

    def clean(self):
        cleaned_data = super().clean()
        aadhar  = cleaned_data.get("adharno")
        contact = cleaned_data.get("contact1")

        # ✅ Staff has no real "adharno" field → check JSONField key instead
        if aadhar and Staff.objects.exclude(pk=self.instance.pk)\
                .filter(extra_data__adharno=aadhar).exists():
            self.add_error("adharno", "Aadhar number already exists.")

        # ✅ contact1 is a real model field → keep your original check
        if contact and Staff.objects.exclude(pk=self.instance.pk)\
                .filter(contact1=contact).exists():
            self.add_error("contact1", "Contact number already exists.")

        return cleaned_data

    def save(self, commit=True):
        """
        Preserve previous behavior and ALSO persist non-model fields
        (adharno, housecontactno) into extra_data so they aren't lost.
        This is additive and safe even if your view already handles extra_data.
        """
        instance = super().save(commit=False)
        instance.extra_data = (instance.extra_data or {}).copy()

        # store non-model fields
        adhar  = self.cleaned_data.get("adharno")
        hcont  = self.cleaned_data.get("housecontactno")
        if adhar is not None:
            instance.extra_data["adharno"] = adhar
        if hcont is not None:
            instance.extra_data["housecontactno"] = hcont

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ProductForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Product
        fields = "__all__"


class ClientForm(ExcludeRawCSVDataForm):
    aadhar = forms.CharField(
        validators=[aadhar_validator],
        widget=TextInput(attrs={"placeholder": "0000 0000 0000"})
    )
    contactno = forms.CharField(validators=[phone_validator], required=False)

    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Client
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        aadhar = cleaned_data.get("aadhar")
        contact = cleaned_data.get("contactno")

        if aadhar and Client.objects.exclude(pk=self.instance.pk).filter(aadhar=aadhar).exists():
            self.add_error("aadhar", "Aadhar number already exists.")

        if contact and Client.objects.exclude(pk=self.instance.pk).filter(contactno=contact).exists():
            self.add_error("contactno", "Contact number already exists.")

        # 🔁 ensure cleaned_data is returned (bug fix)
        return cleaned_data


class LoanApplicationForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = LoanApplication
        fields = "__all__"


class LoanApprovalForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = LoanApproval
        fields = "__all__"


class DisbursementForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Disbursement
        fields = "__all__"


class BusinessSettingForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = BusinessSetting
        fields = "__all__"


class FieldScheduleForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = FieldSchedule
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only active staff in schedule picker
        try:
            from django.db.models import Q
            if "staff" in self.fields:
                self.fields["staff"].queryset = Staff.objects.filter(
                    Q(status="active") | Q(status=1) | Q(status="1") | Q(status=True)
                ).order_by("name")
        except Exception:
            pass


class FieldReportForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = FieldReport
        fields = "__all__"


class WeeklyReportForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = WeeklyReport
        fields = "__all__"


class MonthlyReportForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = MonthlyReport
        fields = "__all__"


class ColumnForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Column
        fields = "__all__"


class CadreForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Cadre
        fields = "__all__"


# ─────────  NEW BUSINESS TABLE FORMS  ─────────
class AccountHeadForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = AccountHead
        fields = "__all__"


class VoucherForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Voucher
        fields = "__all__"


class PostingForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Posting
        fields = "__all__"


class RecoveryPostingForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = RecoveryPosting
        fields = "__all__"


# ─────────  FEATURE FORMS (OFFLINE KYC, ESCALATION ALERTS)  ─────────
class KYCDocumentForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = KYCDocument
        fields = "__all__"
        # Optional: explicit widgets (safe; preserves base styling)
        widgets = {
            "doc_type": forms.Select(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "client_ref": TextInput(attrs={"class": "form-control"}),
            "client_name": TextInput(attrs={"class": "form-control"}),
            "number": TextInput(attrs={"class": "form-control"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class AlertRuleForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = AlertRule
        fields = "__all__"
        widgets = {
            "name": TextInput(attrs={"class": "form-control"}),
            "entity": TextInput(attrs={"class": "form-control", "placeholder": "e.g., recoveryposting"}),
            # JSON fields: let users paste JSON; ModelForm will validate/parse
            "condition": forms.Textarea(attrs={"class": "form-control", "rows": 6, "placeholder": '{"filter": {"days_overdue__gte": 7}}'}),
            # channels is ArrayField or JSONField depending on DB; accept JSON list
            "channels": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": '["EMAIL","SMS"]'}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


# ───────── HRPM FORMS (added) ─────────
class AppointmentForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = Appointment
        fields = "__all__"


class SalaryStatementForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = SalaryStatement
        fields = "__all__"


# ───────── UserPermission (separate UI) ─────────
class UserPermissionForm(ExcludeRawCSVDataForm):
    class Meta(ExcludeRawCSVDataForm.Meta):
        model = UserPermission
        fields = "__all__"


# ─────────  AUTO-GENERATED FORMS FOR CSV TABLES  ─────────
_csv_models = [
    AccCashbook, AccCashbookold, AccHeads, Aadhar, Accfundloancols, Accfundloans,
    Accountmaster, Arrear, Cheque, Codes, Contacts, Dayend, Equity2,
    Equityshare31032014, Equityshare31032015, Gr, Groups, MXAgent, MXCode,
    MXMember, MXSavings, Massposting, MasterBranch, MasterCategories, MasterFs,
    MasterLoanpurposes, MasterLoantypes, MasterMonth, MasterSectors, MasterSetup,
    MasterWeeks, MXAgriment, MXLoancols, MXLoans, MXSalaries, Pdc, RptDaybook,
    Securitydeposit, Staffloans, Transefer, Cobarower, Collectionrpt, Fund,
    Loancols, Loans, Loansmfi41110, Mloanschedule, Mloancols, Mloans, Mlogin,
    Mmisc, Mrecvisit, Msetup, Msurity, MasterBusinessmode, Memberdeposits,
    Members, Memberskaikaluru, Pbdet, Rptincome, RptGrcollectionsheet,
    RptOutstanding, RptPassbook, RptPassbookcommon, RptTb, RptDisRegister,
    RptHigh, RptSavings, RptSumsheet, Savings, Setup, Setupn, Share, Share1,
    Smtavail, Temp, Users
]

for model_cls in _csv_models:
    form_name = f"{model_cls.__name__}Form"
    meta_cls = type("Meta", (ExcludeRawCSVDataForm.Meta,), {
        "model": model_cls,
        "fields": "__all__"
    })
    globals()[form_name] = type(form_name, (ExcludeRawCSVDataForm,), {
        "Meta": meta_cls
    })
