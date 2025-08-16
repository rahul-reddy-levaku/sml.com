"""
companies/models.py
Complete file – every model defined in full, no placeholders.
Keeps all prior logic and adds:
    • AutoCodeMixin  → every model with a `code` field auto-generates codes
    • __str__ overrides on FK parents so dropdowns / grids show the NAME
    • phone / Aadhaar validators + status choices remain
"""
# companies/models.py
from django.db import models, connection
from django.db.models import Q
from django.core.validators import MinValueValidator, RegexValidator
from django.contrib.auth.models import User as AuthUser
try:
    from django.db.models import JSONField  # Django 3.1+
except Exception:
    from django.contrib.postgres.fields import JSONField
from django.contrib.postgres.fields import ArrayField  # used only when DB is Postgres

# ────────────────────────────────────────────────────────────────────────────
# Validators / Choices
# ────────────────────────────────────────────────────────────────────────────

phone_validator  = RegexValidator(r"^\d{10}$", "Phone number must be exactly 10 digits.")
aadhar_validator = RegexValidator(r"^\d{4}\s\d{4}\s\d{4}$", "Aadhaar must be in '1234 5678 9012' format.")

STATUS_CHOICES   = [("active","Active"),("inactive","Inactive"),("pending","Pending"),("blocked","Blocked")]
CATEGORY_CHOICES = [("loan","Loan"),("deposit","Deposit")]

# ────────────────────────────────────────────────────────────────────────────
# Core Mixins
# ────────────────────────────────────────────────────────────────────────────

class AutoCodeMixin(models.Model):
    """
    Keeps CSV code if provided; otherwise auto-generates PREFIX### on the configured code field.
    By default uses a field named 'code'. Override CODE_FIELD in subclasses if the identifier
    field has a different name (e.g., 'voucher_no', 'smtcode', 'staffcode', 'VCode').
    """
    CODE_PREFIX = ""
    CODE_FIELD  = "code"

    class Meta:
        abstract = True

    def _next_code(self):
        prefix = (self.CODE_PREFIX or self.__class__.__name__[:3]).upper()
        last = self.__class__.objects.order_by("-id").first()
        nxt = (last.id + 1) if last else 1
        return f"{prefix}{nxt:03d}"

    def save(self, *args, **kwargs):
        field = getattr(self, "CODE_FIELD", "code")
        if hasattr(self, field):
            val = getattr(self, field)
            if not val:
                setattr(self, field, self._next_code())
        super().save(*args, **kwargs)

class BaseRaw(models.Model):
    """Holds original CSV row + extra flags."""
    extra_data   = JSONField(default=dict, blank=True, null=True)
    raw_csv_data = JSONField(blank=True, null=True)
    STR_FIELDS   = ("name","code","label","field_name","value","key")

    def __str__(self):
        for f in self.STR_FIELDS:
            val = getattr(self, f, None)
            if val not in (None, ""):
                return str(val)
        return f"{self.__class__.__name__} #{self.pk}"

    class Meta:
        abstract = True

# ────────────────────────────────────────────────────────────────────────────
# MASTER: COMPANY / BRANCH / VILLAGE / CENTER / GROUP
# ────────────────────────────────────────────────────────────────────────────

class Company(AutoCodeMixin, BaseRaw):
    CODE_PREFIX = "CMP"
    code          = models.CharField(max_length=50, unique=True, blank=True)
    name          = models.CharField(max_length=255)
    opening_date  = models.DateField(blank=True, null=True)
    address       = models.TextField(blank=True, null=True)
    phone         = models.CharField(max_length=20, blank=True, null=True, validators=[phone_validator])
    email         = models.EmailField(blank=True, null=True)
    logo          = models.ImageField(upload_to="company_logos/", blank=True, null=True)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

class Branch(AutoCodeMixin, BaseRaw):
    CODE_PREFIX = "BRN"
    code       = models.CharField(max_length=50, unique=True, blank=True)
    name       = models.CharField(max_length=255)
    company    = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="branches")
    open_date  = models.DateField(blank=True, null=True)
    address1   = models.CharField(max_length=255, blank=True, null=True)
    phone      = models.CharField(max_length=20, blank=True, null=True, validators=[phone_validator])
    district   = models.CharField(max_length=100, blank=True, null=True)
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

class Village(AutoCodeMixin, BaseRaw):
    CODE_PREFIX = "VIL"
    CODE_FIELD  = "VCode"
    VCode   = models.CharField(max_length=50, unique=True, blank=True, null=True, db_index=True)
    VName   = models.CharField(max_length=255)
    branch  = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="villages", null=True, blank=True)
    TDate   = models.DateField(blank=True, null=True)
    status  = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

class Center(AutoCodeMixin, BaseRaw):
    CODE_PREFIX = "CTR"
    code         = models.CharField(max_length=50, unique=True, blank=True, null=True, db_index=True)
    name         = models.CharField(max_length=255)
    village      = models.ForeignKey(Village, to_field="VCode", db_column="VCode",
                                     on_delete=models.CASCADE, related_name="centers", null=True, blank=True)
    collection_day = models.CharField(max_length=50, blank=True, null=True)
    meet_place     = models.CharField(max_length=255, blank=True, null=True)
    created_on     = models.DateField(blank=True, null=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

class Group(AutoCodeMixin, BaseRaw):
    CODE_PREFIX = "GRP"
    code        = models.CharField(max_length=50, unique=True, blank=True, null=True, db_index=True)
    name        = models.CharField(max_length=255)
    center      = models.ForeignKey(Center, to_field="code", db_column="CenterCode",
                                    on_delete=models.CASCADE, related_name="groups", null=True, blank=True)
    week_day    = models.CharField(max_length=20, blank=True, null=True)
    meeting_time= models.CharField(max_length=20, blank=True, null=True)
    borrower_count = models.PositiveIntegerField(blank=True, null=True)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

# ────────────────────────────────────────────────────────────────────────────
# ROLES / STAFF / USER
# ────────────────────────────────────────────────────────────────────────────

class Role(BaseRaw):
    name        = models.CharField(max_length=100, unique=True)
    permissions = JSONField(blank=True, null=True)

class Cadre(BaseRaw):
    name    = models.CharField(max_length=255)
    branch  = models.ForeignKey(Branch, on_delete=models.CASCADE)
    status  = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

# companies/models.py

class Staff(AutoCodeMixin, BaseRaw):
    CODE_FIELD    = "staffcode"
    staffcode     = models.CharField("Empcode", max_length=50, unique=True, blank=True, null=True, db_index=True)
    name          = models.CharField(max_length=255, blank=True, null=True)

    branch = models.ForeignKey(
        Branch,
        to_field="code",          # ← keep Branch.code as FK target
        db_column="branch",       # ← legacy DB column name
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="staff",
    )

    cadre         = models.ForeignKey(Cadre, on_delete=models.SET_NULL, null=True, blank=True)
    designation   = models.CharField(max_length=100, blank=True, null=True)
    joining_date  = models.DateField(blank=True, null=True)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    bank          = models.CharField(max_length=100, blank=True, null=True)
    ifsc          = models.CharField(max_length=20, blank=True, null=True)
    contact1      = models.CharField(max_length=15, blank=True, null=True, validators=[phone_validator], unique=True)
    photo         = models.ImageField(upload_to="staff_photos/", blank=True, null=True)

    def __str__(self):
        return self.name or f"Staff #{self.pk}"

    # ✅ Normalize legacy truthy "active" values at save time
    def save(self, *args, **kwargs):
        if str(self.status).strip().lower() in {"1", "true", "active"} or self.status in (1, True):
            self.status = "active"
        super().save(*args, **kwargs)


class UserProfile(BaseRaw):
    user = models.ForeignKey(
        AuthUser,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        db_column="user"
    )
    # ✅ Allow legacy truthy "active" values to pass FK constraint
    staff = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to=(
            Q(status__iexact="active") |
            Q(status="1") | Q(status=1) | Q(status=True)
        ),
        related_name="user_profile"
    )
    full_name  = models.CharField(max_length=255, blank=True, null=True)
    branch     = models.ForeignKey("Branch", on_delete=models.SET_NULL, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    mobile     = models.CharField(max_length=20, blank=True, null=True, validators=[phone_validator])
    is_admin        = models.BooleanField(default=False)
    is_master       = models.BooleanField(default=False)
    is_data_entry   = models.BooleanField(default=False)
    is_reports      = models.BooleanField(default=False)
    is_accounting   = models.BooleanField(default=False)
    is_recovery_agent = models.BooleanField(default=False)
    is_auditor        = models.BooleanField(default=False)
    is_manager        = models.BooleanField(default=False)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    password = models.CharField(max_length=128, blank=True, null=True,
                                help_text="Hashed password for non-Django auth use")

    def set_password(self, raw_password):
        from django.contrib.auth.hashers import make_password
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        from django.contrib.auth.hashers import check_password
        return check_password(raw_password, self.password)


class UserPermission(BaseRaw):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="permissions_set")
    is_admin        = models.BooleanField(default=False)
    is_master       = models.BooleanField(default=False)
    is_data_entry   = models.BooleanField(default=False)
    is_accounting   = models.BooleanField(default=False)
    is_recovery_agent = models.BooleanField(default=False)
    is_auditor        = models.BooleanField(default=False)
    is_manager        = models.BooleanField(default=False)
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

# ────────────────────────────────────────────────────────────────────────────
# PRODUCTS / CLIENTS
# ────────────────────────────────────────────────────────────────────────────

class Product(AutoCodeMixin, BaseRaw):
    CODE_PREFIX = "PRD"
    code     = models.CharField(max_length=100, unique=True, blank=True)
    name     = models.CharField(max_length=255)
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, blank=True, null=True)
    status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

class Client(AutoCodeMixin, BaseRaw):
    CODE_PREFIX = "CL"
    CODE_FIELD  = "smtcode"
    smtcode   = models.CharField(max_length=50, unique=True, blank=True, db_index=True)
    name      = models.CharField(max_length=255)
    gender    = models.CharField(max_length=10, blank=True, null=True)
    group     = models.ForeignKey("Group", to_field="code", db_column="GCode",
                                  on_delete=models.SET_NULL, null=True, blank=True, related_name="clients")
    join_date = models.DateField(blank=True, null=True)
    aadhar    = models.CharField(max_length=14, blank=True, null=True, validators=[aadhar_validator], unique=True)
    contactno = models.CharField(max_length=20, blank=True, null=True, validators=[phone_validator], unique=True)
    status    = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

# ────────────────────────────────────────────────────────────────────────────
# LOAN FLOW
# ────────────────────────────────────────────────────────────────────────────

class LoanApplication(BaseRaw):
    application_number = models.CharField(max_length=100, unique=True)
    client        = models.ForeignKey(Client, to_field="smtcode", db_column="SMTCode",
                                      on_delete=models.CASCADE, related_name="loan_applications")
    product       = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    amount_requested = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    interest_rate    = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    tenure_months    = models.PositiveIntegerField(blank=True, null=True)
    applied_date     = models.DateField(blank=True, null=True)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

class LoanApproval(BaseRaw):
    loan_application = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name="approvals")
    approved_amount  = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    approval_date    = models.DateField(blank=True, null=True)
    approver         = models.ForeignKey(Staff, to_field="staffcode", db_column="StaffCode",
                                         on_delete=models.SET_NULL, null=True, blank=True)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

class Disbursement(BaseRaw):
    loan_application = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name="disbursements")
    amount           = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    disbursement_date= models.DateField(blank=True, null=True)
    channel          = models.CharField(max_length=100, blank=True, null=True)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

# ────────────────────────────────────────────────────────────────────────────
# HRPM
# ────────────────────────────────────────────────────────────────────────────

class Appointment(BaseRaw):
    staff        = models.ForeignKey(Staff, to_field="staffcode", db_column="StaffCode",
                                     on_delete=models.CASCADE, related_name="appointments")
    appointment_date = models.DateField(blank=True, null=True)
    designation  = models.CharField(max_length=100, blank=True, null=True)
    branch       = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    remarks      = models.TextField(blank=True, null=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

class SalaryStatement(BaseRaw):
    staff        = models.ForeignKey(Staff, to_field="staffcode", db_column="StaffCode",
                                     on_delete=models.CASCADE, related_name="salary_statements")
    month        = models.PositiveSmallIntegerField(help_text="1-12")
    year         = models.PositiveSmallIntegerField()
    basic_pay    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pay      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    generated_on = models.DateField(blank=True, null=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

# ────────────────────────────────────────────────────────────────────────────
# SETTINGS / FIELD OPS / REPORTS
# ────────────────────────────────────────────────────────────────────────────

class BusinessSetting(BaseRaw):
    key     = models.CharField(max_length=100)
    value   = models.TextField()
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="settings")

class FieldSchedule(BaseRaw):
    schedule_date = models.DateField(blank=True, null=True)
    # ✅ Allow legacy truthy "active" values to pass FK constraint
    staff  = models.ForeignKey(
        Staff, to_field="staffcode", db_column="StaffCode",
        on_delete=models.SET_NULL, null=True, blank=True,
        limit_choices_to=(
            Q(status__iexact="active") |
            Q(status="1") | Q(status=1) | Q(status=True)
        )
    )
    center = models.ForeignKey(Center, to_field="code", db_column="CenterCode",
                               on_delete=models.SET_NULL, null=True, blank=True)
    notes  = models.TextField(blank=True, null=True)

class FieldReport(BaseRaw):
    report_date = models.DateField(blank=True, null=True)
    schedule    = models.ForeignKey(FieldSchedule, on_delete=models.SET_NULL, null=True, blank=True)
    summary     = models.TextField(blank=True, null=True)

class WeeklyReport(BaseRaw):
    period_start = models.DateField(blank=True, null=True)
    period_end   = models.DateField(blank=True, null=True)
    generated_on = models.DateField(blank=True, null=True)
    summary      = models.TextField(blank=True, null=True)

class MonthlyReport(BaseRaw):
    period_start = models.DateField(blank=True, null=True)
    period_end   = models.DateField(blank=True, null=True)
    generated_on = models.DateField(blank=True, null=True)
    summary      = models.TextField(blank=True, null=True)

# ────────────────────────────────────────────────────────────────────────────
# DYNAMIC COLUMNS
# ────────────────────────────────────────────────────────────────────────────

class Column(BaseRaw):
    module     = models.CharField(max_length=100)
    field_name = models.CharField(max_length=100)
    label      = models.CharField(max_length=100)
    field_type = models.CharField(max_length=50, default="text")
    required   = models.BooleanField(default=False)
    order      = models.IntegerField(default=0, validators=[MinValueValidator(0)], blank=True, null=True)

    class Meta:
        unique_together = (("module", "field_name"),)

# ────────────────────────────────────────────────────────────────────────────
# ACCOUNTING
# ────────────────────────────────────────────────────────────────────────────

class AccountHead(AutoCodeMixin, BaseRaw):
    CODE_PREFIX = "AH"
    code         = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
    name         = models.CharField(max_length=100)
    parent       = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    abbreviation = models.CharField(max_length=20, blank=True, null=True)
    ac_type      = models.CharField(max_length=20, blank=True, null=True)
    vtype        = models.CharField(max_length=10, blank=True, null=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

class Voucher(AutoCodeMixin, BaseRaw):
    CODE_PREFIX = "VCH"
    CODE_FIELD  = "voucher_no"
    voucher_no   = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
    date         = models.DateField()
    account_head = models.ForeignKey(AccountHead, on_delete=models.PROTECT)
    narration    = models.TextField(blank=True, null=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

class Posting(BaseRaw):
    voucher      = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name="postings")
    account_head = models.ForeignKey(AccountHead, on_delete=models.PROTECT)
    debit        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ttype        = models.CharField(max_length=10, blank=True, null=True)
    narration    = models.TextField(blank=True, null=True)

class RecoveryPosting(BaseRaw):
    client  = models.ForeignKey(Client, to_field="smtcode", db_column="SMTCode", on_delete=models.PROTECT)
    date    = models.DateField()
    amount  = models.DecimalField(max_digits=12, decimal_places=2)
    voucher = models.ForeignKey(Voucher, on_delete=models.PROTECT, null=True, blank=True)
    status  = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

# ────────────────────────────────────────────────────────────────────
# OFFLINE KYC
# ────────────────────────────────────────────────────────────────────

class KYCDocument(models.Model):
    DOC_TYPES = [("aadhar","Aadhaar"),("pan","PAN"),("voter","Voter ID"),("ration","Ration Card"),("photo","Photo"),("other","Other")]
    STATUS = [("pending","Pending"),("verified","Verified"),("rejected","Rejected")]
    client_ref = models.CharField(max_length=64, blank=True, null=True, help_text="Client code/number")
    client_name = models.CharField(max_length=255, blank=True, null=True)
    doc_type = models.CharField(max_length=20, choices=DOC_TYPES)
    file = models.FileField(upload_to="kyc/", blank=True, null=True)
    number = models.CharField(max_length=64, blank=True, null=True, help_text="ID number printed on document")
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    remarks = models.TextField(blank=True, null=True)
    extra_data = JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "companies_kycdocument"

    def __str__(self):
        return f"KYC[{self.doc_type}] {self.client_ref or ''}".strip()

# ────────────────────────────────────────────────────────────────────
# ESCALATION ALERTS
# ────────────────────────────────────────────────────────────────────

class AlertRule(models.Model):
    name = models.CharField(max_length=120, unique=True)
    entity = models.CharField(max_length=64)
    condition = JSONField(default=dict, blank=True)
    channels = (ArrayField(models.CharField(max_length=16), default=list, blank=True)
                if connection.vendor == "postgresql" else JSONField(default=list, blank=True))
    is_active = models.BooleanField(default=True)
    extra_data = JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "companies_alertrule"

    def __str__(self):
        return self.name

class AlertEvent(models.Model):
    rule_name = models.CharField(max_length=120)
    entity = models.CharField(max_length=64)
    object_pk = models.CharField(max_length=64)
    payload = JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, default="queued")  # queued|sent|failed|skipped
    message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "companies_alertevent"
        indexes = [models.Index(fields=["entity", "status"])]

    def __str__(self):
        return f"{self.rule_name}:{self.object_pk}:{self.status}"













# Auto-pruned models: only high-signal fields (identifiers, relations, dates, amounts, status).
class Members(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    photo = models.ImageField(upload_to="member_photos/", blank=True, null=True)
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_memberscsvmodel')
    name = models.CharField(max_length=255, blank=True, null=True)
    s_due = models.FloatField(blank=True, null=True)
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_memberscsvmodel')
    gname = models.CharField(max_length=255, blank=True, null=True)
    cbname = models.CharField(max_length=255, blank=True, null=True)
    age = models.FloatField(blank=True, null=True)
    flg_active = models.FloatField(blank=True, null=True)
    with_date = models.CharField(max_length=50, blank=True, null=True)
    flg_repl = models.FloatField(blank=True, null=True)
    rep_date = models.CharField(max_length=50, blank=True, null=True)
    entryfee = models.FloatField(blank=True, null=True)
    sq = models.FloatField(blank=True, null=True)
    contactno = models.CharField(max_length=255, blank=True, null=True)
    equity = models.FloatField(blank=True, null=True)
    maturitydate = models.CharField(max_length=50, blank=True, null=True)
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_memberscsvmodel')
    inistallmentamt = models.FloatField(blank=True, null=True)
    lastupdate = models.CharField(max_length=50, blank=True, null=True)
    insupaiddate = models.CharField(max_length=50, blank=True, null=True)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_memberscsvmodel')
    agent = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_memberscsvmodel')
    clientis = models.CharField(max_length=255, blank=True, null=True)
    husadhaarno = models.FloatField(blank=True, null=True)
    empcode = models.CharField(max_length=255, blank=True, null=True)
    arrear = models.FloatField(blank=True, null=True)
    grm = models.FloatField(blank=True, null=True)
    gl = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)
class AccCashbook(BaseRaw):
    voucherno = models.FloatField(blank=True, null=True)
    tdate = models.CharField(max_length=50, blank=True, null=True)
    acode = models.CharField(max_length=255, blank=True, null=True)
    credit = models.FloatField(blank=True, null=True)
    debit = models.FloatField(blank=True, null=True)
    pid = models.FloatField(blank=True, null=True)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_acccashbookcsvmodel')
    raw_csv_data = models.JSONField(blank=True, null=True)

class AccCashbookold(BaseRaw):
    voucherno = models.FloatField(blank=True, null=True)
    tdate = models.CharField(max_length=50, blank=True, null=True)
    acode = models.CharField(max_length=255, blank=True, null=True)
    credit = models.FloatField(blank=True, null=True)
    debit = models.FloatField(blank=True, null=True)
    pid = models.FloatField(blank=True, null=True)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_acccashbookoldcsvmodel')
    raw_csv_data = models.JSONField(blank=True, null=True)

class AccHeads(BaseRaw):
    vtype = models.FloatField(blank=True, null=True)
    acode = models.CharField(max_length=255, blank=True, null=True)
    typecode = models.FloatField(blank=True, null=True)
    slno = models.FloatField(blank=True, null=True)
    isvisiable = models.FloatField(blank=True, null=True)
    pid = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Aadhar(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    aadharno = models.CharField(max_length=255, blank=True, null=True)
    edate = models.CharField(max_length=50, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Accfundloancols(BaseRaw):
    issdate = models.CharField(max_length=50, blank=True, null=True)
    facode = models.CharField(max_length=255, blank=True, null=True)
    amount = models.FloatField(blank=True, null=True)
    acbalance = models.FloatField(blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    prinbal = models.FloatField(blank=True, null=True)
    prininstal = models.FloatField(blank=True, null=True)
    colsc = models.FloatField(blank=True, null=True)
    date1 = models.CharField(max_length=50, blank=True, null=True)
    prepaidamt = models.FloatField(blank=True, null=True)
    prin_due = models.FloatField(blank=True, null=True)
    int_due = models.FloatField(blank=True, null=True)
    tbno = models.FloatField(blank=True, null=True)
    carporate = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Accfundloans(BaseRaw):
    facode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    lamount = models.FloatField(blank=True, null=True)
    balamt = models.FloatField(blank=True, null=True)
    balsc = models.FloatField(blank=True, null=True)
    roi = models.FloatField(blank=True, null=True)
    ldate = models.CharField(max_length=50, blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    bal_inst = models.FloatField(blank=True, null=True)
    acode = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Accountmaster(BaseRaw):
    mastername = models.CharField(max_length=255, blank=True, null=True)
    mastercode = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Arrear(BaseRaw):
    issdate = models.CharField(max_length=50, blank=True, null=True)
    smtcode = models.FloatField(blank=True, null=True)
    amount = models.FloatField(blank=True, null=True)
    acbalance = models.FloatField(blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    prinbal = models.FloatField(blank=True, null=True)
    actarrprin = models.FloatField(blank=True, null=True)
    actarrsc = models.FloatField(blank=True, null=True)
    arradm = models.FloatField(blank=True, null=True)
    colsc = models.FloatField(blank=True, null=True)
    adm = models.FloatField(blank=True, null=True)
    date1 = models.CharField(max_length=50, blank=True, null=True)
    prepaidamt = models.FloatField(blank=True, null=True)
    prin_due = models.FloatField(blank=True, null=True)
    int_due = models.FloatField(blank=True, null=True)
    adm_due = models.FloatField(blank=True, null=True)
    tbno = models.FloatField(blank=True, null=True)
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_arrearcsvmodel')
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_arrearcsvmodel')
    week = models.FloatField(blank=True, null=True)
    slno = models.FloatField(blank=True, null=True)
    carporate = models.FloatField(blank=True, null=True)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_arrearcsvmodel')
    scode = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Cheque(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    issdate = models.CharField(max_length=50, blank=True, null=True)
    branch = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Codes(BaseRaw):
    scode = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Contacts(BaseRaw):
    centerno = models.FloatField(blank=True, null=True)
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    contactno = models.FloatField(blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    edate = models.CharField(max_length=50, blank=True, null=True)
    aadharno = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Dayend(BaseRaw):
    dayend = models.CharField(max_length=50, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Equity2(BaseRaw):
    slno = models.FloatField(blank=True, null=True)
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    date = models.CharField(max_length=50, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Equityshare31032014(BaseRaw):
    slno = models.FloatField(blank=True, null=True)
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    shareamt = models.FloatField(blank=True, null=True)
    saving = models.FloatField(blank=True, null=True)
    thrift = models.FloatField(blank=True, null=True)
    advance = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Equityshare31032015(BaseRaw):
    slno = models.FloatField(blank=True, null=True)
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    shareamt = models.FloatField(blank=True, null=True)
    saving = models.FloatField(blank=True, null=True)
    thrift = models.FloatField(blank=True, null=True)
    advance = models.FloatField(blank=True, null=True)
    total = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Gr(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    issdate = models.CharField(max_length=50, blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    memcontactno = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Groups(BaseRaw):
    gcode = models.FloatField(blank=True, null=True)
    gname = models.CharField(max_length=255, blank=True, null=True)
    llimit = models.FloatField(blank=True, null=True)
    wday = models.FloatField(blank=True, null=True)
    cno = models.FloatField(blank=True, null=True)
    noofborrw = models.FloatField(blank=True, null=True)
    scode = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MXAgent(BaseRaw):
    agent = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxagentcsvmodel')
    name = models.CharField(max_length=255, blank=True, null=True)
    ajf = models.FloatField(blank=True, null=True)
    village = models.CharField(max_length=255, blank=True, null=True)
    contactno = models.FloatField(blank=True, null=True)
    nominee = models.CharField(max_length=255, blank=True, null=True)
    age = models.FloatField(blank=True, null=True)
    isactive = models.FloatField(blank=True, null=True)
    reasonofwithdraw = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MXCode(BaseRaw):
    code = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MXMember(BaseRaw):
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxmembercsvmodel')
    name = models.CharField(max_length=255, blank=True, null=True)
    gender = models.FloatField(blank=True, null=True)
    age = models.FloatField(blank=True, null=True)
    efee = models.FloatField(blank=True, null=True)
    status = models.FloatField(blank=True, null=True)
    nominee = models.CharField(max_length=255, blank=True, null=True)
    projectperiod = models.FloatField(blank=True, null=True)
    inistallmentamt = models.FloatField(blank=True, null=True)
    closedate = models.CharField(max_length=50, blank=True, null=True)
    meturitydate = models.CharField(max_length=50, blank=True, null=True)
    agent = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxmembercsvmodel')
    contactno = models.FloatField(blank=True, null=True)
    village = models.ForeignKey(Village, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxmembercsvmodel')
    istakeloan = models.FloatField(blank=True, null=True)
    misstat = models.FloatField(blank=True, null=True)
    statdate = models.CharField(max_length=50, blank=True, null=True)
    totsavingamt = models.FloatField(blank=True, null=True)
    interest = models.FloatField(blank=True, null=True)
    lastupdate = models.CharField(max_length=50, blank=True, null=True)
    memono = models.FloatField(blank=True, null=True)
    equity = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MXSavings(BaseRaw):
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxsavingscsvmodel')
    tdate = models.CharField(max_length=50, blank=True, null=True)
    creditamt = models.FloatField(blank=True, null=True)
    debit = models.FloatField(blank=True, null=True)
    balance = models.FloatField(blank=True, null=True)
    typecode = models.FloatField(blank=True, null=True)
    intpayble = models.FloatField(blank=True, null=True)
    paidinterest = models.FloatField(blank=True, null=True)
    tbno = models.FloatField(blank=True, null=True)
    agent = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxsavingscsvmodel')
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxsavingscsvmodel')
    gcod = models.FloatField(blank=True, null=True)
    acode = models.CharField(max_length=255, blank=True, null=True)
    acholdername = models.CharField(max_length=255, blank=True, null=True)
    paidacno = models.FloatField(blank=True, null=True)
    bankbranch = models.CharField(max_length=255, blank=True, null=True)
    paymentmode = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Massposting(BaseRaw):
    tdate = models.CharField(max_length=50, blank=True, null=True)
    cencode = models.FloatField(blank=True, null=True)
    upfee = models.FloatField(blank=True, null=True)
    centerfund = models.FloatField(blank=True, null=True)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_masspostingcsvmodel')
    raw_csv_data = models.JSONField(blank=True, null=True)

class MasterBranch(BaseRaw):
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_masterbranchcsvmodel')
    br_name = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MasterCategories(BaseRaw):
    catcode = models.FloatField(blank=True, null=True)
    rateofint = models.FloatField(blank=True, null=True)
    duration = models.FloatField(blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MasterFs(BaseRaw):
    yearwk = models.FloatField(blank=True, null=True)
    wkno = models.FloatField(blank=True, null=True)
    meetingdate = models.CharField(max_length=50, blank=True, null=True)
    meetingday = models.CharField(max_length=50, blank=True, null=True)
    cencode = models.FloatField(blank=True, null=True)
    cenname = models.CharField(max_length=255, blank=True, null=True)
    ispostedrec = models.FloatField(blank=True, null=True)
    nxtmeetingdate = models.CharField(max_length=50, blank=True, null=True)
    borrower = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MasterLoanpurposes(BaseRaw):
    purpcode = models.FloatField(blank=True, null=True)
    sectorecode = models.FloatField(blank=True, null=True)
    purpname = models.CharField(max_length=255, blank=True, null=True)
    newpurposename = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MasterLoantypes(BaseRaw):
    typecode = models.CharField(max_length=255, blank=True, null=True)
    min = models.FloatField(blank=True, null=True)
    max1 = models.FloatField(blank=True, null=True)
    firstinst = models.FloatField(blank=True, null=True)
    dur1 = models.FloatField(blank=True, null=True)
    interest = models.FloatField(blank=True, null=True)
    catcode = models.FloatField(blank=True, null=True)
    pininstal = models.FloatField(blank=True, null=True)
    ltypestatus = models.FloatField(blank=True, null=True)
    upfee = models.FloatField(blank=True, null=True)
    denomination = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MasterMonth(BaseRaw):
    month = models.FloatField(blank=True, null=True)
    year = models.FloatField(blank=True, null=True)
    st_date = models.CharField(max_length=50, blank=True, null=True)
    end_date = models.CharField(max_length=50, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MasterSectors(BaseRaw):
    sectorcode = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MasterSetup(BaseRaw):
    tnr = models.FloatField(blank=True, null=True)
    colsc = models.FloatField(blank=True, null=True)
    adm = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MasterWeeks(BaseRaw):
    week_no = models.FloatField(blank=True, null=True)
    year = models.FloatField(blank=True, null=True)
    st_date = models.CharField(max_length=50, blank=True, null=True)
    end_date = models.CharField(max_length=50, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MXAgriment(BaseRaw):
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxagrimentcsvmodel')
    agrimentdate = models.CharField(max_length=50, blank=True, null=True)
    agrimentid = models.FloatField(blank=True, null=True)
    firstinstallmentdate = models.CharField(max_length=50, blank=True, null=True)
    lastinistallmentdate = models.CharField(max_length=50, blank=True, null=True)
    meturitydate = models.CharField(max_length=50, blank=True, null=True)
    dividentamt = models.FloatField(blank=True, null=True)
    projectperiod = models.FloatField(blank=True, null=True)
    amountperinistallment = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MXLoancols(BaseRaw):
    issdate = models.CharField(max_length=50, blank=True, null=True)
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxloancolscsvmodel')
    amount = models.FloatField(blank=True, null=True)
    acbalance = models.FloatField(blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    prininstal = models.FloatField(blank=True, null=True)
    colsc = models.FloatField(blank=True, null=True)
    date1 = models.CharField(max_length=50, blank=True, null=True)
    prepaidamt = models.FloatField(blank=True, null=True)
    prin_due = models.FloatField(blank=True, null=True)
    int_due = models.FloatField(blank=True, null=True)
    tbno = models.FloatField(blank=True, null=True)
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxloancolscsvmodel')
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxloancolscsvmodel')
    week = models.FloatField(blank=True, null=True)
    slno = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MXLoans(BaseRaw):
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxloanscsvmodel')
    loanamt = models.FloatField(blank=True, null=True)
    balamt = models.FloatField(blank=True, null=True)
    balsc = models.FloatField(blank=True, null=True)
    bal_inst = models.FloatField(blank=True, null=True)
    prin_inst = models.FloatField(blank=True, null=True)
    prin_sc = models.FloatField(blank=True, null=True)
    penal_interest = models.FloatField(blank=True, null=True)
    lastupdate = models.CharField(max_length=50, blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    issdate = models.CharField(max_length=50, blank=True, null=True)
    expdate = models.CharField(max_length=50, blank=True, null=True)
    closedate = models.FloatField(blank=True, null=True)
    sectorcode = models.FloatField(blank=True, null=True)
    efund = models.FloatField(blank=True, null=True)
    colsc = models.FloatField(blank=True, null=True)
    sarvicecharge = models.FloatField(blank=True, null=True)
    gff = models.FloatField(blank=True, null=True)
    nextduedate = models.CharField(max_length=50, blank=True, null=True)
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxloanscsvmodel')
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxloanscsvmodel')
    week = models.FloatField(blank=True, null=True)
    slno = models.FloatField(blank=True, null=True)
    dloanamt = models.FloatField(blank=True, null=True)
    roi = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MXSalaries(BaseRaw):
    agent = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_mxsalariescsvmodel')
    tdate = models.CharField(max_length=50, blank=True, null=True)
    collection = models.FloatField(blank=True, null=True)
    salary = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Pdc(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    bankbranch = models.CharField(max_length=255, blank=True, null=True)
    acno = models.FloatField(blank=True, null=True)
    ifsccode = models.CharField(max_length=255, blank=True, null=True)
    noofcheqs = models.FloatField(blank=True, null=True)
    chqnos = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class RptDaybook(BaseRaw):
    slno = models.CharField(max_length=255, blank=True, null=True)
    acode = models.CharField(max_length=255, blank=True, null=True)
    tdate = models.CharField(max_length=50, blank=True, null=True)
    lfno = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Securitydeposit(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    tdate = models.CharField(max_length=50, blank=True, null=True)
    credit = models.FloatField(blank=True, null=True)
    debit = models.FloatField(blank=True, null=True)
    ltypecode = models.CharField(max_length=255, blank=True, null=True)
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_securitydepositcsvmodel')
    raw_csv_data = models.JSONField(blank=True, null=True)

class Staffloans(BaseRaw):
    staffcode = models.CharField(max_length=255, blank=True, null=True)
    loantype = models.CharField(max_length=255, blank=True, null=True)
    loanamt = models.FloatField(blank=True, null=True)
    issdate = models.CharField(max_length=50, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Transefer(BaseRaw):
    tdate = models.CharField(max_length=50, blank=True, null=True)
    oldcenter = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='transfers_oldcenter')
    oldsmtcode = models.FloatField(blank=True, null=True)
    newcenter = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='transfers_newcenter')
    newsmtcode = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Cobarower(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    barowname = models.CharField(max_length=255, blank=True, null=True)
    contactno = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Collectionrpt(BaseRaw):
    slno = models.CharField(max_length=255, blank=True, null=True)
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Fund(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    tdate = models.CharField(max_length=50, blank=True, null=True)
    credit = models.FloatField(blank=True, null=True)
    debit = models.FloatField(blank=True, null=True)
    balance = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Loancols(BaseRaw):
    issdate = models.CharField(max_length=50, blank=True, null=True)
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    amount = models.FloatField(blank=True, null=True)
    acbalance = models.FloatField(blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    prinbal = models.FloatField(blank=True, null=True)
    actarrprin = models.FloatField(blank=True, null=True)
    actarrsc = models.FloatField(blank=True, null=True)
    arradm = models.FloatField(blank=True, null=True)
    prininstal = models.FloatField(blank=True, null=True)
    colsc = models.FloatField(blank=True, null=True)
    adm = models.FloatField(blank=True, null=True)
    savings = models.FloatField(blank=True, null=True)
    penal_int = models.FloatField(blank=True, null=True)
    date1 = models.CharField(max_length=50, blank=True, null=True)
    prepaidamt = models.FloatField(blank=True, null=True)
    prin_due = models.FloatField(blank=True, null=True)
    int_due = models.FloatField(blank=True, null=True)
    adm_due = models.FloatField(blank=True, null=True)
    tbno = models.FloatField(blank=True, null=True)
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_loancolscsvmodel')
    gcod = models.FloatField(blank=True, null=True)
    week = models.FloatField(blank=True, null=True)
    misc_mem = models.FloatField(blank=True, null=True)
    slno = models.FloatField(blank=True, null=True)
    carporate = models.CharField(max_length=255, blank=True, null=True)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_loancolscsvmodel')
    scode = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Loans(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    loanamt = models.FloatField(blank=True, null=True)
    prin_inst = models.FloatField(blank=True, null=True)
    prin_sc = models.FloatField(blank=True, null=True)
    prin_adm = models.FloatField(blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    issdate = models.CharField(max_length=50, blank=True, null=True)
    tenure = models.FloatField(blank=True, null=True)
    balamt = models.FloatField(blank=True, null=True)
    bal_inst = models.FloatField(blank=True, null=True)
    balsc = models.FloatField(blank=True, null=True)
    s_due = models.FloatField(blank=True, null=True)
    baladm = models.FloatField(blank=True, null=True)
    lastupdate = models.CharField(max_length=50, blank=True, null=True)
    fstemidt = models.CharField(max_length=255, blank=True, null=True)
    expdate = models.CharField(max_length=50, blank=True, null=True)
    closedate = models.CharField(max_length=50, blank=True, null=True)
    purpose = models.FloatField(blank=True, null=True)
    carporate = models.CharField(max_length=255, blank=True, null=True)
    sectorcode = models.FloatField(blank=True, null=True)
    efund = models.FloatField(blank=True, null=True)
    colsc = models.FloatField(blank=True, null=True)
    sarvicecharge = models.FloatField(blank=True, null=True)
    pfee = models.FloatField(blank=True, null=True)
    llprovision = models.FloatField(blank=True, null=True)
    nextduedate = models.CharField(max_length=50, blank=True, null=True)
    misstat = models.FloatField(blank=True, null=True)
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_loanscsvmodel')
    gcod = models.FloatField(blank=True, null=True)
    week = models.FloatField(blank=True, null=True)
    slno = models.FloatField(blank=True, null=True)
    dloanamt = models.FloatField(blank=True, null=True)
    roi = models.FloatField(blank=True, null=True)
    acode = models.CharField(max_length=255, blank=True, null=True)
    insureddate = models.FloatField(blank=True, null=True)
    arrprin = models.FloatField(blank=True, null=True)
    arrsc = models.FloatField(blank=True, null=True)
    arradm = models.FloatField(blank=True, null=True)
    sarrear = models.FloatField(blank=True, null=True)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_loanscsvmodel')
    product = models.CharField(max_length=255, blank=True, null=True)
    passbookdiff = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Loansmfi41110(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    loanamt = models.FloatField(blank=True, null=True)
    balamt = models.FloatField(blank=True, null=True)
    balsc = models.FloatField(blank=True, null=True)
    bal_inst = models.FloatField(blank=True, null=True)
    prin_inst = models.FloatField(blank=True, null=True)
    prin_sc = models.FloatField(blank=True, null=True)
    exc_due = models.FloatField(blank=True, null=True)
    lastupdate = models.CharField(max_length=50, blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    issdate = models.CharField(max_length=50, blank=True, null=True)
    expdate = models.CharField(max_length=50, blank=True, null=True)
    closedate = models.CharField(max_length=50, blank=True, null=True)
    purpose = models.FloatField(blank=True, null=True)
    sectorcode = models.FloatField(blank=True, null=True)
    efund = models.FloatField(blank=True, null=True)
    colsc = models.FloatField(blank=True, null=True)
    sarvicecharge = models.FloatField(blank=True, null=True)
    gff = models.FloatField(blank=True, null=True)
    nextduedate = models.CharField(max_length=50, blank=True, null=True)
    misstat = models.FloatField(blank=True, null=True)
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_loansmfi41110csvmodel')
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_loansmfi41110csvmodel')
    week = models.FloatField(blank=True, null=True)
    arrprin = models.FloatField(blank=True, null=True)
    ason_due = models.FloatField(blank=True, null=True)
    slno = models.FloatField(blank=True, null=True)
    dloanamt = models.FloatField(blank=True, null=True)
    roi = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Mloanschedule(BaseRaw):
    issdate = models.CharField(max_length=50, blank=True, null=True)
    smtcode = models.FloatField(blank=True, null=True)
    amount = models.FloatField(blank=True, null=True)
    prindue = models.FloatField(blank=True, null=True)
    intdue = models.FloatField(blank=True, null=True)
    emi = models.FloatField(blank=True, null=True)
    duedate = models.CharField(max_length=50, blank=True, null=True)
    tbno = models.FloatField(blank=True, null=True)
    noofdays = models.FloatField(blank=True, null=True)
    penalinterest = models.FloatField(blank=True, null=True)
    balance = models.FloatField(blank=True, null=True)
    date1 = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Mloancols(BaseRaw):
    issdate = models.CharField(max_length=50, blank=True, null=True)
    smt = models.FloatField(blank=True, null=True)
    tdate = models.CharField(max_length=50, blank=True, null=True)
    credit = models.FloatField(blank=True, null=True)
    debit = models.FloatField(blank=True, null=True)
    balance = models.FloatField(blank=True, null=True)
    intdue = models.FloatField(blank=True, null=True)
    prdue = models.FloatField(blank=True, null=True)
    prininstal = models.FloatField(blank=True, null=True)
    colsc = models.FloatField(blank=True, null=True)
    arrint = models.FloatField(blank=True, null=True)
    tbno = models.FloatField(blank=True, null=True)
    prepaid = models.FloatField(blank=True, null=True)
    daysdiff = models.FloatField(blank=True, null=True)
    vfee = models.FloatField(blank=True, null=True)
    loginid = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Mloans(BaseRaw):
    loginid = models.FloatField(blank=True, null=True)
    smtcode = models.FloatField(blank=True, null=True)
    issdate = models.CharField(max_length=50, blank=True, null=True)
    loanamt = models.FloatField(blank=True, null=True)
    balamt = models.FloatField(blank=True, null=True)
    emi = models.FloatField(blank=True, null=True)
    tenure = models.FloatField(blank=True, null=True)
    balinst = models.FloatField(blank=True, null=True)
    roi = models.FloatField(blank=True, null=True)
    loantype = models.CharField(max_length=255, blank=True, null=True)
    emiday = models.FloatField(blank=True, null=True)
    totint = models.FloatField(blank=True, null=True)
    pfee = models.FloatField(blank=True, null=True)
    arr = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Mlogin(BaseRaw):
    loginid = models.FloatField(blank=True, null=True)
    smt = models.FloatField(blank=True, null=True)
    logindate = models.CharField(max_length=50, blank=True, null=True)
    dname = models.CharField(max_length=255, blank=True, null=True)
    contactno = models.FloatField(blank=True, null=True)
    pin = models.FloatField(blank=True, null=True)
    distance = models.FloatField(blank=True, null=True)
    loginfee = models.FloatField(blank=True, null=True)
    dvalue = models.FloatField(blank=True, null=True)
    yards = models.FloatField(blank=True, null=True)
    rqstln = models.FloatField(blank=True, null=True)
    appdate = models.CharField(max_length=50, blank=True, null=True)
    techfee = models.FloatField(blank=True, null=True)
    techfeedate = models.CharField(max_length=50, blank=True, null=True)
    survaydate = models.FloatField(blank=True, null=True)
    aprdln = models.FloatField(blank=True, null=True)
    disstatus = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Mmisc(BaseRaw):
    raw_csv_data = models.JSONField(blank=True, null=True)

class Mrecvisit(BaseRaw):
    vdate = models.CharField(max_length=50, blank=True, null=True)
    noofstaff = models.CharField(max_length=255, blank=True, null=True)
    noofkms = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Msetup(BaseRaw):
    effectdate = models.CharField(max_length=50, blank=True, null=True)
    loginfee = models.FloatField(blank=True, null=True)
    techfee = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Msurity(BaseRaw):
    tempid = models.FloatField(blank=True, null=True)
    smt = models.FloatField(blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    contact = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class MasterBusinessmode(BaseRaw):
    businessid = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Memberdeposits(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    tdate = models.CharField(max_length=50, blank=True, null=True)
    credit = models.FloatField(blank=True, null=True)
    balance = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Memberskaikaluru(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_memberskaikalurucsvmodel')
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_memberskaikalurucsvmodel')
    age = models.FloatField(blank=True, null=True)
    flg_active = models.FloatField(blank=True, null=True)
    with_date = models.CharField(max_length=50, blank=True, null=True)
    flg_repl = models.FloatField(blank=True, null=True)
    rep_date = models.CharField(max_length=50, blank=True, null=True)
    entryfee = models.FloatField(blank=True, null=True)
    kycno = models.FloatField(blank=True, null=True)
    contactno = models.CharField(max_length=255, blank=True, null=True)
    equitydate = models.FloatField(blank=True, null=True)
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_memberskaikalurucsvmodel')
    insureddate = models.FloatField(blank=True, null=True)
    insupaiddate = models.CharField(max_length=50, blank=True, null=True)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_memberskaikalurucsvmodel')
    clientis = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Pbdet(BaseRaw):
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_pbdetcsvmodel')
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    loantype = models.CharField(max_length=255, blank=True, null=True)
    disbdate = models.CharField(max_length=50, blank=True, null=True)
    loanamount = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Rptincome(BaseRaw):
    cencode = models.FloatField(blank=True, null=True)
    cenname = models.CharField(max_length=255, blank=True, null=True)
    lamt = models.FloatField(blank=True, null=True)
    efee = models.FloatField(blank=True, null=True)
    lc = models.FloatField(blank=True, null=True)
    miscmem = models.FloatField(blank=True, null=True)
    efund = models.FloatField(blank=True, null=True)
    gff = models.FloatField(blank=True, null=True)
    missta = models.FloatField(blank=True, null=True)
    total = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class RptGrcollectionsheet(BaseRaw):
    slno = models.CharField(max_length=255, blank=True, null=True)
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    genout = models.CharField(max_length=255, blank=True, null=True)
    gname = models.CharField(max_length=255, blank=True, null=True)
    grcode = models.CharField(max_length=255, blank=True, null=True)
    gendue = models.CharField(max_length=50, blank=True, null=True)
    cdate = models.CharField(max_length=50, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class RptOutstanding(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    issdate = models.CharField(max_length=50, blank=True, null=True)
    loanamt = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class RptPassbook(BaseRaw):
    slno = models.FloatField(blank=True, null=True)
    wkno = models.FloatField(blank=True, null=True)
    date1 = models.CharField(max_length=50, blank=True, null=True)
    ints = models.FloatField(blank=True, null=True)
    prinbal = models.FloatField(blank=True, null=True)
    due = models.FloatField(blank=True, null=True)
    tenor = models.FloatField(blank=True, null=True)
    savnor = models.FloatField(blank=True, null=True)
    savex = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class RptPassbookcommon(BaseRaw):
    slno = models.CharField(max_length=255, blank=True, null=True)
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    tdate = models.CharField(max_length=50, blank=True, null=True)
    savnor = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class RptTb(BaseRaw):
    acode = models.CharField(max_length=255, blank=True, null=True)
    slno = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class RptDisRegister(BaseRaw):
    centerno = models.FloatField(blank=True, null=True)
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    issdate = models.CharField(max_length=50, blank=True, null=True)
    loanamt = models.CharField(max_length=255, blank=True, null=True)
    closedate = models.CharField(max_length=50, blank=True, null=True)
    meturitydate = models.CharField(max_length=50, blank=True, null=True)
    agentname = models.FloatField(blank=True, null=True)
    balance = models.FloatField(blank=True, null=True)
    openbal = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class RptHigh(BaseRaw):
    slno = models.CharField(max_length=255, blank=True, null=True)
    uptolast = models.FloatField(blank=True, null=True)
    during = models.FloatField(blank=True, null=True)
    payment = models.FloatField(blank=True, null=True)
    ason = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class RptSavings(BaseRaw):
    slno = models.CharField(max_length=255, blank=True, null=True)
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    grcode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    norbal = models.CharField(max_length=255, blank=True, null=True)
    gendue = models.CharField(max_length=50, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class RptSumsheet(BaseRaw):
    slno = models.FloatField(blank=True, null=True)
    agent = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_rptsumsheetcsvmodel')
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_rptsumsheetcsvmodel')
    name = models.CharField(max_length=255, blank=True, null=True)
    efee = models.FloatField(blank=True, null=True)
    prin = models.FloatField(blank=True, null=True)
    colsc = models.FloatField(blank=True, null=True)
    adm = models.FloatField(blank=True, null=True)
    norsav = models.FloatField(blank=True, null=True)
    totalcr = models.FloatField(blank=True, null=True)
    exsav = models.FloatField(blank=True, null=True)
    exdr = models.FloatField(blank=True, null=True)
    norwd = models.FloatField(blank=True, null=True)
    totdr = models.FloatField(blank=True, null=True)
    balance = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Savings(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_savingscsvmodel')
    gcod = models.FloatField(blank=True, null=True)
    tdate = models.CharField(max_length=50, blank=True, null=True)
    weekno = models.FloatField(blank=True, null=True)
    sdue = models.FloatField(blank=True, null=True)
    creditamt = models.FloatField(blank=True, null=True)
    sarrear = models.FloatField(blank=True, null=True)
    debitamt = models.FloatField(blank=True, null=True)
    extracredit = models.FloatField(blank=True, null=True)
    extradebit = models.FloatField(blank=True, null=True)
    exbl = models.FloatField(blank=True, null=True)
    balance = models.FloatField(blank=True, null=True)
    centerfund = models.FloatField(blank=True, null=True)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_savingscsvmodel')
    scode = models.CharField(max_length=255, blank=True, null=True)
    ppamt = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Setup(BaseRaw):
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_setupcsvmodel')
    tdate = models.CharField(max_length=50, blank=True, null=True)
    savings = models.FloatField(blank=True, null=True)
    roi = models.FloatField(blank=True, null=True)
    adm = models.FloatField(blank=True, null=True)
    s_due = models.FloatField(blank=True, null=True)
    gff = models.FloatField(blank=True, null=True)
    remittance = models.FloatField(blank=True, null=True)
    efund = models.FloatField(blank=True, null=True)
    sta = models.FloatField(blank=True, null=True)
    efee = models.FloatField(blank=True, null=True)
    shareamt = models.FloatField(blank=True, null=True)
    insuranceamt = models.FloatField(blank=True, null=True)
    spp = models.FloatField(blank=True, null=True)
    noofwks = models.FloatField(blank=True, null=True)
    totint = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Setupn(BaseRaw):
    valu = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Share(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    tdate = models.CharField(max_length=50, blank=True, null=True)
    ef = models.FloatField(blank=True, null=True)
    deposit = models.FloatField(blank=True, null=True)
    withdraw = models.FloatField(blank=True, null=True)
    center = models.ForeignKey(Center, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_sharecsvmodel')
    gcod = models.FloatField(blank=True, null=True)
    paidinterest = models.FloatField(blank=True, null=True)
    tbno = models.FloatField(blank=True, null=True)
    agent = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='related_sharecsvmodel')
    centercode1 = models.FloatField(blank=True, null=True)
    acode = models.FloatField(blank=True, null=True)
    acholdername = models.FloatField(blank=True, null=True)
    paidacno = models.FloatField(blank=True, null=True)
    bankbranch = models.CharField(max_length=255, blank=True, null=True)
    paymentmode = models.CharField(max_length=255, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Share1(BaseRaw):
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    tdate = models.CharField(max_length=50, blank=True, null=True)
    sharecr = models.FloatField(blank=True, null=True)
    sharedr = models.FloatField(blank=True, null=True)
    savings = models.FloatField(blank=True, null=True)
    belongsto = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Smtavail(BaseRaw):
    smtcode = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Temp(BaseRaw):
    slno = models.CharField(max_length=255, blank=True, null=True)
    smtcode = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    typecode = models.CharField(max_length=255, blank=True, null=True)
    issdate = models.CharField(max_length=50, blank=True, null=True)
    expdate = models.CharField(max_length=50, blank=True, null=True)
    date1 = models.CharField(max_length=50, blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)

class Users(BaseRaw):
    uname = models.FloatField(blank=True, null=True)
    creat_date = models.CharField(max_length=50, blank=True, null=True)
    valid_date = models.CharField(max_length=50, blank=True, null=True)
    user_name = models.CharField(max_length=255, blank=True, null=True)
    user_desig = models.CharField(max_length=255, blank=True, null=True)
    r_member = models.FloatField(blank=True, null=True)
    r_accounts = models.FloatField(blank=True, null=True)
    r_reports = models.FloatField(blank=True, null=True)
    r_security = models.FloatField(blank=True, null=True)
    u_code = models.CharField(max_length=255, blank=True, null=True)
    pfcode = models.FloatField(blank=True, null=True)
    uattempts = models.FloatField(blank=True, null=True)
    passwordchangedate = models.CharField(max_length=50, blank=True, null=True)
    uploadstatus = models.FloatField(blank=True, null=True)
    raw_csv_data = models.JSONField(blank=True, null=True)
# ──── AUTO-GENERATE CODES IF EMPTY ────

