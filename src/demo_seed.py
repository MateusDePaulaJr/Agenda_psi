# src/demo_seed.py
import sqlite3
from pathlib import Path
from datetime import date
import hashlib

# Caminho do banco (agenda.db na raiz do projeto)
DB_PATH = (Path(__file__).resolve().parent.parent / "agenda.db")

def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def create_tables(cur):
    # Psicólogos
    cur.execute("""
        CREATE TABLE IF NOT EXISTS psicologos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL
        );
    """)

    # Pacientes (por psicólogo)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            psicologo_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            valor_sessao REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (psicologo_id) REFERENCES psicologos(id)
        );
    """)

    # Sessões
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            psicologo_id INTEGER NOT NULL,
            paciente_id INTEGER NOT NULL,
            data TEXT NOT NULL,            -- YYYY-MM-DD
            valor REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (psicologo_id) REFERENCES psicologos(id),
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
        );
    """)

def seed():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    create_tables(cur)

    # 1) Psicólogo padrão
    usuario = "mateus"
    senha_plana = "1234"  # apenas para DEMO
    hash_senha = sha256_hex(senha_plana)

    cur.execute("SELECT id FROM psicologos WHERE usuario = ?", (usuario,))
    row = cur.fetchone()
    if row:
        psicologo_id = row[0]
    else:
        cur.execute(
            "INSERT INTO psicologos (usuario, senha_hash) VALUES (?, ?)",
            (usuario, hash_senha)
        )
        psicologo_id = cur.lastrowid

    # 2) Pacientes
    pacientes_demo = [
        ("Ana Souza", 180.0),
        ("Bruno Lima", 200.0),
    ]
    pac_ids = []
    for nome, valor in pacientes_demo:
        cur.execute(
            "INSERT INTO pacientes (psicologo_id, nome, valor_sessao) VALUES (?, ?, ?)",
            (psicologo_id, nome, valor)
        )
        pac_ids.append(cur.lastrowid)

    # 3) Sessões (datas no mês atual)
    today = date.today()
    y, m = today.year, today.month
    sessoes_demo = [
        (pac_ids[0], f"{y}-{m:02d}-05", 180.0),
        (pac_ids[0], f"{y}-{m:02d}-12", 180.0),
        (pac_ids[1], f"{y}-{m:02d}-07", 200.0),
        (pac_ids[1], f"{y}-{m:02d}-21", 200.0),
    ]
    for paciente_id, data_str, valor in sessoes_demo:
        cur.execute(
            "INSERT INTO sessoes (psicologo_id, paciente_id, data, valor) VALUES (?, ?, ?, ?)",
            (psicologo_id, paciente_id, data_str, valor)
        )

    con.commit()
    con.close()

    print("OK! Banco populado em:", DB_PATH)
    print("Login de demonstração → usuário: mateus | senha: 1234")

if __name__ == "__main__":
    seed()
