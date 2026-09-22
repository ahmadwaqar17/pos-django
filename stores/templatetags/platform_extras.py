from django import template

register = template.Library()


@register.filter
def mod(value, arg):
    """``forloop.counter0|mod:4`` -> value % arg (for rotating avatar classes)."""
    try:
        return int(value) % int(arg)
    except (TypeError, ValueError):
        return 0
