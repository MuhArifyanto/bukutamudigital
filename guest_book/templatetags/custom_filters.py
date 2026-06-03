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
