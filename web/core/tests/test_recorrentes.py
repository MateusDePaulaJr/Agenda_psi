"""Sessões recorrentes (semanal/quinzenal): tudo ou nada, isolamento e cancelamento da série."""
from datetime import datetime, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.forms import SessaoForm
from core.models import Paciente, Pagamento, Sessao
from core.services import (
    HorarioOcupado,
    SerieComConflito,
    agendar_serie,
    agendar_sessao,
    cancelar_serie_a_partir_de,
    datas_da_serie,
)


def em(dias, hora, minuto=0):
    base = timezone.localdate() + timedelta(days=dias)
    return timezone.make_aware(datetime.combine(base, datetime.min.time()).replace(hour=hora, minute=minuto))


@pytest.fixture
def beatriz(usuaria):
    return Paciente.objects.create(usuario=usuaria, nome="Beatriz R.", telefone="11999990002", valor_sessao=150)


def dados_form(paciente, inicio, repetir="", quantidade="", **extra):
    local = timezone.localtime(inicio)
    return {
        "paciente": paciente.pk, "data": local.date().isoformat(), "horario": f"{local:%H:%M}",
        "duracao_minutos": 50, "repetir": repetir, "quantidade": quantidade, **extra,
    }


# ---- Regra de negócio ----

def test_serie_semanal_cria_n_sessoes_e_pagamentos(paciente):
    sessoes = agendar_serie(paciente, em(2, 14), 50, "Terapia", 7, 4)
    assert len(sessoes) == 4
    assert Sessao.objects.count() == 4 and Pagamento.objects.count() == 4
    inicios = [timezone.localtime(s.inicio) for s in Sessao.objects.order_by("inicio")]
    assert inicios[0] == timezone.localtime(em(2, 14))
    assert all((b - a) == timedelta(days=7) for a, b in zip(inicios, inicios[1:]))
    assert all(i.hour == 14 and i.minute == 0 for i in inicios)
    series = set(Sessao.objects.values_list("serie", flat=True))
    assert len(series) == 1 and None not in series
    for s in Sessao.objects.all():
        assert s.pagamento.status == Pagamento.A_RECEBER and s.pagamento.valor == paciente.valor_sessao
        assert s.observacao == "Terapia" and s.status == Sessao.AGENDADA


def test_serie_quinzenal_tem_14_dias_entre_sessoes(paciente):
    agendar_serie(paciente, em(1, 9), 50, "", 14, 3)
    inicios = list(Sessao.objects.order_by("inicio").values_list("inicio", flat=True))
    assert [b - a for a, b in zip(inicios, inicios[1:])] == [timedelta(days=14)] * 2


def test_datas_mantem_horario_local():
    datas = datas_da_serie(em(1, 8, 30), 7, 24)
    assert len(datas) == 24
    assert all((timezone.localtime(d).hour, timezone.localtime(d).minute) == (8, 30) for d in datas)


def test_conflito_em_qualquer_data_nao_cria_nada(paciente, beatriz):
    agendar_sessao(beatriz, em(2 + 7, 14, 30))
    agendar_sessao(beatriz, em(2 + 21, 13, 30))
    with pytest.raises(SerieComConflito) as erro:
        agendar_serie(paciente, em(2, 14), 50, "", 7, 4)
    assert Sessao.objects.count() == 2 and Pagamento.objects.count() == 2
    datas = [timezone.localtime(i).date() for i, _ in erro.value.conflitos]
    assert datas == [em(9, 14).date(), em(23, 14).date()]
    assert all(ocupante.paciente == beatriz for _, ocupante in erro.value.conflitos)
    texto = str(erro.value)
    assert "2 datas" in texto and f"{em(9, 14):%d/%m}" in texto and f"{em(23, 14):%d/%m}" in texto
    # Também é um HorarioOcupado (mesmo estilo de erro).
    assert isinstance(erro.value, HorarioOcupado) and erro.value.conflito.paciente == beatriz


def test_mensagem_no_singular_quando_uma_data_conflita(paciente, beatriz):
    agendar_sessao(beatriz, em(9, 14))
    with pytest.raises(SerieComConflito) as erro:
        agendar_serie(paciente, em(2, 14), 50, "", 7, 2)
    assert str(erro.value).startswith("1 data da série já está ocupada")


def test_serie_ignora_sessoes_de_outra_usuaria(paciente, outra_usuaria):
    alheio = Paciente.objects.create(usuario=outra_usuaria, nome="Z", telefone="3", valor_sessao=90)
    agendar_sessao(alheio, em(9, 14))
    agendar_serie(paciente, em(2, 14), 50, "", 7, 3)
    assert Sessao.objects.filter(paciente=paciente).count() == 3


def test_sessoes_canceladas_nao_bloqueiam_a_serie(paciente, beatriz):
    s = agendar_sessao(beatriz, em(9, 14))
    s.status = Sessao.CANCELADA
    s.save()
    agendar_serie(paciente, em(2, 14), 50, "", 7, 2)
    assert Sessao.objects.filter(paciente=paciente).count() == 2


def test_corrida_durante_a_criacao_desfaz_toda_a_serie(paciente, beatriz, monkeypatch):
    """Se outra requisição ocupar um horário depois da verificação, nada fica salvo."""
    import core.services as services

    original = services.agendar_sessao
    chamadas = []

    def agendar_com_corrida(pac, inicio, *args, **kwargs):
        chamadas.append(inicio)
        if len(chamadas) == 3:
            outra = Sessao.objects.create(paciente=beatriz, inicio=inicio)
            raise HorarioOcupado(outra)
        return original(pac, inicio, *args, **kwargs)

    monkeypatch.setattr(services, "agendar_sessao", agendar_com_corrida)
    with pytest.raises(SerieComConflito) as erro:
        agendar_serie(paciente, em(2, 14), 50, "", 7, 4)
    assert erro.value.conflitos[0][0] == chamadas[2]
    assert Sessao.objects.count() == 0 and Pagamento.objects.count() == 0


@pytest.mark.parametrize("quantidade", [1, 25])
def test_servico_recusa_quantidade_fora_dos_limites(paciente, quantidade):
    with pytest.raises(ValueError):
        agendar_serie(paciente, em(2, 14), 50, "", 7, quantidade)
    assert not Sessao.objects.exists()


def test_posicao_na_serie(paciente):
    sessoes = agendar_serie(paciente, em(2, 14), 50, "", 7, 4)
    assert [s.posicao_na_serie() for s in sessoes] == [(1, 4), (2, 4), (3, 4), (4, 4)]
    assert agendar_sessao(paciente, em(1, 8)).posicao_na_serie() is None


def test_cancelar_esta_e_as_proximas_so_mexe_nas_futuras_agendadas(paciente, beatriz):
    sessoes = agendar_serie(paciente, em(2, 14), 50, "", 7, 5)
    avulsa = agendar_sessao(paciente, em(40, 14))
    s1, s2, s3, s4, s5 = sessoes
    Sessao.objects.filter(pk=s4.pk).update(status=Sessao.REALIZADA)
    Sessao.objects.filter(pk=s5.pk).update(status=Sessao.FALTA)
    assert cancelar_serie_a_partir_de(s2) == 2
    status = dict(Sessao.objects.values_list("pk", "status"))
    assert status[s1.pk] == Sessao.AGENDADA
    assert status[s2.pk] == status[s3.pk] == Sessao.CANCELADA
    assert status[s4.pk] == Sessao.REALIZADA and status[s5.pk] == Sessao.FALTA
    assert status[avulsa.pk] == Sessao.AGENDADA
    # Os horários ficaram livres para outro paciente.
    agendar_sessao(beatriz, s2.inicio)
    agendar_sessao(beatriz, s3.inicio)


def test_cancelar_serie_nao_mexe_em_sessoes_passadas(paciente):
    sessoes = agendar_serie(paciente, em(2, 14), 50, "", 7, 3)
    s1, s2, s3 = sessoes
    # Simula a primeira sessão já no passado e a segunda também (ainda "agendada").
    Sessao.objects.filter(pk=s1.pk).update(inicio=em(-14, 14))
    Sessao.objects.filter(pk=s2.pk).update(inicio=em(-7, 14))
    s1.refresh_from_db()
    assert cancelar_serie_a_partir_de(s1) == 2  # s1 (a escolhida) e s3 (futura); s2 já passou
    status = dict(Sessao.objects.values_list("pk", "status"))
    assert status[s2.pk] == Sessao.AGENDADA


def test_cancelar_serie_de_sessao_avulsa_ou_nao_agendada_nao_faz_nada(paciente):
    avulsa = agendar_sessao(paciente, em(1, 8))
    assert cancelar_serie_a_partir_de(avulsa) == 0
    s1, s2 = agendar_serie(paciente, em(2, 14), 50, "", 7, 2)
    s1.status = Sessao.REALIZADA
    s1.save()
    assert cancelar_serie_a_partir_de(s1) == 0
    s2.refresh_from_db()
    assert s2.status == Sessao.AGENDADA


# ---- Formulário ----

@pytest.mark.parametrize("quantidade,valido", [("1", False), ("2", True), ("24", True), ("25", False)])
def test_form_valida_limites_da_quantidade(usuaria, paciente, quantidade, valido):
    form = SessaoForm(dados_form(paciente, em(2, 14), "semanal", quantidade), usuario=usuaria)
    assert form.is_valid() is valido
    if not valido:
        assert "Informe de 2 a 24 sessões." in form.errors["quantidade"]


def test_form_usa_4_sessoes_quando_quantidade_vazia(usuaria, paciente):
    form = SessaoForm(dados_form(paciente, em(2, 14), "quinzenal", ""), usuario=usuaria)
    assert form.is_valid() and form.cleaned_data["quantidade"] == 4


def test_form_ignora_quantidade_sem_repeticao(usuaria, paciente):
    form = SessaoForm(dados_form(paciente, em(2, 14), "", "99"), usuario=usuaria)
    assert form.is_valid() and form.cleaned_data["quantidade"] == 1


def test_form_quantidade_invalida_nao_quebra(usuaria, paciente):
    form = SessaoForm(dados_form(paciente, em(2, 14), "semanal", "abc"), usuario=usuaria)
    assert not form.is_valid() and "quantidade" in form.errors


def test_form_recusa_repeticao_desconhecida(usuaria, paciente):
    form = SessaoForm(dados_form(paciente, em(2, 14), "diaria", "4"), usuario=usuaria)
    assert not form.is_valid() and "repetir" in form.errors


# ---- Telas (cliente HTTP) ----

def test_tela_tem_campos_de_repeticao(cliente_logado):
    html = cliente_logado.get(reverse("sessao_nova")).content.decode()
    assert 'id="id_repetir"' in html and 'id="campo-quantidade"' in html
    assert "Não repetir" in html and "quinzenal" in html and 'value="4"' in html


def test_tela_agenda_serie_e_redireciona_para_semana_da_primeira(cliente_logado, paciente):
    inicio = em(3, 10)
    resp = cliente_logado.post(reverse("sessao_nova"), dados_form(paciente, inicio, "semanal", "4"))
    sessoes = list(Sessao.objects.order_by("inicio"))
    assert len(sessoes) == 4 and Pagamento.objects.count() == 4
    esperado = f"{reverse('agenda')}?semana={inicio.date().isoformat()}&destaque={sessoes[0].pk}"
    assert resp.status_code == 302 and resp["Location"] == esperado
    pagina = cliente_logado.get(resp["Location"]).content.decode()
    ultima = timezone.localtime(sessoes[-1].inicio)
    assert f"4 sessões agendadas (semanal, até {ultima:%d/%m})." in pagina
    assert "sessão recorrente" in pagina


def test_tela_quinzenal(cliente_logado, paciente):
    resp = cliente_logado.post(reverse("sessao_nova"), dados_form(paciente, em(3, 10), "quinzenal", "2"))
    s1, s2 = Sessao.objects.order_by("inicio")
    assert s2.inicio - s1.inicio == timedelta(days=14)
    pagina = cliente_logado.get(resp["Location"]).content.decode()
    assert "2 sessões agendadas (quinzenal, até" in pagina


def test_tela_conflito_lista_datas_e_mantem_formulario(cliente_logado, paciente, beatriz):
    ocupada = agendar_sessao(beatriz, em(10, 10, 30))
    resp = cliente_logado.post(
        reverse("sessao_nova"), dados_form(paciente, em(3, 10), "semanal", "4", observacao="Nova série")
    )
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Horário indisponível" in html and "Nada foi salvo" in html
    assert f"{timezone.localtime(ocupada.inicio):%d/%m/%Y}" in html and "ocupado por Beatriz R." in html
    assert "10h30–11h20" in html
    assert 'value="Nova série"' in html and '<option value="semanal" selected>' in html
    assert Sessao.objects.count() == 1


def test_tela_quantidade_fora_do_limite_mostra_erro(cliente_logado, paciente):
    resp = cliente_logado.post(reverse("sessao_nova"), dados_form(paciente, em(3, 10), "semanal", "30"))
    assert resp.status_code == 200 and "Informe de 2 a 24 sessões." in resp.content.decode()
    assert not Sessao.objects.exists()


def test_tela_sem_repeticao_continua_igual(cliente_logado, paciente):
    resp = cliente_logado.post(reverse("sessao_nova"), dados_form(paciente, em(3, 10)))
    sessao = Sessao.objects.get()
    assert resp["Location"] == reverse("sessao_detalhe", args=[sessao.pk])
    assert sessao.serie is None and sessao.pagamento.status == Pagamento.A_RECEBER
    html = cliente_logado.get(resp["Location"]).content.decode()
    assert "da série" not in html


def test_detalhe_mostra_posicao_e_botao_da_serie(cliente_logado, paciente):
    sessoes = agendar_serie(paciente, em(2, 14), 50, "", 7, 4)
    html = cliente_logado.get(reverse("sessao_detalhe", args=[sessoes[1].pk])).content.decode()
    assert "Sessão 2 de 4 da série" in html
    assert "Cancelar esta e as próximas da série" in html and "Cancelar sessão" in html


def test_detalhe_sem_botao_da_serie_quando_ja_realizada(cliente_logado, paciente):
    sessoes = agendar_serie(paciente, em(2, 14), 50, "", 7, 2)
    Sessao.objects.filter(pk=sessoes[0].pk).update(status=Sessao.REALIZADA)
    html = cliente_logado.get(reverse("sessao_detalhe", args=[sessoes[0].pk])).content.decode()
    assert "Sessão 1 de 2 da série" in html and "Cancelar esta e as próximas" not in html


def test_tela_cancelar_esta_e_as_proximas(cliente_logado, paciente):
    s1, s2, s3 = agendar_serie(paciente, em(2, 14), 50, "", 7, 3)
    resp = cliente_logado.post(reverse("sessao_cancelar_serie", args=[s2.pk]))
    assert resp.status_code == 302
    assert resp["Location"] == f"{reverse('agenda')}?semana={timezone.localtime(s2.inicio).date().isoformat()}"
    status = dict(Sessao.objects.values_list("pk", "status"))
    assert status == {s1.pk: Sessao.AGENDADA, s2.pk: Sessao.CANCELADA, s3.pk: Sessao.CANCELADA}
    assert "2 sessões da série canceladas" in cliente_logado.get(resp["Location"]).content.decode()


def test_tela_cancelar_serie_da_ultima_usa_singular(cliente_logado, paciente):
    _, s2 = agendar_serie(paciente, em(2, 14), 50, "", 7, 2)
    resp = cliente_logado.post(reverse("sessao_cancelar_serie", args=[s2.pk]), follow=True)
    assert "1 sessão da série cancelada." in resp.content.decode()


def test_tela_cancelar_serie_sem_nada_para_cancelar(cliente_logado, paciente):
    avulsa = agendar_sessao(paciente, em(2, 14))
    resp = cliente_logado.post(reverse("sessao_cancelar_serie", args=[avulsa.pk]))
    assert resp["Location"] == reverse("sessao_detalhe", args=[avulsa.pk])
    avulsa.refresh_from_db()
    assert avulsa.status == Sessao.AGENDADA


def test_cancelar_serie_por_get_nao_altera(cliente_logado, paciente):
    s1, _ = agendar_serie(paciente, em(2, 14), 50, "", 7, 2)
    resp = cliente_logado.get(reverse("sessao_cancelar_serie", args=[s1.pk]))
    assert resp["Location"] == reverse("sessao_detalhe", args=[s1.pk])
    assert not Sessao.objects.filter(status=Sessao.CANCELADA).exists()


def test_cancelar_serie_de_outra_usuaria_da_404(client, outra_usuaria, paciente):
    s1, _ = agendar_serie(paciente, em(2, 14), 50, "", 7, 2)
    client.force_login(outra_usuaria)
    assert client.post(reverse("sessao_cancelar_serie", args=[s1.pk])).status_code == 404
    assert not Sessao.objects.filter(status=Sessao.CANCELADA).exists()


def test_cancelar_serie_exige_login(client, paciente):
    s1, _ = agendar_serie(paciente, em(2, 14), 50, "", 7, 2)
    resp = client.post(reverse("sessao_cancelar_serie", args=[s1.pk]))
    assert resp.status_code == 302 and "/login/" in resp["Location"]
    assert not Sessao.objects.filter(status=Sessao.CANCELADA).exists()
