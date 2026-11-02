"""Fixtures compartilhadas: planilha falsa, ctx falso e isolamento do estado global do bot."""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import gspread
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import main as main_module  # noqa: E402  (precisa do sys.path acima)


# ---------------------------------------------------------------- planilha ---
HEADER = ["Rank", "N°", "Nome", "Descrição", "Status"]


def tabela(*frutas, cabecalho=HEADER, linhas_antes=()):
    """Monta o retorno de get_all_values(): [(rank, num, nome, status), ...]."""
    linhas = [list(l) for l in linhas_antes] + [list(cabecalho)]
    for rank, num, nome, status in frutas:
        linhas.append([rank, str(num), nome, "", status])
    return linhas


def api_error(code=403, message="The caller does not have permission"):
    """Cria um gspread.exceptions.APIError real, igual ao do log de produção."""
    resp = MagicMock()
    resp.status_code = code
    resp.text = message
    resp.json.return_value = {"error": {"code": code, "message": message, "status": "ERR"}}
    return gspread.exceptions.APIError(resp)


class FakeSheet:
    """Imita o worksheet do gspread (só o que o bot usa)."""

    def __init__(self, valores=None, write_error=None, read_error=None):
        self.valores = valores if valores is not None else []
        self.write_error = write_error
        self.read_error = read_error
        self.updates = []  # (row, col, value) de cada update_cell

    def get_all_values(self):
        if self.read_error:
            raise self.read_error
        return [list(r) for r in self.valores]

    def update_cell(self, row, col, value):
        if self.write_error:
            raise self.write_error
        self.updates.append((row, col, value))
        while len(self.valores[row - 1]) < col:
            self.valores[row - 1].append("")
        self.valores[row - 1][col - 1] = value


# --------------------------------------------------------------- discord ---
def make_role(role_id, name="role"):
    r = MagicMock()
    r.id = role_id
    r.name = name
    return r


def make_ctx(roles=(), author_name="Luis"):
    """ctx falso com send/typing/message assíncronos."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    ctx.reply = AsyncMock()
    ctx.author = MagicMock()
    ctx.author.roles = list(roles)
    ctx.author.display_name = author_name
    ctx.author.mention = f"<@{author_name}>"
    ctx.message = MagicMock()
    ctx.message.delete = AsyncMock()
    ctx.message.add_reaction = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.send = AsyncMock()
    ctx.channel.purge = AsyncMock()
    ctx.guild = MagicMock()
    ctx.bot = main_module.bot

    typing_cm = MagicMock()
    typing_cm.__aenter__ = AsyncMock(return_value=None)
    typing_cm.__aexit__ = AsyncMock(return_value=False)
    ctx.typing = MagicMock(return_value=typing_cm)
    return ctx


@pytest.fixture
def staff_role():
    return make_role(main_module.CARGOS_PERMITIDOS[0], "Staff")


@pytest.fixture
def ctx():
    return make_ctx()


@pytest.fixture
def staff_ctx(staff_role):
    return make_ctx(roles=[staff_role])


# ------------------------------------------------------------ estado global ---
@pytest.fixture(autouse=True)
def estado_isolado(tmp_path, monkeypatch):
    """Cada teste começa com arquivos em tmp_path e variáveis globais zeradas."""
    m = main_module
    monkeypatch.setattr(m, "ARQUIVO_MSGS", str(tmp_path / "mensagens.json"))
    monkeypatch.setattr(m, "ARQUIVO_CACHE", str(tmp_path / ".doffy_cache.json"))
    monkeypatch.setattr(m, "msg_ids", {"C": None, "B": None, "A": None})
    monkeypatch.setattr(m, "history", {"C": [], "B": [], "A": []})
    monkeypatch.setattr(m, "announce_on", True)
    monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)
    # bot.wait_for real exige o bot conectado; por padrão "ninguém reage" (timeout).
    monkeypatch.setattr(m.bot, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError), raising=False)
    yield


@pytest.fixture
def main_mod():
    return main_module


@pytest.fixture
def cog_factory(monkeypatch):
    """Cria um EstoqueCog sem tocar no Google; devolve (cog, sheet)."""

    def _make(valores=None, **kw):
        monkeypatch.setattr(main_module.EstoqueCog, "connect_gsheets", lambda self: True)
        cog = main_module.EstoqueCog(main_module.bot)
        cog.sheet = FakeSheet(valores, **kw)
        return cog, cog.sheet

    return _make


@pytest.fixture
def cog_registrado(cog_factory, monkeypatch):
    """EstoqueCog registrado no bot real (para bot.get_cog funcionar)."""

    async def _make(valores=None, **kw):
        cog, sheet = cog_factory(valores, **kw)
        monkeypatch.setattr(main_module.bot, "get_cog", lambda nome: cog if nome == "EstoqueCog" else None)
        return cog, sheet

    return _make


@pytest.fixture
def frutas_basicas():
    return tabela(
        ("C", 1, "Gomu Gomu no Mi", ""),
        ("C", 2, "Mera Mera no Mi", "Ingerida por Ace"),
        ("C", 3, "Hana Hana no Mi", ""),
        ("B", 1, "Bara Bara no Mi", ""),
        ("A", 1, "Ope Ope no Mi", "Em posse do bando Heart"),
        ("A", 2, "Netsu Netsu no Mi", ""),
        ("S", 1, "Hito Hito no Mi Model Nika", ""),
    )


# ------------------------------------------------------------------ helpers ---
def http_exc(cls, status=404):
    """discord.NotFound / Forbidden / HTTPException reais."""
    resp = MagicMock()
    resp.status = status
    resp.reason = "erro"
    return cls(resp, "mensagem")


def make_channel(msg_id=1000):
    """Canal falso: send() devolve uma mensagem com id; fetch_message() devolve a mesma."""
    ch = MagicMock()
    msg = MagicMock()
    msg.id = msg_id
    msg.edit = AsyncMock()
    ch.send = AsyncMock(return_value=msg)
    ch.fetch_message = AsyncMock(return_value=msg)
    ch.mention = f"<#{msg_id}>"
    return ch, msg


@pytest.fixture
def bot_user(monkeypatch):
    """Dá uma identidade ao bot (bot.user é None sem conexão)."""
    u = MagicMock()
    u.id = 555
    monkeypatch.setattr(main_module.bot._connection, "user", u, raising=False)
    return u
