"""Segurança e dados: bloqueio de login, proteção do banco contra sobreposição e backup."""
import gzip
import importlib
import json
import re
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.urls import reverse
from django.utils import timezone

from core.models import Pagamento, Paciente, Prontuario, Sessao, TentativaLogin
from core.services import HorarioOcupado, agendar_sessao
from core.tests.test_agenda import em

SENHA = "SenhaForte#2026"


def entrar(client, username="ana", password="errada"):
    return client.post(reverse("login"), {"username": username, "password": password})


# ---- Bloqueio de login após 5 falhas (RNF01) ----

def test_cinco_falhas_bloqueiam_o_login(client, usuaria):
    for _ in range(4):
        resp = entrar(client)
        assert "Usuário ou senha inválidos" in resp.content.decode()
    resp = entrar(client)
    assert resp.status_code == 200
    assert "Muitas tentativas. Tente novamente em 15 minutos." in resp.content.decode()
    assert TentativaLogin.objects.get(username="ana").falhas == 5


def test_sexta_tentativa_bloqueada_mesmo_com_senha_correta(client, usuaria):
    for _ in range(5):
        entrar(client)
    resp = entrar(client, password=SENHA)
    assert resp.status_code == 200
    assert "Muitas tentativas" in resp.content.decode()
    assert "_auth_user_id" not in client.session


def test_bloqueio_vale_para_maiusculas_e_espacos(client, usuaria):
    for _ in range(5):
        entrar(client, username=" ANA ")
    assert "Muitas tentativas" in entrar(client, password=SENHA).content.decode()


def test_libera_depois_de_15_minutos(client, usuaria):
    agora = timezone.now()
    with mock.patch("django.utils.timezone.now", return_value=agora):
        for _ in range(5):
            entrar(client)
    with mock.patch("django.utils.timezone.now", return_value=agora + timedelta(minutes=14, seconds=1)):
        assert "Tente novamente em 1 minuto." in entrar(client, password=SENHA).content.decode()
    with mock.patch("django.utils.timezone.now", return_value=agora + timedelta(minutes=15, seconds=1)):
        resp = entrar(client, password=SENHA)
    assert resp.status_code == 302
    assert resp["Location"] == reverse("agenda")


def test_falha_apos_bloqueio_expirado_recomeca_contagem(client, usuaria):
    agora = timezone.now()
    with mock.patch("django.utils.timezone.now", return_value=agora):
        for _ in range(5):
            entrar(client)
    with mock.patch("django.utils.timezone.now", return_value=agora + timedelta(minutes=16)):
        resp = entrar(client)
    assert "Usuário ou senha inválidos" in resp.content.decode()
    tentativa = TentativaLogin.objects.get(username="ana")
    assert tentativa.falhas == 1 and tentativa.bloqueado_ate is None


def test_login_com_sucesso_zera_o_contador(client, usuaria):
    for _ in range(4):
        entrar(client)
    assert entrar(client, password=SENHA).status_code == 302
    assert not TentativaLogin.objects.exists()
    client.logout()
    for _ in range(4):
        entrar(client)
    assert entrar(client, password=SENHA).status_code == 302


def test_bloqueio_nao_revela_se_usuario_existe(client, usuaria):
    respostas = {}
    for nome in ("ana", "ninguem"):
        for _ in range(5):
            resp = entrar(client, username=nome)
        respostas[nome] = re.search(r'role="alert">(.*?)</div>', resp.content.decode()).group(1)
    assert "Muitas tentativas" in respostas["ninguem"]
    assert respostas["ana"] == respostas["ninguem"]


def test_bloqueio_de_um_usuario_nao_afeta_outro(client, usuaria, outra_usuaria):
    for _ in range(5):
        entrar(client)
    assert entrar(client, username="bia", password=SENHA).status_code == 302


def test_formulario_sem_usuario_nao_conta_tentativa(client, db):
    resp = entrar(client, username="")
    assert resp.status_code == 200
    assert not TentativaLogin.objects.exists()
    assert str(TentativaLogin(username="ana", falhas=2)) == "ana (2 falhas)"


def test_login_do_admin_tambem_e_bloqueado(client, usuaria):
    usuaria.is_staff = True
    usuaria.save()
    url = reverse("admin:login")
    for _ in range(5):
        client.post(url, {"username": "ana", "password": "errada"})
    resp = client.post(url, {"username": "ana", "password": SENHA})
    assert resp.status_code == 200
    assert "Muitas tentativas" in resp.content.decode()


# ---- Proteção do banco contra sobreposição (RF04) ----

MIGRACAO = importlib.import_module("core.migrations.0005_sessao_sem_sobreposicao_pg")


@pytest.mark.parametrize("funcao", [MIGRACAO.criar_restricao, MIGRACAO.remover_restricao])
def test_migracao_nao_faz_nada_fora_do_postgres(funcao):
    editor = mock.Mock()
    editor.connection.vendor = "sqlite"
    funcao(None, editor)
    editor.execute.assert_not_called()


def test_migracao_cria_extensao_e_restricao_no_postgres():
    editor = mock.Mock()
    editor.connection.vendor = "postgresql"
    MIGRACAO.criar_restricao(None, editor)
    sql = " ".join(c.args[0] for c in editor.execute.call_args_list)
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in sql
    assert "EXCLUDE USING gist (usuario_id WITH =, periodo WITH &&)" in sql
    assert "status IN ('agendada', 'realizada')" in sql


@pytest.mark.skipif(connection.vendor != "sqlite", reason="verifica o banco de desenvolvimento")
def test_sqlite_nao_recebe_colunas_extras(db):
    with connection.cursor() as cursor:
        colunas = {c.name for c in connection.introspection.get_table_description(cursor, "core_sessao")}
    assert "usuario_id" not in colunas and "periodo" not in colunas


@pytest.fixture
def beatriz(usuaria):
    return Paciente.objects.create(usuario=usuaria, nome="Beatriz R.", telefone="11999990002", valor_sessao=150)


def test_integrity_error_da_restricao_vira_horario_ocupado(paciente, beatriz):
    existente = agendar_sessao(paciente, em(3, 14))
    erro = IntegrityError('conflicting key value violates exclusion constraint "sessao_sem_sobreposicao"')
    # Simula a corrida: a verificação inicial não vê conflito, mas o banco recusa.
    with mock.patch.object(Sessao, "conflitos", side_effect=[[], [existente]]), \
            mock.patch.object(Sessao, "save", side_effect=erro):
        with pytest.raises(HorarioOcupado) as excecao:
            agendar_sessao(beatriz, em(3, 14, 30))
    assert "Carlos M." in str(excecao.value)
    assert Sessao.objects.count() == 1 and Pagamento.objects.count() == 1


def test_outros_integrity_errors_nao_sao_mascarados(paciente):
    with mock.patch.object(Sessao, "save", side_effect=IntegrityError("outra restrição")):
        with pytest.raises(IntegrityError):
            agendar_sessao(paciente, em(3, 14))


def test_view_mostra_conflito_quando_o_banco_recusa(cliente_logado, paciente, beatriz):
    existente = agendar_sessao(paciente, em(3, 14))
    erro = IntegrityError('violates exclusion constraint "sessao_sem_sobreposicao"')
    dados = {"paciente": beatriz.pk, "data": em(3, 14).date().isoformat(), "horario": "14:00", "duracao_minutos": 50}
    with mock.patch.object(Sessao, "conflitos", side_effect=[[], [existente]]), \
            mock.patch.object(Sessao, "save", side_effect=erro):
        resp = cliente_logado.post(reverse("sessao_nova"), dados)
    assert resp.status_code == 200
    assert "Este horário já está ocupado por Carlos M." in resp.content.decode()


@pytest.mark.skipif(connection.vendor != "postgresql", reason="restrição só existe no PostgreSQL")
@pytest.mark.django_db(transaction=True)
def test_postgres_recusa_sobreposicao_direto_no_banco(usuaria, paciente, beatriz):
    agendar_sessao(paciente, em(3, 14))
    with pytest.raises(IntegrityError, match="sessao_sem_sobreposicao"):
        Sessao.objects.create(paciente=beatriz, inicio=em(3, 14, 30))
    Sessao.objects.create(paciente=beatriz, inicio=em(3, 14, 50))  # encostada: permitida
    Sessao.objects.create(paciente=beatriz, inicio=em(3, 14, 10), status=Sessao.CANCELADA)
    # Corrida real: a 1ª verificação "não vê" o conflito e quem barra é o PostgreSQL.
    original, chamadas = Sessao.conflitos, []

    def conflitos_atrasados(self):
        chamadas.append(1)
        return [] if len(chamadas) == 1 else original(self)

    with mock.patch.object(Sessao, "conflitos", conflitos_atrasados), pytest.raises(HorarioOcupado):
        agendar_sessao(beatriz, em(3, 14, 20))


# ---- Backup ----

def test_exportar_backup_gera_json_gzip_que_o_loaddata_le(tmp_path, paciente):
    sessao = agendar_sessao(paciente, em(3, 14))
    Prontuario.objects.create(sessao=sessao, evolucao="Texto clínico")
    TentativaLogin.objects.create(username="x", falhas=2)
    arquivo = tmp_path / "copia.json.gz"
    call_command("exportar_backup", str(arquivo))

    with gzip.open(arquivo, "rt", encoding="utf-8") as f:
        objetos = json.load(f)
    modelos = {o["model"] for o in objetos}
    assert {"auth.user", "core.paciente", "core.sessao", "core.pagamento", "core.prontuario"} <= modelos
    assert "core.tentativalogin" not in modelos

    Prontuario.objects.all().delete()
    Pagamento.objects.all().delete()
    Sessao.objects.all().delete()
    Paciente.objects.all().delete()
    User.objects.all().delete()
    call_command("loaddata", str(arquivo), verbosity=0)
    assert User.objects.get(username="ana").check_password(SENHA)
    assert Prontuario.objects.get().evolucao == "Texto clínico"
    assert Sessao.objects.get().pagamento.valor == paciente.valor_sessao


def test_exportar_backup_usa_nome_com_data_e_hora(tmp_path, monkeypatch, usuaria, capsys):
    monkeypatch.chdir(tmp_path)
    call_command("exportar_backup")
    gerados = list(tmp_path.glob("backup-psiagenda-*.json.gz"))
    assert len(gerados) == 1
    saida = capsys.readouterr().out
    assert gerados[0].name in saida
    assert "argon2" not in saida
