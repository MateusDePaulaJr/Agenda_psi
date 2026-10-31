"""Painel (tela inicial): indicadores, listas, gráfico, isolamento por usuária e navegação."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import Paciente, Pagamento, PerfilProfissional, Sessao
from core.services import GRAFICO_BARRA_MAX, agendar_sessao, dados_painel

# Quarta-feira, 17/04/2030, 15h (horário de Brasília). Semana: 15/04 a 21/04.
AGORA = timezone.make_aware(datetime(2030, 4, 17, 15, 0))


def em(ano, mes, dia, hora, minuto=0):
    return timezone.make_aware(datetime(ano, mes, dia, hora, minuto))


def criar(paciente, inicio, status=Sessao.AGENDADA, pago=False):
    sessao = agendar_sessao(paciente, inicio)
    if status != Sessao.AGENDADA:
        sessao.status = status
        sessao.save(update_fields=["status"])
    if pago:
        Pagamento.objects.filter(sessao=sessao).update(status=Pagamento.PAGO, data_pagamento=inicio.date())
    return sessao


@pytest.fixture
def agora():
    with mock.patch("django.utils.timezone.now", return_value=AGORA):
        yield AGORA


@pytest.fixture
def logada(agora, client, usuaria):
    """Login feito já no horário simulado (senão a sessão de 30 minutos estaria expirada)."""
    client.force_login(usuaria)
    return client


@pytest.fixture
def paciente_da_outra(outra_usuaria):
    return Paciente.objects.create(usuario=outra_usuaria, nome="Outra Pessoa Z.", telefone="11999990009", valor_sessao=999)


def dados(usuaria):
    return dados_painel(usuaria, AGORA)


# --- Acesso e navegação -------------------------------------------------------

def test_login_abre_o_painel(client, usuaria):
    resp = client.post(reverse("login"), {"username": "ana", "password": "SenhaForte#2026"})
    assert resp.status_code == 302
    assert resp["Location"] == reverse("painel")


def test_painel_exige_login(client):
    resp = client.get(reverse("painel"))
    assert resp.status_code == 302
    assert reverse("login") in resp["Location"]


def test_menu_marca_painel_como_pagina_atual(cliente_logado):
    html = cliente_logado.get(reverse("painel")).content.decode()
    link = html.split('<nav class="pa-nav"', 1)[1].split("</a>", 1)[0]
    assert reverse("painel") in link and 'aria-current="page"' in link and "ativo" in link
    assert f'class="pa-brand" href="{reverse("painel")}"' in html


def test_painel_e_o_primeiro_item_do_menu_e_agenda_continua(cliente_logado):
    html = cliente_logado.get(reverse("agenda")).content.decode()
    nav = html.split('<nav class="pa-nav"', 1)[1].split("</nav>", 1)[0]
    assert nav.index(reverse("painel")) < nav.index('href="/"')
    primeiro = nav.split("</a>", 1)[0]
    assert "aria-current" not in primeiro  # na agenda, o Painel não é a página atual


# --- Indicadores ----------------------------------------------------------------

def test_sessoes_na_semana(usuaria, paciente):
    criar(paciente, em(2030, 4, 15, 8))                       # segunda, conta
    criar(paciente, em(2030, 4, 16, 10), Sessao.REALIZADA)    # conta
    criar(paciente, em(2030, 4, 18, 9), Sessao.FALTA)         # conta
    criar(paciente, em(2030, 4, 21, 23))                      # domingo à noite, conta
    criar(paciente, em(2030, 4, 19, 9), Sessao.CANCELADA)     # cancelada, não conta
    criar(paciente, em(2030, 4, 14, 23))                      # domingo anterior
    criar(paciente, em(2030, 4, 22, 0))                       # segunda seguinte, 0h
    assert dados(usuaria)["sessoes_semana"] == 4


def test_recebido_e_a_receber_no_mes(usuaria, paciente):
    criar(paciente, em(2030, 4, 2, 10), Sessao.REALIZADA, pago=True)
    criar(paciente, em(2030, 4, 30, 23), Sessao.AGENDADA, pago=True)   # pago adiantado, mês atual
    criar(paciente, em(2030, 4, 10, 10), Sessao.REALIZADA)            # a receber
    criar(paciente, em(2030, 4, 25, 10))                              # a receber (futura)
    criar(paciente, em(2030, 4, 11, 10), Sessao.CANCELADA, pago=True)  # cancelada: fora
    criar(paciente, em(2030, 4, 12, 10), Sessao.CANCELADA)             # cancelada: fora
    criar(paciente, em(2030, 3, 31, 23), Sessao.REALIZADA, pago=True)  # mês anterior
    criar(paciente, em(2030, 5, 1, 0))                                 # mês seguinte
    d = dados(usuaria)
    assert d["recebido_mes"] == Decimal("300.00")
    assert d["a_receber_mes"] == Decimal("300.00")


def test_valores_zerados_sem_dados(usuaria):
    d = dados(usuaria)
    assert d["recebido_mes"] == Decimal("0") and d["a_receber_mes"] == Decimal("0")
    assert d["sessoes_semana"] == 0 and d["pacientes_ativos"] == 0
    assert d["sessoes_hoje"] == [] and d["proximas"] == [] and d["pendentes"] == []
    assert d["lembretes_amanha"] == 0 and d["total_pendentes"] == 0


def test_taxa_de_comparecimento_nos_ultimos_30_dias(usuaria, paciente):
    criar(paciente, em(2030, 4, 1, 10), Sessao.REALIZADA)
    criar(paciente, em(2030, 4, 8, 10), Sessao.REALIZADA)
    criar(paciente, em(2030, 4, 17, 9), Sessao.REALIZADA)   # hoje cedo
    criar(paciente, em(2030, 4, 3, 10), Sessao.FALTA)
    criar(paciente, em(2030, 3, 18, 14), Sessao.FALTA)      # 30 dias e 1h atrás: fora
    criar(paciente, em(2030, 4, 5, 10), Sessao.CANCELADA)   # não entra na conta
    criar(paciente, em(2030, 4, 9, 10))                     # agendada passada: não entra
    d = dados(usuaria)
    assert (d["realizadas_30_dias"], d["faltas_30_dias"]) == (3, 1)
    assert d["taxa_comparecimento"] == 75


def test_taxa_de_comparecimento_arredonda(usuaria, paciente):
    criar(paciente, em(2030, 4, 1, 10), Sessao.REALIZADA)
    criar(paciente, em(2030, 4, 2, 10), Sessao.REALIZADA)
    criar(paciente, em(2030, 4, 3, 10), Sessao.FALTA)
    assert dados(usuaria)["taxa_comparecimento"] == 67


def test_taxa_de_comparecimento_sem_dados(usuaria, paciente, logada):
    criar(paciente, em(2030, 4, 9, 10))  # só agendada: não conta
    assert dados(usuaria)["taxa_comparecimento"] is None
    html = logada.get(reverse("painel")).content.decode()
    assert "Comparecimento (30 dias)</span>\n      <strong>—</strong>" in html


def test_pacientes_ativos(usuaria, paciente, paciente_da_outra):
    Paciente.objects.create(usuario=usuaria, nome="Inativo", telefone="11999990002", valor_sessao=100, ativo=False)
    Paciente.objects.create(usuario=usuaria, nome="Outro", telefone="11999990003", valor_sessao=100)
    assert dados(usuaria)["pacientes_ativos"] == 2


# --- Listas -------------------------------------------------------------------

def test_sessoes_de_hoje_em_ordem_sem_canceladas(usuaria, paciente):
    tarde = criar(paciente, em(2030, 4, 17, 18))
    cedo = criar(paciente, em(2030, 4, 17, 8), Sessao.REALIZADA, pago=True)
    falta = criar(paciente, em(2030, 4, 17, 10), Sessao.FALTA)
    criar(paciente, em(2030, 4, 17, 12), Sessao.CANCELADA)
    criar(paciente, em(2030, 4, 16, 23, 59))
    criar(paciente, em(2030, 4, 18, 0))
    hoje = dados(usuaria)["sessoes_hoje"]
    assert [i["sessao"] for i in hoje] == [cedo, falta, tarde]
    # Lembrete só para a sessão agendada que ainda vai acontecer.
    assert [i["lembrete"] is not None for i in hoje] == [False, False, True]
    assert hoje[2]["lembrete"]["url"].startswith("https://wa.me/5511999990001?text=")


def test_proximas_sessoes_cinco_a_partir_de_agora(usuaria, paciente):
    criar(paciente, em(2030, 4, 17, 14))                     # já começou: fora
    criar(paciente, em(2030, 4, 18, 9), Sessao.CANCELADA)    # cancelada: fora
    criar(paciente, em(2030, 4, 18, 11), Sessao.REALIZADA)   # não agendada: fora
    futuras = [criar(paciente, em(2030, 4, 17 + i, 16)) for i in range(7)]
    proximas = dados(usuaria)["proximas"]
    assert proximas == futuras[:5]


def test_pagamentos_pendentes_mais_antigos_de_sessoes_realizadas(usuaria, paciente):
    realizadas = [criar(paciente, em(2030, 1, 10 + i, 10), Sessao.REALIZADA) for i in range(7)]
    criar(paciente, em(2029, 12, 1, 10), Sessao.REALIZADA, pago=True)  # pago: fora
    criar(paciente, em(2029, 12, 2, 10), Sessao.FALTA)                 # falta: fora
    criar(paciente, em(2029, 12, 3, 10))                               # agendada: fora
    criar(paciente, em(2029, 12, 4, 10), Sessao.CANCELADA)             # cancelada: fora
    d = dados(usuaria)
    assert [p.sessao for p in d["pendentes"]] == realizadas[:5]
    assert d["total_pendentes"] == 7


def test_lembretes_de_amanha(usuaria, paciente):
    criar(paciente, em(2030, 4, 18, 9))
    criar(paciente, em(2030, 4, 18, 23))
    criar(paciente, em(2030, 4, 18, 11), Sessao.CANCELADA)
    criar(paciente, em(2030, 4, 19, 0))
    criar(paciente, em(2030, 4, 17, 20))
    assert dados(usuaria)["lembretes_amanha"] == 2


# --- Gráfico ------------------------------------------------------------------

def test_grafico_tem_seis_meses_com_meses_zerados(usuaria, paciente):
    criar(paciente, em(2029, 10, 31, 23), Sessao.REALIZADA, pago=True)  # antes da janela
    criar(paciente, em(2029, 11, 1, 0), Sessao.REALIZADA, pago=True)    # novembro
    criar(paciente, em(2029, 11, 20, 10), Sessao.REALIZADA, pago=True)
    criar(paciente, em(2030, 1, 15, 10), Sessao.REALIZADA, pago=True)
    criar(paciente, em(2030, 1, 16, 10), Sessao.REALIZADA)              # a receber: fora
    criar(paciente, em(2030, 2, 1, 10), Sessao.CANCELADA, pago=True)    # cancelada: fora
    criar(paciente, em(2030, 4, 30, 23), pago=True)                     # abril
    criar(paciente, em(2030, 5, 1, 10), pago=True)                      # maio: fora
    grafico = dados(usuaria)["grafico"]
    meses = grafico["meses"]
    assert [m["rotulo"] for m in meses] == ["nov/29", "dez/29", "jan/30", "fev/30", "mar/30", "abr/30"]
    assert [m["inicio"] for m in meses] == [date(2029, 11, 1), date(2029, 12, 1), date(2030, 1, 1),
                                            date(2030, 2, 1), date(2030, 3, 1), date(2030, 4, 1)]
    assert [m["valor"] for m in meses] == [Decimal("300"), 0, Decimal("150"), 0, 0, Decimal("150")]
    assert [m["largura"] for m in meses] == [GRAFICO_BARRA_MAX, 0, GRAFICO_BARRA_MAX / 2, 0, 0, GRAFICO_BARRA_MAX / 2]
    assert grafico["altura"] == 6 * 34


def test_grafico_vazio_nao_divide_por_zero(usuaria):
    meses = dados(usuaria)["grafico"]["meses"]
    assert len(meses) == 6 and all(m["valor"] == 0 and m["largura"] == 0 for m in meses)


def test_grafico_vira_o_ano(usuaria, paciente):
    with mock.patch("django.utils.timezone.now", return_value=em(2031, 2, 10, 12)):
        meses = dados_painel(usuaria, em(2031, 2, 10, 12))["grafico"]["meses"]
    assert [m["rotulo"] for m in meses] == ["set/30", "out/30", "nov/30", "dez/30", "jan/31", "fev/31"]


def test_tela_mostra_grafico_acessivel_com_valores_em_reais(logada, paciente):
    criar(paciente, em(2030, 2, 5, 10), Sessao.REALIZADA, pago=True)
    paciente.valor_sessao = Decimal("1234.50")
    paciente.save()
    criar(paciente, em(2030, 4, 2, 10), Sessao.REALIZADA, pago=True)
    html = logada.get(reverse("painel")).content.decode()
    svg = html.split("<svg viewBox=\"0 0 360 204\"", 1)[1].split("</svg>", 1)[0]
    assert 'width="172.0"' in svg and 'width="20.9"' in svg  # sem vírgula decimal no SVG
    assert svg.count('class="pa-grafico-barra"') == 2
    tabela = html.split("<caption>Valor recebido por mês nos últimos 6 meses</caption>", 1)[1].split("</table>", 1)[0]
    assert tabela.count("<tr>") == 7
    assert "<th scope=\"row\">Fevereiro de 2030</th><td>R$ 150,00</td>" in tabela
    assert "<th scope=\"row\">Março de 2030</th><td>R$ 0,00</td>" in tabela
    assert "<th scope=\"row\">Abril de 2030</th><td>R$ 1.234,50</td>" in tabela


# --- Tela -----------------------------------------------------------------------

def test_tela_vazia(logada):
    html = logada.get(reverse("painel")).content.decode()
    assert "Nenhuma sessão hoje" in html
    assert "Lembretes de amanhã" not in html
    assert "Quarta-feira, 17 de abril de 2030" in html
    assert "Boa tarde, ana" in html


def test_tela_completa(logada, usuaria, paciente):
    PerfilProfissional.objects.create(usuario=usuaria, nome_exibicao="Dra. Ana Souza")
    hoje = criar(paciente, em(2030, 4, 17, 18))
    pendente = criar(paciente, em(2030, 4, 10, 10), Sessao.REALIZADA)
    criar(paciente, em(2030, 4, 18, 9))
    html = logada.get(reverse("painel")).content.decode()
    assert "Boa tarde, Dra. Ana Souza" in html
    assert reverse("sessao_detalhe", args=[hoje.pk]) in html
    assert "Lembrar pelo WhatsApp" in html
    assert reverse("sessao_lembrete_enviado", args=[hoje.pk]) in html
    assert reverse("pagamento_registrar", args=[pendente.pk]) in html
    assert f'{reverse("agenda")}?semana=2030-04-18&amp;lembretes=1#lembretes-amanha' in html
    assert "1 sessão agendada para lembrar" in html
    assert "Nenhuma sessão hoje" not in html


def test_atalho_abre_lembretes_na_agenda(logada, paciente):
    criar(paciente, em(2030, 4, 18, 9))
    html = logada.get(reverse("agenda") + "?semana=2030-04-15&lembretes=1").content.decode()
    assert 'id="lembretes-amanha" open' in html
    html = logada.get(reverse("agenda") + "?semana=2030-04-15").content.decode()
    assert 'id="lembretes-amanha">' in html


@pytest.mark.parametrize("hora, saudacao", [(6, "Bom dia"), (11, "Bom dia"), (12, "Boa tarde"), (18, "Boa noite"), (23, "Boa noite")])
def test_saudacao_pela_hora_local(usuaria, hora, saudacao):
    assert dados_painel(usuaria, em(2030, 4, 17, hora))["saudacao"] == saudacao


# --- Isolamento e desempenho ----------------------------------------------------

def test_nenhum_bloco_mostra_dados_de_outra_usuaria(logada, usuaria, paciente_da_outra):
    p = paciente_da_outra
    criar(p, em(2030, 4, 17, 8), Sessao.REALIZADA, pago=True)   # hoje, semana, mês, gráfico, comparecimento
    criar(p, em(2030, 4, 17, 18))                               # hoje, próximas
    criar(p, em(2030, 4, 16, 9), Sessao.FALTA)                  # comparecimento
    criar(p, em(2030, 4, 10, 10), Sessao.REALIZADA)             # pendente, a receber
    criar(p, em(2030, 4, 18, 9))                                # lembrete de amanhã
    criar(p, em(2030, 1, 10, 10), Sessao.REALIZADA, pago=True)  # gráfico
    d = dados(usuaria)
    assert d["sessoes_hoje"] == [] and d["proximas"] == [] and d["pendentes"] == []
    assert d["sessoes_semana"] == 0 and d["pacientes_ativos"] == 0
    assert d["recebido_mes"] == 0 and d["a_receber_mes"] == 0
    assert d["taxa_comparecimento"] is None and d["lembretes_amanha"] == 0 and d["total_pendentes"] == 0
    assert all(m["valor"] == 0 for m in d["grafico"]["meses"])
    html = logada.get(reverse("painel")).content.decode()
    assert "Outra Pessoa" not in html and "999" not in html


def test_numero_de_consultas_nao_cresce_com_os_dados(usuaria, paciente, django_assert_max_num_queries):
    outro = Paciente.objects.create(usuario=usuaria, nome="Outro", telefone="11999990002", valor_sessao=100)
    for i in range(6):
        criar(paciente if i % 2 else outro, em(2030, 4, 17, 16 + i))
        criar(paciente, em(2030, 3, 1 + i, 10), Sessao.REALIZADA)
        criar(outro, em(2030, 4, 18 + i, 10))
    PerfilProfissional.objects.create(usuario=usuaria, nome_exibicao="Dra. Ana")
    with django_assert_max_num_queries(7):
        dados(usuaria)
