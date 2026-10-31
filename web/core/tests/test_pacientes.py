from django.urls import reverse

from core.models import Paciente


def test_cadastra_paciente_valido(cliente_logado, usuaria):
    resp = cliente_logado.post(
        reverse("paciente_novo"),
        {"nome": "Beatriz R.", "telefone": "11999990002", "valor_sessao": "150.00"},
    )
    assert resp.status_code == 302
    assert Paciente.objects.filter(usuario=usuaria, nome="Beatriz R.").exists()


def test_nome_obrigatorio(cliente_logado):
    resp = cliente_logado.post(reverse("paciente_novo"), {"nome": "", "telefone": "1", "valor_sessao": "150"})
    assert resp.status_code == 200
    assert Paciente.objects.count() == 0


def test_valor_deve_ser_positivo(cliente_logado):
    cliente_logado.post(reverse("paciente_novo"), {"nome": "X", "telefone": "1", "valor_sessao": "0"})
    assert Paciente.objects.count() == 0


def test_telefone_repetido_e_recusado(cliente_logado, paciente):
    resp = cliente_logado.post(
        reverse("paciente_novo"), {"nome": "Outro", "telefone": paciente.telefone, "valor_sessao": "100"}
    )
    assert "Já existe um paciente ativo com este telefone." in resp.content.decode()
    assert Paciente.objects.count() == 1


def test_lista_mostra_apenas_pacientes_da_usuaria(client, outra_usuaria, paciente):
    client.force_login(outra_usuaria)
    resp = client.get(reverse("pacientes"))
    assert "Carlos M." not in resp.content.decode()


def test_outra_usuaria_nao_edita_paciente_alheio(client, outra_usuaria, paciente):
    client.force_login(outra_usuaria)
    resp = client.get(reverse("paciente_editar", args=[paciente.pk]))
    assert resp.status_code == 404


def test_nome_com_script_e_escapado(cliente_logado, usuaria):
    Paciente.objects.create(usuario=usuaria, nome="<script>alert(1)</script>", telefone="2", valor_sessao=10)
    html = cliente_logado.get(reverse("pacientes")).content.decode()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
