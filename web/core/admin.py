from django.contrib import admin

from .forms import AdminLoginForm
from .models import Paciente, Pagamento, Prontuario, Sessao, TentativaLogin

# O login do /admin/ também passa pelo bloqueio após 5 falhas (RNF01).
admin.site.login_form = AdminLoginForm
admin.site.register([Paciente, Sessao, Pagamento])


@admin.register(Prontuario)
class ProntuarioAdmin(admin.ModelAdmin):
    # Não exibe o texto clínico em listagens (RNF02 – minimização).
    list_display = ("sessao", "criado_em")


@admin.register(TentativaLogin)
class TentativaLoginAdmin(admin.ModelAdmin):
    # Permite à psicóloga ver e desfazer um bloqueio (apagando o registro).
    list_display = ("username", "falhas", "bloqueado_ate", "atualizado_em")
