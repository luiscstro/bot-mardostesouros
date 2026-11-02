"""atualizar_planilha_status + comandos posse/ingerir/cuspir.

Aqui está o teste de regressão do erro do log:
    APIError: [403]: The caller does not have permission
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from conftest import api_error, make_ctx, make_role, tabela


@pytest.fixture
def valores():
    return tabela(
        ("C", 1, "Gomu Gomu no Mi", ""),
        ("C", 2, "Mera Mera no Mi", "Ingerida por Ace"),
        ("A", 1, "Ope Ope no Mi", ""),
    )


# --------------------------------------------------- atualizar_planilha_status ---
class TestAtualizarPlanilhaStatus:
    async def test_escreve_status_na_linha_e_coluna_certas(self, main_mod, cog_registrado, valores, ctx):
        cog, sheet = await cog_registrado(valores)
        nome = await main_mod.atualizar_planilha_status(ctx, "gomu", "Ingerida por Luffy")
        assert nome == "Gomu Gomu no Mi"
        # cabeçalho = linha 1; Gomu Gomu = linha 2; coluna Status = 5
        assert sheet.updates == [(2, 5, "Ingerida por Luffy")]

    async def test_limpar_status_escreve_string_vazia(self, main_mod, cog_registrado, valores, ctx):
        cog, sheet = await cog_registrado(valores)
        assert await main_mod.atualizar_planilha_status(ctx, "mera", "") == "Mera Mera no Mi"
        assert sheet.updates == [(3, 5, "")]

    @pytest.mark.parametrize("busca", ["gomu", "GOMU GOMU", "gomugomu", "1", "c1", "C1"])
    async def test_varias_formas_de_buscar(self, main_mod, cog_registrado, valores, ctx, busca):
        cog, sheet = await cog_registrado(valores)
        assert await main_mod.atualizar_planilha_status(ctx, busca, "x") == "Gomu Gomu no Mi"

    async def test_busca_por_rank_e_numero_acha_a_fruta_certa(self, main_mod, cog_registrado, valores, ctx):
        cog, sheet = await cog_registrado(valores)
        assert await main_mod.atualizar_planilha_status(ctx, "a1", "x") == "Ope Ope no Mi"
        assert sheet.updates[0][0] == 4

    async def test_fruta_inexistente_avisa_e_nao_escreve(self, main_mod, cog_registrado, valores, ctx):
        cog, sheet = await cog_registrado(valores)
        assert await main_mod.atualizar_planilha_status(ctx, "naoexiste", "x") is None
        assert sheet.updates == []
        assert "naoexiste" in ctx.send.call_args.args[0]

    async def test_planilha_desconectada(self, main_mod, cog_registrado, ctx):
        cog, sheet = await cog_registrado([])
        cog.sheet = None
        assert await main_mod.atualizar_planilha_status(ctx, "x", "y") is None
        assert "não conectada" in ctx.send.call_args.args[0]

    async def test_cog_nao_registrado(self, main_mod, monkeypatch, ctx):
        monkeypatch.setattr(main_mod.bot, "get_cog", lambda n: None)
        assert await main_mod.atualizar_planilha_status(ctx, "x", "y") is None
        ctx.send.assert_awaited_once()

    # --- regressão do bug do log ---
    async def test_403_avisa_para_compartilhar_como_editor(self, main_mod, cog_registrado, valores, ctx, capsys):
        cog, sheet = await cog_registrado(valores, write_error=api_error(403))
        cog.service_account_email = "bot@proj.iam.gserviceaccount.com"
        assert await main_mod.atualizar_planilha_status(ctx, "gomu", "x") is None
        msg = ctx.send.call_args.args[0]
        assert "Editor" in msg
        assert "bot@proj.iam.gserviceaccount.com" in msg
        assert "403" in capsys.readouterr().out  # ficou no log

    async def test_403_sem_email_conhecido_ainda_responde(self, main_mod, cog_registrado, valores, ctx):
        cog, _ = await cog_registrado(valores, write_error=api_error(403))
        cog.service_account_email = None
        assert await main_mod.atualizar_planilha_status(ctx, "gomu", "x") is None
        assert "Editor" in ctx.send.call_args.args[0]

    @pytest.mark.parametrize("codigo", [400, 429, 500, 503])
    async def test_outros_erros_da_api_tem_mensagem_generica(self, main_mod, cog_registrado, valores, ctx, codigo):
        cog, _ = await cog_registrado(valores, write_error=api_error(codigo, "falha"))
        assert await main_mod.atualizar_planilha_status(ctx, "gomu", "x") is None
        msg = ctx.send.call_args.args[0]
        assert "Editor" not in msg and "recusou" in msg

    async def test_erro_na_leitura_da_api_nao_vaza_excecao(self, main_mod, cog_registrado, valores, ctx):
        # get_frutas engole o erro (retorna []) -> "não achei", mas nunca levanta
        cog, _ = await cog_registrado(valores, read_error=api_error(403))
        assert await main_mod.atualizar_planilha_status(ctx, "gomu", "x") is None

    async def test_erro_inesperado_que_nao_e_apierror_propaga(self, main_mod, cog_registrado, valores, ctx):
        cog, _ = await cog_registrado(valores, write_error=RuntimeError("bug"))
        with pytest.raises(RuntimeError):
            await main_mod.atualizar_planilha_status(ctx, "gomu", "x")

    async def test_nome_duplicado_atualiza_a_primeira_ocorrencia(self, main_mod, cog_registrado, ctx):
        v = tabela(("C", 1, "Igual", ""), ("B", 1, "Igual", ""))
        cog, sheet = await cog_registrado(v)
        await main_mod.atualizar_planilha_status(ctx, "igual", "x")
        assert sheet.updates == [(2, 5, "x")]


# ---------------------------------------------------------------- comandos ---
class TestPosse:
    async def test_sucesso(self, main_mod, cog_registrado, valores, staff_ctx):
        cog, sheet = await cog_registrado(valores)
        msg = AsyncMock()
        staff_ctx.send.return_value = msg
        await main_mod.posse.callback(staff_ctx, texto="Gomu Gomu, Piratas do Sol")
        assert sheet.updates == [(2, 5, "Em posse do bando Piratas do Sol")]
        assert "Sucesso" in msg.edit.call_args.kwargs["content"]

    async def test_sem_virgula_nao_escreve(self, main_mod, cog_registrado, valores, staff_ctx):
        cog, sheet = await cog_registrado(valores)
        await main_mod.posse.callback(staff_ctx, texto="Gomu Gomu Piratas")
        assert sheet.updates == []
        assert "vírgula" in staff_ctx.send.call_args.args[0]

    async def test_virgula_extra_fica_no_nome_do_bando(self, main_mod, cog_registrado, valores, staff_ctx):
        cog, sheet = await cog_registrado(valores)
        staff_ctx.send.return_value = AsyncMock()
        await main_mod.posse.callback(staff_ctx, texto="Gomu, Bando A, B")
        assert sheet.updates[0][2] == "Em posse do bando Bando A, B"

    async def test_403_nao_deixa_mensagem_presa_em_aguarde(self, main_mod, cog_registrado, valores, staff_ctx):
        """Antes da correção a exceção subia e a msg ficava em '⏳ ... Aguarde.' para sempre."""
        cog, _ = await cog_registrado(valores, write_error=api_error(403))
        msg = AsyncMock()
        staff_ctx.send.return_value = msg
        await main_mod.posse.callback(staff_ctx, texto="Gomu, Bando")  # não pode levantar
        assert "Falha" in msg.edit.call_args.kwargs["content"]


class TestCuspir:
    async def test_limpa_status(self, main_mod, cog_registrado, valores, staff_ctx):
        cog, sheet = await cog_registrado(valores)
        staff_ctx.send.return_value = AsyncMock()
        await main_mod.cuspir.callback(staff_ctx, busca_fruta="mera")
        assert sheet.updates == [(3, 5, "")]

    async def test_fruta_inexistente(self, main_mod, cog_registrado, valores, staff_ctx):
        cog, sheet = await cog_registrado(valores)
        msg = AsyncMock()
        staff_ctx.send.return_value = msg
        await main_mod.cuspir.callback(staff_ctx, busca_fruta="zzz")
        assert "Falha" in msg.edit.call_args.kwargs["content"]
        assert sheet.updates == []

    async def test_403(self, main_mod, cog_registrado, valores, staff_ctx):
        cog, _ = await cog_registrado(valores, write_error=api_error(403))
        msg = AsyncMock()
        staff_ctx.send.return_value = msg
        await main_mod.cuspir.callback(staff_ctx, busca_fruta="mera")
        assert "Falha" in msg.edit.call_args.kwargs["content"]


class TestIngerir:
    async def test_aprovado_pela_staff_escreve_nick_do_jogador(self, main_mod, cog_registrado, valores, ctx, monkeypatch):
        cog, sheet = await cog_registrado(valores)
        msg = AsyncMock()
        msg.id = 10
        ctx.send.return_value = msg
        ctx.author.display_name = "Luffy"
        monkeypatch.setattr(main_mod.bot, "wait_for", AsyncMock(return_value=(MagicMock(), MagicMock(mention="<@s>"))))
        await main_mod.ingerir.callback(ctx, busca_fruta="gomu")
        assert sheet.updates == [(2, 5, "Ingerida por Luffy")]
        msg.add_reaction.assert_awaited_with("✅")
        msg.clear_reactions.assert_awaited()

    async def test_timeout_expira_sem_escrever(self, main_mod, cog_registrado, valores, ctx, monkeypatch):
        cog, sheet = await cog_registrado(valores)
        msg = AsyncMock()
        ctx.send.return_value = msg
        monkeypatch.setattr(main_mod.bot, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError))
        await main_mod.ingerir.callback(ctx, busca_fruta="gomu")
        assert sheet.updates == []
        assert "expirou" in msg.edit.call_args.kwargs["content"]

    async def test_fruta_inexistente_depois_de_aprovada(self, main_mod, cog_registrado, valores, ctx, monkeypatch):
        cog, sheet = await cog_registrado(valores)
        msg = AsyncMock()
        ctx.send.return_value = msg
        monkeypatch.setattr(main_mod.bot, "wait_for", AsyncMock(return_value=(MagicMock(), MagicMock(mention="<@s>"))))
        await main_mod.ingerir.callback(ctx, busca_fruta="zzz")
        assert "Não consegui" in msg.edit.call_args.kwargs["content"]

    async def test_403_depois_de_aprovada_nao_levanta(self, main_mod, cog_registrado, valores, ctx, monkeypatch):
        cog, _ = await cog_registrado(valores, write_error=api_error(403))
        msg = AsyncMock()
        ctx.send.return_value = msg
        monkeypatch.setattr(main_mod.bot, "wait_for", AsyncMock(return_value=(MagicMock(), MagicMock(mention="<@s>"))))
        await main_mod.ingerir.callback(ctx, busca_fruta="gomu")
        assert "Não consegui" in msg.edit.call_args.kwargs["content"]

    async def test_check_do_wait_for_so_aceita_staff(self, main_mod, cog_registrado, valores, ctx, monkeypatch):
        cog, _ = await cog_registrado(valores)
        msg = AsyncMock()
        msg.id = 99
        ctx.send.return_value = msg
        capturado = {}

        async def fake_wait_for(evento, timeout, check):
            capturado["check"] = check
            raise asyncio.TimeoutError

        monkeypatch.setattr(main_mod.bot, "wait_for", fake_wait_for)
        await main_mod.ingerir.callback(ctx, busca_fruta="gomu")
        check = capturado["check"]

        def reacao(msg_id=99, emoji="✅"):
            r = MagicMock()
            r.message.id = msg_id
            r.emoji = emoji
            return r

        staff = MagicMock(roles=[make_role(main_mod.CARGOS_PERMITIDOS[0])])
        jogador = MagicMock(roles=[make_role(1)])
        sem_roles = MagicMock(spec=[])  # sem atributo roles (ex.: discord.User)
        assert check(reacao(), staff) is True
        assert check(reacao(), jogador) is False
        assert check(reacao(), sem_roles) is False
        assert check(reacao(msg_id=1), staff) is False      # outra mensagem
        assert check(reacao(emoji="❌"), staff) is False     # outro emoji
        bot_user = MagicMock(roles=[make_role(main_mod.CARGOS_PERMITIDOS[0])])  # até com cargo staff
        monkeypatch.setattr(main_mod.bot._connection, "user", bot_user, raising=False)
        assert check(reacao(), bot_user) is False             # o próprio bot
