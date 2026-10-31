from django import forms

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
