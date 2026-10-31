"""Perfil da psicóloga: campos novos, padrões de atendimento e página pública (/p/<slug>/)."""
from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from core.forms import PacienteForm, PerfilProfissionalForm, SessaoForm
from core.models import Paciente, PerfilProfissional, Sessao
from core.services import (
    MENSAGEM_CONTATO_PUBLICO,
    agendar_sessao,
    cartao_publico,
    iniciais_profissional,
    normalizar_instagram,
)
from core.templatetags.psiagenda import avatar_perfil

COMPLETO = {
    "nome_exibicao": "Dra. Ana Souza",
    "crp": "06/123456",
    "cor_avatar": "petroleo",
    "bio": "  Atendo adultos com escuta acolhedora.\nSessões online.  ",
    "abordagem": "TCC",
    "especialidades": " ansiedade,  luto , Ansiedade,, relacionamentos ",
    "publico": ["adultos", "casais"],
    "idiomas": "Português, Inglês",
    "modalidade": "Online",
    "duracao_padrao": "45",
    "valor_padrao": "180.00",
    "whatsapp": "(11) 98888-7777",
    "email_publico": "contato@anapsi.com.br",
    "instagram": "@ana.psi",
    "site": "anapsi.com.br",
    "perfil_publico": "on",
    "slug": "",
    "mostrar_cidade": "",
    "documento": "123.456.789-00",
    "cidade": "Santos/SP",
    "mensagem_lembrete": "",
}


@pytest.fixture
def publicado(usuaria):
    return PerfilProfissional.objects.create(
        usuario=usuaria, nome_exibicao="Dra. Ana Souza", crp="06/123456", documento="123.456.789-00",
        cidade="Santos/SP", bio="Escuta acolhedora.", abordagem="Psicanálise", especialidades="ansiedade, luto",
        publico="adultos,adolescentes", idiomas="Português", whatsapp="(11) 98888-7777",
        email_publico="contato@anapsi.com.br", instagram="https://www.instagram.com/ana.psi/",
        site="https://anapsi.com.br", cor_avatar="rosa", perfil_publico=True,
        mensagem_lembrete="Oi {primeiro_nome}",
    )


# --- Salvar o perfil -----------------------------------------------------------

def test_salva_todos_os_campos_normalizados(cliente_logado, usuaria):
    resp = cliente_logado.post(reverse("perfil"), COMPLETO)
    assert resp.status_code == 302 and resp.url == reverse("perfil")
    p = PerfilProfissional.objects.get(usuario=usuaria)
    assert p.bio == "Atendo adultos com escuta acolhedora.\nSessões online."
    assert p.especialidades == "ansiedade, luto, relacionamentos"
    assert p.lista_especialidades == ["ansiedade", "luto", "relacionamentos"]
    assert p.publico == "adultos,casais" and p.lista_publico == ["Adultos", "Casais"]
    assert (p.duracao_padrao, p.valor_padrao) == (45, Decimal("180.00"))
    assert p.instagram == "https://www.instagram.com/ana.psi/"
    assert p.site == "https://anapsi.com.br"
    assert (p.cor_avatar, p.perfil_publico, p.mostrar_cidade) == ("petroleo", True, False)
    assert p.slug == "dra-ana-souza"
    # Ao reabrir, as opções salvas vêm marcadas.
    form = PerfilProfissionalForm(instance=p)
    assert form.initial["publico"] == ["adultos", "casais"]


def test_envio_minimo_usa_padroes(cliente_logado, usuaria):
    """Campos novos ausentes do POST (como nos formulários antigos) não dão erro."""
    assert cliente_logado.post(reverse("perfil"), {"crp": "06/1"}).status_code == 302
    p = PerfilProfissional.objects.get(usuario=usuaria)
    assert (p.duracao_padrao, p.cor_avatar, p.valor_padrao, p.perfil_publico) == (50, "indigo", None, False)
    assert p.slug == "ana"


@pytest.mark.parametrize("campo,valor,erro", [
    ("duracao_padrao", "9", "maior ou igual a 10"),
    ("duracao_padrao", "241", "menor ou igual a 240"),
    ("bio", "a" * 601, "no máximo 600 caracteres"),
    ("site", "javascript:alert(1)", "URL válida"),
    ("site", "ftp://anapsi.com.br", "URL válida"),
    ("instagram", "https://evil.example.com/ana", "instagram.com"),
    ("instagram", "nome com espaço", "instagram.com"),
    ("email_publico", "nao-e-email", "email válido"),
    ("whatsapp", "1234", "Número inválido"),
    ("valor_padrao", "0", "maior ou igual a 0.01"),
    ("especialidades", ",".join(f"tema{i}" for i in range(13)), "no máximo 12 temas"),
    ("especialidades", "x" * 41, "no máximo 40 caracteres"),
    ("cor_avatar", "neon", "Faça uma escolha válida"),
])
def test_validacoes(cliente_logado, usuaria, campo, valor, erro):
    resp = cliente_logado.post(reverse("perfil"), {**COMPLETO, campo: valor})
    assert resp.status_code == 200
    html = resp.content.decode()
    assert erro in html and "Não foi possível salvar" in html
    assert not PerfilProfissional.objects.filter(usuario=usuaria).exists()


def test_pagina_publica_exige_crp(cliente_logado, usuaria):
    resp = cliente_logado.post(reverse("perfil"), {**COMPLETO, "crp": ""})
    assert "Informe o CRP para ativar a página pública." in resp.content.decode()
    assert not PerfilProfissional.objects.filter(usuario=usuaria).exists()
    # Sem página pública, o CRP continua opcional.
    resp = cliente_logado.post(reverse("perfil"), {**COMPLETO, "crp": "", "perfil_publico": ""})
    assert resp.status_code == 302


def test_instagram_aceita_varios_formatos():
    esperado = "https://www.instagram.com/ana.psi/"
    for texto in ("@ana.psi", "ana.psi", "instagram.com/ana.psi", "https://www.instagram.com/ana.psi/?hl=pt-br"):
        assert normalizar_instagram(texto) == esperado
    assert normalizar_instagram("  ") == ""
    assert normalizar_instagram("https://instagram.com.evil.com/ana") is None


# --- Endereço (slug) -----------------------------------------------------------

def test_slug_automatico_e_unico(usuaria, outra_usuaria):
    terceira = User.objects.create_user("cris", password="SenhaForte#2026")
    a = PerfilProfissional.objects.create(usuario=usuaria, nome_exibicao="Ana Souza")
    b = PerfilProfissional.objects.create(usuario=outra_usuaria, nome_exibicao="Ana Souza")
    c = PerfilProfissional.objects.create(usuario=terceira, nome_exibicao="Ana  Souza!")
    assert (a.slug, b.slug, c.slug) == ("ana-souza", "ana-souza-2", "ana-souza-3")
    # Salvar de novo não muda o endereço já criado.
    a.nome_exibicao = "Outro Nome"
    a.save()
    assert a.slug == "ana-souza"


def test_slug_sem_letras_usa_padrao(usuaria):
    perfil = PerfilProfissional.objects.create(usuario=usuaria, nome_exibicao="!!!")
    assert perfil.slug == "psicologa"


def test_slug_editavel_e_validado(cliente_logado, usuaria, outra_usuaria):
    PerfilProfissional.objects.create(usuario=outra_usuaria, nome_exibicao="Bia", slug="bia-psi")
    resp = cliente_logado.post(reverse("perfil"), {**COMPLETO, "slug": "bia-psi"})
    assert "Este endereço já está em uso." in resp.content.decode()
    resp = cliente_logado.post(reverse("perfil"), {**COMPLETO, "slug": "!!!"})
    assert "Use letras, números ou hífen." in resp.content.decode()
    resp = cliente_logado.post(reverse("perfil"), {**COMPLETO, "slug": "  Ana Psicóloga  "})
    assert resp.status_code == 302
    perfil = PerfilProfissional.objects.get(usuario=usuaria)
    assert perfil.slug == "ana-psicologa"
    # Manter o próprio endereço não acusa conflito; apagar gera de novo a partir do nome.
    assert cliente_logado.post(reverse("perfil"), {**COMPLETO, "slug": "ana-psicologa"}).status_code == 302
    cliente_logado.post(reverse("perfil"), {**COMPLETO, "slug": ""})
    perfil.refresh_from_db()
    assert perfil.slug == "dra-ana-souza"


def test_meu_perfil_mostra_link_copiar_e_previa(cliente_logado, usuaria):
    html = cliente_logado.get(reverse("perfil")).content.decode()
    assert "Salve o perfil para gerar o endereço" in html
    for secao in ("Identificação", "Apresentação", "Atendimento", "Contato público", "Página pública",
                  "Documentos do recibo", "Mensagem de lembrete"):
        assert secao in html
    PerfilProfissional.objects.create(usuario=usuaria, nome_exibicao="Ana Souza")
    html = cliente_logado.get(reverse("perfil")).content.decode()
    assert 'value="http://testserver/p/ana-souza/"' in html
    assert 'id="botao-copiar"' in html and "Pré-visualizar" in html and "Desativada" in html


# --- Página pública ------------------------------------------------------------

def test_pagina_desativada_e_404(client, usuaria, outra_usuaria, publicado):
    publicado.perfil_publico = False
    publicado.save()
    url = reverse("perfil_publico", args=[publicado.slug])
    assert client.get(url).status_code == 404
    client.force_login(outra_usuaria)
    assert client.get(url).status_code == 404
    assert client.get(reverse("perfil_publico", args=["nao-existe"])).status_code == 404


def test_dona_ve_previa_com_noindex(cliente_logado, publicado):
    publicado.perfil_publico = False
    publicado.save()
    resp = cliente_logado.get(reverse("perfil_publico", args=[publicado.slug]))
    html = resp.content.decode()
    assert resp.status_code == 200 and "Pré-visualização" in html
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert resp["X-Robots-Tag"] == "noindex, nofollow"


def test_conta_desativada_tira_pagina_do_ar(client, usuaria, publicado):
    usuaria.is_active = False
    usuaria.save()
    assert client.get(reverse("perfil_publico", args=[publicado.slug])).status_code == 404


def test_pagina_ativa_abre_sem_login_e_mostra_so_o_permitido(client, usuaria, paciente, publicado):
    sessao = agendar_sessao(paciente, timezone.now() + timedelta(days=2))
    resp = client.get(reverse("perfil_publico", args=[publicado.slug]))
    assert resp.status_code == 200
    html = resp.content.decode()
    for permitido in ("Dra. Ana Souza", "CRP 06/123456", "Psicanálise", "Escuta acolhedora.", "Online",
                      "Adolescentes, Adultos", "mailto:contato@anapsi.com.br", "https://www.instagram.com/ana.psi/",
                      "https://anapsi.com.br", "<li>ansiedade</li>", "<li>luto</li>"):
        assert permitido in html
    for proibido in ("123.456.789-00", "CPF", "CNPJ", "Santos", paciente.nome, "Carlos", "Oi {primeiro_nome}",
                     "180", reverse("sessao_detalhe", args=[sessao.pk]), "Sair", "Agenda"):
        assert proibido not in html
    assert "noindex" not in html and "X-Robots-Tag" not in resp


def test_cidade_so_aparece_se_ela_escolher(client, publicado):
    url = reverse("perfil_publico", args=[publicado.slug])
    assert "Santos/SP" not in client.get(url).content.decode()
    publicado.mostrar_cidade = True
    publicado.save()
    assert "Santos/SP" in client.get(url).content.decode()


def test_link_do_whatsapp(client, publicado):
    html = client.get(reverse("perfil_publico", args=[publicado.slug])).content.decode()
    esperado = f"https://wa.me/5511988887777?text={quote(MENSAGEM_CONTATO_PUBLICO, safe='')}"
    assert esperado in html
    assert MENSAGEM_CONTATO_PUBLICO == "Olá! Vi seu perfil e gostaria de saber sobre horários."


def test_meta_tags_de_compartilhamento(client, publicado):
    html = client.get(reverse("perfil_publico", args=[publicado.slug])).content.decode()
    assert '<meta property="og:title" content="Dra. Ana Souza – Psicóloga · CRP 06/123456">' in html
    assert '<meta name="description" content="Psicóloga · CRP 06/123456 · Psicanálise · Atendimento online. Escuta acolhedora.">' in html
    assert 'property="og:description"' in html
    assert '<link rel="canonical" href="http://testserver/p/dra-ana-souza/">' in html


def test_cartao_minimo_sem_contatos(usuaria):
    perfil = PerfilProfissional.objects.create(usuario=usuaria, modalidade="", whatsapp="123", bio="x " * 200)
    cartao = cartao_publico(perfil)
    assert cartao["whatsapp_url"] is None and cartao["instagram_usuario"] == "" and cartao["site_rotulo"] == ""
    assert cartao["nome"] == "ana" and cartao["iniciais"] == "A"
    assert len(cartao["descricao"]) <= 160 and cartao["descricao"].endswith("…")
    assert cartao_publico(PerfilProfissional(usuario=usuaria))["descricao"] == "Psicóloga · Atendimento online."


def test_cartao_nao_tem_dados_privados(publicado):
    cartao = cartao_publico(publicado)
    assert "123.456.789-00" not in str(cartao) and "Santos" not in str(cartao)
    assert "documento" not in cartao and "valor_padrao" not in cartao and "mensagem_lembrete" not in cartao


# --- Avatar ------------------------------------------------------------------

def test_iniciais_ignoram_titulos():
    assert iniciais_profissional("Dra. Ana Beatriz Souza") == "AS"
    assert iniciais_profissional("Dra. Ana (demonstração)") == "A"
    assert iniciais_profissional("") == "?"


def test_avatar_renderiza_cor_e_iniciais(cliente_logado, client, publicado):
    html = str(avatar_perfil("AS", "rosa", "Dra. Ana"))
    assert 'class="pa-perfil-avatar pa-perfil-avatar-m pa-cor-rosa"' in html
    assert 'role="img" aria-label="Avatar de Dra. Ana"' in html and '<span aria-hidden="true">AS</span>' in html
    assert "pa-cor-indigo" in str(avatar_perfil("AS", "<script>", "X"))
    assert "&lt;b&gt;" in str(avatar_perfil("AS", "rosa", "<b>"))
    html = cliente_logado.get(reverse("perfil")).content.decode()
    assert "pa-cor-rosa" in html and 'aria-label="Avatar de Dra. Ana Souza"' in html
    html = client.get(reverse("perfil_publico", args=[publicado.slug])).content.decode()
    assert "pa-perfil-avatar-g pa-cor-rosa" in html and '<span aria-hidden="true">AS</span>' in html


# --- Padrões de atendimento ------------------------------------------------------

def test_paciente_novo_vem_com_valor_padrao(cliente_logado, usuaria, paciente):
    html = cliente_logado.get(reverse("paciente_novo")).content.decode()
    assert 'name="valor_sessao" value=' not in html  # sem perfil, campo vazio
    PerfilProfissional.objects.create(usuario=usuaria, valor_padrao=Decimal("180.00"))
    html = cliente_logado.get(reverse("paciente_novo")).content.decode()
    assert 'value="180.00"' in html
    # Editar paciente existente mantém o valor dele.
    html = cliente_logado.get(reverse("paciente_editar", args=[paciente.pk])).content.decode()
    assert 'value="150.00"' in html and 'value="180.00"' not in html
    # O valor pode ser alterado no cadastro.
    cliente_logado.post(reverse("paciente_novo"), {"nome": "Rita", "telefone": "11911112222", "valor_sessao": "200"})
    assert Paciente.objects.get(nome="Rita").valor_sessao == Decimal("200")


def test_paciente_form_sem_usuario_nao_quebra():
    assert "valor_sessao" not in PacienteForm(usuario=None).initial


def test_nova_sessao_usa_duracao_padrao(cliente_logado, usuaria, paciente):
    assert SessaoForm(usuario=usuaria)["duracao_minutos"].value() == 50
    PerfilProfissional.objects.create(usuario=usuaria, duracao_padrao=40)
    html = cliente_logado.get(reverse("sessao_nova")).content.decode()
    assert 'name="duracao_minutos" value="40"' in html
    # Com o valor vindo da tela, vale o que foi enviado.
    inicio = timezone.localtime() + timedelta(days=3)
    cliente_logado.post(reverse("sessao_nova"), {
        "paciente": paciente.pk, "data": inicio.date().isoformat(), "horario": "10:00", "duracao_minutos": 40,
    })
    assert Sessao.objects.get().duracao_minutos == 40
