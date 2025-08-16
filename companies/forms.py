# forms.py
from django import forms
from django.forms import TextInput, ClearableFileInput
from django.utils.timezone import localdate
from django.utils import timezone
from django.db.models import ForeignKey

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
DATE_INPUT_FORMATS = ["%d/%m/%Y", "%Y-%m-%d"]


def _truthy_active(v):
    s = str(v or "").strip().lower()
    return s in {"active", "1", "true", "yes", "y", "t"}


# ── permissive: accept PKs even if not in queryset (handles CSV-imported rows) ──
class PermissiveModelChoiceField(forms.ModelChoiceField):
    default_error_messages = {
        "required": "This field is required.",
        "invalid_choice": "Selected value is not available.",
    }

    # Ensure bound/initial values render as PK strings (prevents “None” UI edge cases)
    def prepare_value(self, value):
        if isinstance(value, self.queryset.model):
            return str(value.pk)
        return super().prepare_value(value)

    # Return instance for pk/int/str
    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, self.queryset.model):
            return value
        try:
            pk = str(value).strip()
            return self.queryset.model._base_manager.get(pk=pk)
        except (ValueError, self.queryset.model.DoesNotExist):
            raise forms.ValidationError(self.error_messages["invalid_choice"], code="invalid_choice")

    # Skip queryset-membership checks entirely
    def validate(self, value):
        if self.required and value in self.empty_values:
            raise forms.ValidationError(self.error_messages["required"], code="required")

    # Allow values that resolve to an instance
    def valid_value(self, value):
        if value in self.empty_values:
            return True
        if isinstance(value, self.queryset.model):
            return True
        try:
            pk = str(value).strip()
            self.queryset.model._base_manager.get(pk=pk)
            return True
        except self.queryset.model.DoesNotExist:
            return False

    def clean(self, value):
        if value in self.empty_values:
            if self.required:
                raise forms.ValidationError(self.error_messages["required"], code="required")
            return None
        return self.to_python(value)


class ExcludeRawCSVDataForm(forms.ModelForm):
    class Meta:
        exclude = ["raw_csv_data"]

    def __init__(self, *args, **kwargs):
        self.extra_fields = kwargs.pop("extra_fields", [])
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
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
                if hasattr(field, "input_formats"):
                    field.input_formats = DATE_INPUT_FORMATS

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

            elif name in ("code", "voucher_no", "smtcode", "empcode", "staffcode", "VCode"):
                field.widget.attrs.setdefault("class", "form-control autocode")
                if not self.instance.pk:
                    field.widget.attrs["readonly"] = "readonly"
                    field.widget.attrs.setdefault("placeholder", "auto")
                else:
                    field.widget.attrs.pop("readonly", None)

            elif isinstance(field, (forms.ImageField, forms.FileField)):
                field.widget = ClearableFileInput(attrs={"class": "form-control"})

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

            elif not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-control")

        for name in ("status", "is_active", "active"):
            if name in self.fields:
                f = self.fields[name]
                f.required = False
                f.widget = forms.HiddenInput()
                if name == "status":
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
                    val = True if isinstance(f, forms.BooleanField) else "1"
                    f.initial = val
                    self.initial.setdefault(name, val)

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

        for nm, f in self.fields.items():
            if not isinstance(f.widget, forms.HiddenInput):
                if getattr(f, "required", False) or isinstance(f, forms.DateField):
                    f.widget.attrs.setdefault("data-required", "true")

    def clean(self):
        cleaned = super().clean()
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

    # Keep validation wide-open; control DISPLAY separately (below)
    staff = PermissiveModelChoiceField(
        queryset=Staff._base_manager.all(),
        required=False,
        error_messages={"invalid_choice": "Selected staff is not available."},
    )

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
        exclude = ExcludeRawCSVDataForm.Meta.exclude + [
            "user",
            "is_admin", "is_master", "is_data_entry", "is_accounting",
            "is_recovery_agent", "is_auditor", "is_manager"
        ]
        field_classes = {"staff": PermissiveModelChoiceField}

    def __init__(self, *args, **kwargs):
        from django.db.models import Q
        super().__init__(*args, **kwargs)

        # ⬇️ Replace the auto-built field to avoid any limit_choices_to leakage
        self.fields["staff"] = PermissiveModelChoiceField(
            queryset=Staff._base_manager.all(),
            required=False,
            error_messages={"invalid_choice": "Selected staff is not available."},
        )

        edit_staff_id = getattr(self.instance, "staff_id", None)

        # posted id (str/int both ok)
        raw_posted = self.data.get(self.add_prefix("staff")) or self.data.get("staff")
        posted_id = str(raw_posted).strip() if raw_posted not in (None, "") else None

        # Build the *display* list for the dropdown (active & not-linked)
        active_q = Q(status__iexact="active") | Q(status=1) | Q(status="1") | Q(status=True)
        linked_ids = set(
            UserProfile.objects.exclude(staff_id=edit_staff_id).values_list("staff_id", flat=True)
        )
        display_qs = Staff._base_manager.filter(active_q).exclude(id__in=linked_ids)

        # Ensure current/edit and posted ids show up visually too
        if edit_staff_id:
            display_qs = display_qs | Staff._base_manager.filter(pk=edit_staff_id)
        if posted_id:
            display_qs = display_qs | Staff._base_manager.filter(pk=posted_id)

        display_qs = display_qs.distinct().order_by("name")

        if "staff" in self.fields:
            # IMPORTANT:
            # 1) Keep field.queryset = ALL staff for validation (prevents “not a valid choice”)
            # 2) Limit ONLY what is rendered by overriding widget.choices
            field = self.fields["staff"]
            field.queryset = Staff._base_manager.all()  # wide for validation
            field.empty_label = "— select —"
            field.error_messages["invalid_choice"] = "Selected staff is not available."
            field.widget.choices = [("", "— select —")] + [
                (str(s.pk), getattr(s, "name", f"Staff #{s.pk}")) for s in display_qs
            ]

        if "is_reports" in self.fields:
            self.fields["is_reports"].initial = True
            try:
                self.fields["is_reports"].disabled = True
            except Exception:
                pass

        if "branch" in self.fields:
            self.fields["branch"].required = False
            self.fields["branch"].widget = forms.HiddenInput()

        try:
            if getattr(self.instance, "user_id", None) and "user" in self.fields:
                self.fields["user"].initial = self.instance.user.username
        except Exception:
            pass

        try:
            want_first = ["staff", "user", "password"]
            ordered = [f for f in want_first if f in self.fields] + \
                      [f for f in self.fields if f not in want_first]
            self.order_fields(ordered)
        except Exception:
            pass

    def clean_staff(self):
        staff = self.cleaned_data.get("staff")
        if not staff:
            return staff
        if getattr(self.instance, "pk", None) and self.instance.staff_id == staff.id:
            return staff
        if not _truthy_active(getattr(staff, "status", None)):
            raise forms.ValidationError("Selected staff is inactive.")
        if UserProfile.objects.filter(staff_id=staff.id).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise forms.ValidationError("Selected staff is already linked to a user profile.")
        return staff

    def clean(self):
        cleaned = super().clean()

        # Self-heal: if staff flagged invalid but PK exists, coerce and drop error
        try:
            if "staff" in getattr(self, "errors", {}):
                raw = self.data.get(self.add_prefix("staff")) or self.data.get("staff")
                if raw not in (None, "", []):
                    inst = Staff._base_manager.get(pk=str(raw).strip())
                    cleaned["staff"] = inst
                    self._errors.pop("staff", None)
        except Staff.DoesNotExist:
            pass
        except Exception:
            pass

        # Optional guard: must have either staff or username
        u = (cleaned.get("user") or (self.data.get(self.add_prefix("user")) or self.data.get("user") or "")).strip()
        st = cleaned.get("staff")
        if not st and not u:
            self.add_error("staff", "Select a staff or enter a username.")
            raise forms.ValidationError("Staff or Username is required.")

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


# ───────── NEW: User Permission Form ─────────
class UserPermissionForm(ExcludeRawCSVDataForm):
    user_profile = PermissiveModelChoiceField(
        queryset=UserProfile._base_manager.all(),
        required=True,
        error_messages={"invalid_choice": "Selected user is not available."},
        label="User Profile",
    )

    class Meta(ExcludeRawCSVDataForm.Meta):
        model = UserPermission
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Order fields for usability
        want_first = ["user_profile", "is_admin", "is_master", "is_data_entry",
                      "is_accounting", "is_recovery_agent", "is_auditor", "is_manager", "status"]
        ordered = [f for f in want_first if f in self.fields] + \
                  [f for f in self.fields if f not in want_first]
        try:
            self.order_fields(ordered)
        except Exception:
            pass

        # Friendly labels in the dropdown (show Staff/Name or Username instead of "UserProfile #")
        try:
            field = self.fields.get("user_profile")
            if field:
                qs = UserProfile._base_manager.select_related("staff", "branch").all()

                def _label(up):
                    name = ""
                    try:
                        name = (getattr(getattr(up, "staff", None), "name", "") or
                                getattr(up, "full_name", "") or "")
                    except Exception:
                        pass
                    if not name:
                        try:
                            ed = up.extra_data or {}
                            name = ed.get("name") or ed.get("full_name") or ""
                        except Exception:
                            pass
                    if not name:
                        # derive username from either FK or CharField
                        try:
                            user_field = UserProfile._meta.get_field("user")
                            if isinstance(user_field, ForeignKey):
                                name = getattr(getattr(up, "user", None), "username", "") or ""
                            else:
                                name = getattr(up, "user", "") or ""
                        except Exception:
                            name = getattr(up, "user", "") or ""
                    if not name:
                        name = f"UserProfile #{up.pk}"
                    # Optional branch suffix
                    try:
                        bname = getattr(getattr(up, "branch", None), "name", "") or ""
                        if bname:
                            name = f"{name} — {bname}"
                    except Exception:
                        pass
                    return name

                field.queryset = UserProfile._base_manager.all()  # keep wide for validation
                field.empty_label = "— select —"
                field.widget.choices = [("", "— select —")] + [(str(up.pk), _label(up)) for up in qs]
        except Exception:
            pass


class StaffForm(ExcludeRawCSVDataForm):
    adharno = forms.CharField(
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
        if "photo" in self.fields:
            self.fields["photo"].widget = ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
                "capture": "environment"
            })

    def clean(self):
        cleaned_data = super().clean()
        aadhar = cleaned_data.get("adharno")
        contact = cleaned_data.get("contact1")

        if aadhar and Staff._base_manager.exclude(pk=self.instance.pk)\
                .filter(extra_data__adharno=aadhar).exists():
            self.add_error("adharno", "Aadhar number already exists.")

        if contact and Staff._base_manager.exclude(pk=self.instance.pk)\
                .filter(contact1=contact).exists():
            self.add_error("contact1", "Contact number already exists.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.extra_data = (instance.extra_data or {}).copy()

        adhar = self.cleaned_data.get("adharno")
        hcont = self.cleaned_data.get("housecontactno")
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
        try:
            from django.db.models import Q
            if "staff" in self.fields:
                self.fields["staff"].queryset = Staff._base_manager.filter(
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
