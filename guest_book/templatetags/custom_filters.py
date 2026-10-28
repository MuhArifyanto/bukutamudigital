from django import template
from django.utils import timezone
import datetime

register = template.Library()

@register.filter
def smart_date(value):
    """
    Returns 'HARI INI', 'KEMARIN', or 'DD MMM YYYY' based on the date.
    """
    if not value:
        return ""
    
    if isinstance(value, datetime.datetime):
        date_val = value.date()
        # Convert timezone-aware to local or just use naive date
        if timezone.is_aware(value):
            date_val = timezone.localtime(value).date()
    else:
        date_val = value
        
    now = timezone.localtime(timezone.now()).date()
    delta = now - date_val
    
    if delta.days == 0:
        return "HARI INI"
    elif delta.days == 1:
        return "KEMARIN"
    else:
        # Example: 25 MEI 2026
        months = ["JAN", "FEB", "MAR", "APR", "MEI", "JUN", "JUL", "AGU", "SEP", "OKT", "NOV", "DES"]
        return f"{date_val.day} {months[date_val.month - 1]} {date_val.year}"


@register.filter
def role_display(role):
    """
    Get display name for pegawai role
    """
    ROLE_DISPLAY = {
        'staff': 'Staff',
        'supervisor': 'Supervisor',
        'manager': 'Manager',
        'admin': 'Admin',
    }
    return ROLE_DISPLAY.get(role, role.title() if role else '-')


@register.filter
def role_badge_class(role):
    """
    Get CSS badge class for pegawai role
    """
    ROLE_BADGE_CLASS = {
        'staff': 'badge-secondary',
        'supervisor': 'badge-info',
        'manager': 'badge-primary',
        'admin': 'badge-danger',
    }
    return ROLE_BADGE_CLASS.get(role, 'badge-secondary')


@register.filter
def has_role_permission(pegawai, required_role):
    """
    Check if pegawai has minimum required role level
    
    Usage in template:
        {% if request.pegawai|has_role_permission:'supervisor' %}
            <!-- Show supervisor+ features -->
        {% endif %}
    """
    if not pegawai or not hasattr(pegawai, 'role'):
        return False
        
    ROLE_HIERARCHY = {
        'staff': 1,
        'supervisor': 2,
        'manager': 3,
        'admin': 4,
    }
    
    current_level = ROLE_HIERARCHY.get(pegawai.role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    
    return current_level >= required_level

@register.filter
def replace(value, arg):
    """
    Replacing filter
    Use `{{ "aaa"|replace:"a|b" }}`
    """
    if len(arg.split('|')) != 2:
        return value
    what, to = arg.split('|')
    return str(value).replace(what, to)
