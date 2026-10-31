"""Proteção no banco contra sessões sobrepostas (RF04), só no PostgreSQL.

A regra de negócio continua em services.agendar_sessao; esta restrição é a
última barreira para o caso de duas requisições simultâneas passarem pela
verificação ao mesmo tempo.

Por que trigger + colunas extras, e não um ExclusionConstraint do Django:
- a dona da sessão está em outra tabela (sessao -> paciente -> usuario), e uma
  restrição de exclusão só enxerga colunas da própria tabela;
- a sessão guarda início + duração, e a expressão "inicio + intervalo" com
  timestamptz não é IMMUTABLE no PostgreSQL, então não pode ir direto no índice.
Por isso um trigger preenche duas colunas em core_sessao, invisíveis para o
Django: usuario_id (copiado do paciente) e periodo (tstzrange [inicio, fim)).
A restrição EXCLUDE usa essas colunas e só vale para status que bloqueiam o
horário (agendada/realizada), como em Sessao.BLOQUEIAM_HORARIO. O intervalo é
semiaberto, então uma sessão que começa exatamente no fim da outra é permitida.
Se um paciente mudar de usuária, um segundo trigger recalcula as sessões dele.

No SQLite (desenvolvimento e testes) a migração não faz nada.
"""
from django.db import migrations

CRIAR = [
    "CREATE EXTENSION IF NOT EXISTS btree_gist",
    "ALTER TABLE core_sessao ADD COLUMN IF NOT EXISTS usuario_id bigint",
    "ALTER TABLE core_sessao ADD COLUMN IF NOT EXISTS periodo tstzrange",
    """
    CREATE OR REPLACE FUNCTION core_sessao_preenche_periodo() RETURNS trigger AS $$
    BEGIN
        SELECT p.usuario_id INTO NEW.usuario_id FROM core_paciente p WHERE p.id = NEW.paciente_id;
        NEW.periodo := tstzrange(NEW.inicio, NEW.inicio + make_interval(mins => NEW.duracao_minutos), '[)');
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE TRIGGER core_sessao_preenche_periodo
        BEFORE INSERT OR UPDATE OF paciente_id, inicio, duracao_minutos ON core_sessao
        FOR EACH ROW EXECUTE FUNCTION core_sessao_preenche_periodo()
    """,
    """
    CREATE OR REPLACE FUNCTION core_paciente_atualiza_sessoes() RETURNS trigger AS $$
    BEGIN
        UPDATE core_sessao SET paciente_id = paciente_id WHERE paciente_id = NEW.id;
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE TRIGGER core_paciente_atualiza_sessoes
        AFTER UPDATE OF usuario_id ON core_paciente
        FOR EACH ROW WHEN (OLD.usuario_id IS DISTINCT FROM NEW.usuario_id)
        EXECUTE FUNCTION core_paciente_atualiza_sessoes()
    """,
    # Preenche as sessões que já existem (o UPDATE dispara o trigger).
    "UPDATE core_sessao SET paciente_id = paciente_id",
    "ALTER TABLE core_sessao ALTER COLUMN usuario_id SET NOT NULL",
    "ALTER TABLE core_sessao ALTER COLUMN periodo SET NOT NULL",
    """
    ALTER TABLE core_sessao ADD CONSTRAINT sessao_sem_sobreposicao
        EXCLUDE USING gist (usuario_id WITH =, periodo WITH &&)
        WHERE (status IN ('agendada', 'realizada'))
    """,
]

DESFAZER = [
    "ALTER TABLE core_sessao DROP CONSTRAINT IF EXISTS sessao_sem_sobreposicao",
    "DROP TRIGGER IF EXISTS core_paciente_atualiza_sessoes ON core_paciente",
    "DROP FUNCTION IF EXISTS core_paciente_atualiza_sessoes()",
    "DROP TRIGGER IF EXISTS core_sessao_preenche_periodo ON core_sessao",
    "DROP FUNCTION IF EXISTS core_sessao_preenche_periodo()",
    "ALTER TABLE core_sessao DROP COLUMN IF EXISTS periodo",
    "ALTER TABLE core_sessao DROP COLUMN IF EXISTS usuario_id",
    # A extensão btree_gist fica instalada: removê-la exigiria privilégios e não faz mal.
]


def _executar(comandos):
    def aplicar(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        for sql in comandos:
            schema_editor.execute(sql)

    return aplicar


criar_restricao = _executar(CRIAR)
remover_restricao = _executar(DESFAZER)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_tentativas_login"),
    ]

    operations = [
        migrations.RunPython(criar_restricao, remover_restricao),
    ]
