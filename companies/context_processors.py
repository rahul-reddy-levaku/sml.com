# companies/context_processors.py

def user_header_info(request):
    if not request.user.is_authenticated:
        return {}

    # Display name: prefer full name, fallback to username
    name = request.user.get_full_name() or request.user.username

    # Try to get branch from userprofile first, then fallback to staff_info
    branch_name = ""
    profile = getattr(request.user, "userprofile", None)
    if profile and getattr(profile, "branch", None):
        branch = profile.branch
        branch_name = getattr(branch, "name", str(branch))
    else:
        staff_info = getattr(request.user, "staff_info", None)
        if staff_info and getattr(staff_info, "branch", None):
            branch = staff_info.branch
            branch_name = getattr(branch, "name", str(branch))

    # Role label for clarity (optional)
    role_label = None
    if request.user.is_superuser:
        role_label = "Superuser"
    elif request.user.is_staff:
        role_label = "Staff"

    return {
        "header_user_display_name": name,
        "header_branch_name": branch_name,
        "header_role_label": role_label,
    }
# companies/context_processors.py
from django.conf import settings

def sml_features(request):
    """
    Make feature flags available in all templates as `SML_FEATURES`.
    Safe if the setting is missing (returns empty dict).
    """
    return {"SML_FEATURES": getattr(settings, "SML_FEATURES", {})}
