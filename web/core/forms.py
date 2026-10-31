from django import forms

from datetime import datetime

from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone

from .models import Paciente, Pagamento, PerfilProfissional, Prontuario
from .services import (
    MAX_SESSOES_SERIE,
    MIN_SESSOES_SERIE,
    limpar_falhas_login,
    minutos_de_bloqueio,
    registrar_falha_login,
)


def mensagem_bloqueio(minutos):
    return f"Muitas tentativas. Tente novamente em {minutos} minuto{'s' if minutos != 1 else ''}."


class BloqueioLoginMixin:
    """Bloqueia o login após 5 falhas seguidas do mesmo usuário (RNF01).

    A mensagem é a mesma para usuários existentes ou não, e durante o bloqueio
    nem a senha correta é aceita.
    """

    def clean(self):
        username = self.cleaned_data.get("username")
        if username is None:
            return super().clean()
        minutos = minutos_de_bloqueio(username)
        if minutos:
            raise forms.ValidationError(mensagem_bloqueio(minutos), code="bloqueado")
        try:
            dados = super().clean()
        except forms.ValidationError as erro:
            if getattr(erro, "code", None) == "invalid_login":
                minutos = registrar_falha_login(username)
                if minutos:
                    raise forms.ValidationError(mensagem_bloqueio(minutos), code="bloqueado") from erro
            raise
        limpar_falhas_login(username)
        return dados


class LoginForm(BloqueioLoginMixin, AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Usuário ou senha inválidos.",
    }


class AdminLoginForm(BloqueioLoginMixin, AdminAuthenticationForm):
    pass


class PacienteForm(forms.ModelForm):
    class Meta:
        model = Paciente
        fields = ["nome", "telefone", "email", "valor_sessao"]
        labels = {
            "nome": "Nome (obrigatório)",
            "telefone": "Telefone (obrigatório)",
            "email": "E-mail (opcional)",
            "valor_sessao": "Valor da sessão em R$ (obrigatório)",
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control"

    def clean_telefone(self):
        telefone = self.cleaned_data["telefone"].strip()
        repetido = Paciente.objects.filter(usuario=self.usuario, telefone=telefone, ativo=True)
        if self.instance.pk:
            repetido = repetido.exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Já existe um paciente ativo com este telefone.")
        return telefone


class SessaoForm(forms.Form):
    paciente = forms.ModelChoiceField(queryset=Paciente.objects.none(), label="Paciente (obrigatório)")
    data = forms.DateField(label="Data (obrigatório)", widget=forms.DateInput(attrs={"type": "date"}))
    horario = forms.TimeField(label="Horário de início (obrigatório)", widget=forms.TimeInput(attrs={"type": "time"}))
    duracao_minutos = forms.IntegerField(label="Duração em minutos", initial=50, min_value=10, max_value=240)
    repetir = forms.ChoiceField(
        label="Repetir",
        required=False,
        choices=[("", "Não repetir"), ("semanal", "Toda semana (semanal)"), ("quinzenal", "A cada 2 semanas (quinzenal)")],
    )
    # Os limites são conferidos em clean(), só quando a sessão se repete, para não
    # dar erro num campo escondido.
    quantidade = forms.IntegerField(
        label=f"Quantidade de sessões ({MIN_SESSOES_SERIE} a {MAX_SESSOES_SERIE}, contando a primeira)",
        required=False,
        initial=4,
        widget=forms.NumberInput(attrs={"min": MIN_SESSOES_SERIE, "max": MAX_SESSOES_SERIE}),
    )
    observacao = forms.CharField(label="Observação (opcional)", required=False, max_length=200)

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paciente"].queryset = Paciente.objects.filter(usuario=usuario, ativo=True)
        selecoes = (self.fields["paciente"], self.fields["repetir"])
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-select" if campo in selecoes else "form-control"

    def clean(self):
        dados = super().clean()
        if dados.get("data") and dados.get("horario"):
            inicio = timezone.make_aware(datetime.combine(dados["data"], dados["horario"]))
            if inicio <= timezone.now():
                raise forms.ValidationError("A data e o horário precisam ser futuros.")
            dados["inicio"] = inicio
        if dados.get("repetir"):
            quantidade = dados.get("quantidade")
            if quantidade is None and "quantidade" not in self.errors:
                quantidade = dados["quantidade"] = 4
            if quantidade is not None and not MIN_SESSOES_SERIE <= quantidade <= MAX_SESSOES_SERIE:
                self.add_error(
                    "quantidade",
                    f"Informe de {MIN_SESSOES_SERIE} a {MAX_SESSOES_SERIE} sessões.",
                )
        else:
            dados["quantidade"] = 1
        return dados


class PagamentoForm(forms.ModelForm):
    class Meta:
        model = Pagamento
        fields = ["data_pagamento", "forma_pagamento"]
        labels = {"data_pagamento": "Data do pagamento (obrigatório)", "forma_pagamento": "Forma de pagamento"}
        widgets = {"data_pagamento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_pagamento"].required = True
        if not self.initial.get("data_pagamento"):
            self.initial["data_pagamento"] = timezone.localdate()
        self.fields["data_pagamento"].widget.attrs["class"] = "form-control"
        self.fields["forma_pagamento"].widget.attrs["class"] = "form-select"


class ProntuarioForm(forms.ModelForm):
    class Meta:
        model = Prontuario
        fields = ["evolucao"]
        labels = {"evolucao": "Evolução da sessão (obrigatório)"}
        widgets = {"evolucao": forms.Textarea(attrs={"class": "form-control", "rows": 8})}


class PerfilProfissionalForm(forms.ModelForm):
    class Meta:
        model = PerfilProfissional
        fields = ["nome_exibicao", "crp", "documento", "cidade"]
        labels = {
            "nome_exibicao": "Nome no recibo (opcional; vazio usa o nome da conta)",
            "crp": "CRP (opcional, ex.: 06/123456)",
            "documento": "CPF ou CNPJ (opcional)",
            "cidade": "Cidade (opcional, ex.: São Paulo/SP)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control"
