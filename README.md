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
```
AgendaPsico_CLI_SQLite/
├─ .gitignore
├─ README.md
├─ requirements.txt
└─ src/
   ├─ app.py      # menu principal (interface de texto)
   ├─ db.py       # conexão e criação de tabelas
   └─ auth.py     # funções simples de segurança (hash de senha)
```

---

## ▶️ Como Executar

```bash
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
```

---

## 📌 Fluxo de Uso
1. **Criar conta** (psicólogo) com usuário e senha  
2. **Login**  
3. **Cadastrar pacientes** e valor da sessão  
4. **Registrar sessões** (informando paciente e data)  
5. **Gerar relatório mensal** (ex.: `2025-08`) com total do mês e detalhes por paciente  

---

## 💻 Exemplo no Terminal
```txt
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
```

---

## 🔒 Observações
- Senhas são guardadas com **hash** (`hashlib`), não em texto puro.
- Projeto **didático**: foco em lógica, uso de funções, banco de dados e segurança básica.
- Próximos passos possíveis:
  - versão web com Flask
  - exportar relatórios para CSV/PDF
  - integração com Google Calendar ou APIs financeiras

---

## 📜 Licença
Este projeto está sob a licença [MIT](https://opensource.org/licenses/MIT).  
Sinta-se livre para usar, estudar e modificar.  

---

✍️ **Autor:** Mateus Junior  
