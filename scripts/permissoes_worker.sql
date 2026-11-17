-- Usuário de banco do worker de IA: só escreve nas tabelas de IA.
-- (AGENTS.md, "Isolamento garantido".) Idempotente; rode depois das migrations,
-- com um usuário que possa criar roles e conceder permissões (ex.: postgres):
--
--   psql "$URL_DE_SUPERUSUARIO" -v senha="'<senha do worker>'" -f scripts/permissoes_worker.sql
--
-- A senha entra por variável do psql, nunca escrita neste arquivo.
\set ON_ERROR_STOP on

SELECT NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nps_worker') AS criar \gset
\if :criar
  CREATE ROLE nps_worker LOGIN;
\endif
ALTER ROLE nps_worker PASSWORD :senha;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM nps_worker;
GRANT USAGE ON SCHEMA public TO nps_worker;

-- Núcleo: só leitura do que precisa analisar...
GRANT SELECT ON submissao TO nps_worker;
-- ...e escrita em UMA coluna: o resultado do mascaramento de PII.
GRANT UPDATE (status_mascaramento_pii) ON submissao TO nps_worker;

-- Camada de IA
GRANT SELECT ON prompt, versao_modelo, comentario_golden_set TO nps_worker;
GRANT SELECT, INSERT, UPDATE ON job_ia, analise_feedback TO nps_worker;
GRANT SELECT, INSERT ON avaliacao_golden_set, evento_circuit_breaker TO nps_worker;

-- Sem acesso: usuario, pesquisa, link_pesquisa, snapshot_nps, log_auditoria,
-- log_exportacao. O worker não tem como alterar nota, faixa ou NPS.
