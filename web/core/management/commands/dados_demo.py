"""Cria uma usuária de demonstração e pacientes/sessões FICTÍCIOS para testes de usabilidade."""
from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Paciente
from core.services import HorarioOcupado, agendar_sessao


class Command(BaseCommand):
    help = "Cria dados fictícios de demonstração (usuária 'demo')."

    def add_arguments(self, parser):
        parser.add_argument("--senha", required=True, help="Senha da usuária demo (mín. 10 caracteres)")

    def handle(self, *args, **opts):
        user, _ = User.objects.get_or_create(username="demo", defaults={"first_name": "Dra. Ana (demonstração)"})
        user.set_password(opts["senha"])
        user.save()
        nomes = ["Carlos M.", "Rafael S.", "João P.", "Marina T.", "Beatriz R."]
        pacientes = [
            Paciente.objects.get_or_create(usuario=user, nome=n, defaults={"telefone": f"1190000000{i}", "valor_sessao": 150})[0]
            for i, n in enumerate(nomes)
        ]
        hoje = timezone.localdate()
        segunda = hoje - timedelta(days=hoje.weekday()) + timedelta(days=7)
        plano = [(0, 14, 0), (0, 15, 1), (1, 9, 2), (2, 18, 3)]
        for dia, hora, idx in plano:
            inicio = timezone.make_aware(datetime.combine(segunda + timedelta(days=dia), datetime.min.time()) + timedelta(hours=hora))
            try:
                agendar_sessao(pacientes[idx], inicio)
            except HorarioOcupado:
                pass
        self.stdout.write(self.style.SUCCESS("Dados de demonstração criados. Usuário: demo"))
