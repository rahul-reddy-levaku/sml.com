# companies/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # AUTH & CORE
    path("",                    views.home_view,       name="home"),
    path("login/",              views.login_view,      name="login"),
    path("logout/",             views.logout_view,     name="logout"),
    path("dashboard/",          views.dashboard_view,  name="dashboard"),
    path("switch-account/",     views.switch_account,  name="switch_account"),

    # AJAX HELPERS
    path("next_code/",                views.next_code_view,      name="next_code"),
    path("search/client/aadhar/",     views.search_aadhar,       name="search_aadhar"),
    path("permission-group/",         views.permission_group,    name="permission_group"),
    path("user-permissions/",         views.entity_list, {"entity": "userpermission"}, name="user_permissions"),  # list + modal add

    # FEATURES
    path("api/credit-bureau/pull/",   views.credit_bureau_pull,  name="credit_bureau_pull"),
    path("npa/",                      views.npa_dashboard,       name="npa_dashboard"),

    # SHORTCUT MENUS
    path("hrpm/",                      views.entity_list, {"entity": "staff"},            name="hrpm_home"),
    path("hrpm/staff/",                views.entity_list, {"entity": "staff"},            name="hrpm_staff"),
    path("hrpm/appointment/",          views.entity_list, {"entity": "appointment"},      name="hrpm_appointment"),
    path("hrpm/salary-statement/",     views.entity_list, {"entity": "salarystatement"},  name="hrpm_salary_statement"),

    # GENERIC CRUD
    path("<str:entity>/get/",               views.entity_get,    name="entity_get_new"),
    path("<str:entity>/get/<int:pk>/",      views.entity_get,    name="entity_get"),
    path("<str:entity>/create/",            views.entity_create, name="entity_create"),
    path("<str:entity>/update/<int:pk>/",   views.entity_update, name="entity_update"),
    path("<str:entity>/delete/<int:pk>/",   views.entity_delete, name="entity_delete"),

    # keep LAST
    path("<str:entity>/",                   views.entity_list,   name="entity_list"),
]
