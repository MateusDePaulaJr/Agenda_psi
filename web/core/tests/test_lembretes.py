"""Lembretes ao paciente por link do WhatsApp (wa.me): telefone, mensagem, telas e marcação de envio."""
from datetime import datetime, timedelta
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import Paciente, PerfilProfissional, Prontuario, Sessao
from core.services import (
    MENSAGEM_LEMBRETE_PADRAO,
    agendar_sessao,
    lembrete_whatsapp,
    link_whatsapp,
    mensagem_lembrete,
    numero_whatsapp,
    pode_lembrar,
)

SEGREDO_CLINICO = "Relato clínico confidencial XYZ"


def em(dias, hora, minuto=0):
    base = timezone.localdate() + timedelta(days=dias)
    return timezone.make_aware(datetime.combine(base, datetime.min.time()).replace(hour=hora, minute=minuto))


def no_dia(ano, mes, dia, hora, minuto=0):
    return timezone.make_aware(datetime(ano, mes, dia, hora, minuto))


@pytest.fixture
def futura(paciente):
    return agendar_sessao(paciente, em(3, 14, 30), observacao="Observação interna")


def texto_do_link(url):
    return parse_qs(urlsplit(url).query)["text"][0]


# --- Telefone -----------------------------------------------------------------

@pytest.mark.parametrize("telefone, esperado", [
    ("(11) 99999-0001", "5511999990001"),
    ("11 3333-4444", "551133334444"),
    ("11999990001", "5511999990001"),
    ("1133334444", "551133334444"),
    ("+55 (11) 99999-0001", "5511999990001"),
    ("55 11 3333-4444", "551133334444"),
    ("5511999990001", "5511999990001"),
    ("(55) 99999-0001", "5555999990001"),  # DDD 55 (RS) com 11 dígitos
    ("99999-0001", None),
    ("123", None),
    ("+1 212 555 0100 99", None),
    ("011 99999-0001", "5511999990001"),
    ("0000", None),
    ("abc", None),
    ("", None),
    (None, None),
])
def test_numero_whatsapp(telefone, esperado):
    assert numero_whatsapp(telefone) == esperado


def test_link_whatsapp_codifica_o_texto():
    url = link_whatsapp("5511999990001", "Olá, Ana! Sessão às 14h30 & até lá? #1 – 100%/ok\nfim")
    assert url.startswith("https://wa.me/5511999990001?text=")
    consulta = url.split("?text=", 1)[1]
    assert " " not in consulta and "&" not in consulta and "#" not in consulta and "/" not in consulta
    assert "%C3%A1" in consulta and "%26" in consulta and "%0A" in consulta
    assert texto_do_link(url) == "Olá, Ana! Sessão às 14h30 & até lá? #1 – 100%/ok\nfim"


# --- Mensagem -----------------------------------------------------------------

def test_mensagem_padrao_em_portugues(paciente):
    sessao = agendar_sessao(paciente, no_dia(2030, 11, 5, 14, 30))  # terça-feira
    texto = mensagem_lembrete(sessao, "", "Ana Souza")
    assert texto == (
        "Olá, Carlos! Passando para lembrar da sua sessão de terça-feira, 05/11 às 14h30. Até lá! – Ana Souza"
    )
    assert mensagem_lembrete(sessao, "   ", "Ana Souza") == texto


def test_mensagem_personalizada_com_todos_os_marcadores(paciente):
    sessao = agendar_sessao(paciente, no_dia(2030, 11, 10, 9, 5))  # domingo
    modelo = "{paciente}|{primeiro_nome}|{data}|{hora}|{dia_semana}|{profissional}|{primeiro_nome}"
    assert mensagem_lembrete(sessao, modelo, "Dra. Ana") == "Carlos M.|Carlos|10/11|09h05|domingo|Dra. Ana|Carlos"


@pytest.mark.parametrize("modelo", [
    "Oi {paciente.__class__} {desconhecido} {0} {} {paciente!r} {{paciente}} {paciente.usuario.password}",
    "{paciente.__init__.__globals__}",
    "{",
    "}{",
    "%s %(paciente)s",
])
def test_marcador_desconhecido_ou_malicioso_nao_quebra_nem_vaza(paciente, usuaria, modelo):
    sessao = agendar_sessao(paciente, em(2, 10))
    texto = mensagem_lembrete(sessao, modelo, "Ana")
    assert "class '" not in texto and "<" not in texto and "pbkdf2" not in texto and "argon2" not in texto
    assert usuaria.password not in texto
    for literal in ("{paciente.__class__}", "{desconhecido}", "{paciente.__init__.__globals__}", "{paciente!r}"):
        if literal in modelo:
            assert literal in texto


def test_marcador_com_chaves_duplas_troca_so_o_de_dentro(paciente):
    sessao = agendar_sessao(paciente, em(2, 10))
    assert mensagem_lembrete(sessao, "{{paciente}}", "Ana") == "{Carlos M.}"


def test_valor_com_chaves_nao_e_reprocessado(usuaria):
    p = Paciente.objects.create(usuario=usuaria, nome="{profissional} {hora}", telefone="11988887777", valor_sessao=100)
    sessao = agendar_sessao(p, em(2, 10))
    assert mensagem_lembrete(sessao, "{paciente}", "Ana") == "{profissional} {hora}"


def test_lembrete_usa_perfil_e_nao_tem_dados_clinicos(cliente_logado, usuaria, paciente):
    usuaria.first_name, usuaria.last_name = "Ana", "Souza"
    usuaria.save()
    passada = agendar_sessao(paciente, em(-7, 10))
    Prontuario.objects.create(sessao=passada, evolucao=SEGREDO_CLINICO)
    sessao = agendar_sessao(paciente, em(2, 10), observacao=SEGREDO_CLINICO)
    dados = lembrete_whatsapp(sessao)
    assert dados["numero"] == "5511999990001"
    assert dados["mensagem"].endswith("– Ana Souza")
    assert SEGREDO_CLINICO not in dados["mensagem"] and "150" not in dados["mensagem"]
    perfil = PerfilProfissional.objects.create(usuario=usuaria, nome_exibicao="Dra. Ana", mensagem_lembrete="Oi {paciente}, {profissional}")
    dados = lembrete_whatsapp(sessao, perfil)
    assert dados["mensagem"] == "Oi Carlos M., Dra. Ana"
    assert dados["url"] == f"https://wa.me/5511999990001?text={quote('Oi Carlos M., Dra. Ana', safe='')}"


# --- Detalhe da sessão --------------------------------------------------------

def test_detalhe_de_sessao_futura_mostra_botao_whatsapp(cliente_logado, futura):
    html = cliente_logado.get(reverse("sessao_detalhe", args=[futura.pk])).content.decode()
    assert "Lembrar pelo WhatsApp" in html
    assert 'href="https://wa.me/5511999990001?text=Ol%C3%A1%2C%20Carlos' in html
    assert 'target="_blank" rel="noopener noreferrer"' in html
    assert reverse("sessao_lembrete_enviado", args=[futura.pk]) in html
    assert "Observa%C3%A7%C3%A3o" not in html.split("wa.me", 1)[1].split('"', 1)[0]


def test_botao_some_para_sessao_passada_cancelada_ou_realizada(cliente_logado, paciente, futura):
    passada = agendar_sessao(paciente, em(-2, 10))
    cancelada = agendar_sessao(paciente, em(4, 10))
    cancelada.status = Sessao.CANCELADA
    cancelada.save()
    realizada = agendar_sessao(paciente, em(5, 10))
    realizada.status = Sessao.REALIZADA
    realizada.save()
    for sessao in (passada, cancelada, realizada):
        assert not pode_lembrar(sessao)
        html = cliente_logado.get(reverse("sessao_detalhe", args=[sessao.pk])).content.decode()
        assert "Lembrar pelo WhatsApp" not in html and "wa.me" not in html
    assert pode_lembrar(futura)


def test_telefone_invalido_mostra_botao_desativado_com_aviso(cliente_logado, paciente, futura):
    paciente.telefone = "9999-0001"
    paciente.save()
    html = cliente_logado.get(reverse("sessao_detalhe", args=[futura.pk])).content.decode()
    assert "Lembrar pelo WhatsApp" in html and "wa.me" not in html
    assert "disabled" in html
    assert "Telefone do paciente em formato inválido para WhatsApp" in html
    assert reverse("paciente_editar", args=[paciente.pk]) in html


# --- Lembretes de amanhã ------------------------------------------------------

def test_lembretes_de_amanha_so_agendadas_de_amanha_da_usuaria(cliente_logado, usuaria, outra_usuaria, paciente):
    beatriz = Paciente.objects.create(usuario=usuaria, nome="Beatriz R.", telefone="(21) 98888-7777", valor_sessao=150)
    amanha_1 = agendar_sessao(paciente, em(1, 9))
    amanha_2 = agendar_sessao(beatriz, em(1, 15, 30))
    cancelada = agendar_sessao(paciente, em(1, 11))
    cancelada.status = Sessao.CANCELADA
    cancelada.save()
    agendar_sessao(paciente, em(0, 23, 30))
    agendar_sessao(paciente, em(2, 0, 0))
    agendar_sessao(paciente, em(2, 9))
    alheio = Paciente.objects.create(usuario=outra_usuaria, nome="Paciente Alheio", telefone="11977776666", valor_sessao=90)
    agendar_sessao(alheio, em(1, 13))

    resp = cliente_logado.get(reverse("agenda"))
    lista = resp.context["lembretes_amanha"]
    assert [item["sessao"].pk for item in lista] == [amanha_1.pk, amanha_2.pk]
    html = resp.content.decode()
    assert "Lembretes de amanhã" in html
    assert "https://wa.me/5511999990001?text=" in html and "https://wa.me/5521988887777?text=" in html
    assert "Paciente Alheio" not in html and "5511977776666" not in html


def test_lembretes_de_amanha_aparecem_em_qualquer_semana_e_somem_sem_sessoes(cliente_logado, paciente):
    assert "Lembretes de amanhã" not in cliente_logado.get(reverse("agenda")).content.decode()
    agendar_sessao(paciente, em(1, 9))
    html = cliente_logado.get(reverse("agenda") + "?semana=2020-01-06").content.decode()
    assert "Lembretes de amanhã" in html


# --- Marcar lembrete como enviado ---------------------------------------------

def test_marcar_enviado_por_post(cliente_logado, futura):
    url = reverse("sessao_lembrete_enviado", args=[futura.pk])
    resp = cliente_logado.post(url)
    assert resp.status_code == 302 and resp.url == reverse("sessao_detalhe", args=[futura.pk])
    futura.refresh_from_db()
    assert futura.lembrete_enviado_em is not None
    html = cliente_logado.get(resp.url).content.decode()
    assert f"Lembrete enviado em {timezone.localtime(futura.lembrete_enviado_em):%d/%m %H:%M}" in html


def test_marcar_enviado_volta_para_a_agenda_e_ignora_destino_externo(cliente_logado, futura):
    url = reverse("sessao_lembrete_enviado", args=[futura.pk])
    agenda = reverse("agenda") + "?semana=2030-01-07"
    assert cliente_logado.post(url, {"proximo": agenda}).url == agenda
    resp = cliente_logado.post(url, {"proximo": "https://exemplo.com/roubo"})
    assert resp.url == reverse("sessao_detalhe", args=[futura.pk])


def test_marcar_enviado_so_aceita_post(cliente_logado, futura):
    resp = cliente_logado.get(reverse("sessao_lembrete_enviado", args=[futura.pk]))
    assert resp.status_code == 405
    futura.refresh_from_db()
    assert futura.lembrete_enviado_em is None


def test_marcar_enviado_de_outra_usuaria_da_404(client, outra_usuaria, futura):
    client.force_login(outra_usuaria)
    assert client.post(reverse("sessao_lembrete_enviado", args=[futura.pk])).status_code == 404
    futura.refresh_from_db()
    assert futura.lembrete_enviado_em is None


def test_marcar_enviado_exige_login(client, futura):
    resp = client.post(reverse("sessao_lembrete_enviado", args=[futura.pk]))
    assert resp.status_code == 302 and reverse("login") in resp.url
    futura.refresh_from_db()
    assert futura.lembrete_enviado_em is None


def test_marcar_enviado_recusa_sessao_cancelada(cliente_logado, futura):
    futura.status = Sessao.CANCELADA
    futura.save()
    resp = cliente_logado.post(reverse("sessao_lembrete_enviado", args=[futura.pk]), follow=True)
    assert "Só dá para marcar lembrete de sessão agendada." in resp.content.decode()
    futura.refresh_from_db()
    assert futura.lembrete_enviado_em is None


# --- Meu perfil ---------------------------------------------------------------

def test_perfil_salva_mensagem_e_lista_marcadores(cliente_logado, usuaria, futura):
    html = cliente_logado.get(reverse("perfil")).content.decode()
    for marcador in ("{paciente}", "{primeiro_nome}", "{data}", "{hora}", "{dia_semana}", "{profissional}"):
        assert marcador in html
    assert "Meta" in html
    resp = cliente_logado.post(reverse("perfil"), {"mensagem_lembrete": "  Oi {primeiro_nome}, até {data}!  "})
    assert resp.status_code == 302
    perfil = PerfilProfissional.objects.get(usuario=usuaria)
    assert perfil.mensagem_lembrete == "Oi {primeiro_nome}, até {data}!"
    html = cliente_logado.get(reverse("sessao_detalhe", args=[futura.pk])).content.decode()
    assert f"text={quote(f'Oi Carlos, até {timezone.localtime(futura.inicio):%d/%m}!', safe='')}" in html


def test_perfil_em_branco_volta_para_mensagem_padrao(cliente_logado, usuaria, futura):
    PerfilProfissional.objects.create(usuario=usuaria, mensagem_lembrete="Antiga")
    cliente_logado.post(reverse("perfil"), {"mensagem_lembrete": ""})
    assert PerfilProfissional.objects.get(usuario=usuaria).mensagem_lembrete == ""
    assert lembrete_whatsapp(futura, PerfilProfissional.objects.get(usuario=usuaria))["mensagem"].startswith("Olá, Carlos!")
    assert MENSAGEM_LEMBRETE_PADRAO.startswith("Olá, {primeiro_nome}!")


def test_perfil_recusa_mensagem_longa_demais(cliente_logado, usuaria):
    resp = cliente_logado.post(reverse("perfil"), {"mensagem_lembrete": "a" * 1001})
    assert resp.status_code == 200
    assert not PerfilProfissional.objects.filter(usuario=usuaria).exists()
