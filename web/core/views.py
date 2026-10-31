from datetime import date, timedelta

import time

from django.contrib import messages
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from decimal import Decimal

from django.db.models import Sum

from .forms import PacienteForm, PagamentoForm, PerfilProfissionalForm, ProntuarioForm, SessaoForm
from .models import Paciente, Pagamento, PerfilProfissional, Prontuario, Sessao
from .services import (
    MARCADORES_LEMBRETE,
    MENSAGEM_LEMBRETE_PADRAO,
    REPETICOES,
    HorarioOcupado,
    SerieComConflito,
    agendar_serie,
    agendar_sessao,
    cancelar_serie_a_partir_de,
    cartao_publico,
    dados_painel,
    gerar_csv_financeiro,
    horarios_livres,
    iniciais_profissional,
    lembrete_whatsapp,
    nome_profissional,
    numero_recibo,
    pode_lembrar,
)


def _inicio_semana(texto):
    try:
        base = date.fromisoformat(texto) if texto else timezone.localdate()
    except ValueError:
        base = timezone.localdate()
    return base - timedelta(days=base.weekday())


@login_required
def painel(request):
    """Tela inicial: resumo do dia, indicadores e pendências da psicóloga."""
    return render(request, "core/painel.html", dados_painel(request.user, timezone.now()))


@login_required
def agenda(request):
    """Tela 1: agenda da semana (RF03, RF05). Carrega só a semana exibida (RNF03)."""
    segunda = _inicio_semana(request.GET.get("semana"))
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(timezone.datetime.combine(segunda, timezone.datetime.min.time()), tz)
    sessoes = (
        Sessao.objects.filter(paciente__usuario=request.user, inicio__gte=inicio, inicio__lt=inicio + timedelta(days=7))
        .exclude(status=Sessao.CANCELADA)
        .select_related("paciente", "pagamento")
    )
    dias = []
    for i in range(7):
        dia = segunda + timedelta(days=i)
        do_dia = [s for s in sessoes if timezone.localtime(s.inicio).date() == dia]
        if i < 5 or do_dia:
            dias.append({"data": dia, "sessoes": do_dia})
    contexto = {
        "lembretes_amanha": _lembretes_de_amanha(request.user),
        "dias": dias,
        "segunda": segunda,
        "domingo": segunda + timedelta(days=6),
        "anterior": segunda - timedelta(days=7),
        "proxima": segunda + timedelta(days=7),
        "destaque": request.GET.get("destaque"),
    }
    return render(request, "core/agenda.html", contexto)


def _lembretes_de_amanha(usuario):
    """Sessões agendadas de amanhã (hora local), cada uma com o seu link do WhatsApp."""
    amanha = timezone.localdate() + timedelta(days=1)
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(timezone.datetime.combine(amanha, timezone.datetime.min.time()), tz)
    fim = timezone.make_aware(timezone.datetime.combine(amanha + timedelta(days=1), timezone.datetime.min.time()), tz)
    sessoes = Sessao.objects.filter(
        paciente__usuario=usuario, status=Sessao.AGENDADA, inicio__gte=inicio, inicio__lt=fim
    ).select_related("paciente__usuario")
    perfil = PerfilProfissional.objects.filter(usuario=usuario).first()
    return [lembrete_whatsapp(s, perfil) for s in sessoes if pode_lembrar(s)]


@login_required
def sessao_nova(request):
    """Tela 2 e 3: agendar sessão com bloqueio de conflito (RF03, RF04)."""
    inicial = {"data": request.GET.get("data"), "horario": request.GET.get("horario")}
    form = SessaoForm(request.POST or None, usuario=request.user, initial=inicial)
    conflito, sugestoes, conflitos_serie = None, [], []
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        if d["repetir"]:
            # Sessões recorrentes: todas as datas livres ou nenhuma é criada.
            intervalo, rotulo = REPETICOES[d["repetir"]]
            try:
                sessoes = agendar_serie(
                    d["paciente"], d["inicio"], d["duracao_minutos"], d["observacao"], intervalo, d["quantidade"]
                )
            except SerieComConflito as erro:
                conflito, conflitos_serie = str(erro), erro.conflitos
            else:
                ultima = timezone.localtime(sessoes[-1].inicio)
                messages.success(request, f"{len(sessoes)} sessões agendadas ({rotulo}, até {ultima:%d/%m}).")
                semana = timezone.localtime(sessoes[0].inicio).date().isoformat()
                return redirect(f"{reverse('agenda')}?semana={semana}&destaque={sessoes[0].pk}")
        else:
            try:
                sessao = agendar_sessao(d["paciente"], d["inicio"], d["duracao_minutos"], d["observacao"])
            except HorarioOcupado as erro:
                conflito = str(erro)
                sugestoes = horarios_livres(request.user, d["data"], d["duracao_minutos"])[:3]
            else:
                messages.success(request, "Sessão agendada com sucesso.")
                return redirect("sessao_detalhe", pk=sessao.pk)
    return render(request, "core/sessao_form.html", {
        "form": form, "conflito": conflito, "sugestoes": sugestoes, "conflitos_serie": conflitos_serie,
    })


@login_required
def sessao_detalhe(request, pk):
    sessao = get_object_or_404(Sessao.objects.select_related("paciente", "pagamento"), pk=pk, paciente__usuario=request.user)
    lembrete = None
    if pode_lembrar(sessao):
        lembrete = lembrete_whatsapp(sessao, PerfilProfissional.objects.filter(usuario=request.user).first())
    return render(request, "core/sessao_detalhe.html", {
        "sessao": sessao, "posicao_serie": sessao.posicao_na_serie(), "lembrete": lembrete,
    })


@login_required
@require_POST
def sessao_lembrete_enviado(request, pk):
    """Registra que o lembrete foi enviado (marcação manual: o wa.me não confirma o envio)."""
    sessao = get_object_or_404(Sessao, pk=pk, paciente__usuario=request.user)
    if sessao.status != Sessao.AGENDADA:
        messages.error(request, "Só dá para marcar lembrete de sessão agendada.")
    else:
        sessao.lembrete_enviado_em = timezone.now()
        sessao.save(update_fields=["lembrete_enviado_em"])
        messages.success(request, f"Lembrete de {sessao.paciente.nome} marcado como enviado.")
    destino = request.POST.get("proximo", "")
    if url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(destino)
    return redirect("sessao_detalhe", pk=pk)


@login_required
def sessao_cancelar(request, pk):
    sessao = get_object_or_404(Sessao, pk=pk, paciente__usuario=request.user)
    if request.method == "POST":
        sessao.status = Sessao.CANCELADA
        sessao.save(update_fields=["status"])
        messages.success(request, "Sessão cancelada. O horário foi liberado.")
        return redirect("agenda")
    return redirect("sessao_detalhe", pk=pk)


@login_required
def sessao_cancelar_serie(request, pk):
    """Cancela esta sessão e as próximas agendadas da mesma série recorrente."""
    sessao = get_object_or_404(Sessao.objects.select_related("paciente"), pk=pk, paciente__usuario=request.user)
    if request.method != "POST":
        return redirect("sessao_detalhe", pk=pk)
    canceladas = cancelar_serie_a_partir_de(sessao)
    if not canceladas:
        messages.error(request, "Nenhuma sessão da série pôde ser cancelada.")
        return redirect("sessao_detalhe", pk=pk)
    messages.success(
        request,
        f"{canceladas} sess{'ões' if canceladas != 1 else 'ão'} da série cancelada{'s' if canceladas != 1 else ''}. "
        "Os horários foram liberados.",
    )
    return redirect(f"{reverse('agenda')}?semana={timezone.localtime(sessao.inicio).date().isoformat()}")


@login_required
def pacientes(request):
    lista = Paciente.objects.filter(usuario=request.user, ativo=True)
    return render(request, "core/pacientes.html", {"pacientes": lista})


@login_required
def paciente_form(request, pk=None):
    paciente = get_object_or_404(Paciente, pk=pk, usuario=request.user) if pk else None
    form = PacienteForm(request.POST or None, instance=paciente, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        novo = form.save(commit=False)
        novo.usuario = request.user
        novo.save()
        messages.success(request, "Paciente salvo com sucesso.")
        return redirect("pacientes")
    return render(request, "core/paciente_form.html", {"form": form, "paciente": paciente})


@login_required
def pagamento_registrar(request, pk):
    """Marca o pagamento de uma sessão como pago (RF05)."""
    pagamento = get_object_or_404(Pagamento, sessao__pk=pk, sessao__paciente__usuario=request.user)
    form = PagamentoForm(request.POST or None, instance=pagamento)
    if request.method == "POST" and form.is_valid():
        pago = form.save(commit=False)
        pago.status = Pagamento.PAGO
        pago.save()
        messages.success(request, "Pagamento registrado como pago.")
        return redirect("sessao_detalhe", pk=pk)
    return render(request, "core/pagamento_form.html", {"form": form, "pagamento": pagamento})


def _mes_selecionado(request):
    """Lê ?mes=AAAA-M (ou AAAA-MM); valor ausente ou inválido vira o mês atual."""
    hoje = timezone.localdate()
    try:
        ano, mes = map(int, request.GET.get("mes", "").split("-"))
        if not (1 <= mes <= 12 and 1 <= ano <= 9999):
            raise ValueError
    except ValueError:
        ano, mes = hoje.year, hoje.month
    return ano, mes


def _pagamentos_do_mes(usuario, ano, mes):
    """Pagamentos das sessões do mês (exceto canceladas), só da usuária logada."""
    return Pagamento.objects.filter(
        sessao__paciente__usuario=usuario, sessao__inicio__year=ano, sessao__inicio__month=mes
    ).exclude(sessao__status=Sessao.CANCELADA).select_related("sessao__paciente")


@login_required
def financeiro(request):
    """Resumo mensal: total recebido, a receber e pacientes em aberto (RF07)."""
    ano, mes = _mes_selecionado(request)
    pagamentos = _pagamentos_do_mes(request.user, ano, mes)
    recebido = pagamentos.filter(status=Pagamento.PAGO).aggregate(t=Sum("valor"))["t"] or Decimal("0")
    pendentes = pagamentos.filter(status=Pagamento.A_RECEBER)
    a_receber = pendentes.aggregate(t=Sum("valor"))["t"] or Decimal("0")
    em_aberto = pendentes.values("sessao__paciente__nome").annotate(total=Sum("valor")).order_by("sessao__paciente__nome")
    return render(request, "core/financeiro.html", {
        "ano": ano, "mes": mes, "recebido": recebido, "a_receber": a_receber,
        "em_aberto": em_aberto, "pendentes": pendentes.order_by("sessao__inicio"),
    })


@login_required
def financeiro_csv(request):
    """Exporta as sessões do mês em CSV para abrir no Excel (financeiro-AAAA-MM.csv)."""
    ano, mes = _mes_selecionado(request)
    pagamentos = _pagamentos_do_mes(request.user, ano, mes).order_by("sessao__inicio", "pk")
    resposta = HttpResponse(gerar_csv_financeiro(pagamentos), content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="financeiro-{ano:04d}-{mes:02d}.csv"'
    return resposta


@login_required
def recibo(request, pk):
    """Recibo imprimível de uma sessão paga (o navegador salva em PDF).

    Mostra só o necessário para um recibo: nada do prontuário nem observações.
    """
    pagamento = get_object_or_404(
        Pagamento.objects.select_related("sessao__paciente"), sessao__pk=pk, sessao__paciente__usuario=request.user
    )
    if pagamento.status != Pagamento.PAGO:
        messages.error(request, "O recibo só fica disponível depois que o pagamento é registrado como pago.")
        return redirect("sessao_detalhe", pk=pk)
    perfil = PerfilProfissional.objects.filter(usuario=request.user).first()
    nome = nome_profissional(request.user, perfil)
    return render(request, "core/recibo.html", {
        "pagamento": pagamento, "sessao": pagamento.sessao, "perfil": perfil, "profissional": nome,
        "numero": numero_recibo(pagamento), "emitido_em": timezone.localdate(),
    })


@login_required
def perfil(request):
    """Meu perfil: identificação, apresentação, padrões de atendimento, contatos, página pública,
    dados do recibo e a mensagem de lembrete. Tudo opcional."""
    atual = PerfilProfissional.objects.filter(usuario=request.user).first()
    form = PerfilProfissionalForm(request.POST or None, instance=atual)
    if request.method == "POST" and form.is_valid():
        novo = form.save(commit=False)
        novo.usuario = request.user
        novo.save()
        messages.success(request, "Perfil salvo.")
        return redirect("perfil")
    # O avatar e o link mostram o que está salvo (não o que foi digitado num envio com erro).
    salvo = PerfilProfissional.objects.filter(usuario=request.user).first()
    nome = nome_profissional(request.user, salvo)
    link_publico = None
    if salvo and salvo.slug:
        link_publico = request.build_absolute_uri(reverse("perfil_publico", args=[salvo.slug]))
    return render(request, "core/perfil.html", {
        "form": form, "marcadores": MARCADORES_LEMBRETE, "mensagem_padrao": MENSAGEM_LEMBRETE_PADRAO,
        "perfil": salvo, "nome": nome, "iniciais": iniciais_profissional(nome),
        "cor": salvo.cor_avatar if salvo else "indigo", "link_publico": link_publico,
    })


def perfil_publico(request, slug):
    """Cartão de apresentação público (/p/<slug>/), sem login.

    Só existe com a página ativada; desativada, responde 404 para todos, exceto
    para a própria psicóloga logada, que vê uma pré-visualização marcada como
    noindex. O template recebe apenas o dicionário de cartao_publico (allowlist).
    """
    perfil = get_object_or_404(PerfilProfissional.objects.select_related("usuario"), slug=slug)
    dona = request.user.is_authenticated and request.user.pk == perfil.usuario_id
    if not dona and not (perfil.perfil_publico and perfil.usuario.is_active):
        raise Http404
    cartao = cartao_publico(perfil)
    resposta = render(request, "core/perfil_publico.html", {
        "cartao": cartao,
        "previa": not perfil.perfil_publico,
        "url_canonica": request.build_absolute_uri(reverse("perfil_publico", args=[perfil.slug])),
    })
    if not perfil.perfil_publico:
        resposta["X-Robots-Tag"] = "noindex, nofollow"
    return resposta


@login_required
def prontuario_registrar(request, pk):
    """Registra a evolução de uma sessão; marca a sessão como realizada (RF06)."""
    sessao = get_object_or_404(Sessao, pk=pk, paciente__usuario=request.user)
    if sessao.status == Sessao.CANCELADA or sessao.inicio > timezone.now():
        messages.error(request, "O prontuário só pode ser registrado depois do horário da sessão.")
        return redirect("sessao_detalhe", pk=pk)
    prontuario = Prontuario.objects.filter(sessao=sessao).first()
    form = ProntuarioForm(request.POST or None, instance=prontuario)
    if request.method == "POST" and form.is_valid():
        registro = form.save(commit=False)
        registro.sessao = sessao
        registro.save()
        if sessao.status != Sessao.REALIZADA:
            sessao.status = Sessao.REALIZADA
            sessao.save(update_fields=["status"])
        messages.success(request, "Prontuário salvo.")
        return redirect("paciente_historico", pk=sessao.paciente.pk)
    return render(request, "core/prontuario_form.html", {"form": form, "sessao": sessao})


@login_required
def paciente_historico(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk, usuario=request.user)
    registros = Prontuario.objects.filter(sessao__paciente=paciente).select_related("sessao").order_by("-sessao__inicio")
    return render(request, "core/paciente_historico.html", {"paciente": paciente, "registros": registros})


def saude(request):
    """Endpoint de monitoramento (health check) usado pelo Render e pelo UptimeRobot.

    Não exige login e não expõe dados: só informa se a aplicação e o banco respondem.
    """
    inicio = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        banco = "ok"
    except Exception:  # pragma: no cover - só ocorre com o banco fora do ar
        banco = "erro"
    status = 200 if banco == "ok" else 503
    tempo_ms = round((time.perf_counter() - inicio) * 1000, 1)
    return JsonResponse({"status": "ok" if status == 200 else "erro", "banco": banco, "tempo_ms": tempo_ms}, status=status)
