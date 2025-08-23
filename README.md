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
Agenda_psi/
├─ .gitignore
├─ LICENSE
├─ README.md
├─ requirements.txt
├─ agenda.db        # banco de dados (criado em runtime)
└─ src/
   ├─ app.py        # menu principal (interface de texto)
   ├─ db.py         # conexão e criação de tabelas
   ├─ auth.py       # funções de segurança (hash de senha)
   └─ demo_seed.py  # script para popular dados de exemplo
```

---

## ▶️ Como Executar

### 1) (opcional) criar e ativar ambiente virtual
```bash
python -m venv venv
```

**Windows (PowerShell):**
```bash
venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

### 2) instalar dependências (se houver)
```bash
pip install -r requirements.txt
```

*(atualmente não há dependências externas)*

### 3) rodar aplicação
```bash
python src/app.py
```

---

## 🧪 Demo rápida (com dados de exemplo)

Para popular o banco com um usuário e alguns registros de pacientes/sessões:

```bash
# Windows (PowerShell)
py src/demo_seed.py
```

Saída esperada:
```
OK! Banco populado em: ...\agenda.db
Login de demonstração → usuário: mateus | senha: 1234
```

Agora rode a aplicação:
```bash
py src/app.py
```

- **Login demo:** usuário `mateus`, senha `1234`  
- No menu, escolha **Relatório mensal** e informe o mês atual (ex.: `2025-08`).

> Para **resetar o banco**, feche o app e apague o arquivo `agenda.db` na raiz do projeto.  
> Depois, se quiser, rode o `demo_seed.py` novamente.

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
Usuário: mateus
Senha: ******
Login realizado!

--- Menu Principal ---
1. Cadastrar paciente
2. Registrar sessão
3. Relatório mensal
4. Sair
```

---

## 🗺️ Roadmap
- [ ] Exportar relatório mensal para **CSV**
- [ ] Validações de entrada (datas/valores) mais robustas
- [ ] Integração com **Google Calendar** (sincronizar sessões)
- [ ] Versão **web** com Flask + templates
- [ ] Relatórios financeiros: gráficos simples (mês a mês)

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

✍️ **Autor:** Mateus de Paula Jr  
