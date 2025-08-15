from django.contrib import admin
from .models import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "get_username",
        "branch",
        "is_admin",
        "is_master",
        "is_data_entry",
        "is_reports",
        "is_accounting",
        "status",
    )
    search_fields = ("user__username", "extra_data__auth_username", "branch__name")
    list_filter = ("is_admin", "is_master", "is_data_entry", "is_reports", "is_accounting", "status", "branch")
    list_select_related = ("user", "branch")

    def get_username(self, obj):
        """
        Safe username for list display:
        - Prefer FK user.username if present
        - Else read the value we store in extra_data.auth_username
        - Else return empty string to avoid AttributeError
        """
        u = getattr(obj, "user", None)
        if u and getattr(u, "username", None):
            return u.username
        extra = getattr(obj, "extra_data", None) or {}
        return extra.get("auth_username", "")  # gracefully handle None
    get_username.short_description = "Username"
    get_username.admin_order_field = "user__username"
