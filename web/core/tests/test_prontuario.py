from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from core.models import Pagamento, Prontuario, Sessao


def sessao_passada(paciente, horas_atras=2):
    s = Sessao.objects.create(paciente=paciente, inicio=timezone.now() - timedelta(hours=horas_atras))
    Pagamento.objects.create(sessao=s, valor=paciente.valor_sessao)
    return s


def test_registra_prontuario_e_marca_sessao_realizada(cliente_logado, paciente):
    s = sessao_passada(paciente)
    cliente_logado.post(reverse("prontuario_registrar", args=[s.pk]), {"evolucao": "Paciente relatou melhora."})
    s.refresh_from_db()
    assert s.status == Sessao.REALIZADA
    assert Prontuario.objects.get(sessao=s).evolucao == "Paciente relatou melhora."


def test_nao_registra_prontuario_de_sessao_futura(cliente_logado, paciente):
    s = Sessao.objects.create(paciente=paciente, inicio=timezone.now() + timedelta(days=1))
    cliente_logado.post(reverse("prontuario_registrar", args=[s.pk]), {"evolucao": "x"})
    assert Prontuario.objects.count() == 0


def test_um_prontuario_por_sessao_edicao_atualiza(cliente_logado, paciente):
    s = sessao_passada(paciente)
    url = reverse("prontuario_registrar", args=[s.pk])
    cliente_logado.post(url, {"evolucao": "primeira versão"})
    cliente_logado.post(url, {"evolucao": "versão corrigida"})
    assert Prontuario.objects.count() == 1
    assert Prontuario.objects.get().evolucao == "versão corrigida"


def test_historico_em_ordem_e_com_escape(cliente_logado, paciente):
    antiga, recente = sessao_passada(paciente, 48), sessao_passada(paciente, 2)
    Prontuario.objects.create(sessao=antiga, evolucao="ANTIGA")
    Prontuario.objects.create(sessao=recente, evolucao="<script>alert(1)</script>")
    html = cliente_logado.get(reverse("paciente_historico", args=[paciente.pk])).content.decode()
    assert html.index("&lt;script&gt;") < html.index("ANTIGA")
    assert "<script>alert(1)</script>" not in html


def test_outra_usuaria_nao_ve_prontuario(client, outra_usuaria, paciente):
    s = sessao_passada(paciente)
    Prontuario.objects.create(sessao=s, evolucao="sigiloso")
    client.force_login(outra_usuaria)
    assert client.get(reverse("paciente_historico", args=[paciente.pk])).status_code == 404
    assert client.get(reverse("prontuario_registrar", args=[s.pk])).status_code == 404
