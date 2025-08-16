# companies/views.py
from functools import wraps
import json
import re
from datetime import datetime

from django.apps import apps
from django.conf import settings
from django.contrib import auth
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group as AuthGroup, Permission, User
from django.core.cache import cache
from django.core.exceptions import FieldError, FieldDoesNotExist
from django.db import IntegrityError, transaction, connection, DatabaseError
from django.db.models import ProtectedError, Q, ForeignKey
from django.http import JsonResponse, HttpResponseNotAllowed
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST, require_GET

from .models import Company, Column, Client, UserProfile, Staff
from .forms import *
from .services.credit_bureau import CreditBureauClient  # safe if file absent (feature flag off)

# ────────────────────────────────────────────────────────────────────
#  user-profile ⇆ Django-auth sync helpers
# ────────────────────────────────────────────────────────────────────
ROLE_GROUPS = {
    "is_master":     "Master",
    "is_data_entry": "DataEntry",
    "is_reports":    "Reports",
    "is_accounting": "Accounting",
    "is_recovery_agent": "RecoveryAgent",
    "is_auditor":        "Auditor",
    "is_manager":        "Manager",
}

def _desired_groups_for_profile(profile):
    groups = []
    for flag, group_name in ROLE_GROUPS.items():
        if getattr(profile, flag, False):
            grp, _ = AuthGroup.objects.get_or_create(name=group_name)
            groups.append(grp)
    if getattr(profile, "is_admin", False):
        grp, _ = AuthGroup.objects.get_or_create(name="Admin")
        groups.append(grp)
    return groups

def ensure_auth_user_for_profile(profile, username: str, raw_password: str | None):
    username = (username or "").strip()
    if not username:
        return None

    user = User.objects.filter(username=username).first() or User(username=username)

    has_any_role = any([
        getattr(profile, "is_admin", False),
        getattr(profile, "is_data_entry", False),
        getattr(profile, "is_reports", False),
        getattr(profile, "is_accounting", False),
        getattr(profile, "is_recovery_agent", False),
        getattr(profile, "is_auditor", False),
        getattr(profile, "is_manager", False),
    ])
    user.is_active = True
    user.is_staff = has_any_role or getattr(profile, "is_admin", False)
    user.is_superuser = getattr(profile, "is_admin", False)

    try:
        if getattr(profile, "full_name", None):
            user.first_name = profile.full_name
    except Exception:
        pass

    if raw_password:
        user.set_password(raw_password)

    user.save()
    user.groups.set(_desired_groups_for_profile(profile))
    user.save()

    try:
        profile.extra_data = (profile.extra_data or {}) | {
            "auth_user_id": user.id,
            "auth_username": user.username,
        }
        profile.save(update_fields=["extra_data"])
    except Exception:
        try:
            profile.save()
        except Exception:
            pass

    return user


# ────────────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────────────
def is_staff_or_superuser(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff)

@require_POST
def switch_account(request):
    auth.logout(request)
    return redirect(reverse("login"))

def _looks_ajax(request):
    xr = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"
    accepts_json = "application/json" in (request.headers.get("Accept") or "").lower()
    return xr or accepts_json

def ajax_login_required_or_redirect(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if _looks_ajax(request):
                return JsonResponse({"success": False, "error": "Authentication required"}, status=401)
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        return view_func(request, *args, **kwargs)
    return _wrapped

def feature_enabled(key: str) -> bool:
    try:
        return bool(getattr(settings, "SML_FEATURES", {}).get(key, False))
    except Exception:
        return False

def _only_active(qs, model):
    try:
        fields = {f.name for f in model._meta.get_fields()}
    except Exception:
        fields = set()
    q = Q(); added = False
    if "status" in fields:
        q |= Q(status__iexact="active") | Q(status=1) | Q(status=True) | Q(status="1"); added = True
    if "is_active" in fields:
        q |= Q(is_active=True); added = True
    if "active" in fields:
        q |= Q(active=1) | Q(active=True) | Q(active="1"); added = True
    return qs.filter(q) if added else qs

def _exclude_deleted(qs, model):
    try:
        fields = {f.name for f in model._meta.get_fields()}
    except Exception:
        fields = set()
    if "extra_data" in fields:
        try:
            return qs.exclude(extra_data__deleted=True)
        except Exception:
            return qs
    return qs

# dd/mm/yyyy → yyyy-mm-dd
_DDMMYYYY = re.compile(r"^\s*(\d{2})/(\d{2})/(\d{4})\s*$")
_DATE_KEYS = {
    "dob","joining_date","joined_on","from_date","to_date","applied_date",
    "disbursement_date","approval_date","issue_date","expiry_date","birth_date"
}
def _normalize_dates_ddmmyyyy_to_iso(data_dict):
    data = data_dict.copy()
    for key, val in list(data.items()):
        if not isinstance(val, str):
            continue
        kl = key.lower()
        if ("date" in kl) or (kl in _DATE_KEYS):
            m = _DDMMYYYY.match(val)
            if m:
                d, mth, y = m.groups()
                try:
                    data[key] = datetime(int(y), int(mth), int(d)).date().isoformat()
                except ValueError:
                    pass
    return data

def _json_db_error(e: Exception, default="Unexpected database error"):
    msg = str(e)
    return JsonResponse({"success": False, "error": f"{default}: {msg}"}, status=400)


# ────────────────────────────────────────────────────────────────────
#  Auth Views
# ────────────────────────────────────────────────────────────────────
def home_view(request):
    return render(request, "home.html")

ATTEMPT_KEY = "login_attempts:{ip}:{u}"
LOCK_KEY = "login_lock:{ip}:{u}"
MAX_ATTEMPTS = 5
OTP_REQUIRED_AFTER = 3
LOCK_SECONDS = 60

def _client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return fwd.split(",")[0].strip() if fwd else (request.META.get("REMOTE_ADDR") or "unknown").strip()

@csrf_protect
def login_view(request):
    if request.method != "POST":
        from django.middleware.csrf import get_token
        get_token(request)
        return render(request, "home.html")

    username = (request.POST.get("username") or "").strip()
    password = request.POST.get("password") or ""
    otp      = request.POST.get("otp") or ""
    remember = request.POST.get("remember") == "on"

    ip = _client_ip(request)
    attempt_key = ATTEMPT_KEY.format(ip=ip, u=username or "_")
    lock_key    = LOCK_KEY.format(ip=ip, u=username or "_")

    if cache.get(lock_key):
        return JsonResponse({"success": False, "error": "Too many attempts. Please wait a minute."}, status=429)

    attempts = int(cache.get(attempt_key) or 0)
    if attempts >= OTP_REQUIRED_AFTER and not otp:
        return JsonResponse({"success": False, "require_otp": True, "error": "OTP required"}, status=200)

    user = authenticate(request, username=username, password=password)

    def verify_otp(otp_code: str) -> bool:
        if attempts < OTP_REQUIRED_AFTER:
            return True
        return bool(otp_code and otp_code.isdigit() and 4 <= len(otp_code) <= 8)

    if user and is_staff_or_superuser(user) and verify_otp(otp):
        login(request, user)
        request.session.set_expiry(14 * 24 * 3600 if remember else 0)
        cache.delete(attempt_key); cache.delete(lock_key)
        return JsonResponse({"success": True, "redirect_url": "/dashboard/"})

    attempts += 1
    cache.set(attempt_key, attempts, timeout=LOCK_SECONDS * 3)
    if attempts >= MAX_ATTEMPTS:
        cache.set(lock_key, True, timeout=LOCK_SECONDS)
        return JsonResponse({"success": False, "error": "Account temporarily locked due to failed attempts."}, status=429)

    return JsonResponse({
        "success": False,
        "error": "Invalid credentials or permission denied",
        "require_otp": attempts >= OTP_REQUIRED_AFTER
    }, status=200)

@login_required
def logout_view(request):
    logout(request)
    return redirect("home")


# ────────────────────────────────────────────────────────────────────
#  Dashboard
# ────────────────────────────────────────────────────────────────────
@login_required
def dashboard_view(request):
    user = request.user
    display_name = user.get_full_name() or user.username
    branch_name = ""
    role_label = None

    profile = getattr(user, "userprofile", None) or UserProfile.objects.filter(extra_data__auth_user_id=user.id).first()
    if profile:
        if getattr(profile, "branch", None):
            try: branch_name = profile.branch.name
            except Exception: branch_name = ""
        if profile.is_admin:            role_label = "Admin"
        elif profile.is_master:         role_label = "Master"
        elif profile.is_data_entry:     role_label = "Data Entry"
        elif profile.is_reports:        role_label = "Reports"
        elif profile.is_accounting:     role_label = "Accounting"
        elif getattr(profile, "is_manager", False):        role_label = "Manager"
        elif getattr(profile, "is_recovery_agent", False): role_label = "Recovery Agent"
        elif getattr(profile, "is_auditor", False):        role_label = "Auditor"

    return render(
        request, "dashboard.html",
        {
            "staff_info": getattr(user, "staff_info", None),
            "header_user_display_name": display_name,
            "header_branch_name": branch_name,
            "header_role_label": role_label or ("Superuser" if user.is_superuser else "Staff" if user.is_staff else None),
            "profile": profile,
        },
    )


# ────────────────────────────────────────────────────────────────────
#  Entity utilities
# ────────────────────────────────────────────────────────────────────
_FAUX_ENTITIES = {"userpermission", "userpermissions"}

def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "").replace("_", "")

def get_model_class(entity):
    ent = (entity or "").strip()
    if ent.lower() in _FAUX_ENTITIES:
        return None
    try:
        m = apps.get_model("companies", ent)
        if m:
            return m
    except LookupError:
        pass
    try:
        m = apps.get_model("companies", ent.title().replace("_", ""))
        if m:
            return m
    except LookupError:
        pass
    try:
        app = apps.get_app_config("companies")
        tgt = _norm(ent)
        for m in app.get_models():
            if _norm(m.__name__) == tgt:
                return m
    except Exception:
        pass
    return None

def get_form_class(entity):
    name = f"{entity.capitalize()}Form"
    form_class = globals().get(name)
    if form_class:
        return form_class
    parts = entity.split("_")
    camel = "".join(p.capitalize() for p in parts)
    alt_name = f"{camel}Form"
    form_class = globals().get(alt_name)
    if form_class:
        return form_class
    lower_entity = entity.replace("_", "").lower()
    for obj in globals().values():
        if isinstance(obj, type) and obj.__name__.lower().endswith("form"):
            candidate = obj.__name__.lower().replace("form", "")
            if candidate == lower_entity or lower_entity in candidate:
                return obj
    return None

def get_section_map(entity):
    return {
        "clientjoiningform": {"Personal Info": ["member", "joined_on", "referred_by"], "Meta": ["joining_date"]},
        "staff":             {"Staff Details": ["name", "joining_date", "branch"]},
        "loanapplication":   {"Loan Info": ["client", "product", "amount_requested", "applied_date"], "Meta": ["joining_date"]},
        "userprofile":       {"User Setup": ["staff", "user", "branch", "password"], "Permissions": ["is_reports"], "Status": ["status"]},
        "role":              {"Role Details": ["name"]},
        "kycdocument":       {"Document Info": ["doc_type", "number", "file", "status"], "Client": ["client_ref", "client_name"], "Notes": ["remarks"]},
        "alertrule":         {"Basics": ["name", "entity", "is_active"], "Logic": ["condition", "channels"]},
    }.get(entity.lower(), None)

pretty_names = {
    "loanapplication": "Loan Application",
    "clientjoiningform": "Client Joining Form",
    "userprofile": "User Profile",
    "userpermission": "User Permissions",
    "staff": "Staff Registration",
    "role": "Role Management",
    "product": "Products Management",
    "company": "Company",
    "branch": "Branch",
    "village": "Village",
    "center": "Center",
    "group": "Group",
    "column": "Column",
    "businesssetting": "Business Setting Rules",
}

def _truthy(v): return str(v).strip().lower() in {"true", "1", "yes", "y", "t"}
def _flag(profile, attr: str) -> bool:
    v = getattr(profile, attr, False)
    return v if isinstance(v, bool) else _truthy(v)

DE_MODELS_SET  = {"client", "loanapplication", "recoveryposting", "clientjoiningform", "clientjoining"}
ACC_MODELS_SET = {"voucher", "posting", "accounthead"}
REPORT_MODELS_SET = {"fieldreport", "reportdropdownmenu", "reportdropdown"}

def _in_scope(entity_lc: str, scope_set: set[str]) -> bool:
    if entity_lc in scope_set: return True
    n = _norm(entity_lc)
    if n in {_norm(x) for x in scope_set}: return True
    if "report" in n and any("report" in _norm(x) for x in scope_set): return True
    return False

def get_profile_for_user(user):
    username = user.get_username()
    profile = None
    try:
        user_field = UserProfile._meta.get_field("user")
        if isinstance(user_field, ForeignKey):
            profile = UserProfile.objects.filter(user_id=user.id).first() or UserProfile.objects.filter(user__username=username).first()
        else:
            profile = UserProfile.objects.filter(user=username).first() or UserProfile.objects.filter(user__iexact=username).first()
    except Exception:
        profile = None
    if profile is None:
        profile = UserProfile.objects.filter(extra_data__auth_username=username).first()
    if profile is None:
        profile = UserProfile.objects.filter(extra_data__auth_user_id=user.id).first()
    return profile

def user_in_group(user, group_name: str) -> bool:
    return user.groups.filter(name__iexact=group_name).exists()

def user_is_master(user) -> bool:
    profile = get_profile_for_user(user)
    is_m = False
    if profile is not None:
        v = getattr(profile, "is_master", False)
        is_m = v if isinstance(v, bool) else _truthy(v)
        if not is_m:
            try:
                v2 = (profile.extra_data or {}).get("is_master")
                if v2 is not None:
                    is_m = v2 if isinstance(v2, bool) else _truthy(v2)
            except Exception:
                pass
    if not is_m and user_in_group(user, "master"):
        is_m = True
    return is_m

def role_flags(user):
    profile = get_profile_for_user(user)
    admin = reports = data_entry = accounting = False
    recovery_agent = auditor = manager = False

    if profile:
        admin          = _flag(profile, "is_admin")
        reports        = _flag(profile, "is_reports")
        data_entry     = _flag(profile, "is_data_entry")
        accounting     = _flag(profile, "is_accounting")
        recovery_agent = _flag(profile, "is_recovery_agent")
        auditor        = _flag(profile, "is_auditor")
        manager        = _flag(profile, "is_manager")

    admin          = admin or user_in_group(user, "admin")
    reports        = reports or user_in_group(user, "reports")
    data_entry     = data_entry or user_in_group(user, "dataentry")
    accounting     = accounting or user_in_group(user, "accounting")
    recovery_agent = recovery_agent or user_in_group(user, "recoveryagent")
    auditor        = auditor or user_in_group(user, "auditor")
    manager        = manager or user_in_group(user, "manager")

    return {
        "admin": admin,
        "reports": reports,
        "data_entry": data_entry,
        "accounting": accounting,
        "master": user_is_master(user),
        "profile": profile,
        "recovery_agent": recovery_agent,
        "auditor": auditor,
        "manager": manager,
    }

def can_user_delete_entity(user, entity_lc: str) -> bool:
    if user.is_superuser:
        return True

    rf = role_flags(user)
    profile = rf["profile"]
    ent = (entity_lc or "").lower()

    if not profile and not any([rf["admin"], rf["reports"], rf["data_entry"], rf["accounting"], rf["master"]]):
        return True

    if rf["admin"]:
        return True
    if rf["reports"] and _in_scope(ent, REPORT_MODELS_SET):
        return True
    if rf["data_entry"] and _in_scope(ent, DE_MODELS_SET):
        return True
    if rf["accounting"] and _in_scope(ent, ACC_MODELS_SET):
        return True
    if rf["master"]:
        return False
    return False

def _debug_delete(user, entity_lc, allowed):
    try:
        rf = role_flags(user)
        print(f"[DELETE_CHECK] user={user.username} entity={entity_lc} "
              f"roles={{admin:{rf['admin']}, reports:{rf['reports']}, data_entry:{rf['data_entry']}, "
              f"accounting:{rf['accounting']}, master:{rf['master']}}} allowed={allowed}")
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────
#  Lists
# ────────────────────────────────────────────────────────────────────
@login_required
def entity_list(request, entity):
    entity_lc = (entity or "").lower()
    if entity_lc in _FAUX_ENTITIES:
        return redirect("user_permissions")

    model = get_model_class(entity)
    if model is None:
        return JsonResponse({"success": False, "error": f'Model for entity "{entity}" not found.'}, status=404)

    # Show ALL by default to preserve your previous logic
    objects = model.objects.all()

    # Optional filters (opt-in via querystring)
    if request.GET.get("active_only") == "1":
        objects = _only_active(objects, model)
    if request.GET.get("hide_deleted") == "1":
        objects = _exclude_deleted(objects, model)

    grouped_objects = {"All Records": objects}
    try:
        column_fields = Column.objects.filter(module__iexact=entity_lc).order_by("order")
    except DatabaseError:
        column_fields = []

    user = request.user
    profile = get_profile_for_user(user)

    context = {
        "include_template": "companies/grid_list.html",
        "entity": entity,
        "pretty_entity": pretty_names.get(entity_lc, entity.replace("_", " ").title()),
        "grouped_objects": grouped_objects,
        "column_fields": column_fields,
        "profile": profile,
        "can_delete": True,
        "staff_info": getattr(user, "staff_info", None),
    }
    return render(request, "dashboard.html", context)



# ────────────────────────────────────────────────────────────────────
#  Create
# ────────────────────────────────────────────────────────────────────
@ajax_login_required_or_redirect
@require_POST
def entity_create(request, entity):
    entity_lc = (entity or "").lower()
    if entity_lc in _FAUX_ENTITIES:
        return JsonResponse({"success": False, "error": "Use the User Permissions UI page."}, status=400)

    form_class = get_form_class(entity)
    if not form_class:
        return JsonResponse({"success": False, "error": f'Form class for entity "{entity}" not found.'}, status=400)

    try:
        extra_fields = Column.objects.filter(module__iexact=entity_lc).order_by("order")
    except DatabaseError as e:
        extra_fields = []

    post_data = _normalize_dates_ddmmyyyy_to_iso(request.POST)
    form = form_class(post_data, request.FILES, extra_fields=extra_fields)

    if not form.is_valid():
        return JsonResponse({"success": False, "errors": form.errors})

    try:
        with transaction.atomic():
            instance = form.save(commit=False)

            # Staff: auto Empcode if missing
            if entity_lc == "staff" and not getattr(instance, "staffcode", None):
                model = get_model_class(entity)
                last = model.objects.order_by("-id").first()
                nxt = (last.id + 1) if last else 1
                instance.staffcode = f"STF{nxt:03d}"

            # Collect dynamic extra__* fields
            instance.extra_data = instance.extra_data or {}
            for k, v in request.POST.items():
                if k.startswith("extra__"):
                    instance.extra_data[k.replace("extra__", "")] = v

            # Persist NON-MODEL cleaned fields
            model_field_names = {f.name for f in instance._meta.get_fields()}
            for k, v in (form.cleaned_data or {}).items():
                if k not in model_field_names and v is not None:
                    instance.extra_data[k] = v

            # UserProfile: branch from staff when blank
            if entity_lc == "userprofile" and not getattr(instance, "branch_id", None):
                try:
                    if instance.staff and instance.staff.branch_id:
                        instance.branch_id = instance.staff.branch_id
                except Exception:
                    pass

            # Default active flags
            try:
                if hasattr(instance, "status") and not instance.status:
                    instance.status = "active"
            except Exception: pass
            try:
                if hasattr(instance, "is_active") and instance.is_active in (None, ""):
                    instance.is_active = True
            except Exception: pass
            try:
                if hasattr(instance, "active") and instance.active in (None, ""):
                    instance.active = 1
            except Exception: pass

            instance.save()
            form.save_m2m()

            if entity_lc == "userprofile":
                username = (form.cleaned_data.get("user") or "").strip()
                password = form.cleaned_data.get("password") or None
                try:
                    if getattr(instance, "is_reports", None) in (None, False, 0, "0"):
                        instance.is_reports = True
                        instance.save(update_fields=["is_reports"])
                except Exception: pass
                ensure_auth_user_for_profile(instance, username, password)

            return JsonResponse({"success": True})
    except DatabaseError as e:
        return _json_db_error(e, "Create failed")
    except IntegrityError as e:
        return JsonResponse({"success": False, "errors": {"__all__": [str(e)]}}, status=400)
    except ProtectedError:
        return JsonResponse({"success": False, "errors": {"__all__": ["Create blocked due to protected related objects."]}}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "errors": {"__all__": [str(e)]}}, status=400)


# ────────────────────────────────────────────────────────────────────
#  Get (modal)
# ────────────────────────────────────────────────────────────────────
@ajax_login_required_or_redirect
def entity_get(request, entity, pk=None):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    entity_lc = (entity or "").lower()

    if entity_lc in _FAUX_ENTITIES:
        html = "<div class='p-3'>Please use the <strong>User Permissions</strong> page for managing permissions.</div>"
        return JsonResponse({"success": True, "html": html})

    model = get_model_class(entity)
    if model is None:
        return JsonResponse({"success": False, "error": f'Model for entity "{entity}" not found.'}, status=404)

    form_class = get_form_class(entity)
    if not form_class:
        return JsonResponse({"success": False, "error": f'Form class for entity "{entity}" not found.'}, status=400)

    try:
        extra_fields = Column.objects.filter(module__iexact=entity_lc).order_by("order")
        missing_column_table = False
    except DatabaseError:
        extra_fields = []
        missing_column_table = True

    edit_mode = False
    object_id = ""
    if pk:
        obj = get_object_or_404(model, pk=pk)
        form = form_class(instance=obj, extra_fields=extra_fields)
        edit_mode = True
        object_id = pk
    else:
        obj = model()
        try:
            obj.code = obj._next_code() if hasattr(obj, "_next_code") else ""
        except Exception:
            pass
        if entity_lc == "userprofile":
            try:
                obj.is_reports = True
            except Exception:
                pass
        form = form_class(instance=obj, extra_fields=extra_fields)

    # Build branch map for UI only; DO NOT override form's staff queryset
    staff_branch_map_json = None
    if entity_lc == "userprofile" and "staff" in form.fields:
        try:
            smap = {}
            for s in Staff.objects.select_related("branch"):
                smap[str(s.id)] = {
                    "branch_id": getattr(s, "branch_id", None),
                    "branch_name": getattr(getattr(s, "branch", None), "name", "") or "",
                }
            staff_branch_map_json = json.dumps(smap, separators=(",", ":"))
        except Exception:
            staff_branch_map_json = json.dumps({}, separators=(",", ":"))

    has_password = any(
        getattr(getattr(f, "widget", None), "input_type", "") == "password"
        for f in form.fields.values()
    )

    try:
        html = render_to_string(
            "companies/modal_form.html",
            {
                "form": form,
                "entity": entity,
                "edit_mode": edit_mode,
                "object_id": object_id,
                "section_map": get_section_map(entity),
                "extra_fields": extra_fields,
                "staff_branch_map_json": staff_branch_map_json,
            },
            request=request,
        )
        payload = {"success": True, "html": html}
        if missing_column_table:
            payload["warning"] = "Columns config table not found; rendering form without extra fields."
        if has_password:
            payload["password_fields_present"] = True
        return JsonResponse(payload)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Render error: {e}"}, status=400)




# alias for older JS
@login_required
@require_GET
def entity_form(request, entity):
    return entity_get(request, entity)


# ────────────────────────────────────────────────────────────────────
#  Update
# ────────────────────────────────────────────────────────────────────
@ajax_login_required_or_redirect
@require_POST
def entity_update(request, entity, pk):
    entity_lc = (entity or "").lower()
    if entity_lc in _FAUX_ENTITIES:
        return JsonResponse({"success": False, "error": "Use the User Permissions UI page."}, status=400)

    model = get_model_class(entity)
    if model is None:
        return JsonResponse({"success": False, "error": f'Model for entity "{entity}" not found.'}, status=404)

    obj = get_object_or_404(model, pk=pk)
    form_class = get_form_class(entity)
    if not form_class:
        return JsonResponse({"success": False, "error": f'Form class for entity "{entity}" not found.'}, status=400)

    try:
        extra_fields = Column.objects.filter(module__iexact=entity_lc).order_by("order")
    except DatabaseError:
        extra_fields = []

    post_data = _normalize_dates_ddmmyyyy_to_iso(request.POST)
    form = form_class(post_data, request.FILES, instance=obj, extra_fields=extra_fields)

    if not form.is_valid():
        return JsonResponse({"success": False, "errors": form.errors})

    try:
        with transaction.atomic():
            instance = form.save(commit=False)

            instance.extra_data = instance.extra_data or {}
            for k, v in request.POST.items():
                if k.startswith("extra__"):
                    instance.extra_data[k.replace("extra__", "")] = v

            model_field_names = {f.name for f in instance._meta.get_fields()}
            for k, v in (form.cleaned_data or {}).items():
                if k not in model_field_names and v is not None:
                    instance.extra_data[k] = v

            if entity_lc == "userprofile" and not getattr(instance, "branch_id", None):
                try:
                    if instance.staff and instance.staff.branch_id:
                        instance.branch_id = instance.staff.branch_id
                except Exception:
                    pass

            try:
                if hasattr(instance, "status") and not instance.status:
                    instance.status = "active"
            except Exception: pass
            try:
                if hasattr(instance, "is_active") and instance.is_active in (None, ""):
                    instance.is_active = True
            except Exception: pass
            try:
                if hasattr(instance, "active") and instance.active in (None, ""):
                    instance.active = 1
            except Exception: pass

            instance.save()
            form.save_m2m()

            if entity_lc == "userprofile":
                username = (form.cleaned_data.get("user") or "").strip()
                password = form.cleaned_data.get("password") or None
                ensure_auth_user_for_profile(instance, username, password)

            return JsonResponse({"success": True})
    except DatabaseError as e:
        return _json_db_error(e, "Update failed")
    except IntegrityError as e:
        return JsonResponse({"success": False, "errors": {"__all__": [str(e)]}}, status=400)
    except ProtectedError:
        return JsonResponse({"success": False, "errors": {"__all__": ["Update blocked due to protected related objects."]}}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "errors": {"__all__": [str(e)]}}, status=400)


# ────────────────────────────────────────────────────────────────────
#  Delete  → soft-delete first, hard-delete fallback
# ────────────────────────────────────────────────────────────────────
@ajax_login_required_or_redirect
@require_POST
def entity_delete(request, entity, pk):
    import re
    entity_lc = (entity or "").lower()

    if entity_lc in _FAUX_ENTITIES:
        return JsonResponse({"success": False, "error": "This is a settings page with no table. Use the User Permissions UI."}, status=400)

    model = get_model_class(entity)
    if model is None:
        return JsonResponse({"success": False, "error": f'Model for entity "{entity}" not found.'}, status=404)

    allowed = can_user_delete_entity(request.user, entity_lc)
    _debug_delete(request.user, entity_lc, allowed)
    if not allowed:
        if user_is_master(request.user):
            return JsonResponse({"success": False, "error": "Delete is not allowed for Master role for this item."}, status=403)
        return JsonResponse({"success": False, "error": "You don't have permission to delete this item."}, status=403)

    obj = get_object_or_404(model, pk=pk)

    # Soft-delete paths: status→inactive, else extra_data.deleted=True
    try:
        with transaction.atomic():
            if hasattr(obj, "status"):
                obj.status = "inactive"
                obj.save(update_fields=["status"])
                return JsonResponse({"success": True, "soft_deleted": True})

            if hasattr(obj, "extra_data"):
                extra = (obj.extra_data or {}).copy()
                extra["deleted"] = True
                obj.extra_data = extra
                obj.save(update_fields=["extra_data"])
                return JsonResponse({"success": True, "soft_deleted": True})

            # No soft-delete fields → attempt hard delete
            obj.delete()
            return JsonResponse({"success": True, "hard_deleted": True})

    except ProtectedError:
        return JsonResponse({"success": False, "error": "Delete blocked: this item is referenced by other records."}, status=400)

    except DatabaseError as e:
        # Missing table handling (your requirement text)
        msg = str(e)
        missing_tbl = re.search(r"(no such table|does not exist|UndefinedTable|relation .* does not exist|table .* not present)", msg, re.I)
        if missing_tbl:
            # fallback: mark as deleted in extra_data if possible
            try:
                if hasattr(obj, "extra_data"):
                    extra = (obj.extra_data or {}).copy()
                    extra["deleted"] = True
                    obj.extra_data = extra
                    obj.save(update_fields=["extra_data"])
                    # User Profile should show the hint string you asked for
                    if entity_lc in {"userprofile", "appointment", "salarystatement"}:
                        return JsonResponse({"success": True, "soft_deleted": True, "note": "Table missing. Run migrations, then retry delete."})
                    return JsonResponse({"success": True, "soft_deleted": True})
            except Exception:
                pass
            if entity_lc in {"userprofile", "appointment", "salarystatement"}:
                return JsonResponse({"success": False, "error": "Table missing. Run migrations, then retry delete."}, status=400)
            return JsonResponse({"success": False, "error": "Delete failed."}, status=400)

        return JsonResponse({"success": False, "error": f"Delete failed: {msg}"}, status=400)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


# ────────────────────────────────────────────────────────────────────
#  Code generator
# ────────────────────────────────────────────────────────────────────
@ajax_login_required_or_redirect
@require_POST
def next_code_view(request):
    entity = request.POST.get("entity")
    model = get_model_class(entity)
    if model is None:
        return JsonResponse({"success": False, "error": f'Model for entity "{entity}" not found.'}, status=404)

    prefix = request.POST.get("prefix", "")
    count = model.objects.count() + 1
    code = f"{prefix}{str(count).zfill(3)}"
    return JsonResponse({"code": code})


# ────────────────────────────────────────────────────────────────────
#  Permissions UI
# ────────────────────────────────────────────────────────────────────
@login_required
def permission_group(request):
    groups = AuthGroup.objects.all()
    permissions = Permission.objects.all()
    return render(request, "companies/permission_group.html", {"groups": groups, "permissions": permissions})


# ────────────────────────────────────────────────────────────────────
#  Aadhaar type-ahead
# ────────────────────────────────────────────────────────────────────
@require_GET
@login_required
def search_aadhar(request):
    q = request.GET.get("q", "").replace(" ", "")
    data = []
    if q:
        clients = Client.objects.filter(aadhar__startswith=q)[:10]
        data = [{"id": c.id, "name": c.name, "aadhar": c.aadhar} for c in clients]
    return JsonResponse(data, safe=False)

@require_GET
@login_required
def search_client_aadhar(request):
    return search_aadhar(request)


# ────────────────────────────────────────────────────────────────────
#  Feature endpoints
# ────────────────────────────────────────────────────────────────────
@require_POST
@login_required
def credit_bureau_pull(request):
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        data = {}

    client = CreditBureauClient()
    res = client.pull_score(
        pan=data.get("pan", ""),
        aadhar=data.get("aadhar", ""),
        name=data.get("name", ""),
        dob=data.get("dob", ""),
    )
    return JsonResponse({
        "ok": res.ok,
        "provider": res.provider,
        "score": res.score,
        "message": res.message,
        "raw": res.raw,
        "enabled": client.enabled(),
        "feature_on": feature_enabled("CREDIT_BUREAU"),
    })

@require_POST
@login_required
def credit_bureau_pull_api(request):
    return credit_bureau_pull(request)


@login_required
def npa_dashboard(request):
    if not feature_enabled("NPA_DASHBOARD"):
        return render(request, "companies/npa_dashboard.html", {"enabled": False, "buckets": {}})

    buckets = {"Current": 0, "1-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    try:
        with connection.cursor() as cur:
            try:
                cur.execute("SELECT dpd FROM loan_dpd_view LIMIT 1")
                has_view = True
            except Exception:
                has_view = False

        if has_view:
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT
                      SUM(CASE WHEN dpd<=0 THEN 1 ELSE 0 END) AS b0,
                      SUM(CASE WHEN dpd BETWEEN 1 AND 30 THEN 1 ELSE 0 END) AS b1,
                      SUM(CASE WHEN dpd BETWEEN 31 AND 60 THEN 1 ELSE 0 END) AS b2,
                      SUM(CASE WHEN dpd BETWEEN 61 AND 90 THEN 1 ELSE 0 END) AS b3,
                      SUM(CASE WHEN dpd>90 THEN 1 ELSE 0 END) AS b4
                    FROM loan_dpd_view
                """)
                row = cur.fetchone() or [0, 0, 0, 0, 0]
                buckets = {"Current": row[0], "1-30": row[1], "31-60": row[2], "61-90": row[3], "90+": row[4]}
    except Exception:
        pass

    return render(request, "companies/npa_dashboard.html", {"enabled": True, "buckets": buckets})
