from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.agenda, name="agenda"),
    path("sessoes/nova/", views.sessao_nova, name="sessao_nova"),
    path("sessoes/<int:pk>/", views.sessao_detalhe, name="sessao_detalhe"),
    path("sessoes/<int:pk>/cancelar/", views.sessao_cancelar, name="sessao_cancelar"),
    path("pacientes/", views.pacientes, name="pacientes"),
    path("pacientes/novo/", views.paciente_form, name="paciente_novo"),
    path("pacientes/<int:pk>/editar/", views.paciente_form, name="paciente_editar"),
]
