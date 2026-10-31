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


class Sessao(models.Model):
    """Atendimento agendado (RF03). Regra central: não pode haver sobreposição (RF04)."""

    AGENDADA, REALIZADA, CANCELADA, FALTA = "agendada", "realizada", "cancelada", "falta"
    STATUS = [(AGENDADA, "Agendada"), (REALIZADA, "Realizada"), (CANCELADA, "Cancelada"), (FALTA, "Falta")]
    BLOQUEIAM_HORARIO = [AGENDADA, REALIZADA]

    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name="sessoes")
    inicio = models.DateTimeField(db_index=True)
    duracao_minutos = models.PositiveSmallIntegerField(default=50, validators=[MinValueValidator(10)])
    status = models.CharField(max_length=10, choices=STATUS, default=AGENDADA)
    observacao = models.CharField(max_length=200, blank=True)
    # Identifica as sessões criadas juntas como recorrentes (semanal/quinzenal).
    # Vazio para sessões avulsas.
    serie = models.UUIDField(null=True, blank=True, editable=False, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["inicio"]

    @property
    def fim(self):
        from datetime import timedelta

        return self.inicio + timedelta(minutes=self.duracao_minutos)

    def conflitos(self):
        """Sessões da mesma usuária que se sobrepõem a este intervalo."""
        from datetime import timedelta

        candidatas = Sessao.objects.filter(
            paciente__usuario=self.paciente.usuario,
            status__in=self.BLOQUEIAM_HORARIO,
            inicio__lt=self.fim,
            inicio__gt=self.inicio - timedelta(hours=12),
        ).exclude(pk=self.pk)
        return [s for s in candidatas if s.fim > self.inicio]

    def posicao_na_serie(self):
        """Devolve (X, N) para exibir "Sessão X de N da série", ou None se for avulsa."""
        if not self.serie:
            return None
        datas = list(Sessao.objects.filter(serie=self.serie).order_by("inicio", "pk").values_list("pk", flat=True))
        return datas.index(self.pk) + 1, len(datas)

    def __str__(self):
        return f"{self.paciente} – {self.inicio:%d/%m/%Y %H:%M}"


class Pagamento(models.Model):
    """Gerado automaticamente para cada sessão agendada (RF05)."""

    A_RECEBER, PAGO = "a_receber", "pago"
    STATUS = [(A_RECEBER, "A receber"), (PAGO, "Pago")]
    FORMAS = [("pix", "Pix"), ("transferencia", "Transferência"), ("dinheiro", "Dinheiro"), ("cartao", "Cartão")]

    sessao = models.OneToOneField(Sessao, on_delete=models.CASCADE, related_name="pagamento")
    valor = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    status = models.CharField(max_length=10, choices=STATUS, default=A_RECEBER)
    data_pagamento = models.DateField(null=True, blank=True)
    forma_pagamento = models.CharField(max_length=15, choices=FORMAS, blank=True)

    def __str__(self):
        return f"{self.sessao} – {self.get_status_display()}"


class Prontuario(models.Model):
    """Registro clínico (evolução) de uma sessão realizada (RF06). Dado sensível."""

    sessao = models.OneToOneField(Sessao, on_delete=models.PROTECT, related_name="prontuario")
    evolucao = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Prontuário de {self.sessao}"


class TentativaLogin(models.Model):
    """Falhas de login consecutivas por nome de usuário (bloqueio contra força bruta).

    Fica no banco (e não no cache em memória) porque o Render pode reiniciar o
    processo a qualquer momento. É registrada para qualquer nome digitado, exista
    a conta ou não, para não revelar quais usuários existem.
    """

    username = models.CharField(max_length=150, unique=True)
    falhas = models.PositiveSmallIntegerField(default=0)
    bloqueado_ate = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "tentativa de login"
        verbose_name_plural = "tentativas de login"

    def __str__(self):
        return f"{self.username} ({self.falhas} falhas)"
