from django import forms

from datetime import datetime

from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone
from django.utils.text import slugify

from .models import (
    CORES_AVATAR,
    DURACAO_MAXIMA,
    DURACAO_MINIMA,
    PUBLICOS,
    TAMANHO_SLUG,
    Paciente,
    Pagamento,
    PerfilProfissional,
    Prontuario,
)
from .services import (
    MAX_SESSOES_SERIE,
    MENSAGEM_LEMBRETE_PADRAO,
    MIN_SESSOES_SERIE,
    limpar_falhas_login,
    minutos_de_bloqueio,
    normalizar_instagram,
    numero_whatsapp,
    registrar_falha_login,
)


def _perfil_de(usuario):
    if usuario is None or not getattr(usuario, "pk", None):
        return None
    return PerfilProfissional.objects.filter(usuario=usuario).first()


def mensagem_bloqueio(minutos):
    return f"Muitas tentativas. Tente novamente em {minutos} minuto{'s' if minutos != 1 else ''}."


class BloqueioLoginMixin:
    """Bloqueia o login após 5 falhas seguidas do mesmo usuário (RNF01).

    A mensagem é a mesma para usuários existentes ou não, e durante o bloqueio
    nem a senha correta é aceita.
    """

    def clean(self):
        username = self.cleaned_data.get("username")
        if username is None:
            return super().clean()
        minutos = minutos_de_bloqueio(username)
        if minutos:
            raise forms.ValidationError(mensagem_bloqueio(minutos), code="bloqueado")
        try:
            dados = super().clean()
        except forms.ValidationError as erro:
            if getattr(erro, "code", None) == "invalid_login":
                minutos = registrar_falha_login(username)
                if minutos:
                    raise forms.ValidationError(mensagem_bloqueio(minutos), code="bloqueado") from erro
            raise
        limpar_falhas_login(username)
        return dados


class LoginForm(BloqueioLoginMixin, AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Usuário ou senha inválidos.",
    }


class AdminLoginForm(BloqueioLoginMixin, AdminAuthenticationForm):
    pass


class PacienteForm(forms.ModelForm):
    class Meta:
        model = Paciente
        fields = ["nome", "telefone", "email", "valor_sessao"]
        labels = {
            "nome": "Nome (obrigatório)",
            "telefone": "Telefone (obrigatório)",
            "email": "E-mail (opcional)",
            "valor_sessao": "Valor da sessão em R$ (obrigatório)",
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control"
        # Paciente novo já vem com o valor padrão do perfil (se houver); pode ser alterado.
        if not self.instance.pk and not self.is_bound:
            perfil = _perfil_de(usuario)
            if perfil and perfil.valor_padrao:
                self.initial.setdefault("valor_sessao", perfil.valor_padrao)

    def clean_telefone(self):
        telefone = self.cleaned_data["telefone"].strip()
        repetido = Paciente.objects.filter(usuario=self.usuario, telefone=telefone, ativo=True)
        if self.instance.pk:
            repetido = repetido.exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Já existe um paciente ativo com este telefone.")
        return telefone


class SessaoForm(forms.Form):
    paciente = forms.ModelChoiceField(queryset=Paciente.objects.none(), label="Paciente (obrigatório)")
    data = forms.DateField(label="Data (obrigatório)", widget=forms.DateInput(attrs={"type": "date"}))
    horario = forms.TimeField(label="Horário de início (obrigatório)", widget=forms.TimeInput(attrs={"type": "time"}))
    duracao_minutos = forms.IntegerField(
        label="Duração em minutos", initial=50, min_value=DURACAO_MINIMA, max_value=DURACAO_MAXIMA
    )
    repetir = forms.ChoiceField(
        label="Repetir",
        required=False,
        choices=[("", "Não repetir"), ("semanal", "Toda semana (semanal)"), ("quinzenal", "A cada 2 semanas (quinzenal)")],
    )
    # Os limites são conferidos em clean(), só quando a sessão se repete, para não
    # dar erro num campo escondido.
    quantidade = forms.IntegerField(
        label=f"Quantidade de sessões ({MIN_SESSOES_SERIE} a {MAX_SESSOES_SERIE}, contando a primeira)",
        required=False,
        initial=4,
        widget=forms.NumberInput(attrs={"min": MIN_SESSOES_SERIE, "max": MAX_SESSOES_SERIE}),
    )
    observacao = forms.CharField(label="Observação (opcional)", required=False, max_length=200)

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paciente"].queryset = Paciente.objects.filter(usuario=usuario, ativo=True)
        # A duração começa com a duração padrão do perfil (50 min se não houver perfil).
        perfil = _perfil_de(usuario)
        if perfil and "duracao_minutos" not in self.initial:
            self.initial["duracao_minutos"] = perfil.duracao_padrao
        selecoes = (self.fields["paciente"], self.fields["repetir"])
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-select" if campo in selecoes else "form-control"

    def clean(self):
        dados = super().clean()
        if dados.get("data") and dados.get("horario"):
            inicio = timezone.make_aware(datetime.combine(dados["data"], dados["horario"]))
            if inicio <= timezone.now():
                raise forms.ValidationError("A data e o horário precisam ser futuros.")
            dados["inicio"] = inicio
        if dados.get("repetir"):
            quantidade = dados.get("quantidade")
            if quantidade is None and "quantidade" not in self.errors:
                quantidade = dados["quantidade"] = 4
            if quantidade is not None and not MIN_SESSOES_SERIE <= quantidade <= MAX_SESSOES_SERIE:
                self.add_error(
                    "quantidade",
                    f"Informe de {MIN_SESSOES_SERIE} a {MAX_SESSOES_SERIE} sessões.",
                )
        else:
            dados["quantidade"] = 1
        return dados


class PagamentoForm(forms.ModelForm):
    class Meta:
        model = Pagamento
        fields = ["data_pagamento", "forma_pagamento"]
        labels = {"data_pagamento": "Data do pagamento (obrigatório)", "forma_pagamento": "Forma de pagamento"}
        widgets = {"data_pagamento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_pagamento"].required = True
        if not self.initial.get("data_pagamento"):
            self.initial["data_pagamento"] = timezone.localdate()
        self.fields["data_pagamento"].widget.attrs["class"] = "form-control"
        self.fields["forma_pagamento"].widget.attrs["class"] = "form-select"


class ProntuarioForm(forms.ModelForm):
    class Meta:
        model = Prontuario
        fields = ["evolucao"]
        labels = {"evolucao": "Evolução da sessão (obrigatório)"}
        widgets = {"evolucao": forms.Textarea(attrs={"class": "form-control", "rows": 8})}


class PerfilProfissionalForm(forms.ModelForm):
    """Meu perfil, organizado em seções. Todos os campos são opcionais."""

    SECOES = [
        ("identificacao", "Identificação", "Como seu nome aparece no sistema, no recibo e na página pública.",
         ["nome_exibicao", "crp", "cor_avatar"]),
        ("apresentacao", "Apresentação", "Para a sua página pública: escreva para quem ainda não conhece o seu trabalho.",
         ["bio", "abordagem", "especialidades", "publico", "idiomas"]),
        ("atendimento", "Atendimento", "Os padrões já vêm preenchidos ao cadastrar paciente e ao agendar sessão.",
         ["modalidade", "duracao_padrao", "valor_padrao"]),
        ("contato", "Contato público", "Aparecem como botões na página pública. Use contatos profissionais.",
         ["whatsapp", "email_publico", "instagram", "site"]),
        ("pagina", "Página pública", "Um cartão de apresentação para divulgar. Fica desligado até você ativar.",
         ["perfil_publico", "slug", "mostrar_cidade"]),
        ("recibo", "Documentos do recibo", "Usados só no recibo. O CPF/CNPJ nunca aparece na página pública.",
         ["documento", "cidade"]),
        ("lembrete", "Mensagem de lembrete", "", ["mensagem_lembrete"]),
    ]
    MAX_ESPECIALIDADES = 12

    cor_avatar = forms.ChoiceField(
        label="Cor do avatar", choices=CORES_AVATAR, required=False, widget=forms.RadioSelect,
        help_text="O avatar mostra as suas iniciais nesta cor.",
    )
    publico = forms.MultipleChoiceField(
        label="Público atendido (opcional)", choices=PUBLICOS, required=False, widget=forms.CheckboxSelectMultiple
    )
    duracao_padrao = forms.IntegerField(
        label="Duração padrão da sessão, em minutos",
        required=False, min_value=DURACAO_MINIMA, max_value=DURACAO_MAXIMA,
        help_text=f"De {DURACAO_MINIMA} a {DURACAO_MAXIMA} minutos. Em branco usa 50.",
    )
    # CharField (e não URLField) para aceitar também "@usuario"; vira link em clean_instagram.
    instagram = forms.CharField(
        label="Instagram (opcional)", required=False, max_length=200,
        help_text="Seu @usuário ou o link do perfil.",
        widget=forms.TextInput(attrs={"placeholder": "@seuperfil", "autocapitalize": "none", "spellcheck": "false"}),
    )
    site = forms.URLField(
        label="Site (opcional)", required=False, max_length=200, assume_scheme="https",
        widget=forms.URLInput(attrs={"placeholder": "https://www.seusite.com.br"}),
    )
    slug = forms.CharField(
        label="Endereço da página", required=False, max_length=TAMANHO_SLUG,
        help_text="Só letras minúsculas, números e hífen. Em branco é criado a partir do seu nome.",
        widget=forms.TextInput(attrs={"autocapitalize": "none", "spellcheck": "false"}),
    )

    class Meta:
        model = PerfilProfissional
        fields = [
            "nome_exibicao", "crp", "cor_avatar",
            "bio", "abordagem", "especialidades", "publico", "idiomas",
            "modalidade", "duracao_padrao", "valor_padrao",
            "whatsapp", "email_publico", "instagram", "site",
            "perfil_publico", "slug", "mostrar_cidade",
            "documento", "cidade", "mensagem_lembrete",
        ]
        labels = {
            "nome_exibicao": "Nome profissional (opcional; vazio usa o nome da conta)",
            "crp": "CRP (opcional, ex.: 06/123456)",
            "documento": "CPF ou CNPJ (opcional)",
            "cidade": "Cidade (opcional, ex.: São Paulo/SP)",
            "mensagem_lembrete": "Mensagem de lembrete pelo WhatsApp (opcional; vazio usa a mensagem padrão)",
            "bio": "Mini bio (opcional)",
            "abordagem": "Abordagem teórica (opcional)",
            "especialidades": "Especialidades e temas (opcional)",
            "idiomas": "Idiomas (opcional)",
            "modalidade": "Modalidade (opcional)",
            "valor_padrao": "Valor padrão da sessão em R$ (opcional)",
            "whatsapp": "WhatsApp profissional (opcional)",
            "email_publico": "E-mail profissional (opcional)",
            "perfil_publico": "Ativar minha página pública",
            "mostrar_cidade": "Mostrar a cidade na página pública",
        }
        help_texts = {
            "nome_exibicao": "Aparece no recibo, nos lembretes e na página pública.",
            "bio": "Até 600 caracteres. Conte como você trabalha, em linguagem simples.",
            "abordagem": "Ex.: TCC, Psicanálise, Gestalt-terapia.",
            "especialidades": "Separe por vírgula. Ex.: ansiedade, luto, relacionamentos.",
            "idiomas": "Ex.: Português, Inglês.",
            "modalidade": "Ex.: Online (por videochamada).",
            "valor_padrao": "Preenche o valor de pacientes novos. Não aparece na página pública.",
            "whatsapp": "Com DDD, ex.: (11) 98888-7777.",
            "perfil_publico": "Qualquer pessoa com o link poderá ver o cartão, sem login. Para ativar, informe o CRP.",
            "mostrar_cidade": "A cidade do recibo só aparece na página se você marcar aqui.",
            "documento": "Nunca é exibido fora do recibo.",
        }
        widgets = {
            "mensagem_lembrete": forms.Textarea(attrs={"rows": 4, "placeholder": MENSAGEM_LEMBRETE_PADRAO}),
            "bio": forms.Textarea(attrs={"rows": 5, "maxlength": 600}),
            "abordagem": forms.TextInput(attrs={"placeholder": "Ex.: Terapia Cognitivo-Comportamental (TCC)"}),
            "especialidades": forms.TextInput(attrs={"placeholder": "ansiedade, luto, relacionamentos"}),
            "modalidade": forms.TextInput(attrs={"placeholder": "Online"}),
            "whatsapp": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"}),
            "valor_padrao": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs["class"] = "form-check-input"
            elif not isinstance(campo.widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
                campo.widget.attrs["class"] = "form-control"
        self.fields["mensagem_lembrete"].widget.attrs["aria-describedby"] = "ajuda-lembrete"
        if self.instance.pk:
            self.initial["publico"] = [c for c in self.instance.publico.split(",") if c]

    def secoes(self):
        """[(id, título, descrição, [campos])] para o template montar os blocos."""
        return [(ident, titulo, descricao, [self[n] for n in campos]) for ident, titulo, descricao, campos in self.SECOES]

    def clean_mensagem_lembrete(self):
        return self.cleaned_data["mensagem_lembrete"].strip()

    def clean_bio(self):
        return self.cleaned_data["bio"].strip()

    def clean_cor_avatar(self):
        return self.cleaned_data["cor_avatar"] or "indigo"

    def clean_publico(self):
        return ",".join(self.cleaned_data["publico"])

    def clean_duracao_padrao(self):
        duracao = self.cleaned_data["duracao_padrao"]
        return 50 if duracao is None else duracao

    def clean_especialidades(self):
        """Normaliza a lista: tira espaços e repetidos (ignorando maiúsculas) e junta com ", "."""
        temas, vistos = [], set()
        for tema in self.cleaned_data["especialidades"].split(","):
            tema = " ".join(tema.split())
            if tema and tema.lower() not in vistos:
                vistos.add(tema.lower())
                temas.append(tema)
        if len(temas) > self.MAX_ESPECIALIDADES:
            raise forms.ValidationError(f"Informe no máximo {self.MAX_ESPECIALIDADES} temas.")
        if any(len(t) > 40 for t in temas):
            raise forms.ValidationError("Cada tema pode ter no máximo 40 caracteres.")
        return ", ".join(temas)

    def clean_whatsapp(self):
        whatsapp = self.cleaned_data["whatsapp"].strip()
        if whatsapp and not numero_whatsapp(whatsapp):
            raise forms.ValidationError("Número inválido. Informe DDD + número, ex.: (11) 98888-7777.")
        return whatsapp

    def clean_instagram(self):
        link = normalizar_instagram(self.cleaned_data["instagram"])
        if link is None:
            raise forms.ValidationError("Informe o seu @usuário ou um link do instagram.com.")
        return link

    def clean_slug(self):
        texto = self.cleaned_data["slug"].strip()
        if not texto:
            return None  # o modelo gera a partir do nome ao salvar
        slug = slugify(texto)[:TAMANHO_SLUG].strip("-")
        if not slug:
            raise forms.ValidationError("Use letras, números ou hífen.")
        if PerfilProfissional.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Este endereço já está em uso. Escolha outro.")
        return slug

    def clean(self):
        dados = super().clean()
        # Código de Ética do Psicólogo (art. 20): a divulgação deve trazer nome e CRP.
        if dados.get("perfil_publico") and not dados.get("crp"):
            self.add_error("crp", "Informe o CRP para ativar a página pública.")
        return dados
