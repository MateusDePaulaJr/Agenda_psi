"""Regras de negócio do PsiAgenda (camada de regras da arquitetura)."""
import math
import uuid
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


class SerieComConflito(HorarioOcupado):
    """Uma ou mais datas de uma série recorrente já estão ocupadas; nada foi criado.

    `conflitos` é uma lista de pares (início pretendido, sessão que ocupa o horário).
    """

    def __init__(self, conflitos):
        self.conflitos = conflitos
        self.conflito = conflitos[0][1]
        n = len(conflitos)
        datas = ", ".join(f"{timezone.localtime(inicio):%d/%m}" for inicio, _ in conflitos)
        Exception.__init__(
            self,
            f"{n} data{'s' if n != 1 else ''} da série já {'estão' if n != 1 else 'está'} "
            f"ocupada{'s' if n != 1 else ''} ({datas}). Nenhuma sessão foi agendada.",
        )


# Repetições possíveis na tela "Nova sessão": código -> (dias entre as sessões, rótulo).
REPETICOES = {"semanal": (7, "semanal"), "quinzenal": (14, "quinzenal")}
MIN_SESSOES_SERIE, MAX_SESSOES_SERIE = 2, 24


@transaction.atomic
def agendar_sessao(paciente, inicio, duracao_minutos=50, observacao="", serie=None):
    """Cria a sessão e o pagamento 'a receber' juntos, ou nada (RF03, RF04, RF05)."""
    sessao = Sessao(
        paciente=paciente, inicio=inicio, duracao_minutos=duracao_minutos, observacao=observacao, serie=serie
    )
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


def datas_da_serie(inicio, intervalo_dias, quantidade):
    """Inícios das sessões da série, mantendo o mesmo horário de relógio local."""
    tz = timezone.get_current_timezone()
    local = timezone.localtime(inicio, tz).replace(tzinfo=None)
    return [timezone.make_aware(local + timedelta(days=i * intervalo_dias), tz) for i in range(quantidade)]


def agendar_serie(paciente, inicio, duracao_minutos, observacao, intervalo_dias, quantidade):
    """Agenda sessões recorrentes: todas ou nenhuma.

    Primeiro verifica todas as datas com a mesma regra de conflito de uma sessão
    avulsa; se alguma estiver ocupada, levanta SerieComConflito listando cada uma
    e nada é criado. Senão cria cada sessão com agendar_sessao (sessão + pagamento
    'a receber') dentro de uma única transação, todas com o mesmo `serie`.
    """
    if not MIN_SESSOES_SERIE <= quantidade <= MAX_SESSOES_SERIE:
        raise ValueError(f"A série deve ter de {MIN_SESSOES_SERIE} a {MAX_SESSOES_SERIE} sessões.")
    datas = datas_da_serie(inicio, intervalo_dias, quantidade)
    conflitos = []
    for data in datas:
        ocupadas = Sessao(paciente=paciente, inicio=data, duracao_minutos=duracao_minutos).conflitos()
        if ocupadas:
            conflitos.append((data, ocupadas[0]))
    if conflitos:
        raise SerieComConflito(conflitos)
    serie = uuid.uuid4()
    with transaction.atomic():
        sessoes = []
        for data in datas:
            try:
                sessoes.append(agendar_sessao(paciente, data, duracao_minutos, observacao, serie=serie))
            except HorarioOcupado as erro:
                # Outra requisição ocupou o horário depois da verificação: desfaz tudo.
                raise SerieComConflito([(data, erro.conflito)]) from erro
    return sessoes


@transaction.atomic
def cancelar_serie_a_partir_de(sessao):
    """Cancela esta sessão e as próximas da mesma série que ainda estão agendadas.

    Nunca altera sessões realizadas, com falta, já canceladas ou anteriores a esta
    (nem as que já passaram). Devolve quantas foram canceladas.
    """
    if not sessao.serie or sessao.status != Sessao.AGENDADA:
        return 0
    da_serie = Sessao.objects.filter(
        serie=sessao.serie, paciente__usuario=sessao.paciente.usuario, status=Sessao.AGENDADA
    )
    alvo = da_serie.filter(pk=sessao.pk) | da_serie.filter(inicio__gt=sessao.inicio, inicio__gte=timezone.now())
    return Sessao.objects.filter(pk__in=list(alvo.values_list("pk", flat=True))).update(status=Sessao.CANCELADA)


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
