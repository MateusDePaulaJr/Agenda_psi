from django.urls import reverse

from core.templatetags.psiagenda import iniciais


def test_iniciais_do_avatar():
    assert iniciais("Beatriz R.") == "BR"
    assert iniciais("carlos") == "C"
    assert iniciais("") == "?"


def test_menu_marca_pagina_atual(cliente_logado):
    html = cliente_logado.get(reverse("pacientes")).content.decode()
    assert 'aria-current="page"' in html
    assert "psiagenda.css" in html


def test_login_usa_novo_tema(client):
    html = client.get(reverse("login")).content.decode()
    assert "pa-login-card" in html and 'autocomplete="current-password"' in html
