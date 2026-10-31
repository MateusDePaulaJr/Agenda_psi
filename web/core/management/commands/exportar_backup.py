"""Exporta um backup dos dados do PsiAgenda (pacientes, sessões, pagamentos,
prontuários e contas) em JSON compactado com gzip.

Uso:  python manage.py exportar_backup [caminho.json.gz]
Restaurar (em um banco já migrado):  python manage.py loaddata caminho.json.gz

O arquivo contém dados clínicos e hashes de senha: guarde-o em local seguro.
"""
import gzip
from itertools import chain
from pathlib import Path

from django.apps import apps
from django.contrib.auth.models import User
from django.core import serializers
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import TentativaLogin


class Command(BaseCommand):
    help = "Gera um backup .json.gz dos dados (core + usuários) que o loaddata consegue restaurar."

    def add_arguments(self, parser):
        parser.add_argument(
            "caminho", nargs="?",
            help="Arquivo de saída (padrão: backup-psiagenda-AAAAMMDD-HHMMSS.json.gz na pasta atual)",
        )

    def handle(self, *args, **opts):
        caminho = Path(opts["caminho"] or f"backup-psiagenda-{timezone.localtime():%Y%m%d-%H%M%S}.json.gz")
        caminho.parent.mkdir(parents=True, exist_ok=True)
        # Mesmo formato do dumpdata, mas com ordem garantida: usuárias, pacientes,
        # sessões, pagamentos, prontuários. O "dumpdata --natural-foreign" coloca as
        # sessões antes dos pacientes, e no PostgreSQL o trigger da migração 0005
        # precisa do paciente já gravado para preencher a sessão.
        # Tentativas de login são temporárias e não entram no backup.
        modelos = [User] + [m for m in apps.get_app_config("core").get_models() if m is not TentativaLogin]
        objetos = chain.from_iterable(m._default_manager.order_by("pk") for m in modelos)
        with gzip.open(caminho, "wt", encoding="utf-8") as arquivo:
            serializers.serialize("json", objetos, indent=1, use_natural_foreign_keys=True, stream=arquivo)
        # Só informa o caminho e o tamanho; nunca o conteúdo nem credenciais.
        tamanho = caminho.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(f"Backup salvo em {caminho} ({tamanho:.1f} KB)."))
