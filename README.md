# PsiAgenda – Agenda para Psicólogos

![CI](https://github.com/MateusDePaulaJr/Agenda_psi/actions/workflows/ci.yml/badge.svg)

Projeto da disciplina **Projeto de Software**: sistema web para uma psicóloga autônoma que atende online organizar **agenda, pacientes, pagamentos e prontuários**, impedindo que dois pacientes sejam marcados no mesmo horário.

> A versão web principal está na pasta `web/` (Python 3.12 + Django 5.2). A versão CLI original continua em `src/`.

## Funcionalidades (MVP)

| Requisito | Descrição |
|---|---|
| RF01 | Login com senha protegida por hash **Argon2id** |
| RF02 | Cadastro de pacientes com valor da sessão |
| RF03 | Agenda semanal com o nome do paciente em cada horário |
| RF04 | **Bloqueio de horários sobrepostos** com alerta e sugestão de horários livres |
| RF05 | Pagamento "a receber" gerado automaticamente; marcar como pago |
| RF06 | Prontuário por sessão e histórico do paciente |
| RF07 | Resumo financeiro mensal, exportação em CSV e recibo imprimível |

## Como executar (Windows / PowerShell)

```powershell
cd web
py -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py dados_demo --senha "UmaSenhaForte#2026"   # dados FICTÍCIOS
python manage.py runserver
```

Acesse http://127.0.0.1:8000 e entre com o usuário `demo`.

## Testes e cobertura

```powershell
cd web
pytest --cov=core --cov-report=term-missing
```

O GitHub Actions (`.github/workflows/ci.yml`) roda os testes em todo Pull Request e em todo push na `main`, e falha se a cobertura ficar abaixo de 80%.

## Fluxo de trabalho com Git

- Cada funcionalidade é desenvolvida em uma branch (`feat/...`, `fix/...`, `docs/...`).
- Commits seguem o padrão *Conventional Commits* (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- A integração na `main` acontece por **Pull Request**, com revisão e CI aprovado.

---

## Versão CLI original (src/)

### Agenda para Psicólogos (CLI)

Projeto didático (nível iniciante) em **Python** que permite:
- Cadastro e login de psicólogos
- Cadastro de pacientes (por psicólogo) com **valor da sessão**
- Registro de sessões realizadas
- **Relatório de caixa mensal** por psicólogo (total do mês + detalhamento por paciente)
- Interface **Web** com Flask para interação mais amigável

## Por que SQLite?
Usamos **SQLite** (já vem com o Python via `sqlite3`) para ter um banco de dados de verdade sem precisar instalar nada extra.

## Estrutura
```
Agenda_psi/
├─ .gitignore
├─ README.md
├─ requirements.txt
└─ src/
   ├─ app.py        # versão CLI (menu de texto)
   ├─ web_app.py    # versão Web (Flask)
   ├─ db.py         # conexão e criação de tabelas
   ├─ auth.py       # funções simples de segurança (hash de senha)
   └─ export_csv.py # exportação de relatórios CSV
```

## Como executar (CLI)

```bash
# 1) (opcional) criar e ativar venv
python -m venv venv
# Windows (PowerShell)
venv\Scripts\Activate.ps1
# macOS/Linux
source venv/bin/activate

# 2) instalar dependências
py -m pip install -r requirements.txt

# 3) rodar CLI
py src/app.py
```

## Fluxo básico (CLI)
1. **Criar conta** (psicólogo) com usuário e senha
2. **Login**
3. **Cadastrar pacientes** e valor da sessão
4. **Registrar sessões**
5. **Relatório mensal** (ex.: 2025-08)

---

## Modo Web (Flask)

Além da versão **CLI**, o projeto agora conta com uma interface **Web** usando **Flask + Bootstrap** 🎉

### Como executar

1. Garanta que as dependências estejam instaladas:
   ```bash
   py -m pip install -r requirements.txt
   ```

2. Rode o servidor Flask:
   ```bash
   py src/web_app.py
   ```

3. Acesse no navegador:
   - [http://127.0.0.1:5000/](http://127.0.0.1:5000/) → Tela de Login
   - [http://127.0.0.1:5000/dashboard](http://127.0.0.1:5000/dashboard) → Dashboard

### Funcionalidades Web

- Login com o mesmo banco `agenda.db` (usuários criados na CLI também funcionam)
- **Pacientes**:
  - Cadastrar
  - Editar nome e valor
  - Listar com valores
- **Agendar Sessões**:
  - Seleção de paciente
  - Escolha de data com calendário
  - Valor sugerido automaticamente pelo paciente (editável)
- **Agenda do Dia**:
  - Lista de sessões do dia
  - Total diário
- **Dashboard** com botões rápidos para cada funcionalidade

---

## Observações
- Senhas são guardadas com *hash* (não em texto puro), usando `hashlib`.
- Esse projeto é didático: foco em aprender lógica, arquivos, funções, banco de dados e um pouco de segurança.
- Próximos passos possíveis: relatórios gráficos, integração com Google Calendar, deploy em nuvem (Heroku/Render).


## Implantação (Render) e monitoramento

- `render.yaml` cria o serviço web (Gunicorn + WhiteNoise) e o banco PostgreSQL gratuito.
- Variáveis secretas definidas no painel: `PSI_USUARIO`, `PSI_SENHA`, `PSI_NOME` (conta da psicóloga, criada no build por `python manage.py criar_usuaria`). `DJANGO_SECRET_KEY` é gerada pelo Render.
- **Monitoramento:** `GET /saude/` responde `{"status":"ok","banco":"ok","tempo_ms":...}` sem login e sem dados pessoais. É usado pelo health check do Render e por um monitor externo de disponibilidade (UptimeRobot, a cada 5 min). Erros de requisição vão para os logs do Render.

## Sessões recorrentes

- Em **Nova sessão**, o campo *Repetir* permite agendar o mesmo paciente toda semana ou a cada 2 semanas, no mesmo horário, de 2 a 24 sessões (padrão 4).
- É tudo ou nada: todas as datas são verificadas antes; se alguma estiver ocupada, nada é criado e a tela lista cada data e quem ocupa o horário, mantendo o formulário preenchido.
- Cada sessão da série é uma sessão normal (com seu pagamento "a receber") e guarda o mesmo identificador `serie`. No detalhe aparece "Sessão X de N da série" e o botão *Cancelar esta e as próximas da série*, que só cancela as sessões ainda agendadas e futuras (realizadas, faltas e passadas não mudam).

## Recibos e relatórios

- **Recibo:** no detalhe de uma sessão paga, o botão *Recibo* abre uma página pronta para imprimir, com nome da psicóloga, paciente, data/horário e duração, valor (R$ 1.234,56), data e forma de pagamento, número (`ANO-ID do pagamento`), cidade/data e linha de assinatura. *Imprimir / Salvar PDF* usa a impressão do navegador (sem biblioteca de PDF no servidor). O recibo não mostra prontuário, observações nem telefone.
- **Meu perfil** (no topo da tela): nome no recibo, CRP, CPF/CNPJ e cidade, todos opcionais; o que ficar em branco não aparece no recibo.
- **Financeiro:** *Exportar CSV* baixa `financeiro-AAAA-MM.csv` do mês escolhido (separador `;`, vírgula decimal, UTF-8 com BOM, abre direto no Excel em português), com as mesmas sessões do resumo (canceladas ficam de fora). *Imprimir* gera o resumo do mês sem menu nem botões.

## Lembretes pelo WhatsApp

- No detalhe de uma sessão **agendada e futura**, o botão *Lembrar pelo WhatsApp* abre (em nova aba) um link `https://wa.me/55DDDNÚMERO?text=...` com a mensagem pronta. **Nada é enviado automaticamente** e não há API paga: o WhatsApp abre com o texto e é a psicóloga quem aperta enviar.
- O telefone do paciente é texto livre; o sistema pega só os dígitos: 10 ou 11 dígitos (DDD + número) ganham o `55` na frente, 12 ou 13 dígitos começando com `55` são usados como estão. Fora disso, o botão aparece desativado com o aviso "Telefone do paciente em formato inválido para WhatsApp" e um link para corrigir o cadastro.
- **Mensagem:** a padrão é "Olá, {primeiro_nome}! Passando para lembrar da sua sessão de {dia_semana}, {data} às {hora}. Até lá! – {profissional}". Em **Meu perfil** dá para escrever outra usando os marcadores `{paciente}`, `{primeiro_nome}`, `{data}`, `{hora}`, `{dia_semana}` e `{profissional}`; marcadores desconhecidos aparecem no texto como foram escritos. Campo em branco volta para a padrão.
- **Lembretes de amanhã:** na agenda, a seção recolhível lista as sessões agendadas de amanhã, cada uma com o seu link, para lembrar todos em sequência.
- **Marcar lembrete como enviado:** como o link não tem como confirmar o envio, o botão ao lado registra à mão "Lembrete enviado em dd/mm hh:mm" na sessão.
- **Privacidade:** a mensagem só tem nomes, data e horário, nunca dados clínicos (não escreva informações clínicas na mensagem personalizada). Ao enviar, o texto e o número do paciente passam pelo WhatsApp (Meta), sujeitos aos termos e à política de privacidade dele.

## Painel

- Depois do login a psicóloga cai no **Painel** (`/painel/`, primeiro item do menu; o logo também leva para lá). A **Agenda** continua em `/`.
- **Hoje:** as sessões do dia (sem as canceladas) com horário, paciente, situação e pagamento; nas agendadas que ainda vão acontecer aparecem os botões de lembrete pelo WhatsApp.
- **Indicadores:** sessões na semana (segunda a domingo, sem canceladas); recebido e a receber no mês (mesma regra do Financeiro: pelo mês da sessão, sem canceladas); comparecimento nos últimos 30 dias (realizadas ÷ (realizadas + faltas), "—" quando não há nenhuma); pacientes ativos.
- **Próximas sessões** (as 5 próximas agendadas) e **Pagamentos pendentes** (as 5 sessões realizadas mais antigas ainda a receber, com o botão *Registrar pagamento*).
- **Gráfico** do valor recebido nos últimos 6 meses, desenhado no servidor em SVG (sem JavaScript nem bibliotecas externas), com uma tabela equivalente para leitores de tela.
- **Lembretes de amanhã:** atalho que abre a seção de lembretes da agenda, só quando há sessões agendadas para o dia seguinte.
- Os dados são montados em `services.dados_painel(usuario, agora)` com um número fixo de consultas ao banco.

## Segurança e backup

- **Bloqueio de login:** após 5 tentativas erradas seguidas para o mesmo usuário, o login (inclusive o do `/admin/`) fica bloqueado por 15 minutos, mesmo com a senha certa. O contador fica no banco (tabela `core_tentativalogin`) e zera no primeiro login bem-sucedido. Para liberar antes, apague o registro do usuário em *Admin → Tentativas de login*.
- **Sessões sobrepostas no PostgreSQL:** além da verificação na aplicação, a migração `0005` cria no PostgreSQL a extensão `btree_gist` e uma restrição `EXCLUDE` que impede duas sessões ativas da mesma psicóloga no mesmo horário (no SQLite ela não faz nada).

### Backup pela aplicação (JSON)

```bash
cd web
python manage.py exportar_backup                       # gera backup-psiagenda-AAAAMMDD-HHMMSS.json.gz
python manage.py exportar_backup backups/psiagenda.json.gz
```

O arquivo contém pacientes, sessões, pagamentos, prontuários e as contas (com hash de senha): **guarde em local seguro e nunca versione no Git**. Para restaurar em um banco vazio já migrado:

```bash
python manage.py migrate
python manage.py loaddata backup-psiagenda-AAAAMMDD-HHMMSS.json.gz
```

### Backup do PostgreSQL do Render (pg_dump)

1. No painel do Render, abra o banco `psiagenda-db` → *Connect* → copie a **External Database URL**.
2. No seu computador (com o cliente PostgreSQL na mesma versão do servidor ou mais nova), guarde a URL numa variável de ambiente, sem colá-la em arquivos do projeto:

```bash
# Linux/macOS (o espaço inicial evita salvar no histórico em muitos shells)
 export PSI_DB_URL='postgresql://...'
pg_dump "$PSI_DB_URL" --format=custom --no-owner --file="psiagenda-$(date +%Y%m%d).dump"
```

```powershell
# Windows (PowerShell)
$env:PSI_DB_URL = 'postgresql://...'
pg_dump $env:PSI_DB_URL --format=custom --no-owner --file="psiagenda-$(Get-Date -Format yyyyMMdd).dump"
```

3. Para restaurar em um banco **vazio** (por exemplo, um novo banco do Render): `pg_restore --no-owner --dbname="$PSI_DB_URL" psiagenda-AAAAMMDD.dump`. Para sobrescrever um banco existente, acrescente `--clean --if-exists`.

O plano gratuito do Render não tem backups automáticos e o banco gratuito expira após um período (confira no painel): faça o `pg_dump` com frequência.
