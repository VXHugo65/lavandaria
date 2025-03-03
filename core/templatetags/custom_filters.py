from django import template

register = template.Library()


@register.filter(name='ljust')
def ljust(value, length):
    return str(value).ljust(length)
