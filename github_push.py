"""
Script para fazer upload de todos os arquivos do projeto para o GitHub via API REST.
Usa apenas bibliotecas padrão do Python (urllib + json + base64).

Uso:
    python github_push.py --token SEU_TOKEN_AQUI
    ou defina a variável de ambiente GITHUB_TOKEN antes de rodar.
"""
import argparse
import base64
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

# ─── Configuração ─────────────────────────────────────────────────────────────
OWNER = "PortoCya"
REPO = "Banco_PORTO_2026"
BRANCH = "main"
API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"

# Arquivos/pastas a ignorar no upload
IGNORAR = {
    ".git", "__pycache__", "venv", "env", ".venv",
    ".env", "*.db", "*.sqlite", "*.pyc", ".gitignore"
}


def deve_ignorar(path: Path) -> bool:
    name = path.name
    if name.startswith(".") and name != ".env.example":
        return True
    for pat in IGNORAR:
        if pat.startswith("*"):
            if name.endswith(pat[1:]):
                return True
        elif name == pat:
            return True
    return False


def api_request(url: str, method: str, token: str, data: dict = None) -> dict:
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-consulting-uploader/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        raise RuntimeError(f"HTTP {e.code} em {url}: {body}")


def get_file_sha(path_in_repo: str, token: str) -> str | None:
    """Retorna o SHA do arquivo se já existir no repo (necessário para update)."""
    url = f"{API_BASE}/contents/{path_in_repo}?ref={BRANCH}"
    try:
        result = api_request(url, "GET", token)
        return result.get("sha")
    except RuntimeError:
        return None


def upload_file(local_path: Path, repo_path: str, token: str, commit_message: str):
    content = local_path.read_bytes()
    content_b64 = base64.b64encode(content).decode("utf-8")
    sha = get_file_sha(repo_path, token)

    payload = {
        "message": commit_message,
        "content": content_b64,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    url = f"{API_BASE}/contents/{repo_path}"
    api_request(url, "PUT", token, payload)
    action = "Atualizado" if sha else "Criado"
    print(f"  [{action}] {repo_path}")


def ensure_branch_exists(token: str):
    """Cria o branch main se não existir (a partir do default branch)."""
    try:
        api_request(f"{API_BASE}/git/refs/heads/{BRANCH}", "GET", token)
        print(f"Branch '{BRANCH}' ja existe.")
    except RuntimeError:
        # Pega o SHA do HEAD do repo
        info = api_request(API_BASE, "GET", token)
        default_branch = info.get("default_branch", "main")
        if default_branch == BRANCH:
            return
        ref_info = api_request(
            f"{API_BASE}/git/refs/heads/{default_branch}", "GET", token
        )
        sha = ref_info["object"]["sha"]
        api_request(
            f"{API_BASE}/git/refs",
            "POST",
            token,
            {"ref": f"refs/heads/{BRANCH}", "sha": sha},
        )
        print(f"Branch '{BRANCH}' criado.")


def collect_files(root: Path):
    """Coleta todos os arquivos do projeto respeitando IGNORAR."""
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            # Checa cada componente do caminho
            skip = False
            for part in path.relative_to(root).parts:
                if deve_ignorar(Path(part)):
                    skip = True
                    break
            if not skip:
                files.append(path)
    return files


def main():
    parser = argparse.ArgumentParser(description="Upload projeto para GitHub via API")
    parser.add_argument("--token", help="GitHub Personal Access Token")
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERRO: Forneça o token via --token ou variavel GITHUB_TOKEN")
        print("       Crie em: https://github.com/settings/tokens")
        print("       Permissoes necessarias: repo (read/write contents)")
        sys.exit(1)

    root = Path(__file__).parent
    print(f"\nRepositorio: https://github.com/{OWNER}/{REPO}")
    print(f"Branch: {BRANCH}")
    print(f"Diretorio local: {root}\n")

    # Garante que o branch existe
    ensure_branch_exists(token)

    # Coleta e faz upload dos arquivos
    files = collect_files(root)
    print(f"{len(files)} arquivo(s) para upload:\n")

    erros = []
    for local_path in files:
        repo_path = local_path.relative_to(root).as_posix()
        try:
            upload_file(
                local_path,
                repo_path,
                token,
                commit_message=f"chore: add {repo_path}",
            )
        except Exception as exc:
            print(f"  [ERRO] {repo_path}: {exc}")
            erros.append((repo_path, str(exc)))

    print(f"\n{'='*60}")
    print(f"Upload concluido: {len(files) - len(erros)}/{len(files)} arquivos")
    if erros:
        print(f"{len(erros)} erro(s):")
        for path, msg in erros:
            print(f"  - {path}: {msg}")
    else:
        print(f"Repositorio: https://github.com/{OWNER}/{REPO}")

if __name__ == "__main__":
    main()
