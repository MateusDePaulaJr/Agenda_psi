# Agenda para Psicólogos (CLI + Web com Flask)

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
