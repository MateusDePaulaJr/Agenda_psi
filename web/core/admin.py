from django.contrib import admin

from .models import Paciente, Pagamento, Prontuario, Sessao

admin.site.register([Paciente, Sessao, Pagamento])


@admin.register(Prontuario)
class ProntuarioAdmin(admin.ModelAdmin):
    # Não exibe o texto clínico em listagens (RNF02 – minimização).
    list_display = ("sessao", "criado_em")
