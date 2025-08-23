# src/app.py
import sqlite3
from pathlib import Path
import hashlib
import re
from datetime import date, datetime

# Exportação para CSV (salva em ./exports/relatorio_YYYY-MM.csv)
from export_csv import exportar_relatorio

DB_PATH = (Path(__file__).resolve().parent.parent / "agenda.db")

# -----------------------
# Utilidades / Segurança
# -----------------------
def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

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

# -----------------------
# Datas pt-BR (entrada) ↔ ISO (armazenamento)
# -----------------------
def parse_data_ptbr_to_iso(dia_mes_ano: str) -> str:
    """Recebe 'DD/MM/AAAA' e devolve 'YYYY-MM-DD' (valida datas reais)."""
    try:
        dt = datetime.strptime(dia_mes_ano, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError("Data inválida. Use o formato DD/MM/AAAA (ex.: 23/08/2025).")

def parse_mes_ptbr_to_iso(mes_ano: str) -> str:
    """Recebe 'MM/AAAA' e devolve 'YYYY-MM' (valida mês real)."""
    try:
        dt = datetime.strptime(mes_ano, "%m/%Y")
        return dt.strftime("%Y-%m")
    except ValueError:
        raise ValueError("Mês inválido. Use o formato MM/AAAA (ex.: 08/2025).")

def format_iso_to_ptbr(iso_yyyy_mm_dd: str) -> str:
    """Recebe 'YYYY-MM-DD' e devolve 'DD/MM/AAAA' para exibir."""
    try:
        dt = datetime.strptime(iso_yyyy_mm_dd, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return iso_yyyy_mm_dd  # fallback

def input_data_ptbr(msg: str) -> str:
    """Lê uma data DD/MM/AAAA do usuário e retorna no formato ISO YYYY-MM-DD."""
    while True:
        v = input(msg).strip()
        try:
            return parse_data_ptbr_to_iso(v)
        except ValueError as e:
            print(e)

def input_mes_ptbr(msg: str) -> str:
    """Lê um mês MM/AAAA do usuário e retorna no formato ISO YYYY-MM."""
    while True:
        v = input(msg).strip()
        try:
            return parse_mes_ptbr_to_iso(v)
        except ValueError as e:
            print(e)

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

    data_iso = input_data_ptbr("Data (DD/MM/AAAA): ")
    valor = input_float("Valor (R$): ")
    if valor == 0:
        print("Atenção: valor zero. Se for gratuito, confirme; do contrário, informe o valor correto.")

    con = get_con()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO sessoes (psicologo_id, paciente_id, data, valor) VALUES (?, ?, ?, ?)",
        (psicologo_id, paciente_id, data_iso, valor)
    )
    con.commit()
    con.close()
    print("Sessão registrada!")

# -----------------------
# Relatório mensal
# -----------------------
def relatorio_mensal(psicologo_id: int):
    print("\n=== Relatório mensal ===")
    mes_iso = input_mes_ptbr("Informe o mês (MM/AAAA): ").strip()  # → YYYY-MM

    con = get_con()
    cur = con.cursor()
    cur.execute("""
        SELECT p.nome, s.data, s.valor
        FROM sessoes s
        JOIN pacientes p ON p.id = s.paciente_id
        WHERE s.psicologo_id = ?
          AND substr(s.data,1,7) = ?
        ORDER BY s.data
    """, (psicologo_id, mes_iso))
    rows = cur.fetchall()

    cur.execute("""
        SELECT COALESCE(SUM(valor), 0)
        FROM sessoes
        WHERE psicologo_id = ?
          AND substr(data,1,7) = ?
    """, (psicologo_id, mes_iso))
    total = cur.fetchone()[0] or 0.0
    con.close()

    print(f"\n--- Caixa de {mes_iso[5:]}/{mes_iso[:4]} ---")  # exibe como MM/AAAA
    if not rows:
        print("Nenhuma sessão no período.")
    else:
        for nome, data_iso, valor in rows:
            print(f"{format_iso_to_ptbr(data_iso)}  |  {nome:<20}  R$ {valor:7.2f}")
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
            mes_iso = input_mes_ptbr("Informe o mês (MM/AAAA): ")
            exportar_relatorio(mes_iso, psicologo_id)
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
