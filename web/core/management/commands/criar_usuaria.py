"""Cria (ou atualiza) a conta da psicóloga a partir de variáveis de ambiente.

Usado na implantação: PSI_USUARIO, PSI_SENHA e PSI_NOME são definidos no painel
da hospedagem, para que nenhuma senha fique no código.
"""
import os

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Cria a conta da psicóloga usando PSI_USUARIO, PSI_SENHA e PSI_NOME."

    def handle(self, *args, **opts):
        usuario, senha = os.environ.get("PSI_USUARIO"), os.environ.get("PSI_SENHA")
        if not usuario or not senha:
            self.stdout.write("PSI_USUARIO/PSI_SENHA não definidos – nenhuma conta criada.")
            return
        conta, criada = User.objects.get_or_create(username=usuario)
        conta.first_name = os.environ.get("PSI_NOME", usuario)
        if criada:
            validate_password(senha, conta)
            conta.set_password(senha)
        conta.save()
        self.stdout.write(self.style.SUCCESS(f"Conta '{usuario}' {'criada' if criada else 'já existia'}."))
