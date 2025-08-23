# src/export_csv.py
import sqlite3
import csv
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "agenda.db"

def exportar_relatorio(mes: str, psicologo_id: int):
    """Exporta relatório mensal de um psicólogo para CSV.
       'mes' no formato YYYY-MM (ex.: '2025-08').
       O arquivo é salvo/atualizado em ./exports/relatorio_YYYY-MM.csv
    """
    con = sqlite3.connect(DB_PATH)
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
    con.close()

    if not rows:
        print(f"Nenhuma sessão encontrada para {mes}")
        return

    # Pasta de exportação (criada se não existir)
    export_dir = Path(__file__).resolve().parent.parent / "exports"
    export_dir.mkdir(exist_ok=True)

    out_path = export_dir / f"relatorio_{mes}.csv"

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Paciente", "Data", "Valor"])
        writer.writerows(rows)

    print(f"Relatório exportado com sucesso: {out_path.resolve()}")

if __name__ == "__main__":
    # Exemplo manual: exportar mês atual do psicólogo 1
    exportar_relatorio("2025-08", 1)
