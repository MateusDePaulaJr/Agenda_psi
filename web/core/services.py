"""Regras de negócio do PsiAgenda (camada de regras da arquitetura)."""
from django.db import transaction
from django.utils import timezone

from .models import Pagamento, Sessao


class HorarioOcupado(Exception):
    def __init__(self, conflito):
        self.conflito = conflito
        super().__init__(
            f"Este horário já está ocupado por {conflito.paciente.nome} "
            f"({timezone.localtime(conflito.inicio):%H:%M}–{timezone.localtime(conflito.fim):%H:%M}). "
            "Escolha outro horário ou outro dia."
        )


@transaction.atomic
def agendar_sessao(paciente, inicio, duracao_minutos=50, observacao=""):
    """Cria a sessão e o pagamento 'a receber' juntos, ou nada (RF03, RF04, RF05)."""
    sessao = Sessao(paciente=paciente, inicio=inicio, duracao_minutos=duracao_minutos, observacao=observacao)
    conflitos = sessao.conflitos()
    if conflitos:
        raise HorarioOcupado(conflitos[0])
    sessao.save()
    Pagamento.objects.create(sessao=sessao, valor=paciente.valor_sessao)
    return sessao


def horarios_livres(usuario, dia, duracao=50, inicio_expediente=8, fim_expediente=20):
    """Sugere horários cheios livres no dia (usado no alerta de conflito)."""
    from datetime import datetime, timedelta

    tz = timezone.get_current_timezone()
    livres = []
    for hora in range(inicio_expediente, fim_expediente):
        inicio = timezone.make_aware(datetime.combine(dia, datetime.min.time()) + timedelta(hours=hora), tz)
        if inicio <= timezone.now():
            continue
        fim = inicio + timedelta(minutes=duracao)
        ocupados = Sessao.objects.filter(
            paciente__usuario=usuario, status__in=Sessao.BLOQUEIAM_HORARIO,
            inicio__lt=fim, inicio__gt=inicio - timedelta(hours=12),
        )
        if not any(s.fim > inicio for s in ocupados):
            livres.append(inicio)
    return livres
