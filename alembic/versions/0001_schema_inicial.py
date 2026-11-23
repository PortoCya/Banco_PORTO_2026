"""schema inicial: as 16 tabelas do AGENTS.md, com constraints e índices

Revision ID: 0001
Revises:
Create Date: 2026-11-16

Linha de base. Bancos criados antes desta migration (pelo antigo
Base.metadata.create_all) têm outro schema e devem ser recriados.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('comentario_golden_set',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('texto_comentario', sa.Text(), nullable=False),
    sa.Column('rotulo_sentimento_humano', sa.Enum('POSITIVO', 'NEUTRO', 'NEGATIVO', name='ck_golden_sentimento', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('rotulo_tema_humano', sa.Enum('atendimento', 'preco', 'produto', 'prazo', 'usabilidade', 'outro', name='ck_golden_tema', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('evento_circuit_breaker',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('motivo', sa.String(length=300), nullable=False),
    sa.Column('custo_acumulado', sa.Numeric(precision=12, scale=4, asdecimal=False), nullable=False),
    sa.Column('limite_custo', sa.Numeric(precision=12, scale=4, asdecimal=False), nullable=False),
    sa.Column('disparado_em', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolvido_em', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_evento_circuit_breaker_disparado_em', 'evento_circuit_breaker', ['disparado_em'], unique=False)
    op.create_index('ix_evento_circuit_breaker_resolvido_em', 'evento_circuit_breaker', ['resolvido_em'], unique=False)
    op.create_table('prompt',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('objetivo', sa.Text(), nullable=False),
    sa.Column('contexto', sa.Text(), nullable=False),
    sa.Column('saida_esperada', sa.Text(), nullable=False),
    sa.Column('problemas_encontrados', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('snapshot_telemetria',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('inicio_janela', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fim_janela', sa.DateTime(timezone=True), nullable=False),
    sa.Column('latencia_p50_ms', sa.Integer(), nullable=False),
    sa.Column('latencia_p95_ms', sa.Integer(), nullable=False),
    sa.Column('taxa_erro_5xx', sa.Numeric(precision=5, scale=4, asdecimal=False), nullable=False),
    sa.Column('pct_descartado_ec12', sa.Numeric(precision=5, scale=4, asdecimal=False), nullable=False),
    sa.Column('pct_descartado_ec13', sa.Numeric(precision=5, scale=4, asdecimal=False), nullable=False),
    sa.Column('qtd_pii_mascaramento_falhou', sa.Integer(), nullable=False),
    sa.Column('status_circuit_breaker', sa.String(length=50), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_snapshot_telemetria_inicio_janela', 'snapshot_telemetria', ['inicio_janela'], unique=False)
    op.create_table('usuario',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('senha_hash', sa.String(length=255), nullable=False),
    sa.Column('papel', sa.Enum('ADMIN', 'ANALYST', name='ck_usuario_papel', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('log_auditoria',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('id_usuario_ator', sa.Uuid(), nullable=True),
    sa.Column('acao', sa.String(length=150), nullable=False),
    sa.Column('tipo_entidade', sa.String(length=100), nullable=False),
    sa.Column('id_entidade', sa.Uuid(), nullable=False),
    sa.Column('estado_antes', sa.JSON(), nullable=True),
    sa.Column('estado_depois', sa.JSON(), nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['id_usuario_ator'], ['usuario.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_log_auditoria_acao_criado_em', 'log_auditoria', ['acao', 'criado_em'], unique=False)
    op.create_index('ix_log_auditoria_ator_criado_em', 'log_auditoria', ['id_usuario_ator', 'criado_em'], unique=False)
    op.create_index('ix_log_auditoria_criado_em', 'log_auditoria', ['criado_em'], unique=False)
    op.create_index('ix_log_auditoria_entidade', 'log_auditoria', ['tipo_entidade', 'id_entidade', 'criado_em'], unique=False)
    op.create_table('pesquisa',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('titulo', sa.String(length=300), nullable=False),
    sa.Column('texto_pergunta_nps', sa.Text(), nullable=False),
    sa.Column('texto_pergunta_aberta', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('RASCUNHO', 'PUBLICADA', 'PAUSADA', 'ARQUIVADA', name='ck_pesquisa_status', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('numero_versao', sa.Integer(), nullable=False),
    sa.Column('id_pesquisa_pai', sa.Uuid(), nullable=True),
    sa.Column('criado_por', sa.Uuid(), nullable=False),
    sa.Column('criada_em', sa.DateTime(timezone=True), nullable=False),
    sa.Column('atualizada_em', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['criado_por'], ['usuario.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_pesquisa_pai'], ['pesquisa.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pesquisa_criado_por', 'pesquisa', ['criado_por'], unique=False)
    op.create_index('ix_pesquisa_id_pesquisa_pai', 'pesquisa', ['id_pesquisa_pai'], unique=False)
    op.create_index('ix_pesquisa_status_criada_em', 'pesquisa', ['status', 'criada_em'], unique=False)
    op.create_table('rotulo_golden_set',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('id_comentario_golden_set', sa.Uuid(), nullable=False),
    sa.Column('rotulado_por', sa.Uuid(), nullable=False),
    sa.Column('eh_desempate', sa.Boolean(), nullable=False),
    sa.Column('rotulo_sentimento', sa.Enum('POSITIVO', 'NEUTRO', 'NEGATIVO', name='ck_rotulo_sentimento', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('rotulo_tema', sa.Enum('atendimento', 'preco', 'produto', 'prazo', 'usabilidade', 'outro', name='ck_rotulo_tema', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.ForeignKeyConstraint(['id_comentario_golden_set'], ['comentario_golden_set.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['rotulado_por'], ['usuario.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rotulo_golden_set_id_comentario', 'rotulo_golden_set', ['id_comentario_golden_set'], unique=False)
    op.create_index('ix_rotulo_golden_set_rotulado_por', 'rotulo_golden_set', ['rotulado_por'], unique=False)
    op.create_table('versao_modelo',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('provedor', sa.String(length=100), nullable=False),
    sa.Column('nome_modelo', sa.String(length=100), nullable=False),
    sa.Column('rotulo_versao', sa.String(length=100), nullable=False),
    sa.Column('id_prompt', sa.Uuid(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('promovida_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('criada_em', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['id_prompt'], ['prompt.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rotulo_versao')
    )
    op.create_index('ix_versao_modelo_id_prompt', 'versao_modelo', ['id_prompt'], unique=False)
    op.create_index('uq_versao_modelo_unica_ativa', 'versao_modelo', ['ativo'], unique=True, postgresql_where=sa.text('ativo'), sqlite_where=sa.text('ativo'))
    op.create_table('avaliacao_golden_set',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('id_versao_modelo', sa.Uuid(), nullable=False),
    sa.Column('acuracia_sentimento', sa.Numeric(precision=5, scale=4, asdecimal=False), nullable=False),
    sa.Column('acuracia_tema', sa.Numeric(precision=5, scale=4, asdecimal=False), nullable=False),
    sa.Column('taxa_falso_positivo', sa.Numeric(precision=5, scale=4, asdecimal=False), nullable=False),
    sa.Column('status', sa.Enum('APROVADO', 'REPROVADO', name='ck_avaliacao_status', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('executada_em', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['id_versao_modelo'], ['versao_modelo.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_avaliacao_versao_executada_em', 'avaliacao_golden_set', ['id_versao_modelo', 'executada_em'], unique=False)
    op.create_table('link_pesquisa',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('id_pesquisa', sa.Uuid(), nullable=False),
    sa.Column('tipo', sa.Enum('NOMINAL', 'ABERTO', name='ck_link_pesquisa_tipo', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('token', sa.String(length=128), nullable=False),
    sa.Column('usado_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['id_pesquisa'], ['pesquisa.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
    op.create_index('ix_link_pesquisa_id_pesquisa_criado_em', 'link_pesquisa', ['id_pesquisa', 'criado_em'], unique=False)
    op.create_table('log_exportacao',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('id_analista', sa.Uuid(), nullable=False),
    sa.Column('id_pesquisa', sa.Uuid(), nullable=False),
    sa.Column('campos_exportados', sa.String(length=500), nullable=False),
    sa.Column('anonimizado', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['id_analista'], ['usuario.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_pesquisa'], ['pesquisa.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_log_exportacao_criado_em', 'log_exportacao', ['criado_em'], unique=False)
    op.create_index('ix_log_exportacao_id_analista', 'log_exportacao', ['id_analista'], unique=False)
    op.create_index('ix_log_exportacao_id_pesquisa', 'log_exportacao', ['id_pesquisa'], unique=False)
    op.create_table('snapshot_nps',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('id_pesquisa', sa.Uuid(), nullable=False),
    sa.Column('periodo_inicio', sa.Date(), nullable=False),
    sa.Column('periodo_fim', sa.Date(), nullable=False),
    sa.Column('valor_nps', sa.Integer(), nullable=False),
    sa.Column('total_respostas', sa.Integer(), nullable=False),
    sa.Column('qtd_promotores', sa.Integer(), nullable=False),
    sa.Column('qtd_neutros', sa.Integer(), nullable=False),
    sa.Column('qtd_detratores', sa.Integer(), nullable=False),
    sa.Column('calculado_em', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('valor_nps >= -100 AND valor_nps <= 100', name='ck_snapshot_nps_valor'),
    sa.ForeignKeyConstraint(['id_pesquisa'], ['pesquisa.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id_pesquisa', 'periodo_inicio', 'periodo_fim', name='uq_snapshot_nps_pesquisa_periodo')
    )
    op.create_table('submissao',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('id_pesquisa', sa.Uuid(), nullable=False),
    sa.Column('id_link_pesquisa', sa.Uuid(), nullable=True),
    sa.Column('nota_nps', sa.Integer(), nullable=False),
    sa.Column('texto_comentario', sa.Text(), nullable=True),
    sa.Column('chave_idempotencia', sa.String(length=128), nullable=False),
    sa.Column('fingerprint_dispositivo', sa.String(length=255), nullable=True),
    sa.Column('endereco_ip', sa.String(length=128), nullable=True),
    sa.Column('status', sa.Enum('VALIDA', 'BLOQUEADA_DUPLICADA', name='ck_submissao_status', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('status_mascaramento_pii', sa.Enum('NAO_APLICAVEL', 'MASCARADO', 'FALHA_MASCARAMENTO_PII', name='ck_submissao_status_pii', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('criada_em', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('nota_nps >= 0 AND nota_nps <= 10', name='ck_submissao_nota_nps_0_10'),
    sa.ForeignKeyConstraint(['id_link_pesquisa'], ['link_pesquisa.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_pesquisa'], ['pesquisa.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_submissao_id_link_pesquisa', 'submissao', ['id_link_pesquisa'], unique=False)
    op.create_index('ix_submissao_pesquisa_criada_em', 'submissao', ['id_pesquisa', 'criada_em'], unique=False)
    op.create_index('ix_submissao_pesquisa_status_nota', 'submissao', ['id_pesquisa', 'status', 'nota_nps'], unique=False)
    op.create_index('uq_submissao_chave_idempotencia_valida', 'submissao', ['chave_idempotencia'], unique=True, postgresql_where=sa.text("status = 'VALIDA'"), sqlite_where=sa.text("status = 'VALIDA'"))
    op.create_table('analise_feedback',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('id_submissao', sa.Uuid(), nullable=False),
    sa.Column('id_versao_modelo', sa.Uuid(), nullable=False),
    sa.Column('sentimento', sa.Enum('POSITIVO', 'NEUTRO', 'NEGATIVO', name='ck_analise_sentimento', native_enum=False, create_constraint=True, length=40), nullable=True),
    sa.Column('tema', sa.Enum('atendimento', 'preco', 'produto', 'prazo', 'usabilidade', 'outro', name='ck_analise_tema', native_enum=False, create_constraint=True, length=40), nullable=True),
    sa.Column('confianca', sa.Float(), nullable=True),
    sa.Column('justificativa', sa.Text(), nullable=True),
    sa.Column('sequencia_versao', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('PENDENTE', 'CONCLUIDA', 'FALHA_SCHEMA', 'DESCARTADA_MANUAL', 'BAIXA_CONFIANCA', name='ck_analise_status', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('criada_em', sa.DateTime(timezone=True), nullable=False),
    sa.Column('atualizada_em', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('confianca IS NULL OR (confianca >= 0 AND confianca <= 1)', name='ck_analise_confianca_0_1'),
    sa.ForeignKeyConstraint(['id_submissao'], ['submissao.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['id_versao_modelo'], ['versao_modelo.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id_submissao', 'sequencia_versao', name='uq_analise_submissao_sequencia')
    )
    op.create_index('ix_analise_feedback_id_versao_modelo', 'analise_feedback', ['id_versao_modelo'], unique=False)
    op.create_table('job_ia',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('id_submissao', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('NA_FILA', 'PROCESSANDO', 'CONCLUIDO', 'FALHOU', 'TENTANDO_NOVAMENTE', name='ck_job_ia_status', native_enum=False, create_constraint=True, length=40), nullable=False),
    sa.Column('tentativas', sa.Integer(), nullable=False),
    sa.Column('ultimo_erro', sa.String(length=500), nullable=True),
    sa.Column('proxima_tentativa_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['id_submissao'], ['submissao.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_job_ia_id_submissao', 'job_ia', ['id_submissao'], unique=False)
    op.create_index('ix_job_ia_status_proxima_tentativa', 'job_ia', ['status', 'proxima_tentativa_em'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_job_ia_status_proxima_tentativa', table_name='job_ia')
    op.drop_index('ix_job_ia_id_submissao', table_name='job_ia')
    op.drop_table('job_ia')
    op.drop_index('ix_analise_feedback_id_versao_modelo', table_name='analise_feedback')
    op.drop_table('analise_feedback')
    op.drop_index('uq_submissao_chave_idempotencia_valida', table_name='submissao', postgresql_where=sa.text("status = 'VALIDA'"), sqlite_where=sa.text("status = 'VALIDA'"))
    op.drop_index('ix_submissao_pesquisa_status_nota', table_name='submissao')
    op.drop_index('ix_submissao_pesquisa_criada_em', table_name='submissao')
    op.drop_index('ix_submissao_id_link_pesquisa', table_name='submissao')
    op.drop_table('submissao')
    op.drop_table('snapshot_nps')
    op.drop_index('ix_log_exportacao_id_pesquisa', table_name='log_exportacao')
    op.drop_index('ix_log_exportacao_id_analista', table_name='log_exportacao')
    op.drop_index('ix_log_exportacao_criado_em', table_name='log_exportacao')
    op.drop_table('log_exportacao')
    op.drop_index('ix_link_pesquisa_id_pesquisa_criado_em', table_name='link_pesquisa')
    op.drop_table('link_pesquisa')
    op.drop_index('ix_avaliacao_versao_executada_em', table_name='avaliacao_golden_set')
    op.drop_table('avaliacao_golden_set')
    op.drop_index('uq_versao_modelo_unica_ativa', table_name='versao_modelo', postgresql_where=sa.text('ativo'), sqlite_where=sa.text('ativo'))
    op.drop_index('ix_versao_modelo_id_prompt', table_name='versao_modelo')
    op.drop_table('versao_modelo')
    op.drop_index('ix_rotulo_golden_set_rotulado_por', table_name='rotulo_golden_set')
    op.drop_index('ix_rotulo_golden_set_id_comentario', table_name='rotulo_golden_set')
    op.drop_table('rotulo_golden_set')
    op.drop_index('ix_pesquisa_status_criada_em', table_name='pesquisa')
    op.drop_index('ix_pesquisa_id_pesquisa_pai', table_name='pesquisa')
    op.drop_index('ix_pesquisa_criado_por', table_name='pesquisa')
    op.drop_table('pesquisa')
    op.drop_index('ix_log_auditoria_entidade', table_name='log_auditoria')
    op.drop_index('ix_log_auditoria_criado_em', table_name='log_auditoria')
    op.drop_index('ix_log_auditoria_ator_criado_em', table_name='log_auditoria')
    op.drop_index('ix_log_auditoria_acao_criado_em', table_name='log_auditoria')
    op.drop_table('log_auditoria')
    op.drop_table('usuario')
    op.drop_index('ix_snapshot_telemetria_inicio_janela', table_name='snapshot_telemetria')
    op.drop_table('snapshot_telemetria')
    op.drop_table('prompt')
    op.drop_index('ix_evento_circuit_breaker_resolvido_em', table_name='evento_circuit_breaker')
    op.drop_index('ix_evento_circuit_breaker_disparado_em', table_name='evento_circuit_breaker')
    op.drop_table('evento_circuit_breaker')
    op.drop_table('comentario_golden_set')
