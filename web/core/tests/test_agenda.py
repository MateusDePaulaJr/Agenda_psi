from datetime import datetime, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import Pagamento, Paciente, Sessao
from core.services import HorarioOcupado, agendar_sessao


def em(dias, hora, minuto=0):
    base = timezone.localdate() + timedelta(days=dias)
    return timezone.make_aware(datetime.combine(base, datetime.min.time()).replace(hour=hora, minute=minuto))


@pytest.fixture
def beatriz(usuaria):
    return Paciente.objects.create(usuario=usuaria, nome="Beatriz R.", telefone="11999990002", valor_sessao=150)


# ---- Testes unitários da regra de negócio (RF04) ----

def test_agendar_cria_sessao_e_pagamento_a_receber(paciente):
    sessao = agendar_sessao(paciente, em(3, 14))
    assert sessao.pagamento.status == Pagamento.A_RECEBER
    assert sessao.pagamento.valor == paciente.valor_sessao


@pytest.mark.parametrize("hora,minuto", [(14, 0), (14, 30), (13, 20)])
def test_horario_sobreposto_e_bloqueado(paciente, beatriz, hora, minuto):
    agendar_sessao(paciente, em(3, 14))
    with pytest.raises(HorarioOcupado) as erro:
        agendar_sessao(beatriz, em(3, hora, minuto))
    assert "Carlos M." in str(erro.value)
    assert Sessao.objects.count() == 1
    assert Pagamento.objects.count() == 1


def test_horario_logo_apos_o_fim_e_permitido(paciente, beatriz):
    agendar_sessao(paciente, em(3, 14))
    agendar_sessao(beatriz, em(3, 14, 50))
    assert Sessao.objects.count() == 2


def test_sessao_cancelada_libera_horario(paciente, beatriz):
    s = agendar_sessao(paciente, em(3, 14))
    s.status = Sessao.CANCELADA
    s.save()
    agendar_sessao(beatriz, em(3, 14))
    assert Sessao.objects.exclude(status=Sessao.CANCELADA).count() == 1


def test_conflito_so_considera_a_mesma_usuaria(paciente, outra_usuaria):
    agendar_sessao(paciente, em(3, 14))
    p2 = Paciente.objects.create(usuario=outra_usuaria, nome="Z", telefone="3", valor_sessao=90)
    agendar_sessao(p2, em(3, 14))
    assert Sessao.objects.count() == 2


# ---- Testes de integração (view + banco) ----

def test_fluxo_agendar_pela_tela(cliente_logado, beatriz):
    d = em(4, 10)
    resp = cliente_logado.post(reverse("sessao_nova"), {
        "paciente": beatriz.pk, "data": d.date().isoformat(), "horario": "10:00", "duracao_minutos": 50,
    })
    sessao = Sessao.objects.get()
    assert resp.status_code == 302 and resp["Location"] == reverse("sessao_detalhe", args=[sessao.pk])
    agenda = cliente_logado.get(reverse("agenda") + f"?semana={d.date().isoformat()}").content.decode()
    assert "Beatriz R." in agenda and "A receber" in agenda


def test_tela_mostra_alerta_de_conflito_e_sugestoes(cliente_logado, paciente, beatriz):
    agendar_sessao(paciente, em(4, 14))
    resp = cliente_logado.post(reverse("sessao_nova"), {
        "paciente": beatriz.pk, "data": em(4, 14).date().isoformat(), "horario": "14:30", "duracao_minutos": 50,
    })
    html = resp.content.decode()
    assert "Horário indisponível" in html and 'role="alert"' in html
    assert "Horários livres neste dia" in html
    assert Sessao.objects.count() == 1


def test_data_passada_e_recusada(cliente_logado, beatriz):
    ontem = timezone.localdate() - timedelta(days=1)
    resp = cliente_logado.post(reverse("sessao_nova"), {
        "paciente": beatriz.pk, "data": ontem.isoformat(), "horario": "10:00", "duracao_minutos": 50,
    })
    assert "precisam ser futuros" in resp.content.decode()
    assert Sessao.objects.count() == 0


def test_nao_agenda_paciente_de_outra_usuaria(client, outra_usuaria, paciente):
    client.force_login(outra_usuaria)
    client.post(reverse("sessao_nova"), {
        "paciente": paciente.pk, "data": em(4, 10).date().isoformat(), "horario": "10:00", "duracao_minutos": 50,
    })
    assert Sessao.objects.count() == 0


def test_detalhe_de_sessao_alheia_retorna_404(client, outra_usuaria, paciente):
    s = agendar_sessao(paciente, em(3, 9))
    client.force_login(outra_usuaria)
    assert client.get(reverse("sessao_detalhe", args=[s.pk])).status_code == 404


def test_cancelar_sessao(cliente_logado, paciente):
    s = agendar_sessao(paciente, em(3, 9))
    cliente_logado.post(reverse("sessao_cancelar", args=[s.pk]))
    s.refresh_from_db()
    assert s.status == Sessao.CANCELADA
