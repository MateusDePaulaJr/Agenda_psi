import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        # psicologos
        cur.execute('''
            CREATE TABLE IF NOT EXISTS psicologos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                usuario TEXT UNIQUE NOT NULL,
                salt TEXT NOT NULL,
                hash_senha TEXT NOT NULL
            );
        ''')
        # pacientes
        cur.execute('''
            CREATE TABLE IF NOT EXISTS pacientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                psicologo_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                valor_sessao REAL NOT NULL,
                FOREIGN KEY (psicologo_id) REFERENCES psicologos(id)
            );
        ''')
        # sessoes
        cur.execute('''
            CREATE TABLE IF NOT EXISTS sessoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id INTEGER NOT NULL,
                data TEXT NOT NULL,  -- YYYY-MM-DD
                valor REAL NOT NULL, -- valor cobrado nesta sessão
                FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
            );
        ''')
        conn.commit()
