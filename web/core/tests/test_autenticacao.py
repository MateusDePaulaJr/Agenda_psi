import pytest  # noqa: F401
from django.urls import reverse



def test_agenda_exige_login(client):
    resp = client.get(reverse("agenda"))
    assert resp.status_code == 302
    assert reverse("login") in resp["Location"]


def test_login_valido_abre_agenda(client, usuaria):
    resp = client.post(reverse("login"), {"username": "ana", "password": "SenhaForte#2026"})
    assert resp.status_code == 302
    assert resp["Location"] == reverse("agenda")


def test_login_invalido_mostra_mensagem_generica(client, usuaria):
    resp = client.post(reverse("login"), {"username": "ana", "password": "errada"})
    assert resp.status_code == 200
    assert "Usuário ou senha inválidos" in resp.content.decode()


def test_senha_salva_com_argon2(usuaria):
    assert usuaria.password.startswith("argon2$argon2id$")
    assert "SenhaForte" not in usuaria.password


def test_logout_encerra_sessao(client, usuaria):
    client.force_login(usuaria)
    client.post(reverse("logout"))
    resp = client.get(reverse("agenda"))
    assert resp.status_code == 302
