import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import Paciente, Pagamento, PerfilProfissional, Prontuario, Sessao
from core.services import agendar_sessao, formatar_moeda, gerar_csv_financeiro, numero_recibo
from core.templatetags.psiagenda import moeda

SEGREDO_CLINICO = "Relato clínico confidencial XYZ"


def no_dia(dia, hora, minuto=0):
    return timezone.make_aware(datetime.combine(dia, datetime.min.time()).replace(hour=hora, minute=minuto))


def marcar_pago(sessao, dia=date(2026, 3, 12), forma="pix"):
    pagamento = sessao.pagamento
    pagamento.status, pagamento.data_pagamento, pagamento.forma_pagamento = Pagamento.PAGO, dia, forma
    pagamento.save()
    return pagamento


@pytest.fixture
def sessao_paga(usuaria, paciente):
    usuaria.first_name, usuaria.last_name = "Ana", "Souza"
    usuaria.save()
    paciente.valor_sessao = Decimal("1234.56")
    paciente.save()
    sessao = agendar_sessao(paciente, no_dia(date(2026, 3, 10), 14, 30), duracao_minutos=50)
    marcar_pago(sessao)
    return sessao


def ler_csv(resposta):
    texto = resposta.content.decode("utf-8")
    assert texto.startswith("﻿")
    return list(csv.reader(io.StringIO(texto[1:]), delimiter=";"))


# --- Formatação ---------------------------------------------------------------

def test_formatar_moeda_no_padrao_brasileiro():
    assert formatar_moeda(Decimal("1234.56")) == "R$ 1.234,56"
    assert formatar_moeda(Decimal("150")) == "R$ 150,00"
    assert formatar_moeda(Decimal("1234567.8"), simbolo=False) == "1.234.567,80"
    assert formatar_moeda(None) == "" and formatar_moeda("abc") == ""
    assert moeda(Decimal("99.9")) == "R$ 99,90"


def test_numero_do_recibo_usa_ano_do_pagamento_e_id(sessao_paga):
    pagamento = sessao_paga.pagamento
    assert numero_recibo(pagamento) == f"2026-{pagamento.pk:06d}"
    pagamento.data_pagamento = None
    assert numero_recibo(pagamento) == f"{timezone.localdate().year}-{pagamento.pk:06d}"


# --- Recibo -------------------------------------------------------------------

def test_detalhe_mostra_botao_recibo_so_quando_pago(cliente_logado, paciente, sessao_paga):
    url_recibo = reverse("recibo", args=[sessao_paga.pk])
    assert url_recibo in cliente_logado.get(reverse("sessao_detalhe", args=[sessao_paga.pk])).content.decode()
    pendente = agendar_sessao(paciente, no_dia(date(2026, 3, 11), 9))
    html = cliente_logado.get(reverse("sessao_detalhe", args=[pendente.pk])).content.decode()
    assert reverse("recibo", args=[pendente.pk]) not in html


def test_recibo_de_sessao_paga(cliente_logado, sessao_paga):
    resp = cliente_logado.get(reverse("recibo", args=[sessao_paga.pk]))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Ana Souza" in html and "Carlos M." in html
    assert "R$ 1.234,56" in html
    assert "10/03/2026" in html and "14:30" in html and "15:20" in html and "50 minutos" in html
    assert "12/03/2026" in html and "Pix" in html
    assert f"2026-{sessao_paga.pagamento.pk:06d}" in html
    assert "window.print()" in html and "Salvar PDF" in html
    assert "pa-recibo-assinatura" in html


def test_recibo_sem_perfil_omite_campos_opcionais(cliente_logado, sessao_paga):
    html = cliente_logado.get(reverse("recibo", args=[sessao_paga.pk])).content.decode()
    assert "CRP" not in html and "CPF/CNPJ" not in html
    # Sem cidade, a linha de local e data começa direto pela data.
    assert '<p class="pa-recibo-local">12 de' in html


def test_recibo_mostra_campos_do_perfil(cliente_logado, usuaria, sessao_paga):
    PerfilProfissional.objects.create(
        usuario=usuaria, nome_exibicao="Dra. Ana P. Souza", crp="06/123456", documento="123.456.789-00", cidade="Campinas/SP"
    )
    html = cliente_logado.get(reverse("recibo", args=[sessao_paga.pk])).content.decode()
    assert "Dra. Ana P. Souza" in html
    assert "CRP 06/123456" in html and "CPF/CNPJ: 123.456.789-00" in html
    assert "Campinas/SP, 12 de março de 2026." in html


def test_recibo_com_perfil_parcial_omite_so_o_que_falta(cliente_logado, usuaria, sessao_paga):
    PerfilProfissional.objects.create(usuario=usuaria, crp="06/999")
    html = cliente_logado.get(reverse("recibo", args=[sessao_paga.pk])).content.decode()
    assert "Ana Souza" in html and "CRP 06/999" in html
    assert "CPF/CNPJ" not in html


def test_recibo_usa_username_sem_nome_completo(cliente_logado, usuaria, paciente):
    sessao = agendar_sessao(paciente, no_dia(date(2026, 3, 10), 9))
    marcar_pago(sessao, forma="")
    html = cliente_logado.get(reverse("recibo", args=[sessao.pk])).content.decode()
    assert '<p class="pa-recibo-nome">ana</p>' in html
    assert "Forma de pagamento" not in html


def test_recibo_nao_contem_prontuario_nem_observacao(cliente_logado, paciente):
    sessao = agendar_sessao(paciente, no_dia(date(2026, 3, 10), 9), observacao="Observação interna ABC")
    Prontuario.objects.create(sessao=sessao, evolucao=SEGREDO_CLINICO)
    marcar_pago(sessao)
    html = cliente_logado.get(reverse("recibo", args=[sessao.pk])).content.decode()
    assert SEGREDO_CLINICO not in html and "Observação interna ABC" not in html
    assert "11999990001" not in html  # telefone do paciente também não aparece


def test_recibo_de_outra_usuaria_retorna_404(client, outra_usuaria, sessao_paga):
    client.force_login(outra_usuaria)
    assert client.get(reverse("recibo", args=[sessao_paga.pk])).status_code == 404


def test_recibo_de_sessao_inexistente_retorna_404(cliente_logado, db):
    assert cliente_logado.get(reverse("recibo", args=[999999])).status_code == 404


def test_recibo_de_pagamento_nao_pago_redireciona_com_aviso(cliente_logado, paciente):
    sessao = agendar_sessao(paciente, no_dia(date(2026, 3, 10), 9))
    resp = cliente_logado.get(reverse("recibo", args=[sessao.pk]), follow=True)
    assert resp.redirect_chain[-1][0] == reverse("sessao_detalhe", args=[sessao.pk])
    assert "só fica disponível depois que o pagamento" in resp.content.decode()


# --- Meu perfil ---------------------------------------------------------------

def test_menu_tem_link_para_meu_perfil(cliente_logado):
    assert reverse("perfil") in cliente_logado.get(reverse("agenda")).content.decode()


def test_perfil_cria_e_atualiza(cliente_logado, usuaria):
    assert cliente_logado.get(reverse("perfil")).status_code == 200
    dados = {"nome_exibicao": "  Ana Souza  ", "crp": "06/1", "documento": "", "cidade": "Santos"}
    resp = cliente_logado.post(reverse("perfil"), dados)
    assert resp.status_code == 302 and resp.url == reverse("perfil")
    perfil = PerfilProfissional.objects.get(usuario=usuaria)
    assert (perfil.nome_exibicao, perfil.crp, perfil.documento, perfil.cidade) == ("Ana Souza", "06/1", "", "Santos")

    cliente_logado.post(reverse("perfil"), {**dados, "crp": "06/2", "cidade": ""})
    assert PerfilProfissional.objects.count() == 1
    perfil.refresh_from_db()
    assert perfil.crp == "06/2" and perfil.cidade == ""
    html = cliente_logado.get(reverse("perfil")).content.decode()
    assert 'value="06/2"' in html and 'value="Ana Souza"' in html
    assert str(perfil) == "Perfil de ana"


def test_perfil_e_por_usuaria(client, usuaria, outra_usuaria):
    PerfilProfissional.objects.create(usuario=usuaria, crp="06/111")
    client.force_login(outra_usuaria)
    assert "06/111" not in client.get(reverse("perfil")).content.decode()
    client.post(reverse("perfil"), {"nome_exibicao": "", "crp": "06/222", "documento": "", "cidade": ""})
    assert PerfilProfissional.objects.get(usuario=usuaria).crp == "06/111"
    assert PerfilProfissional.objects.get(usuario=outra_usuaria).crp == "06/222"


def test_perfil_rejeita_valor_longo_demais(cliente_logado, usuaria):
    resp = cliente_logado.post(reverse("perfil"), {"crp": "9" * 30})
    assert resp.status_code == 200 and not PerfilProfissional.objects.filter(usuario=usuaria).exists()


# --- Exportação CSV -----------------------------------------------------------

def test_csv_do_mes(cliente_logado, usuaria, paciente):
    outro = Paciente.objects.create(usuario=usuaria, nome="=Rafael; S.", telefone="5", valor_sessao=Decimal("1234.5"))
    paga = agendar_sessao(paciente, no_dia(date(2026, 3, 10), 9))
    marcar_pago(paga, forma="transferencia")
    agendar_sessao(outro, no_dia(date(2026, 3, 20), 15, 30))
    cancelada = agendar_sessao(paciente, no_dia(date(2026, 3, 21), 9))
    cancelada.status = Sessao.CANCELADA
    cancelada.save()
    agendar_sessao(paciente, no_dia(date(2026, 4, 1), 9))  # outro mês
    agendar_sessao(paciente, no_dia(date(2026, 2, 28), 9))  # outro mês

    resp = cliente_logado.get(reverse("financeiro_csv") + "?mes=2026-3")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    assert resp["Content-Disposition"] == 'attachment; filename="financeiro-2026-03.csv"'
    linhas = ler_csv(resp)
    assert linhas[0] == [
        "Data da sessão", "Paciente", "Status da sessão", "Valor",
        "Status do pagamento", "Data do pagamento", "Forma de pagamento",
    ]
    assert linhas[1:] == [
        ["10/03/2026 09:00", "Carlos M.", "Agendada", "150,00", "Pago", "12/03/2026", "Transferência"],
        ["20/03/2026 15:30", "'=Rafael; S.", "Agendada", "1234,50", "A receber", "", ""],
    ]
    texto = resp.content.decode("utf-8")
    assert texto.splitlines()[0].count(";") == 6


def test_csv_so_tem_dados_da_usuaria(client, usuaria, outra_usuaria, paciente):
    agendar_sessao(paciente, no_dia(date(2026, 3, 10), 9))
    dela = Paciente.objects.create(usuario=outra_usuaria, nome="Paciente da Bia", telefone="7", valor_sessao=200)
    agendar_sessao(dela, no_dia(date(2026, 3, 11), 9))
    client.force_login(outra_usuaria)
    linhas = ler_csv(client.get(reverse("financeiro_csv") + "?mes=2026-03"))
    assert [linha[1] for linha in linhas[1:]] == ["Paciente da Bia"]


def test_csv_mes_invalido_usa_mes_atual(cliente_logado, db):
    hoje = timezone.localdate()
    for mes in ("2026-13", "abc", ""):
        resp = cliente_logado.get(reverse("financeiro_csv") + f"?mes={mes}")
        assert f"financeiro-{hoje.year:04d}-{hoje.month:02d}.csv" in resp["Content-Disposition"]
        assert len(ler_csv(resp)) == 1


def test_gerar_csv_sem_linhas_tem_so_cabecalho():
    texto = gerar_csv_financeiro([])
    assert texto.startswith("﻿Data da sessão;Paciente;") and texto.endswith("\r\n")


def test_financeiro_tem_botoes_exportar_e_imprimir(cliente_logado, db):
    html = cliente_logado.get(reverse("financeiro") + "?mes=2026-3").content.decode()
    assert reverse("financeiro_csv") + "?mes=2026-03" in html
    assert "Exportar CSV" in html and "window.print()" in html
    assert "pa-no-print" in html and 'value="2026-03"' in html


def test_css_de_impressao_esconde_menu_e_botoes(cliente_logado):
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "static" / "core" / "psiagenda.css").read_text(encoding="utf-8")
    assert "@media print" in css and ".pa-topbar" in css.split("@media print")[1]


# --- Login obrigatório --------------------------------------------------------

@pytest.mark.parametrize("nome,args", [("recibo", [1]), ("financeiro_csv", []), ("perfil", [])])
def test_novas_telas_exigem_login(client, db, nome, args):
    resp = client.get(reverse(nome, args=args))
    assert resp.status_code == 302 and resp.url.startswith(reverse("login"))
