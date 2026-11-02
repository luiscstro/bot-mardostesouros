"""Verificações estáticas e de contrato do repositório: sintaxe, segredos, imports, limites do Discord."""
import ast
import glob
import os
import re
import subprocess
import sys

import pytest

pytestmark = pytest.mark.static

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVOS_PY = sorted(glob.glob(os.path.join(ROOT, "*.py")))

PADROES_SEGREDO = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "Groq key": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    "Discord token": re.compile(r"[MN][A-Za-z\d]{23,27}\.[\w-]{6}\.[\w-]{27,}"),
    "Chave privada": re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
}


def segredos_em(caminho):
    with open(caminho, encoding="utf-8", errors="ignore") as f:
        conteudo = f.read()
    return [nome for nome, rx in PADROES_SEGREDO.items() if rx.search(conteudo)]


@pytest.mark.parametrize("caminho", ARQUIVOS_PY, ids=os.path.basename)
def test_sintaxe_valida(caminho):
    with open(caminho, encoding="utf-8") as f:
        ast.parse(f.read(), filename=caminho)


@pytest.mark.parametrize("caminho", ARQUIVOS_PY, ids=os.path.basename)
def test_nenhum_segredo_no_codigo(caminho):
    assert segredos_em(caminho) == [], f"{os.path.basename(caminho)} contém segredo hardcoded; use variável de ambiente"


def test_arquivos_sensiveis_estao_no_gitignore():
    with open(os.path.join(ROOT, ".gitignore")) as f:
        conteudo = f.read()
    for item in [".env", "mensagens.json", ".doffy_cache.json", "bot-discord-470223-41527625dc96.json"]:
        assert item in conteudo, f"{item} deveria estar no .gitignore"


def test_credenciais_nao_estao_versionadas():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("git indisponível")
    if out.returncode != 0:
        pytest.skip("não é um repositório git")
    versionados = out.stdout.split()
    proibidos = [f for f in versionados if f.endswith(".env") or f in {"mensagens.json", ".doffy_cache.json"}
                 or re.match(r"bot-discord-.*\.json$", f)]
    assert proibidos == []


def test_importar_main_nao_conecta_nem_trava():
    """Importa em processo isolado: tem que terminar rápido e sem tentar logar."""
    r = subprocess.run([sys.executable, "-c", "import main; print('IMPORT_OK')"], cwd=ROOT,
                       capture_output=True, text=True, timeout=60, env={**os.environ, "DISCORD_TOKEN": ""})
    assert r.returncode == 0 and "IMPORT_OK" in r.stdout, r.stderr[-500:]


def test_main_so_executa_bot_sob_name_main():
    with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    chamadas_no_topo = [n for n in arvore.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                        and "run" in ast.dump(n.value.func)]
    assert chamadas_no_topo == [], "bot.run no nível do módulo impede importar main.py"


def test_discloud_aponta_para_arquivo_existente():
    with open(os.path.join(ROOT, "discloud.config")) as f:
        cfg = dict(l.strip().split("=", 1) for l in f if "=" in l)
    assert os.path.exists(os.path.join(ROOT, cfg["MAIN"]))


def test_dependencias_de_terceiros_estao_no_requirements():
    """Todo import de pacote externo nos módulos do bot precisa estar em requirements.txt."""
    pacote = {"discord": "discord.py", "gspread": "gspread", "oauth2client": "oauth2client",
              "groq": "groq", "dotenv": "dotenv", "aiohttp": "discord.py"}   # aiohttp vem junto do discord.py
    with open(os.path.join(ROOT, "requirements.txt")) as f:
        reqs = {l.strip().lower().replace("_", "-") for l in f if l.strip() and not l.startswith("#")}
    reqs_norm = {r.split("==")[0].split(">=")[0] for r in reqs}
    faltando = set()
    for arq in ["main.py", "ai.py", "racas.py"]:
        with open(os.path.join(ROOT, arq), encoding="utf-8") as f:
            for no in ast.walk(ast.parse(f.read())):
                nomes = [a.name.split(".")[0] for a in no.names] if isinstance(no, ast.Import) else \
                        [no.module.split(".")[0]] if isinstance(no, ast.ImportFrom) and no.module else []
                for n in nomes:
                    if n in pacote:
                        alvo = pacote[n].lower()
                        if alvo not in reqs_norm and not (alvo == "dotenv" and "python-dotenv" in reqs_norm) \
                                and not (alvo == "dotenv" and "dotenv" in reqs_norm):
                            faltando.add(n)
    assert faltando == set()


def test_modulos_do_bot_so_importam_stdlib_e_dependencias_declaradas():
    stdlib = set(sys.stdlib_module_names)
    permitidos = {"discord", "gspread", "oauth2client", "groq", "dotenv", "aiohttp"}
    for arq in ["main.py", "ai.py", "racas.py"]:
        with open(os.path.join(ROOT, arq), encoding="utf-8") as f:
            for no in ast.walk(ast.parse(f.read())):
                nomes = [a.name.split(".")[0] for a in no.names] if isinstance(no, ast.Import) else \
                        [no.module.split(".")[0]] if isinstance(no, ast.ImportFrom) and no.module else []
                for n in nomes:
                    assert n in stdlib or n in permitidos or n in {"ai", "racas"}, f"{arq} importa {n}"


# --------------------------------------------------------- limites do Discord ---
def test_botoes_respeitam_limites_do_discord():
    import racas
    for view in (racas.TicketView(), racas.RollView(), racas.DeleteTicketView()):
        for item in view.children:
            assert len(item.label) <= 80
            assert len(item.custom_id) <= 100


@pytest.mark.parametrize("rank", ["C", "B", "A"])
def test_painel_da_loja_cabe_em_uma_mensagem(main_mod, rank):
    # nome da fruta de até 100 chars (limite razoável do nome na planilha)
    assert len(main_mod.get_msg_content(rank, "x" * 100)) <= 2000


def test_mensagens_de_anuncio_cabem_no_embed(main_mod):
    assert all(len(f) <= 4096 for f in main_mod.frases)
    assert all(g.startswith("https://") for g in main_mod.gifs)
    assert all(re.fullmatch(r"<@&\d+>", m) for m in main_mod.mentions)


def test_ids_de_configuracao_sao_snowflakes(main_mod):
    import racas
    ids = [main_mod.ID_CANAL_C, main_mod.ID_CANAL_B, main_mod.ID_CANAL_A, main_mod.ID_CARGO_ESPECIAL,
           *main_mod.CARGOS_PERMITIDOS, racas.ROLE_LUNARIANO_ID, racas.ROLE_JA_ROLOU_ID,
           racas.CANAL_LOG_ID, *racas.ROLE_STAFF_IDS]
    assert all(isinstance(i, int) and 10**16 < i < 10**20 for i in ids)
    assert len(set([main_mod.ID_CANAL_C, main_mod.ID_CANAL_B, main_mod.ID_CANAL_A])) == 3


def test_staff_do_racas_esta_contido_na_staff_do_main(main_mod):
    import racas
    assert set(racas.ROLE_STAFF_IDS) <= set(main_mod.CARGOS_PERMITIDOS)
