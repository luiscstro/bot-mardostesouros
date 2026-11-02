"""Integração: mensagem -> get_context -> invoke reais do discord.ext.commands.

Passa por parsing de argumentos, conversores, checks de permissão e on_command_error,
com planilha e Discord falsos. É o teste mais próximo do uso real sem rede.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.ext import commands

from conftest import api_error, make_role, tabela

pytestmark = pytest.mark.integration


class FakeContext(commands.Context):
    """Context real, mas send/reply/typing só gravam o que seria enviado."""

    async def send(self, content=None, **kwargs):
        self.__dict__.setdefault("enviadas", []).append((content, kwargs))
        m = MagicMock(); m.edit = AsyncMock(); m.add_reaction = AsyncMock(); m.clear_reactions = AsyncMock()
        self.__dict__.setdefault("mensagens", []).append(m)
        return m

    async def reply(self, content=None, **kwargs):
        return await self.send(content, **kwargs)

    def typing(self, **kw):
        cm = MagicMock(); cm.__aenter__ = AsyncMock(); cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    @property
    def textos(self):
        return [c for c, _ in self.__dict__.get("enviadas", []) if isinstance(c, str)]

    @property
    def embeds(self):
        return [k["embed"] for _, k in self.__dict__.get("enviadas", []) if "embed" in k]


@pytest.fixture
def despachar(main_mod, bot_user, monkeypatch):
    """despachar("doffy!proxima", roles=[...]) -> FakeContext já processado."""
    ids_usados = iter(range(1000, 100000))

    async def _run(texto, roles=()):
        # bot.loop só existe depois do login; usa o loop do teste para o dispatch de eventos
        monkeypatch.setattr(main_mod.bot, "loop", asyncio.get_running_loop(), raising=False)
        msg = MagicMock()
        msg.content = texto
        msg.author = MagicMock(id=next(ids_usados), roles=list(roles), display_name="Luis")
        msg.author.get_role = lambda rid: None
        msg.delete = AsyncMock(); msg.add_reaction = AsyncMock()
        msg.channel.send = AsyncMock(); msg.channel.purge = AsyncMock()
        ctx = await main_mod.bot.get_context(msg, cls=FakeContext)
        await main_mod.bot.invoke(ctx)
        for _ in range(10):          # deixa rodar o dispatch('command_error')
            await asyncio.sleep(0)
        return ctx

    return _run


@pytest.fixture
async def bot_com_estoque(main_mod, cog_factory, frutas_basicas):
    """EstoqueCog de verdade registrado no bot (enc/fruta/check_pool disponíveis)."""
    cog, sheet = cog_factory(frutas_basicas)
    await main_mod.bot.add_cog(cog)
    yield cog, sheet
    await main_mod.bot.remove_cog("EstoqueCog")


@pytest.fixture
def staff(main_mod):
    return [make_role(main_mod.CARGOS_PERMITIDOS[0], "Staff")]


# ------------------------------------------------------------------ prefixo ---
class TestRoteamento:
    async def test_sem_prefixo_e_ignorado(self, despachar):
        ctx = await despachar("proxima")
        assert ctx.command is None and ctx.textos == []

    async def test_comando_inexistente_nao_responde(self, despachar):
        ctx = await despachar("doffy!naoexiste")
        assert ctx.textos == [] and ctx.embeds == []

    async def test_publico_sem_cargo(self, despachar):
        ctx = await despachar("doffy!proxima")
        assert "Próxima Atualização" in ctx.embeds[0].title

    async def test_ajuda_publica(self, despachar):
        ctx = await despachar("doffy!ajuda")
        assert [f.name for f in ctx.embeds[0].fields] == ["📖 Público"]

    async def test_ajuda_staff(self, despachar, staff):
        ctx = await despachar("doffy!ajuda", staff)
        assert "🔒 Staff" in [f.name for f in ctx.embeds[0].fields]


# --------------------------------------------------------------- permissões ---
class TestPermissoesReais:
    @pytest.mark.parametrize("cmd", ["limpar 5", "anuncio off", "historico", "simular", "forcarteste",
                                     "reroll c", "say oi", "posse a, b", "cuspir a"])
    async def test_membro_comum_recebe_sem_permissao(self, despachar, main_mod, cmd):
        ctx = await despachar(f"doffy!{cmd}")
        assert ctx.textos == ["🚫 Sem permissão."]
        assert main_mod.announce_on is True   # nada foi executado

    async def test_staff_executa(self, despachar, staff):
        ctx = await despachar("doffy!limpar 5", staff)
        ctx.channel.purge.assert_awaited_once_with(limit=6)

    async def test_pl_nao_responde_para_ninguem_que_nao_seja_dono(self, despachar, main_mod, monkeypatch, staff):
        monkeypatch.setattr(main_mod.bot, "is_owner", AsyncMock(return_value=False))
        ctx = await despachar("doffy!pl 1 5c", staff)
        assert ctx.textos == []


# ------------------------------------------------------- parsing de argumentos ---
class TestArgumentos:
    async def test_argumento_obrigatorio_faltando(self, despachar, staff):
        ctx = await despachar("doffy!reroll", staff)
        assert "Faltou algo" in ctx.textos[0]

    async def test_conversor_int_invalido_nao_executa_o_comando(self, despachar, staff, capsys):
        ctx = await despachar("doffy!limpar abc", staff)
        ctx.channel.purge.assert_not_awaited()
        assert "limpar" in capsys.readouterr().out   # on_command_error logou

    async def test_texto_com_espacos_vira_um_unico_argumento(self, despachar, staff):
        ctx = await despachar("doffy!say olá   mundo cruel", staff)
        ctx.channel.send.assert_awaited_once_with("olá   mundo cruel")

    async def test_anuncio_off_liga_desliga_de_ponta_a_ponta(self, despachar, staff, main_mod):
        await despachar("doffy!anuncio off", staff)
        assert main_mod.announce_on is False
        await despachar("doffy!anuncio on", staff)
        assert main_mod.announce_on is True


# ---------------------------------------------- planilha: o bug do log, e2e ---
class TestPlanilhaFimAFim:
    async def test_posse_funciona_quando_a_conta_e_editora(self, despachar, bot_com_estoque, staff):
        cog, sheet = bot_com_estoque
        ctx = await despachar("doffy!posse gomu gomu, Piratas do Sol", staff)
        assert sheet.updates == [(2, 5, "Em posse do bando Piratas do Sol")]
        assert "Sucesso" in ctx.mensagens[0].edit.call_args.kwargs["content"]

    async def test_posse_com_403_responde_ao_usuario_e_nao_gera_erro_nao_tratado(self, despachar, bot_com_estoque, staff, capsys):
        """O cenário exato do log de 31/out: leitura OK, escrita 403."""
        cog, sheet = bot_com_estoque
        sheet.write_error = api_error(403)
        cog.service_account_email = "bot@proj.iam.gserviceaccount.com"
        ctx = await despachar("doffy!posse gomu gomu, Piratas do Sol", staff)
        saida = capsys.readouterr()
        assert any("Editor" in t and "bot@proj.iam.gserviceaccount.com" in t for t in ctx.textos)
        assert "Command raised an exception" not in saida.out + saida.err
        assert "Falha ao atualizar" in ctx.mensagens[0].edit.call_args.kwargs["content"]

    async def test_cuspir_com_403(self, despachar, bot_com_estoque, staff):
        _, sheet = bot_com_estoque
        sheet.write_error = api_error(403)
        ctx = await despachar("doffy!cuspir mera", staff)
        assert any("Editor" in t for t in ctx.textos)

    async def test_cuspir_libera_a_fruta_e_ela_volta_a_aparecer_como_disponivel(self, despachar, bot_com_estoque, staff):
        cog, sheet = bot_com_estoque
        await despachar("doffy!cuspir mera", staff)
        assert "Mera Mera no Mi" in await cog.disponiveis("C")

    async def test_posse_tira_a_fruta_do_pool_de_sorteio(self, despachar, bot_com_estoque, staff):
        cog, _ = bot_com_estoque
        assert "Gomu Gomu no Mi" in await cog.disponiveis("C")
        await despachar("doffy!posse gomu gomu, Bando X", staff)
        assert "Gomu Gomu no Mi" not in await cog.disponiveis("C")

    async def test_leitura_com_403_nao_quebra_o_enc(self, despachar, bot_com_estoque):
        _, sheet = bot_com_estoque
        sheet.read_error = api_error(403)
        ctx = await despachar("doffy!enc")
        assert "Nenhuma fruta" in ctx.textos[0]


class TestConsultasFimAFim:
    async def test_fruta(self, despachar, bot_com_estoque):
        ctx = await despachar("doffy!fruta ope ope")
        assert "Ope Ope" in ctx.embeds[0].title

    async def test_enc_filtrado(self, despachar, bot_com_estoque):
        ctx = await despachar("doffy!enc b")
        assert "Rank B" in ctx.embeds[0].title

    async def test_check_pool_so_staff(self, despachar, bot_com_estoque, staff):
        assert "não tem permissão" in (await despachar("doffy!check_pool")).textos[0]
        ctx = await despachar("doffy!check_pool", staff)
        assert ctx.embeds and "Pool de Sorteio" in ctx.embeds[0].title

    async def test_ciclo_completo_posse_consulta_cuspir(self, despachar, bot_com_estoque, staff):
        await despachar("doffy!posse gomu gomu, Bando Z", staff)
        ctx = await despachar("doffy!fruta gomu gomu")
        assert {f.name: f.value for f in ctx.embeds[0].fields}["Status"] == "Em posse do bando bando z"
        await despachar("doffy!cuspir gomu gomu", staff)
        ctx = await despachar("doffy!fruta gomu gomu")
        assert {f.name: f.value for f in ctx.embeds[0].fields}["Status"] == "Disponível"


# -------------------------------------------------- registro de comandos / contrato ---
class TestRegistroDeComandos:
    COMANDOS_ESPERADOS = {
        "ajuda", "anuncio", "cuspir", "darcargo", "editar", "forcarteste", "historico", "ingerir",
        "limpar", "pl", "posse", "proxima", "reenviar", "reroll", "say", "simular",
        "enc", "fruta", "check_pool",   # EstoqueCog
    }

    async def test_conjunto_de_comandos_nao_mudou_sem_querer(self, main_mod, bot_com_estoque):
        """Se você adicionar/remover um comando de propósito, atualize COMANDOS_ESPERADOS."""
        assert {c.name for c in main_mod.bot.commands} == self.COMANDOS_ESPERADOS

    async def test_nenhum_alias_ou_nome_duplicado(self, main_mod, bot_com_estoque):
        todos = []
        for c in main_mod.bot.commands:
            todos += [c.name, *c.aliases]
        assert len(todos) == len(set(todos))

    async def test_extensoes_ai_e_racas_carregam_e_descarregam(self, main_mod, monkeypatch):
        monkeypatch.setattr("ai.GROQ_API_KEY", None, raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        await main_mod.bot.load_extension("ai")
        await main_mod.bot.load_extension("racas")
        try:
            nomes = {c.name for c in main_mod.bot.commands}
            assert {"chat", "painel_racas"} <= nomes
        finally:
            await main_mod.bot.unload_extension("ai")
            await main_mod.bot.unload_extension("racas")
        assert "chat" not in {c.name for c in main_mod.bot.commands}

    async def test_setup_hook_real_sobe_tudo(self, main_mod, monkeypatch, cog_factory):
        monkeypatch.setattr(main_mod.EstoqueCog, "connect_gsheets", lambda self: True)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.setattr("ai.GROQ_API_KEY", None, raising=False)
        monkeypatch.setattr(main_mod.auto_update, "start", MagicMock())
        monkeypatch.setattr(main_mod.auto_update, "is_running", lambda: False)
        try:
            await main_mod.setup_hook()
            nomes = {c.name for c in main_mod.bot.commands}
            assert {"enc", "fruta", "chat", "painel_racas", "posse"} <= nomes
        finally:
            for ext in ("ai", "racas"):
                if ext in main_mod.bot.extensions:
                    await main_mod.bot.unload_extension(ext)
            if main_mod.bot.get_cog("EstoqueCog"):
                await main_mod.bot.remove_cog("EstoqueCog")
