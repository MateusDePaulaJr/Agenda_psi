from django import forms

from datetime import datetime

from django.utils import timezone

from .models import Paciente


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
    observacao = forms.CharField(label="Observação (opcional)", required=False, max_length=200)

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paciente"].queryset = Paciente.objects.filter(usuario=usuario, ativo=True)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-select" if campo is self.fields["paciente"] else "form-control"

    def clean(self):
        dados = super().clean()
        if dados.get("data") and dados.get("horario"):
            inicio = timezone.make_aware(datetime.combine(dados["data"], dados["horario"]))
            if inicio <= timezone.now():
                raise forms.ValidationError("A data e o horário precisam ser futuros.")
            dados["inicio"] = inicio
        return dados
