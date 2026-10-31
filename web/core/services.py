"""Regras de negócio do PsiAgenda (camada de regras da arquitetura)."""
import math
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Pagamento, Sessao, TentativaLogin

# Nome da restrição criada no PostgreSQL pela migração 0005 (última barreira contra sobreposição).
RESTRICAO_SOBREPOSICAO = "sessao_sem_sobreposicao"

# Bloqueio de login (RNF01): 5 falhas seguidas bloqueiam o usuário por 15 minutos.
MAX_FALHAS_LOGIN = 5
TEMPO_BLOQUEIO = timedelta(minutes=15)


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
    try:
        # Savepoint: se o banco recusar, a transação externa continua utilizável.
        with transaction.atomic():
            sessao.save()
    except IntegrityError as erro:
        # Duas requisições simultâneas passaram pela verificação acima; o PostgreSQL
        # barrou a segunda. Mostra a mesma mensagem amigável de horário ocupado.
        conflitos = sessao.conflitos() if RESTRICAO_SOBREPOSICAO in str(erro) else []
        if not conflitos:
            raise
        raise HorarioOcupado(conflitos[0]) from erro
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


def _chave_login(username):
    return (username or "").strip().lower()[:150]


def _minutos_restantes(tentativa):
    if not tentativa or not tentativa.bloqueado_ate:
        return 0
    restante = (tentativa.bloqueado_ate - timezone.now()).total_seconds()
    return math.ceil(restante / 60) if restante > 0 else 0


def minutos_de_bloqueio(username):
    """Minutos que faltam para liberar o login deste usuário (0 = liberado)."""
    return _minutos_restantes(TentativaLogin.objects.filter(username=_chave_login(username)).first())


@transaction.atomic
def registrar_falha_login(username):
    """Conta mais uma falha; na 5ª seguida, bloqueia por 15 minutos. Devolve os minutos de bloqueio."""
    tentativa, _ = TentativaLogin.objects.select_for_update().get_or_create(username=_chave_login(username))
    agora = timezone.now()
    if tentativa.bloqueado_ate and tentativa.bloqueado_ate <= agora:
        # Bloqueio anterior já expirou: recomeça a contagem.
        tentativa.falhas, tentativa.bloqueado_ate = 0, None
    tentativa.falhas += 1
    if tentativa.falhas >= MAX_FALHAS_LOGIN:
        tentativa.bloqueado_ate = agora + TEMPO_BLOQUEIO
    tentativa.save()
    return _minutos_restantes(tentativa)


def limpar_falhas_login(username):
    """Login bem-sucedido zera o contador."""
    TentativaLogin.objects.filter(username=_chave_login(username)).delete()
