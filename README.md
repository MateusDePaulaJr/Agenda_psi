# Agenda para Psicólogos (CLI com SQLite) ![Python](https://img.shields.io/badge/Python-3.10%2B-blue)

Aplicação de linha de comando (CLI) em **Python** que permite psicólogos(as) organizarem seus atendimentos e gerar um relatório financeiro mensal.  

Este é um **projeto didático** de primeiro período da faculdade de Análise e Desenvolvimento de Sistemas.  
Todos os códigos foram criados com auxílio de IA e **revisados linha a linha** por mim.  

---

## ✨ Funcionalidades
- Cadastro e login de psicólogos (com senha hash)
- Cadastro de pacientes por psicólogo (com **valor da sessão**)
- Registro de sessões realizadas
- **Relatório de caixa mensal** por psicólogo:
  - total do mês  
  - detalhamento por paciente  

---

## 🛠️ Por que SQLite?
O **SQLite** já vem embutido no Python (`sqlite3`).  
Assim conseguimos usar um banco de dados real sem instalar nada extra, ideal para projetos de aprendizado.

---

## 📂 Estrutura do Projeto
AgendaPsico_CLI_SQLite/
├─ .gitignore
├─ README.md
├─ requirements.txt
└─ src/
├─ app.py # menu principal (interface de texto)
├─ db.py # conexão e criação de tabelas
└─ auth.py # funções simples de segurança (hash de senha)


## ▶️ Como Executar


# 1) (opcional) criar e ativar ambiente virtual
python -m venv venv
# Windows (PowerShell)
venv\Scripts\Activate.ps1
# macOS/Linux
source venv/bin/activate

# 2) instalar dependências (se houver)
pip install -r requirements.txt

# 3) rodar aplicação
python src/app.py
📌 Fluxo de Uso
Criar conta (psicólogo) com usuário e senha

Login

Cadastrar pacientes e valor da sessão

Registrar sessões (informando paciente e data)

Gerar relatório mensal (ex.: 2025-08) com total do mês e detalhes por paciente

💻 Exemplo no Terminal

==== AGENDA PSI ====
1. Criar conta
2. Login
3. Sair
Escolha: 2
Usuário: joao
Senha: ******
Login realizado!

--- Menu Principal ---
1. Cadastrar paciente
2. Registrar sessão
3. Relatório mensal
4. Sair

🔒 Observações
Senhas são guardadas com hash (hashlib), não em texto puro.

Projeto didático: foco em lógica, uso de funções, banco de dados e segurança básica.

Próximos passos possíveis:

versão web com Flask

exportar relatórios para CSV/PDF

integração com Google Calendar ou APIs financeiras
---

## 🗺️ Roadmap
- [ ] Exportar relatório mensal para **CSV**
- [ ] Validações de entrada (datas/valores) mais robustas
- [ ] Integração com **Google Calendar** (sincronizar sessões)
- [ ] Versão **web** com Flask + templates
- [ ] Relatórios financeiros: gráficos simples (mês a mês)


📜 Licença
Este projeto está sob a licença MIT.
Sinta-se livre para usar, estudar e modificar.

✍️ Autor: Mateus de Paula Jr
**Status:** Em desenvolvimento 🚧
