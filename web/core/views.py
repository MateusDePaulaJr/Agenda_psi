from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from decimal import Decimal

from django.db.models import Sum

from .forms import PacienteForm, PagamentoForm, SessaoForm
from .models import Paciente, Pagamento, Sessao
from .services import HorarioOcupado, agendar_sessao, horarios_livres


def _inicio_semana(texto):
    try:
        base = date.fromisoformat(texto) if texto else timezone.localdate()
    except ValueError:
        base = timezone.localdate()
    return base - timedelta(days=base.weekday())


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
        "dias": dias,
        "segunda": segunda,
        "domingo": segunda + timedelta(days=6),
        "anterior": segunda - timedelta(days=7),
        "proxima": segunda + timedelta(days=7),
        "destaque": request.GET.get("destaque"),
    }
    return render(request, "core/agenda.html", contexto)


@login_required
def sessao_nova(request):
    """Tela 2 e 3: agendar sessão com bloqueio de conflito (RF03, RF04)."""
    inicial = {"data": request.GET.get("data"), "horario": request.GET.get("horario")}
    form = SessaoForm(request.POST or None, usuario=request.user, initial=inicial)
    conflito, sugestoes = None, []
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            sessao = agendar_sessao(d["paciente"], d["inicio"], d["duracao_minutos"], d["observacao"])
        except HorarioOcupado as erro:
            conflito = str(erro)
            sugestoes = horarios_livres(request.user, d["data"], d["duracao_minutos"])[:3]
        else:
            messages.success(request, "Sessão agendada com sucesso.")
            return redirect("sessao_detalhe", pk=sessao.pk)
    return render(request, "core/sessao_form.html", {"form": form, "conflito": conflito, "sugestoes": sugestoes})


@login_required
def sessao_detalhe(request, pk):
    sessao = get_object_or_404(Sessao.objects.select_related("paciente", "pagamento"), pk=pk, paciente__usuario=request.user)
    return render(request, "core/sessao_detalhe.html", {"sessao": sessao})


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


@login_required
def financeiro(request):
    """Resumo mensal: total recebido, a receber e pacientes em aberto (RF07)."""
    hoje = timezone.localdate()
    try:
        ano, mes = map(int, request.GET.get("mes", f"{hoje.year}-{hoje.month}").split("-"))
    except ValueError:
        ano, mes = hoje.year, hoje.month
    pagamentos = Pagamento.objects.filter(
        sessao__paciente__usuario=request.user, sessao__inicio__year=ano, sessao__inicio__month=mes
    ).exclude(sessao__status=Sessao.CANCELADA).select_related("sessao__paciente")
    recebido = pagamentos.filter(status=Pagamento.PAGO).aggregate(t=Sum("valor"))["t"] or Decimal("0")
    pendentes = pagamentos.filter(status=Pagamento.A_RECEBER)
    a_receber = pendentes.aggregate(t=Sum("valor"))["t"] or Decimal("0")
    em_aberto = pendentes.values("sessao__paciente__nome").annotate(total=Sum("valor")).order_by("sessao__paciente__nome")
    return render(request, "core/financeiro.html", {
        "ano": ano, "mes": mes, "recebido": recebido, "a_receber": a_receber,
        "em_aberto": em_aberto, "pendentes": pendentes.order_by("sessao__inicio"),
    })
