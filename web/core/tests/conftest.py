import pytest
from django.contrib.auth.models import User

from core.models import Paciente


@pytest.fixture
def usuaria(db):
    return User.objects.create_user("ana", password="SenhaForte#2026")


@pytest.fixture
def outra_usuaria(db):
    return User.objects.create_user("bia", password="SenhaForte#2026")


@pytest.fixture
def cliente_logado(client, usuaria):
    client.force_login(usuaria)
    return client


@pytest.fixture
def paciente(usuaria):
    return Paciente.objects.create(usuario=usuaria, nome="Carlos M.", telefone="11999990001", valor_sessao=150)
