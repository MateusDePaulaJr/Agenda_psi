from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import PacienteForm
from .models import Paciente


@login_required
def agenda(request):
    return render(request, "core/agenda.html")


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
