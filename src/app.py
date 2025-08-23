# src/app.py
import sqlite3
from pathlib import Path
import hashlib
import re
from datetime import date

# Exportação para CSV
from export_csv import exportar_relatorio

DB_PATH = (Path(__file__).resolve().parent.parent / "agenda.db")

# -----------------------
# Utilidades / Segurança
# -----------------------
def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def is_yyyy_mm(s: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}", s))

def is_yyyy_mm_dd(s: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))

def input_nonempty(msg: str) -> str:
    while True:
        v = input(msg).strip()
        if v:
            return v
        print("Valor não pode ser vazio.")

def input_float(msg: str) -> float:
    while True:
        try:
            v = float(input(msg).strip().replace(",", "."))
            if v < 0:
                print("Valor não pode ser negativo.")
                continue
            return v
        except ValueError:
            print("Digite um número válido (ex.: 180 ou 180.50).")

def input_date(msg: str) -> str:
    while True:
        v = input(msg).strip()
        if is_yyyy_mm_dd(v):
            return v
        print("Data inválida. Use o formato YYYY-MM-DD (ex.: 2025-08-23).")

# -----------------------
# Banco de Dados (SQLite)
# -----------------------
def get_con():
    return sqlite3.connect(DB_PATH)

def init_db():
    con = get_con()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS psicologos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            psicologo_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            valor_sessao REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (psicologo_id) REFERENCES psicologos(id)
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            psicologo_id INTEGER NOT NULL,
            paciente_id INTEGER NOT NULL,
            data TEXT NOT NULL,   -- YYYY-MM-DD
            valor REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (psicologo_id) REFERENCES psicologos(id),
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
        );
    """)
    con.commit()
    con.close()

# -----------------------
# Autenticação
# -----------------------
def criar_conta():
    print("\n=== Criar conta ===")
    usuario = input_nonempty("Usuário: ")
    senha = input_nonempty("Senha: ")
    senha2 = input_nonempty("Confirmar senha: ")
    if senha != senha2:
        print("As senhas não coincidem.")
        return

    con = get_con()
    cur = con.cursor()
    try:
        cur.execute(
            "INSERT INTO psicologos (usuario, senha_hash) VALUES (?, ?)",
            (usuario, sha256_hex(senha))
        )
        con.commit()
        print("Conta criada com sucesso!")
    except sqlite3.IntegrityError:
        print("Usuário já existe. Tente outro.")
    finally:
        con.close()

def login():
    print("\n=== Login ===")
    usuario = input_nonempty("Usuário: ")
    senha = input_nonempty("Senha: ")

    con = get_con()
    cur = con.cursor()
    cur.execute("SELECT id, senha_hash FROM psicologos WHERE usuario = ?", (usuario,))
    row = cur.fetchone()
    con.close()

    if not row:
        print("Usuário não encontrado.")
        return None, None

    pid, hash_db = row
    if sha256_hex(senha) != hash_db:
        print("Senha incorreta.")
        return None, None

    print("Login realizado!")
    return pid, usuario

# -----------------------
# Pacientes
# -----------------------
def cadastrar_paciente(psicologo_id: int):
    print("\n=== Cadastrar paciente ===")
    nome = input_nonempty("Nome: ")
    valor = input_float("Valor da sessão (R$): ")
    con = get_con()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO pacientes (psicologo_id, nome, valor_sessao) VALUES (?, ?, ?)",
        (psicologo_id, nome, valor)
    )
    con.commit()
    con.close()
    print("Paciente cadastrado!")

def listar_pacientes(psicologo_id: int):
    con = get_con()
    cur = con.cursor()
    cur.execute(
        "SELECT id, nome, valor_sessao FROM pacientes WHERE psicologo_id = ? ORDER BY nome",
        (psicologo_id,)
    )
    rows = cur.fetchall()
    con.close()
    if not rows:
        print("Nenhum paciente cadastrado.")
        return []
    print("\n--- Pacientes ---")
    for pid, nome, valor in rows:
        print(f"[{pid}] {nome} — R$ {valor:.2f}")
    return rows

# -----------------------
# Sessões
# -----------------------
def registrar_sessao(psicologo_id: int):
    print("\n=== Registrar sessão ===")
    pacientes = listar_pacientes(psicologo_id)
    if not pacientes:
        return
    while True:
        try:
            paciente_id = int(input("ID do paciente: ").strip())
            if any(p[0] == paciente_id for p in pacientes):
                break
            print("ID inválido.")
        except ValueError:
            print("Digite um número válido.")

    data_ = input_date("Data (YYYY-MM-DD): ")
    valor = input_float("Valor (R$): ")

    con = get_con()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO sessoes (psicologo_id, paciente_id, data, valor) VALUES (?, ?, ?, ?)",
        (psicologo_id, paciente_id, data_, valor)
    )
    con.commit()
    con.close()
    print("Sessão registrada!")

# -----------------------
# Relatório mensal
# -----------------------
def relatorio_mensal(psicologo_id: int):
    print("\n=== Relatório mensal ===")
    while True:
        mes = input("Informe o mês (YYYY-MM): ").strip()
        if is_yyyy_mm(mes):
            break
        print("Formato inválido. Ex.: 2025-08")

    con = get_con()
    cur = con.cursor()
    cur.execute("""
        SELECT p.nome, s.data, s.valor
        FROM sessoes s
        JOIN pacientes p ON p.id = s.paciente_id
        WHERE s.psicologo_id = ?
          AND substr(s.data,1,7) = ?
        ORDER BY s.data
    """, (psicologo_id, mes))
    rows = cur.fetchall()

    cur.execute("""
        SELECT COALESCE(SUM(valor), 0)
        FROM sessoes
        WHERE psicologo_id = ?
          AND substr(data,1,7) = ?
    """, (psicologo_id, mes))
    total = cur.fetchone()[0] or 0.0
    con.close()

    print(f"\n--- Caixa de {mes} ---")
    if not rows:
        print("Nenhuma sessão no período.")
    else:
        for nome, data_, valor in rows:
            print(f"{data_}  |  {nome:<20}  R$ {valor:7.2f}")
    print(f"\nTOTAL: R$ {total:.2f}")

# -----------------------
# Menu principal
# -----------------------
def menu(psicologo_id: int, usuario: str):
    while True:
        print("\n--- Menu Principal ---")
        print("1. Cadastrar paciente")
        print("2. Registrar sessão")
        print("3. Relatório mensal")
        print("4. Exportar relatório (CSV)")
        print("5. Sair")
        opcao = input("Escolha: ").strip()

        if opcao == "1":
            cadastrar_paciente(psicologo_id)
        elif opcao == "2":
            registrar_sessao(psicologo_id)
        elif opcao == "3":
            relatorio_mensal(psicologo_id)
        elif opcao == "4":
            mes = input("Informe o mês (YYYY-MM): ").strip()
            if not is_yyyy_mm(mes):
                print("Formato inválido. Ex.: 2025-08")
                continue
            exportar_relatorio(mes, psicologo_id)
        elif opcao == "5":
            print("Saindo...")
            break
        else:
            print("Opção inválida.")

def main():
    init_db()
    while True:
        print("\n==== AGENDA PSI ====")
        print("1. Criar conta")
        print("2. Login")
        print("3. Sair")
        escolha = input("Escolha: ").strip()
        if escolha == "1":
            criar_conta()
        elif escolha == "2":
            pid, usuario = login()
            if pid:
                menu(pid, usuario)
        elif escolha == "3":
            print("Até mais!")
            break
        else:
            print("Opção inválida.")

if __name__ == "__main__":
    main()
