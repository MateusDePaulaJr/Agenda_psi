from django import template

register = template.Library()


@register.filter
def iniciais(nome):
    """'Beatriz R.' -> 'BR' (usado no avatar da agenda)."""
    partes = [p for p in str(nome).replace(".", " ").split() if p]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


@register.simple_tag
def avatar_perfil(iniciais, cor, nome, tamanho="m"):
    """Círculo com as iniciais na cor escolhida no perfil (sem upload de foto).

    Leitores de tela ouvem "Avatar de <nome>"; as letras em si ficam ocultas.
    """
    from django.utils.html import format_html

    from core.models import CORES_AVATAR

    cor = cor if cor in dict(CORES_AVATAR) else "indigo"
    return format_html(
        '<span class="pa-perfil-avatar pa-perfil-avatar-{} pa-cor-{}" role="img" aria-label="Avatar de {}">'
        '<span aria-hidden="true">{}</span></span>',
        tamanho, cor, nome, iniciais,
    )


@register.filter
def moeda(valor):
    """Decimal('1234.5') -> 'R$ 1.234,50' (formato brasileiro)."""
    from core.services import formatar_moeda

    return formatar_moeda(valor)
