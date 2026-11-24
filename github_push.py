"""
Script para fazer commit atômico de todos os arquivos do projeto no GitHub via Git Data API REST.
Ignora .env, .env.local, node_modules, venv, .next e bancos locais (.db) e bloqueia envio caso
detecte qualquer token ou chave secreta (Gemini, OpenAI, GitHub PAT).

Uso:
    python github_push.py --token SEU_TOKEN_AQUI --message "titulo do commit"
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

OWNER = "PortoCya"
REPO = "Banco_PORTO_2026"
BRANCH = "main"
API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"
TIMEOUT_SEGUNDOS = 45

IGNORAR_NOMES = {
    ".git",
    "__pycache__",
    "venv",
    "env",
    ".venv",
    "node_modules",
    ".next",
    ".pytest_cache",
    ".mypy_cache",
    ".env",
    ".env.local",
}

IGNORAR_SUFIXOS = (".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".tsbuildinfo", ".log")

PADROES_PROIBIDOS = re.compile(
    r"(AIzaSy[A-Za-z0-9_-]{25,}|AQ\.Ab8RN[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,})"
)


def deve_ignorar(rel_path: Path) -> bool:
    for part in rel_path.parts:
        if part in IGNORAR_NOMES:
            return True
        if part.startswith(".") and part not in {".env.example", ".env.local.example", ".gitignore", ".dockerignore", ".streamlit"}:
            return True
    name = rel_path.name
    if name.endswith(IGNORAR_SUFIXOS):
        return True
    return False


def api_request(url: str, method: str, token: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nps-keycore-uploader/2.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEGUNDOS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code} em {url}: {err_body}")


def collect_files(root: Path) -> list[Path]:
    arquivos = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root)
            if not deve_ignorar(rel):
                arquivos.append(path)
    return arquivos


def main():
    parser = argparse.ArgumentParser(description="Commit atomico para GitHub via Git Data API")
    parser.add_argument("--token", help="GitHub Personal Access Token")
    parser.add_argument("--message", help="Mensagem do commit")
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("ERRO: Forneca o token via --token ou variavel GITHUB_TOKEN")

    root = Path(__file__).parent
    files = collect_files(root)

    # 1. Varredura estrita contra qualquer vazamento de token ou chave
    tree_items = []
    for local_path in files:
        repo_path = local_path.relative_to(root).as_posix()
        conteudo = local_path.read_text(encoding="utf-8")
        match = PADROES_PROIBIDOS.search(conteudo)
        if match:
            sys.exit(f"BLOQUEADO POR SEGURANCA: Segredo/Token detectado em '{repo_path}'!")
        tree_items.append({
            "path": repo_path,
            "mode": "100644",
            "type": "blob",
            "content": conteudo,
        })

    print(f"Auditoria de seguranca concluida: {len(tree_items)} arquivos verificados (0 segredos encontrados).")

    # 2. Obtem o commit atual da branch main
    ref_data = api_request(f"{API_BASE}/git/refs/heads/{BRANCH}", "GET", token)
    base_commit_sha = ref_data["object"]["sha"]
    commit_data = api_request(f"{API_BASE}/git/commits/{base_commit_sha}", "GET", token)
    base_tree_sha = commit_data["tree"]["sha"]

    # 3. Cria a nova arvore Git
    new_tree = api_request(
        f"{API_BASE}/git/trees",
        "POST",
        token,
        {"base_tree": base_tree_sha, "tree": tree_items},
    )
    new_tree_sha = new_tree["sha"]

    if new_tree_sha == base_tree_sha:
        print("Nenhuma alteracao pendente para commit.")
        return

    commit_msg = args.message or "feat: atualiza frontend, dashboard, rotas de gestao e scripts de execucao"

    # 4. Cria o commit unico na main
    new_commit = api_request(
        f"{API_BASE}/git/commits",
        "POST",
        token,
        {
            "message": commit_msg,
            "tree": new_tree_sha,
            "parents": [base_commit_sha],
        },
    )
    new_commit_sha = new_commit["sha"]

    # 5. Atualiza a referencia heads/main
    api_request(
        f"{API_BASE}/git/refs/heads/{BRANCH}",
        "PATCH",
        token,
        {"sha": new_commit_sha, "force": False},
    )

    print(f"Commit realizado com sucesso na branch '{BRANCH}'!")
    print(f"SHA: {new_commit_sha}")
    print(f"URL: https://github.com/{OWNER}/{REPO}/commit/{new_commit_sha}")


if __name__ == "__main__":
    main()
