from datetime import datetime, timedelta

from django.urls import reverse
from django.utils import timezone

from core.models import Pagamento, Paciente, Sessao
from core.services import agendar_sessao


def em(dias, hora):
    base = timezone.localdate() + timedelta(days=dias)
    return timezone.make_aware(datetime.combine(base, datetime.min.time()).replace(hour=hora))


def test_marcar_como_pago_exige_data(cliente_logado, paciente):
    s = agendar_sessao(paciente, em(2, 10))
    resp = cliente_logado.post(reverse("pagamento_registrar", args=[s.pk]), {"data_pagamento": "", "forma_pagamento": "pix"})
    assert resp.status_code == 200
    s.pagamento.refresh_from_db()
    assert s.pagamento.status == Pagamento.A_RECEBER


def test_marcar_como_pago(cliente_logado, paciente):
    s = agendar_sessao(paciente, em(2, 10))
    hoje = timezone.localdate().isoformat()
    cliente_logado.post(reverse("pagamento_registrar", args=[s.pk]), {"data_pagamento": hoje, "forma_pagamento": "pix"})
    s.pagamento.refresh_from_db()
    assert s.pagamento.status == Pagamento.PAGO and s.pagamento.forma_pagamento == "pix"


def test_resumo_mensal_soma_recebido_e_a_receber(cliente_logado, usuaria, paciente):
    """Critério do RF07: 3 sessões pagas de R$150 e 1 a receber de R$150."""
    outro = Paciente.objects.create(usuario=usuaria, nome="Rafael S.", telefone="5", valor_sessao=150)
    dia = timezone.localdate().replace(day=1) + timedelta(days=40)
    base = timezone.make_aware(datetime.combine(dia, datetime.min.time()))
    for h in (9, 10, 11):
        s = agendar_sessao(paciente, base + timedelta(hours=h))
        s.pagamento.status = Pagamento.PAGO
        s.pagamento.save()
    agendar_sessao(outro, base + timedelta(hours=15))
    cancelada = agendar_sessao(outro, base + timedelta(hours=17))
    cancelada.status = Sessao.CANCELADA
    cancelada.save()
    html = cliente_logado.get(reverse("financeiro") + f"?mes={dia.year}-{dia.month}").content.decode()
    assert "R$ 450,00" in html and "R$ 150,00" in html and "Rafael S." in html


def test_pagamento_de_outra_usuaria_retorna_404(client, outra_usuaria, paciente):
    s = agendar_sessao(paciente, em(2, 10))
    client.force_login(outra_usuaria)
    assert client.get(reverse("pagamento_registrar", args=[s.pk])).status_code == 404
