from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import LoginForm

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(authentication_form=LoginForm), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.agenda, name="agenda"),
    path("saude/", views.saude, name="saude"),
    path("sessoes/nova/", views.sessao_nova, name="sessao_nova"),
    path("sessoes/<int:pk>/", views.sessao_detalhe, name="sessao_detalhe"),
    path("sessoes/<int:pk>/cancelar/", views.sessao_cancelar, name="sessao_cancelar"),
    path("sessoes/<int:pk>/pagamento/", views.pagamento_registrar, name="pagamento_registrar"),
    path("sessoes/<int:pk>/prontuario/", views.prontuario_registrar, name="prontuario_registrar"),
    path("pacientes/<int:pk>/historico/", views.paciente_historico, name="paciente_historico"),
    path("financeiro/", views.financeiro, name="financeiro"),
    path("pacientes/", views.pacientes, name="pacientes"),
    path("pacientes/novo/", views.paciente_form, name="paciente_novo"),
    path("pacientes/<int:pk>/editar/", views.paciente_form, name="paciente_editar"),
]
