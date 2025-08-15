# companies/templatetags/custom_tags.py
from django import template
from datetime import date, datetime
from collections import defaultdict
import re

register = template.Library()

# ======= Safe Attribute Getter ======= #
@register.filter
def attr(obj, attr_name):
    if obj is None or attr_name is None:
        return ''
    try:
        return getattr(obj, attr_name, '')
    except AttributeError:
        return ''

@register.filter(name='get_attr')
def get_attr(obj, attr_name):
    return attr(obj, attr_name)

# ======= Classname for Type Checking ======= #
@register.filter
def classname(obj):
    return obj.__class__.__name__.lower() if obj else ''

# ======= Safe Dict/Object Getter ======= #
@register.filter
def get_item(container, key):
    if hasattr(container, 'get'):
        return container.get(key, '')
    try:
        return getattr(container, key)
    except AttributeError:
        return ''

# ======= Dynamic Form Field Lookup ======= #
@register.filter
def get_field(form, name):
    try:
        return form[name]
    except Exception:
        return ''

# ======= Flatten any iterable-of-iterables one level ======= #
@register.filter
def flatten(value):
    try:
        result = []
        for sub in value:
            if hasattr(sub, '__iter__') and not isinstance(sub, (str, bytes)):
                result.extend(sub)
            else:
                result.append(sub)
        return result
    except Exception:
        return []

# ======= Date Formatting (dd/mm/yyyy) ======= #
@register.filter
def format_ddmmyyyy(value):
    """
    - If value is a date/datetime: format dd/mm/YYYY
    - If value is an ISO-like string 'YYYY-MM-DD' (or 'YYYY/MM/DD'): convert to dd/mm/YYYY
    - Else: return as-is
    """
    if isinstance(value, (date, datetime)):
        return value.strftime('%d/%m/%Y')
    if isinstance(value, str):
        s = value.strip()
        # Normalize common separators
        if re.fullmatch(r'\d{4}[-/]\d{2}[-/]\d{2}', s):
            parts = re.split(r'[-/]', s)
            yyyy, mm, dd = parts[0], parts[1], parts[2]
            return f"{dd}/{mm}/{yyyy}"
    return value

# ======= Check for DateField in Form ======= #
@register.filter
def is_datefield(field):
    try:
        return field.field.__class__.__name__ == 'DateField'
    except Exception:
        return False

# ======= Add Class to Form Fields ======= #
@register.filter
def add_class(field, css_class):
    if hasattr(field.field, 'widget') and hasattr(field.field.widget, 'attrs'):
        existing = field.field.widget.attrs.get('class', '')
        field.field.widget.attrs['class'] = f"{existing} {css_class}".strip()
    return field

# ======= Add/Set arbitrary attribute on a Form Field widget ======= #
# Usage:
#   {{ field|add_attr:"accept=image/*"|add_attr:"capture=environment" }}
#   {{ field|add_attr:"placeholder=Enter value" }}
#   {{ field|add_attr:"required" }}  -> boolean-like attribute (sets to the same token)
@register.filter(name='add_attr')
def add_attr(field, arg):
    if not hasattr(field, 'field') or not hasattr(field.field, 'widget'):
        return field
    if not arg:
        return field

    s = str(arg)
    if '=' in s:
        key, val = s.split('=', 1)
        key, val = key.strip(), val.strip()
    else:
        key, val = s.strip(), s.strip()  # boolean-like attribute

    attrs = field.field.widget.attrs
    if key == 'class':
        existing = attrs.get('class', '').strip()
        attrs['class'] = f"{existing} {val}".strip() if existing else val
    else:
        attrs[key] = val
    return field

# ======= Field Existence Check ======= #
@register.filter
def has_field(form, field_name):
    return field_name in getattr(form, 'fields', {})

# ======= Group Permissions by Category ======= #
@register.filter
def group_permissions(choices):
    grouped = defaultdict(list)
    for perm_id, name in choices:
        lname = name.lower()
        if 'master' in lname:
            grouped['Master'].append((perm_id, name))
        elif 'entry' in lname:
            grouped['Data Entry'].append((perm_id, name))
        elif 'report' in lname:
            grouped['Reports'].append((perm_id, name))
        else:
            grouped['Other'].append((perm_id, name))
    return grouped.items()

# ======= Split String ======= #
@register.filter
def split(value, delimiter):
    if value and delimiter:
        return value.split(delimiter)
    return []

# ======= Replace Underscores with Spaces ======= #
@register.filter
def replace_underscore(value):
    return str(value).replace('_', ' ').capitalize()

# ======= Check for File Extension ======= #
@register.filter
def is_file_path(value):
    if not isinstance(value, str):
        return False
    return any(value.lower().endswith(ext) for ext in [
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.pdf',
        '.doc', '.docx', '.xls', '.xlsx'
    ])

# ======= Check Value in Comma-Separated List (case-insensitive, trims) ======= #
@register.filter
def in_list(value, arg):
    val = str(value).strip().lower()
    items = [item.strip().lower() for item in (arg or '').split(',')]
    return val in items

# ======= Flatten Section Map (dict or list of pairs) ======= #
@register.filter
def flatten_list(section_map):
    """
    Accepts either:
      - dict-like .items() => iterate values (which are iterables)
      - iterable of (key, values) pairs
    Returns a single flat list of field names.
    """
    out = []
    if hasattr(section_map, 'items'):
        iterable = section_map.items()
    else:
        iterable = section_map or []
    try:
        for _, fields in iterable:
            if hasattr(fields, '__iter__') and not isinstance(fields, (str, bytes)):
                out.extend(fields)
            else:
                out.append(fields)
    except Exception:
        pass
    return out

# ======= Field Label Overrides ======= #
@register.filter
def label_override(field_name):
    custom_labels = {
        'loanapproval': 'Loan Approval / Credit Verification',
        'userprofile': 'User Profile',
        'staffregistration': 'Staff Registration',
        'clientjoining': 'Client Joining',
        'businesssetting': 'Business Setting',
        'productsmanagement': 'Products Management',
        'fieldreport': 'Field Report',
        'loanapplication': 'Loan Application',
        'rolemanagement': 'Role Management',
        'fieldschedule': 'Field Schedule',
        'weeklyreport': 'Weekly Report',
        'monthlyreport': 'Monthly Report',
    }
    if not field_name:
        return ''
    key = str(field_name).lower()
    if key in custom_labels:
        return custom_labels[key]
    spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', str(field_name)).replace('_', ' ')
    return spaced.title()

# ======= Get All Fields from Model Object (skip id/raw_csv_data) ======= #
@register.filter
def get_fields(obj):
    try:
        return [f for f in obj._meta.fields if f.name not in ('id', 'raw_csv_data')]
    except Exception:
        return []

# ======= Pretty formatter (underscores → spaces, title case) ======= #
@register.filter
def pretty(value):
    if value is None:
        return ''
    return str(value).replace('_', ' ').title()

# ======= Pretty Name Mapping (for sidebar and headings) ======= #
@register.filter
def pretty_name(model_name):
    pretty_names = {
        "loanapplication": "Loan Application",
        "clientjoiningform": "Client Joining Form",
        "userprofile": "User Profile",
        "staff": "Staff Registration",
        "role": "Role Management",
        "product": "Products Management",
        "column": "Custom Fields",
        "businesssetting": "Business Setting Rules",
        "fieldschedule": "Field Schedule",
        "fieldreport": "Field Report",
        "accounthead": "Account Head",
        "voucher": "Voucher Entry",
        "posting": "Ledger Posting",
        "recoveryposting": "Recovery Posting",
        "loanapproval": "Loan Approval",
        "disbursement": "Loan Disbursement",
        "cadre": "Cadre",
        "weeklyreport": "Weekly Report",
        "monthlyreport": "Monthly Report",
    }
    key = str(model_name).lower()
    return pretty_names.get(key, str(model_name).replace('_', ' ').title())
