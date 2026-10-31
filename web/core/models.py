from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Paciente(models.Model):
    """Pessoa atendida pela psicóloga (RF02)."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pacientes")
    nome = models.CharField(max_length=120)
    telefone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    valor_sessao = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "telefone"],
                condition=models.Q(ativo=True),
                name="telefone_unico_por_usuaria_ativo",
            )
        ]

    def __str__(self):
        return self.nome
