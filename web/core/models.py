from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import models
from django.utils.text import slugify


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
    # Marcado à mão pela psicóloga depois de enviar o lembrete pelo WhatsApp
    # (o link wa.me não tem como confirmar o envio).
    lembrete_enviado_em = models.DateTimeField(null=True, blank=True)
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


# Cores do avatar com iniciais: todas com contraste AA (≥ 4,5:1) para texto branco.
CORES_AVATAR = [
    ("indigo", "Índigo"),
    ("violeta", "Violeta"),
    ("azul", "Azul"),
    ("petroleo", "Azul-petróleo"),
    ("verde", "Verde"),
    ("rosa", "Rosa"),
    ("terracota", "Terracota"),
    ("grafite", "Grafite"),
]

PUBLICOS = [
    ("criancas", "Crianças"),
    ("adolescentes", "Adolescentes"),
    ("adultos", "Adultos"),
    ("idosos", "Idosos"),
    ("casais", "Casais"),
    ("familias", "Famílias"),
]

DURACAO_MINIMA, DURACAO_MAXIMA = 10, 240
TAMANHO_SLUG = 60
_url_web = URLValidator(schemes=["http", "https"])


class PerfilProfissional(models.Model):
    """Dados da psicóloga: recibo, lembrete, padrões de atendimento e a página pública opcional.

    Todos os campos são opcionais: o que estiver vazio não aparece. A página
    pública (/p/<slug>/) só existe com `perfil_publico` ligado e mostra apenas os
    campos de apresentação e contato (nunca CPF/CNPJ, pacientes ou agenda).
    """

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil_profissional")
    nome_exibicao = models.CharField("nome profissional", max_length=120, blank=True)
    crp = models.CharField("CRP", max_length=20, blank=True)
    documento = models.CharField("CPF ou CNPJ", max_length=20, blank=True)
    cidade = models.CharField("cidade", max_length=80, blank=True)
    # Texto do lembrete pelo WhatsApp; vazio usa a mensagem padrão.
    mensagem_lembrete = models.TextField("mensagem de lembrete", max_length=1000, blank=True)

    # Identificação: avatar gerado com as iniciais (o Render gratuito não guarda arquivos enviados).
    cor_avatar = models.CharField("cor do avatar", max_length=10, choices=CORES_AVATAR, default="indigo")

    # Apresentação
    bio = models.TextField("mini bio", max_length=600, blank=True)
    abordagem = models.CharField("abordagem teórica", max_length=120, blank=True)
    especialidades = models.CharField("especialidades e temas", max_length=400, blank=True)
    publico = models.CharField("público atendido", max_length=100, blank=True)  # códigos de PUBLICOS separados por vírgula
    idiomas = models.CharField("idiomas", max_length=120, blank=True)

    # Atendimento (padrões usados ao cadastrar paciente e agendar sessão)
    modalidade = models.CharField("modalidade", max_length=80, blank=True, default="Online")
    duracao_padrao = models.PositiveSmallIntegerField(
        "duração padrão da sessão (minutos)",
        default=50,
        validators=[MinValueValidator(DURACAO_MINIMA), MaxValueValidator(DURACAO_MAXIMA)],
    )
    valor_padrao = models.DecimalField(
        "valor padrão da sessão", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0.01)],
    )

    # Contato público
    whatsapp = models.CharField("WhatsApp profissional", max_length=20, blank=True)
    email_publico = models.EmailField("e-mail profissional", blank=True)
    instagram = models.URLField("Instagram", blank=True, validators=[_url_web])
    site = models.URLField("site", blank=True, validators=[_url_web])

    # Página pública (opt-in)
    perfil_publico = models.BooleanField("página pública ativa", default=False)
    # Nulo (e não vazio) para que perfis antigos sem endereço não colidam na restrição de unicidade.
    slug = models.SlugField("endereço da página pública", max_length=TAMANHO_SLUG, unique=True, null=True, blank=True)
    mostrar_cidade = models.BooleanField("mostrar a cidade na página pública", default=False)

    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "perfil profissional"
        verbose_name_plural = "perfis profissionais"

    def __str__(self):
        return f"Perfil de {self.usuario}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.slug_disponivel(self.nome_para_slug())
        super().save(*args, **kwargs)

    def nome_para_slug(self):
        return self.nome_exibicao or self.usuario.get_full_name() or self.usuario.username

    def slug_disponivel(self, texto):
        """slugify(texto) livre entre os perfis; se já existir, acrescenta -2, -3..."""
        base = slugify(texto)[: TAMANHO_SLUG - 4].strip("-") or "psicologa"
        ocupados = set(
            PerfilProfissional.objects.filter(slug__startswith=base).exclude(pk=self.pk).values_list("slug", flat=True)
        )
        candidato, n = base, 2
        while candidato in ocupados:
            candidato, n = f"{base}-{n}", n + 1
        return candidato

    @property
    def lista_especialidades(self):
        return [t.strip() for t in self.especialidades.split(",") if t.strip()]

    @property
    def lista_publico(self):
        codigos = set(self.publico.split(","))
        return [rotulo for codigo, rotulo in PUBLICOS if codigo in codigos]
