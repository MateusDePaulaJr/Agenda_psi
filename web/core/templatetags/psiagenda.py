from django import template

register = template.Library()


@register.filter
def iniciais(nome):
    """'Beatriz R.' -> 'BR' (usado no avatar da agenda)."""
    partes = [p for p in str(nome).replace(".", " ").split() if p]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


@register.filter
def moeda(valor):
    """Decimal('1234.5') -> 'R$ 1.234,50' (formato brasileiro)."""
    from core.services import formatar_moeda

    return formatar_moeda(valor)
