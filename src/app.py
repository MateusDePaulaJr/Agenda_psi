# -*- coding: utf-8 -*-
"""Agenda para Psicólogos (CLI + SQLite)

Recursos:
- Cadastro/login de psicólogos (com hash de senha + salt)
- Cadastro de pacientes com valor de sessão
- Registro de sessões (data e valor)
- Relatório mensal por psicólogo (YYYY-MM)

Este é um projeto didático, ideal para iniciantes.
"""

from typing import Optional
import datetime as dt

from db import init_db, get_conn
from auth import gerar_salt, hash_senha, verificar_senha


def input_nao_vazio(msg: str) -> str:
    while True:
        v = input(msg).strip()
        if v:
            return v
        print("⚠ Campo não pode ser vazio.")


# ------------------ AUTENTICAÇÃO ------------------

def criar_conta() -> None:
    print("\n=== Criar conta (psicólogo) ===")
    nome = input_nao_vazio("Seu nome: ")
    usuario = input_nao_vazio("Usuário (login): ")
    senha = input_nao_vazio("Senha: ")
    salt = gerar_salt()
    h = hash_senha(senha, salt)

    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO psicologos (nome, usuario, salt, hash_senha) VALUES (?, ?, ?, ?)",
                (nome, usuario, salt, h)
            )
            conn.commit()
            print("✅ Conta criada com sucesso!\n")
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                print("⚠ Já existe um usuário com esse login. Tente outro.")
            else:
                print("⚠ Erro ao criar conta:", e)


def login() -> Optional[int]:
    print("\n=== Login ===")
    usuario = input_nao_vazio("Usuário: ")
    senha = input_nao_vazio("Senha: ")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, salt, hash_senha, nome FROM psicologos WHERE usuario = ?", (usuario,))
        row = cur.fetchone()
        if not row:
            print("⚠ Usuário não encontrado.\n")
            return None
        if verificar_senha(senha, row["salt"], row["hash_senha"]):
            print(f"✅ Bem-vindo(a), {row['nome']}!\n")
            return row["id"]
        else:
            print("⚠ Senha incorreta.\n")
            return None


# ------------------ PACIENTES ------------------

def cadastrar_paciente(psicologo_id: int) -> None:
    print("\n=== Cadastrar paciente ===")
    nome = input_nao_vazio("Nome do paciente: ")
    while True:
        try:
            valor = float(input_nao_vazio("Valor da sessão (ex.: 180.00): ").replace(",","."))
            break
        except ValueError:
            print("⚠ Informe um número válido (ex.: 180 ou 180.00)." )

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO pacientes (psicologo_id, nome, valor_sessao) VALUES (?, ?, ?)",
            (psicologo_id, nome, valor)
        )
        conn.commit()
    print("✅ Paciente cadastrado!\n")


def listar_pacientes(psicologo_id: int) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nome, valor_sessao FROM pacientes WHERE psicologo_id = ? ORDER BY nome", (psicologo_id,))
        rows = cur.fetchall()
        if not rows:
            print("(Você ainda não tem pacientes cadastrados.)\n")
            return
        print("\nSeus pacientes:")
        for r in rows:
            print(f"[{r['id']}] {r['nome']} - R$ {r['valor_sessao']:.2f}")
        print()


def atualizar_valor_paciente(psicologo_id: int) -> None:
    listar_pacientes(psicologo_id)
    try:
        pid = int(input_nao_vazio("ID do paciente para atualizar valor: "))
        novo_valor = float(input_nao_vazio("Novo valor da sessão: ").replace(",","."))
    except ValueError:
        print("⚠ IDs/valores precisam ser números válidos.\n")
        return

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE pacientes SET valor_sessao = ? WHERE id = ? AND psicologo_id = ?", (novo_valor, pid, psicologo_id))
        if cur.rowcount == 0:
            print("⚠ Paciente não encontrado.\n")
        else:
            conn.commit()
            print("✅ Valor atualizado!\n")


# ------------------ SESSÕES ------------------

def registrar_sessao(psicologo_id: int) -> None:
    listar_pacientes(psicologo_id)
    try:
        pid = int(input_nao_vazio("ID do paciente: "))
    except ValueError:
        print("⚠ ID inválido.\n")
        return

    data_txt = input("Data (YYYY-MM-DD) [enter = hoje]: ").strip()
    if not data_txt:
        data_txt = dt.date.today().isoformat()
    else:
        # valida formato simples
        try:
            _ = dt.date.fromisoformat(data_txt)
        except Exception:
            print("⚠ Data inválida (use formato YYYY-MM-DD).\n")
            return

    # buscar valor padrão do paciente e permitir ajustar antes de salvar
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT valor_sessao FROM pacientes WHERE id = ? AND psicologo_id = ?", (pid, psicologo_id))
        row = cur.fetchone()
        if not row:
            print("⚠ Paciente não encontrado.\n")
            return
        valor_padrao = float(row["valor_sessao"])

    valor_txt = input(f"Valor cobrado [padrão R$ {valor_padrao:.2f}]: ").strip().replace(",",".")
    valor = valor_padrao if not valor_txt else float(valor_txt)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO sessoes (paciente_id, data, valor) VALUES (?, ?, ?)", (pid, data_txt, valor))
        conn.commit()
    print("✅ Sessão registrada!\n")


# ------------------ RELATÓRIO ------------------

def relatorio_mensal(psicologo_id: int) -> None:
    print("\n=== Relatório mensal ===")
    mes = input_nao_vazio("Informe o mês no formato YYYY-MM (ex.: 2025-08): ")
    try:
        ano_i, mes_i = map(int, mes.split("-"))
        inicio = dt.date(ano_i, mes_i, 1)
        # primeiro dia do mês seguinte
        if mes_i == 12:
            fim = dt.date(ano_i + 1, 1, 1)
        else:
            fim = dt.date(ano_i, mes_i + 1, 1)
    except Exception:
        print("⚠ Formato inválido. Use YYYY-MM.\n")
        return

    with get_conn() as conn:
        cur = conn.cursor()
        # buscar sessões do mês para pacientes do psicólogo
        cur.execute('''
            SELECT s.data, s.valor, p.nome AS paciente
            FROM sessoes s
            JOIN pacientes p ON p.id = s.paciente_id
            WHERE p.psicologo_id = ?
              AND date(s.data) >= date(?)
              AND date(s.data) < date(?)
            ORDER BY s.data, p.nome
        ''', (psicologo_id, inicio.isoformat(), fim.isoformat()))
        rows = cur.fetchall()

        if not rows:
            print("(Sem sessões registradas neste mês.)\n")
            return

        total = sum(float(r["valor"]) for r in rows)
        print(f"\nRelatório de {mes}")
        print("Data        Paciente                     Valor")
        print("-"*48)
        for r in rows:
            print(f"{r['data']}  {r['paciente'][:25]:25}  R$ {float(r['valor']):7.2f}")
        print("-"*48)
        print(f"TOTAL: R$ {total:.2f}\n")


# ------------------ MENU ------------------

def menu_logado(psicologo_id: int) -> None:
    while True:
        print("""\n==== MENU (logado) ====
1) Cadastrar paciente
2) Listar pacientes
3) Atualizar valor de sessão do paciente
4) Registrar sessão
5) Relatório mensal (caixa)
0) Sair da conta
========================""")
        op = input("Escolha: ").strip()
        if op == "1":
            cadastrar_paciente(psicologo_id)
        elif op == "2":
            listar_pacientes(psicologo_id)
        elif op == "3":
            atualizar_valor_paciente(psicologo_id)
        elif op == "4":
            registrar_sessao(psicologo_id)
        elif op == "5":
            relatorio_mensal(psicologo_id)
        elif op == "0":
            print("Saindo da conta...\n")
            break
        else:
            print("⚠ Opção inválida.")


def main():
    init_db()
    while True:
        print("""\n==== AGENDA PARA PSICÓLOGOS ====
1) Criar conta
2) Fazer login
0) Sair
================================""")
        op = input("Escolha: ").strip()
        if op == "1":
            criar_conta()
        elif op == "2":
            user_id = login()
            if user_id:
                menu_logado(user_id)
        elif op == "0":
            print("Até mais! 👋")
            break
        else:
            print("⚠ Opção inválida.")


if __name__ == "__main__":
    main()
