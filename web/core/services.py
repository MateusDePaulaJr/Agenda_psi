"""Regras de negócio do PsiAgenda (camada de regras da arquitetura)."""
import csv
import io
import math
import re
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

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


def formatar_moeda(valor, simbolo=True):
    """Decimal('1234.5') -> 'R$ 1.234,50'. Com simbolo=False -> '1.234,50'."""
    try:
        valor = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return ""
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}" if simbolo else texto


def numero_recibo(pagamento):
    """Número do recibo: ano do pagamento + id do pagamento (ex.: 2026-000042)."""
    ano = pagamento.data_pagamento.year if pagamento.data_pagamento else timezone.localdate().year
    return f"{ano}-{pagamento.pk:06d}"


CABECALHO_CSV_FINANCEIRO = [
    "Data da sessão", "Paciente", "Status da sessão", "Valor",
    "Status do pagamento", "Data do pagamento", "Forma de pagamento",
]


def _celula_segura(texto):
    """Evita que o Excel interprete o texto como fórmula (injeção de CSV)."""
    texto = str(texto)
    return f"'{texto}" if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def gerar_csv_financeiro(pagamentos):
    """CSV do financeiro no padrão do Excel em português: ';', vírgula decimal e UTF-8 com BOM."""
    saida = io.StringIO()
    saida.write("\ufeff")
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(CABECALHO_CSV_FINANCEIRO)
    for p in pagamentos:
        sessao = p.sessao
        escritor.writerow([
            f"{timezone.localtime(sessao.inicio):%d/%m/%Y %H:%M}",
            _celula_segura(sessao.paciente.nome),
            sessao.get_status_display(),
            f"{p.valor:.2f}".replace(".", ","),
            p.get_status_display(),
            f"{p.data_pagamento:%d/%m/%Y}" if p.data_pagamento else "",
            p.get_forma_pagamento_display(),
        ])
    return saida.getvalue()


def nome_profissional(usuario, perfil=None):
    """Nome da psicóloga: o do perfil, senão o nome da conta, senão o usuário."""
    return (perfil and perfil.nome_exibicao) or usuario.get_full_name() or usuario.username


# --- Lembretes pelo WhatsApp (links wa.me; nenhuma mensagem é enviada pelo sistema) ---

MENSAGEM_LEMBRETE_PADRAO = (
    "Olá, {primeiro_nome}! Passando para lembrar da sua sessão de {dia_semana}, {data} às {hora}. "
    "Até lá! – {profissional}"
)

# Marcadores aceitos na mensagem: só nomes, data e horário (nada clínico).
MARCADORES_LEMBRETE = {
    "paciente": "nome completo do paciente",
    "primeiro_nome": "primeiro nome do paciente",
    "data": "data da sessão (ex.: 03/11)",
    "hora": "horário da sessão (ex.: 14h30)",
    "dia_semana": "dia da semana (ex.: terça-feira)",
    "profissional": "seu nome (o do perfil ou o da conta)",
}

DIAS_DA_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

# Só {palavra}: qualquer outra coisa entre chaves (ex.: {paciente.__class__}) fica como está.
_MARCADOR = re.compile(r"\{(\w+)\}")


def numero_whatsapp(telefone):
    """Número no formato do wa.me (55 + DDD + número, só dígitos) ou None se não der para usar.

    Zeros à esquerda (ex.: "011 ...") são ignorados. Depois, 10 ou 11 dígitos
    (DDD + número) ganham o 55 na frente; 12 ou 13 dígitos começando com 55 já
    estão completos. Qualquer outra coisa é considerada inválida.
    """
    digitos = re.sub(r"\D", "", telefone or "").lstrip("0")
    if len(digitos) in (10, 11):
        return f"55{digitos}"
    if digitos.startswith("55") and len(digitos) in (12, 13):
        return digitos
    return None


def link_whatsapp(numero, texto):
    """Link click-to-chat: abre o WhatsApp com o texto pronto; quem envia é a psicóloga."""
    return f"https://wa.me/{numero}?text={quote(texto, safe='')}"


def mensagem_lembrete(sessao, modelo="", profissional=""):
    """Monta o texto do lembrete trocando só os marcadores conhecidos.

    Não usa str.format: o texto vem da usuária, então marcadores desconhecidos ou
    com atributos (ex.: {paciente.__class__}) aparecem literalmente, sem erro e
    sem expor nada. A troca é feita em uma única passada, então valores que
    contenham chaves não são reprocessados.
    """
    inicio = timezone.localtime(sessao.inicio)
    nome = sessao.paciente.nome.strip()
    valores = {
        "paciente": nome,
        "primeiro_nome": nome.split()[0] if nome else "",
        "data": f"{inicio:%d/%m}",
        "hora": f"{inicio:%H}h{inicio:%M}",
        "dia_semana": DIAS_DA_SEMANA[inicio.weekday()],
        "profissional": profissional,
    }
    texto = (modelo or "").strip() or MENSAGEM_LEMBRETE_PADRAO
    return _MARCADOR.sub(lambda m: valores.get(m.group(1), m.group(0)), texto)


def pode_lembrar(sessao):
    """Lembrete só faz sentido para sessão agendada que ainda não começou."""
    return sessao.status == Sessao.AGENDADA and sessao.inicio > timezone.now()


def lembrete_whatsapp(sessao, perfil=None):
    """Dados do lembrete de uma sessão: mensagem, número e link (link None se o telefone for inválido)."""
    texto = mensagem_lembrete(
        sessao, perfil.mensagem_lembrete if perfil else "", nome_profissional(sessao.paciente.usuario, perfil)
    )
    numero = numero_whatsapp(sessao.paciente.telefone)
    return {"sessao": sessao, "mensagem": texto, "numero": numero, "url": link_whatsapp(numero, texto) if numero else None}


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
