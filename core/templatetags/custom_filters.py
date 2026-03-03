from django import template

register = template.Library()

# ===== FILTROS DE FORMATAÇÃO =====

@register.filter
def currency_mzn(value):
    """
    Formata valor em Meticais (Mts)
    Exemplo: 1500.50 -> "1.500,50 Mts"
    """
    try:
        valor_float = float(value)
        # Formata com 2 casas decimais e ajusta separadores
        valor_formatado = f"{valor_float:,.2f}"
        valor_formatado = valor_formatado.replace(",", "X")
        valor_formatado = valor_formatado.replace(".", ",")
        valor_formatado = valor_formatado.replace("X", ".")
        return f"{valor_formatado} Mts"
    except (ValueError, TypeError, AttributeError):
        return "0,00 Mts"

# ===== FILTROS DE OPERAÇÕES MATEMÁTICAS =====

@register.filter
def mul(value, arg):
    """Multiplica valor por argumento: {{ valor|mul:2 }}"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def div(value, arg):
    """Divide valor por argumento: {{ valor|div:100 }}"""
    try:
        arg_float = float(arg)
        if arg_float == 0:
            return 0
        return float(value) / arg_float
    except (ValueError, TypeError):
        return 0

@register.filter
def sub(value, arg):
    """Subtrai argumento do valor: {{ valor|sub:100 }}"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def add(value, arg):
    """Soma argumento ao valor: {{ valor|add:100 }}"""
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return 0

# ===== FILTROS DE AGREGAÇÃO =====

@register.filter
def sum_values(queryset, field_name):
    """Soma um campo específico em um queryset"""
    try:
        return sum(getattr(item, field_name, 0) for item in queryset)
    except:
        return 0

@register.filter
def sum_pagos(queryset, field_name):
    """Soma valores apenas dos pedidos pagos"""
    try:
        return sum(getattr(item, field_name, 0) for item in queryset if item.pago)
    except:
        return 0

@register.filter
def sum_nao_pagos(queryset, field_name):
    """Soma valores apenas dos pedidos não pagos"""
    try:
        return sum(getattr(item, field_name, 0) for item in queryset if not item.pago)
    except:
        return 0

# ===== FILTROS DE FORMATAÇÃO DE TEXTO =====

@register.filter
def ljust(value, length):
    """Justifica texto à esquerda com tamanho específico"""
    try:
        return str(value).ljust(length)
    except:
        return str(value)

@register.filter
def rjust(value, length):
    """Justifica texto à direita com tamanho específico"""
    try:
        return str(value).rjust(length)
    except:
        return str(value)

# ===== FILTROS DE PORCENTAGEM =====

@register.filter
def percentage(value, total):
    """Calcula porcentagem: {{ valor|percentage:total }}"""
    try:
        total_float = float(total)
        if total_float == 0:
            return "0%"
        percent = (float(value) / total_float) * 100
        return f"{percent:.1f}%"
    except (ValueError, TypeError):
        return "0%"

# ===== FILTROS DE DATA =====

@register.filter
def date_br(value):
    """Formata data para padrão brasileiro: DD/MM/AAAA"""
    if not value:
        return ""
    try:
        return value.strftime("%d/%m/%Y")
    except AttributeError:
        return str(value)

@register.filter
def datetime_br(value):
    """Formata data e hora: DD/MM/AAAA HH:MM"""
    if not value:
        return ""
    try:
        return value.strftime("%d/%m/%Y %H:%M")
    except AttributeError:
        return str(value)
