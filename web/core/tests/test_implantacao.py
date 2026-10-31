import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse

from psiagenda.settings import banco_a_partir_da_url


def test_saude_responde_sem_login_e_sem_dados(client, db):
    resp = client.get(reverse("saude"))
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["status"] == "ok" and dados["banco"] == "ok"
    assert set(dados) == {"status", "banco", "tempo_ms"}


def test_converte_database_url():
    cfg = banco_a_partir_da_url("postgres://ana:s%40nha@db.exemplo.com:6543/psiagenda")
    assert cfg["ENGINE"].endswith("postgresql")
    assert (cfg["USER"], cfg["PASSWORD"], cfg["HOST"], cfg["PORT"], cfg["NAME"]) == (
        "ana", "s@nha", "db.exemplo.com", "6543", "psiagenda")


def test_criar_usuaria_por_variaveis(monkeypatch, db):
    monkeypatch.setenv("PSI_USUARIO", "jennifer")
    monkeypatch.setenv("PSI_SENHA", "UmaSenhaBemForte#2026")
    monkeypatch.setenv("PSI_NOME", "Jennifer")
    call_command("criar_usuaria")
    conta = User.objects.get(username="jennifer")
    assert conta.check_password("UmaSenhaBemForte#2026")
    assert conta.password.startswith("argon2$")


def test_criar_usuaria_sem_variaveis_nao_faz_nada(monkeypatch, db):
    monkeypatch.delenv("PSI_USUARIO", raising=False)
    monkeypatch.delenv("PSI_SENHA", raising=False)
    call_command("criar_usuaria")
    assert User.objects.count() == 0


def test_criar_usuaria_recusa_senha_fraca(monkeypatch, db):
    from django.core.exceptions import ValidationError
    monkeypatch.setenv("PSI_USUARIO", "x")
    monkeypatch.setenv("PSI_SENHA", "123")
    with pytest.raises(ValidationError):
        call_command("criar_usuaria")
