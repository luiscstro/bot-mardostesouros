"""Comandos da staff e utilitários: is_staff, say, anuncio, reroll, pl, simular, limpar,
editar, reenviar, darcargo, historico, ajuda, on_command_error, setup_hook, on_ready."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from conftest import api_error, http_exc, make_channel, make_ctx, make_role, tabela

STAFF_CMDS = ["say", "forcarteste", "anuncio", "reroll", "simular", "limpar", "editar",
              "reenviar", "darcargo", "historico", "posse", "cuspir"]


# ------------------------------------------------------------------ is_staff ---
class TestIsStaff:
    def test_cada_cargo_permitido_e_staff(self, main_mod):
        for rid in main_mod.CARGOS_PERMITIDOS:
            assert main_mod.is_staff(make_ctx(roles=[make_role(rid)])) is True

    def test_cargo_comum_nao_e_staff(self, main_mod):
        assert main_mod.is_staff(make_ctx(roles=[make_role(1), make_role(2)])) is False

    def test_sem_cargos(self, main_mod):
        assert not main_mod.is_staff(make_ctx(roles=[]))

    def test_basta_um_cargo_staff_entre_varios(self, main_mod):
        assert main_mod.is_staff(make_ctx(roles=[make_role(1), make_role(main_mod.CARGOS_PERMITIDOS[1])]))

    def test_cargo_especial_do_darcargo_e_staff(self, main_mod):
        assert main_mod.ID_CARGO_ESPECIAL in main_mod.CARGOS_PERMITIDOS


class TestChecksDeComandos:
    """Contrato de segurança: comandos sensíveis nunca podem ficar sem o check de staff."""

    @pytest.mark.parametrize("nome", STAFF_CMDS)
    def test_comando_exige_staff(self, main_mod, nome):
        cmd = main_mod.bot.get_command(nome)
        assert cmd is not None, f"comando {nome} sumiu"
        assert len(cmd.checks) >= 1, f"{nome} está sem check de permissão!"

    @pytest.mark.parametrize("nome", STAFF_CMDS)
    async def test_check_bloqueia_membro_comum(self, main_mod, nome):
        cmd = main_mod.bot.get_command(nome)
        ctx = make_ctx(roles=[make_role(1)])
        ctx.command = cmd
        assert await cmd.can_run(ctx) is False

    @pytest.mark.parametrize("nome", STAFF_CMDS)
    async def test_check_libera_staff(self, main_mod, nome, staff_role):
        ctx = make_ctx(roles=[staff_role])
        ctx.command = main_mod.bot.get_command(nome)
        assert await main_mod.bot.get_command(nome).can_run(ctx) is True

    @pytest.mark.parametrize("nome", ["ajuda", "proxima", "ingerir"])
    def test_comandos_publicos_nao_tem_check(self, main_mod, nome):
        assert main_mod.bot.get_command(nome).checks == []


# ----------------------------------------------------------------------- say ---
class TestSay:
    async def test_apaga_comando_e_envia(self, main_mod, staff_ctx):
        await main_mod.say.callback(staff_ctx, m="oi")
        staff_ctx.message.delete.assert_awaited_once()
        staff_ctx.channel.send.assert_awaited_once_with("oi")

    async def test_falha_ao_apagar_nao_impede_envio(self, main_mod, staff_ctx):
        staff_ctx.message.delete.side_effect = discord.Forbidden(MagicMock(status=403, reason="x"), "x")
        await main_mod.say.callback(staff_ctx, m="oi")
        staff_ctx.channel.send.assert_awaited_once()

    async def test_texto_longo_e_dividido(self, main_mod, staff_ctx):
        await main_mod.say.callback(staff_ctx, m="x" * 4500)
        assert staff_ctx.channel.send.await_count == 3


    async def test_anexo_e_reenviado_sem_alterar(self, main_mod, staff_ctx):
        arq = MagicMock()
        anexo = MagicMock()
        anexo.to_file = AsyncMock(return_value=arq)
        staff_ctx.message.attachments = [anexo]
        await main_mod.say.callback(staff_ctx, m="legenda")
        anexo.to_file.assert_awaited_once_with()
        staff_ctx.channel.send.assert_awaited_once_with("legenda", files=[arq])

    async def test_so_anexo_sem_texto(self, main_mod, staff_ctx):
        arq = MagicMock()
        anexo = MagicMock()
        anexo.to_file = AsyncMock(return_value=arq)
        staff_ctx.message.attachments = [anexo]
        await main_mod.say.callback(staff_ctx)
        staff_ctx.channel.send.assert_awaited_once_with(None, files=[arq])

    async def test_sem_texto_e_sem_anexo_avisa(self, main_mod, staff_ctx):
        staff_ctx.message.attachments = []
        await main_mod.say.callback(staff_ctx)
        staff_ctx.channel.send.assert_not_awaited()
        staff_ctx.message.delete.assert_not_awaited()


# ------------------------------------------------------------------- anuncio ---
class TestAnuncio:
    async def test_off_e_on(self, main_mod, staff_ctx):
        await main_mod.anuncio.callback(staff_ctx, acao="off")
        assert main_mod.announce_on is False
        await main_mod.anuncio.callback(staff_ctx, acao="on")
        assert main_mod.announce_on is True

    async def test_sem_argumento_mantem_estado(self, main_mod, staff_ctx):
        main_mod.announce_on = False
        await main_mod.anuncio.callback(staff_ctx)
        assert main_mod.announce_on is False
        assert "False" in staff_ctx.send.call_args.args[0]

    async def test_argumento_invalido_mantem_estado(self, main_mod, staff_ctx):
        await main_mod.anuncio.callback(staff_ctx, acao="talvez")
        assert main_mod.announce_on is True

    async def test_persiste_em_disco(self, main_mod, staff_ctx):
        await main_mod.anuncio.callback(staff_ctx, acao="off")
        main_mod.announce_on = True
        main_mod.load()
        assert main_mod.announce_on is False


# ---------------------------------------------------------------- forcarteste ---
class TestForcarTeste:
    async def test_roda_update_e_confirma(self, main_mod, staff_ctx, monkeypatch):
        run = AsyncMock(); monkeypatch.setattr(main_mod, "run_update", run)
        await main_mod.forcarteste.callback(staff_ctx)
        staff_ctx.message.add_reaction.assert_awaited_with("🔄")
        run.assert_awaited_once()
        assert staff_ctx.send.call_args.args[0] == "✅ Feito!"


# -------------------------------------------------------------------- reroll ---
class TestReroll:
    @pytest.fixture
    def setup(self, main_mod, cog_registrado, monkeypatch):
        async def _s(valores=None):
            valores = valores or tabela(("C", 1, "C1", ""), ("C", 2, "C2", ""), ("B", 1, "B1", ""))
            cog, sheet = await cog_registrado(valores)
            ch, msg = make_channel(7)
            monkeypatch.setattr(main_mod.bot, "get_channel", lambda cid: ch)
            return cog, ch, msg
        return _s

    async def test_rank_invalido_ignora_em_silencio(self, main_mod, staff_ctx, setup):
        _, ch, _ = await setup()
        await main_mod.reroll.callback(staff_ctx, rank="X")
        ch.send.assert_not_awaited(); staff_ctx.send.assert_not_awaited()

    async def test_fruta_explicita_cria_mensagem(self, main_mod, staff_ctx, setup):
        _, ch, msg = await setup()
        await main_mod.reroll.callback(staff_ctx, rank="c", fruta="Mera Mera")   # rank minúsculo
        assert "# Mera Mera" in ch.send.call_args.args[0]
        assert main_mod.msg_ids["C"] == 7
        staff_ctx.message.add_reaction.assert_awaited_with("✅")

    async def test_edita_mensagem_existente(self, main_mod, staff_ctx, setup):
        _, ch, msg = await setup()
        main_mod.msg_ids["B"] = 99
        await main_mod.reroll.callback(staff_ctx, rank="B", fruta="Outra")
        ch.send.assert_not_awaited()
        msg.edit.assert_awaited_once()

    async def test_mensagem_apagada_cria_nova(self, main_mod, staff_ctx, setup):
        _, ch, msg = await setup()
        main_mod.msg_ids["B"] = 99
        ch.fetch_message.side_effect = http_exc(discord.NotFound)
        await main_mod.reroll.callback(staff_ctx, rank="B", fruta="Outra")
        ch.send.assert_awaited_once()

    async def test_sem_fruta_sorteia_da_planilha_e_registra_historico(self, main_mod, staff_ctx, setup):
        await setup()
        await main_mod.reroll.callback(staff_ctx, rank="C")
        assert main_mod.history["C"][0] in {"C1", "C2"}

    async def test_erro_de_leitura_nao_diz_que_nao_ha_frutas(self, main_mod, staff_ctx, setup):
        cog, ch, _ = await setup()
        cog.sheet.read_error = api_error(403)
        await main_mod.reroll.callback(staff_ctx, rank="C")
        assert "Não consegui ler" in staff_ctx.send.call_args.args[0]
        ch.send.assert_not_awaited()

    async def test_sem_frutas_disponiveis(self, main_mod, staff_ctx, setup):
        await setup(tabela(("C", 1, "C1", "ocupada")))
        await main_mod.reroll.callback(staff_ctx, rank="C")
        assert staff_ctx.send.call_args.args[0] == "Sem frutas."

    async def test_salva_estado(self, main_mod, staff_ctx, setup):
        await setup()
        await main_mod.reroll.callback(staff_ctx, rank="C", fruta="X")
        main_mod.msg_ids["C"] = None
        main_mod.load()
        assert main_mod.msg_ids["C"] == 7

    async def test_canal_inexistente_avisa_em_vez_de_quebrar(self, main_mod, staff_ctx, cog_registrado, monkeypatch):
        """Regressão: get_channel -> None causava AttributeError."""
        await cog_registrado(tabela(("C", 1, "C1", "")))
        monkeypatch.setattr(main_mod.bot, "get_channel", lambda cid: None)
        await main_mod.reroll.callback(staff_ctx, rank="C", fruta="X")
        assert "não encontrado" in staff_ctx.send.call_args.args[0]
        staff_ctx.message.add_reaction.assert_not_awaited()
        assert main_mod.msg_ids["C"] is None


# ------------------------------------------------------------------------ pl ---
class TestPl:
    @pytest.fixture
    def setup(self, main_mod, cog_registrado, monkeypatch):
        async def _s(dono=True):
            cog, _ = await cog_registrado(tabela(("C", 5, "Fruta C5", ""), ("A", 2, "Fruta A2", "")))
            monkeypatch.setattr(main_mod.bot, "is_owner", AsyncMock(return_value=dono))
        return _s

    async def test_nao_dono_e_ignorado_por_completo(self, main_mod, ctx, setup):
        await setup(dono=False)
        await main_mod.pl.callback(ctx, x="1", slot="c5")
        ctx.send.assert_not_awaited(); ctx.message.delete.assert_not_awaited()
        assert main_mod._cache_load_sync()["agenda"] == {"C": {}, "B": {}, "A": {}}

    async def test_agenda_fruta_para_daqui_n_rotacoes(self, main_mod, ctx, setup):
        await setup()
        main_mod._cache_save_sync({"contador": 3, "agenda": {"C": {}, "B": {}, "A": {}}})
        await main_mod.pl.callback(ctx, x="2", slot="5c")
        assert main_mod._cache_load_sync()["agenda"]["C"] == {"5": "Fruta C5"}   # 3 + 2
        ctx.message.delete.assert_awaited_once()                                 # esconde o comando
        assert ctx.send.call_args.kwargs["delete_after"] == 3

    @pytest.mark.parametrize("slot", ["2a", "2A", "  2 a "])
    async def test_rank_em_maiusculo_ou_minusculo_e_espacos(self, main_mod, ctx, setup, slot):
        await setup()
        await main_mod.pl.callback(ctx, x="1", slot=slot)
        assert main_mod._cache_load_sync()["agenda"]["A"] == {"1": "Fruta A2"}

    @pytest.mark.parametrize("x,slot", [
        (None, "5c"), ("abc", "5c"), ("0", "5c"), ("-1", "5c"),   # rotações inválidas
        ("1", None), ("1", ""), ("1", "c"), ("1", "5"), ("1", "c5"), ("1", "5cc"),   # slot inválido (formato é <num><rank>)
        ("1", "5s"), ("1", "5z"),                                        # rank fora de C/B/A
        ("1", "99c"), ("1", "5b"),                                       # fruta inexistente
    ])
    async def test_entradas_invalidas_respondem_x_sem_agendar(self, main_mod, ctx, setup, x, slot):
        await setup()
        await main_mod.pl.callback(ctx, x=x, slot=slot)
        assert ctx.send.call_args.args[0] == "❌"
        assert main_mod._cache_load_sync()["agenda"] == {"C": {}, "B": {}, "A": {}}

    async def test_falha_ao_apagar_mensagem_nao_impede(self, main_mod, ctx, setup):
        await setup()
        ctx.message.delete.side_effect = RuntimeError("x")
        await main_mod.pl.callback(ctx, x="1", slot="5c")
        assert "✅" in ctx.send.call_args.args[0]

    def test_comando_e_oculto(self, main_mod):
        assert main_mod.pl.hidden is True


# ------------------------------------------------------------------- simular ---
class TestSimular:
    async def test_nao_mexe_em_canais_oficiais_historico_nem_arquivos(self, main_mod, staff_ctx, cog_registrado, monkeypatch):
        await cog_registrado(tabela(("C", 1, "C1", ""), ("B", 1, "B1", ""), ("A", 1, "A1", "")))
        oficial = MagicMock(); oficial.send = AsyncMock()
        monkeypatch.setattr(main_mod.bot, "get_channel", lambda cid: oficial)
        antes = {k: list(v) for k, v in main_mod.history.items()}
        await main_mod.simular.callback(staff_ctx)
        oficial.send.assert_not_awaited()
        assert main_mod.history == antes
        assert main_mod.msg_ids == {"C": None, "B": None, "A": None}

    async def test_envia_3_paineis_no_canal_atual_e_resumo(self, main_mod, staff_ctx, cog_registrado):
        await cog_registrado(tabela(("C", 1, "C1", ""), ("B", 1, "B1", ""), ("A", 1, "A1", "")))
        await main_mod.simular.callback(staff_ctx)
        paineis = [c.args[0] for c in staff_ctx.channel.send.call_args_list]
        assert len(paineis) == 3 and all("[SIMULAÇÃO" in p for p in paineis)
        assert "Simulação Concluída" in staff_ctx.send.call_args.args[0]

    async def test_rank_sem_fruta_vira_esgotado(self, main_mod, staff_ctx, cog_registrado):
        await cog_registrado(tabela(("C", 1, "C1", "ocupada"), ("B", 1, "B1", ""), ("A", 1, "A1", "")))
        await main_mod.simular.callback(staff_ctx)
        assert "C: Esgotado" in staff_ctx.send.call_args.args[0]

    async def test_respeita_historico_sem_alterar(self, main_mod, staff_ctx, cog_registrado):
        await cog_registrado(tabela(("C", 1, "C1", ""), ("C", 2, "C2", ""), ("B", 1, "B1", ""), ("A", 1, "A1", "")))
        for _ in range(20):
            main_mod.history["C"] = ["C1"]
            staff_ctx.send.reset_mock()
            await main_mod.simular.callback(staff_ctx)
            assert "C: C2" in staff_ctx.send.call_args.args[0]
            assert main_mod.history["C"] == ["C1"]

    async def test_sem_cog(self, main_mod, staff_ctx, monkeypatch):
        monkeypatch.setattr(main_mod.bot, "get_cog", lambda n: None)
        await main_mod.simular.callback(staff_ctx)
        assert "não conectada" in staff_ctx.send.call_args.args[0]

    async def test_erro_inesperado_e_reportado(self, main_mod, staff_ctx, cog_registrado):
        cog, _ = await cog_registrado(tabela(("C", 1, "C1", "")))
        cog.disponiveis = AsyncMock(side_effect=RuntimeError("quebrou"))
        await main_mod.simular.callback(staff_ctx)
        assert "Erro crítico" in staff_ctx.send.call_args.args[0]


# -------------------------------------------------------------------- limpar ---
class TestLimpar:
    async def test_apaga_quantidade_mais_o_proprio_comando(self, main_mod, staff_ctx):
        await main_mod.limpar.callback(staff_ctx, quantidade=10)
        staff_ctx.channel.purge.assert_awaited_once_with(limit=11)
        assert "10" in staff_ctx.send.call_args.args[0]

    async def test_padrao_100(self, main_mod, staff_ctx):
        await main_mod.limpar.callback(staff_ctx)
        staff_ctx.channel.purge.assert_awaited_once_with(limit=101)

    def test_quantidade_nao_numerica_e_rejeitada_pelo_conversor(self, main_mod):
        assert main_mod.limpar.clean_params["quantidade"].annotation is int


# -------------------------------------------------------------------- editar ---
class TestEditar:
    @pytest.fixture
    def conversor(self, main_mod):
        with patch.object(main_mod.commands, "MessageConverter") as cls:
            inst = MagicMock(); inst.convert = AsyncMock(); cls.return_value = inst
            yield inst

    async def test_edita_mensagem_do_proprio_bot(self, main_mod, staff_ctx, conversor, bot_user):
        msg = MagicMock(author=bot_user, edit=AsyncMock()); conversor.convert.return_value = msg
        await main_mod.editar.callback(staff_ctx, link_ou_id="123", novo_texto="novo")
        msg.edit.assert_awaited_once_with(content="novo")
        staff_ctx.message.delete.assert_awaited_once()

    async def test_recusa_editar_mensagem_de_outra_pessoa(self, main_mod, staff_ctx, conversor, bot_user):
        msg = MagicMock(author=MagicMock(), edit=AsyncMock()); conversor.convert.return_value = msg
        await main_mod.editar.callback(staff_ctx, link_ou_id="123", novo_texto="novo")
        msg.edit.assert_not_awaited()
        assert "Só edito minhas" in staff_ctx.send.call_args.args[0]

    async def test_mensagem_nao_encontrada(self, main_mod, staff_ctx, conversor):
        conversor.convert.side_effect = commands.MessageNotFound("x")
        await main_mod.editar.callback(staff_ctx, link_ou_id="123", novo_texto="n")
        assert "Não encontrei" in staff_ctx.send.call_args.args[0]

    async def test_erro_generico_ao_buscar(self, main_mod, staff_ctx, conversor):
        conversor.convert.side_effect = RuntimeError("rede")
        await main_mod.editar.callback(staff_ctx, link_ou_id="123", novo_texto="n")
        assert "Erro ao buscar" in staff_ctx.send.call_args.args[0]

    async def test_erro_ao_editar(self, main_mod, staff_ctx, conversor, bot_user):
        msg = MagicMock(author=bot_user, edit=AsyncMock(side_effect=http_exc(discord.Forbidden, 403)))
        conversor.convert.return_value = msg
        await main_mod.editar.callback(staff_ctx, link_ou_id="1", novo_texto="n")
        assert "Erro ao editar" in staff_ctx.send.call_args.args[0]


# ------------------------------------------------------------------ reenviar ---
class TestReenviar:
    @pytest.fixture
    def conv(self, main_mod):
        with patch.object(main_mod.commands, "MessageConverter") as mc, patch.object(main_mod.commands, "TextChannelConverter") as tc:
            msg_conv = MagicMock(); msg_conv.convert = AsyncMock(); mc.return_value = msg_conv
            ch_conv = MagicMock(); ch_conv.convert = AsyncMock(); tc.return_value = ch_conv
            yield msg_conv, ch_conv

    def _msg(self, content="oi", attachments=(), embeds=()):
        return MagicMock(content=content, attachments=list(attachments), embeds=list(embeds))

    async def test_reenvia_para_canal_por_link(self, main_mod, staff_ctx, conv, monkeypatch):
        msg_conv, _ = conv
        msg_conv.convert.return_value = self._msg("olá")
        destino, _ = make_channel()
        monkeypatch.setattr(main_mod.bot, "get_channel", lambda cid: destino if cid == 777 else None)
        await main_mod.reenviar.callback(staff_ctx, link_msg="m", link_canal="https://discord.com/channels/1/777")
        assert destino.send.call_args.kwargs["content"] == "olá"
        staff_ctx.message.delete.assert_awaited_once()

    async def test_canal_por_mencao_via_conversor(self, main_mod, staff_ctx, conv, monkeypatch):
        msg_conv, ch_conv = conv
        msg_conv.convert.return_value = self._msg()
        destino, _ = make_channel()
        ch_conv.convert.return_value = destino
        await main_mod.reenviar.callback(staff_ctx, link_msg="m", link_canal="#geral")
        destino.send.assert_awaited_once()

    async def test_mensagem_original_ilegivel(self, main_mod, staff_ctx, conv):
        conv[0].convert.side_effect = commands.MessageNotFound("x")
        await main_mod.reenviar.callback(staff_ctx, link_msg="m", link_canal="c")
        assert "mensagem original" in staff_ctx.send.call_args.args[0]

    async def test_canal_invalido(self, main_mod, staff_ctx, conv):
        conv[0].convert.return_value = self._msg()
        conv[1].convert.side_effect = commands.ChannelNotFound("x")
        await main_mod.reenviar.callback(staff_ctx, link_msg="m", link_canal="lixo")
        assert "Canal destino inválido" in staff_ctx.send.call_args.args[0]

    async def test_link_de_canal_malformado_cai_no_conversor(self, main_mod, staff_ctx, conv):
        conv[0].convert.return_value = self._msg()
        conv[1].convert.side_effect = commands.ChannelNotFound("x")
        await main_mod.reenviar.callback(staff_ctx, link_msg="m", link_canal="https://discord.com/channels/1/abc")
        assert "Canal destino inválido" in staff_ctx.send.call_args.args[0]

    async def test_copia_anexos_e_so_embeds_rich(self, main_mod, staff_ctx, conv):
        anexo = MagicMock(filename="a.png"); anexo.read = AsyncMock(return_value=b"bytes")
        rich = MagicMock(type="rich"); link = MagicMock(type="link")
        conv[0].convert.return_value = self._msg(attachments=[anexo], embeds=[rich, link])
        destino, _ = make_channel(); conv[1].convert.return_value = destino
        await main_mod.reenviar.callback(staff_ctx, link_msg="m", link_canal="#c")
        kw = destino.send.call_args.kwargs
        assert kw["embeds"] == [rich]
        assert len(kw["files"]) == 1 and kw["files"][0].filename == "a.png"

    async def test_anexo_que_falha_e_ignorado(self, main_mod, staff_ctx, conv):
        anexo = MagicMock(filename="a.png"); anexo.read = AsyncMock(side_effect=RuntimeError("x"))
        conv[0].convert.return_value = self._msg(attachments=[anexo])
        destino, _ = make_channel(); conv[1].convert.return_value = destino
        await main_mod.reenviar.callback(staff_ctx, link_msg="m", link_canal="#c")
        assert destino.send.call_args.kwargs["files"] == []

    async def test_falha_no_envio(self, main_mod, staff_ctx, conv):
        conv[0].convert.return_value = self._msg()
        destino, _ = make_channel(); destino.send.side_effect = http_exc(discord.Forbidden, 403)
        conv[1].convert.return_value = destino
        await main_mod.reenviar.callback(staff_ctx, link_msg="m", link_canal="#c")
        assert "Erro ao enviar" in staff_ctx.send.call_args.args[0]


# ------------------------------------------------------------------ darcargo ---
class TestDarCargo:
    async def test_da_o_cargo(self, main_mod, staff_ctx):
        cargo = make_role(main_mod.ID_CARGO_ESPECIAL, "Especial")
        staff_ctx.guild.get_role.return_value = cargo
        membro = MagicMock(roles=[], add_roles=AsyncMock())
        await main_mod.darcargo.callback(staff_ctx, membro=membro)
        staff_ctx.guild.get_role.assert_called_with(main_mod.ID_CARGO_ESPECIAL)
        membro.add_roles.assert_awaited_once()
        assert membro.add_roles.call_args.args[0] is cargo
        assert "Especial" in staff_ctx.send.call_args.args[0]

    async def test_cargo_inexistente_no_servidor(self, main_mod, staff_ctx):
        staff_ctx.guild.get_role.return_value = None
        membro = MagicMock(roles=[], add_roles=AsyncMock())
        await main_mod.darcargo.callback(staff_ctx, membro=membro)
        membro.add_roles.assert_not_awaited()
        assert "Não achei" in staff_ctx.send.call_args.args[0]

    async def test_membro_ja_tem_o_cargo(self, main_mod, staff_ctx):
        cargo = make_role(main_mod.ID_CARGO_ESPECIAL, "Especial")
        staff_ctx.guild.get_role.return_value = cargo
        membro = MagicMock(roles=[cargo], add_roles=AsyncMock())
        await main_mod.darcargo.callback(staff_ctx, membro=membro)
        membro.add_roles.assert_not_awaited()
        assert "já tem" in staff_ctx.send.call_args.args[0]

    async def test_hierarquia_insuficiente(self, main_mod, staff_ctx):
        staff_ctx.guild.get_role.return_value = make_role(main_mod.ID_CARGO_ESPECIAL, "Especial")
        membro = MagicMock(roles=[], add_roles=AsyncMock(side_effect=http_exc(discord.Forbidden, 403)))
        await main_mod.darcargo.callback(staff_ctx, membro=membro)
        assert "hierarquia" in staff_ctx.send.call_args.args[0]


# ----------------------------------------------------------------- historico ---
class TestHistorico:
    async def test_mostra_frutas_por_rank(self, main_mod, staff_ctx):
        main_mod.history["C"] = ["Gomu", "Mera"]
        await main_mod.historico_frutas.callback(staff_ctx)
        campos = {f.name: f.value for f in staff_ctx.send.call_args.kwargs["embed"].fields}
        assert campos["Rank C"] == "• Gomu\n• Mera"
        assert "Nenhuma fruta" in campos["Rank B"]

    async def test_recarrega_do_disco_antes_de_mostrar(self, main_mod, staff_ctx):
        main_mod.history["A"] = ["Salva"]
        main_mod.save()
        main_mod.history["A"] = []
        await main_mod.historico_frutas.callback(staff_ctx)
        campos = {f.name: f.value for f in staff_ctx.send.call_args.kwargs["embed"].fields}
        assert "Salva" in campos["Rank A"]


# --------------------------------------------------------------------- ajuda ---
class TestAjuda:
    async def test_membro_nao_ve_comandos_da_staff(self, main_mod, ctx):
        await main_mod.ajuda.callback(ctx)
        emb = ctx.send.call_args.kwargs["embed"]
        assert [f.name for f in emb.fields] == ["📖 Público"]

    async def test_staff_ve_comandos_da_staff(self, main_mod, staff_ctx):
        await main_mod.ajuda.callback(staff_ctx)
        assert "🔒 Staff" in [f.name for f in staff_ctx.send.call_args.kwargs["embed"].fields]

    async def test_embed_dentro_dos_limites_do_discord(self, main_mod, staff_ctx):
        await main_mod.ajuda.callback(staff_ctx)
        for f in staff_ctx.send.call_args.kwargs["embed"].fields:
            assert len(f.value) <= 1024

    async def test_todo_comando_publico_novo_precisa_estar_na_ajuda(self, main_mod, staff_ctx):
        """Se alguém criar um comando e esquecer de documentar, este teste avisa.
        (comandos já conhecidos como não documentados ficam na lista abaixo)"""
        await main_mod.ajuda.callback(staff_ctx)
        emb = staff_ctx.send.call_args.kwargs["embed"]
        texto = " ".join(f.value for f in emb.fields) + (emb.description or "")
        conhecidos_sem_doc = {"say", "pl", "ajuda", "chat", "painel_racas", "check_pool"}
        faltando = [c.name for c in main_mod.bot.commands
                    if f"doffy!{c.name}" not in texto and c.name not in conhecidos_sem_doc]
        assert faltando == []


# ------------------------------------------------------------ on_command_error ---
class TestOnCommandError:
    async def test_comando_inexistente_e_silencioso(self, main_mod, ctx):
        await main_mod.on_command_error(ctx, commands.CommandNotFound())
        ctx.send.assert_not_awaited()

    async def test_argumento_faltando(self, main_mod, ctx):
        param = MagicMock(); param.name = "x"
        await main_mod.on_command_error(ctx, commands.MissingRequiredArgument(param))
        assert "ajuda" in ctx.send.call_args.args[0]

    async def test_sem_permissao(self, main_mod, ctx):
        await main_mod.on_command_error(ctx, commands.CheckFailure())
        assert "Sem permissão" in ctx.send.call_args.args[0]

    async def test_erro_do_comando_loga_traceback_completo(self, main_mod, ctx, capsys):
        """Regressão do log: antes só saía 'Erro: Command raised an exception: ...' sem traceback."""
        ctx.command = "posse"
        try:
            raise api_error(403)
        except Exception as original:
            erro = commands.CommandInvokeError(original)
        await main_mod.on_command_error(ctx, erro)
        saida = capsys.readouterr()
        assert "posse" in saida.out
        assert "Traceback" in saida.err and "APIError" in saida.err and "403" in saida.err

    async def test_nao_manda_detalhes_tecnicos_para_o_canal(self, main_mod, ctx):
        ctx.command = "x"
        await main_mod.on_command_error(ctx, commands.CommandInvokeError(RuntimeError("segredo")))
        ctx.send.assert_not_awaited()


# ------------------------------------------------------- setup_hook / on_ready ---
class TestStartup:
    @pytest.fixture
    def bot_mock(self, main_mod, monkeypatch):
        add_cog = AsyncMock(); load_ext = AsyncMock()
        monkeypatch.setattr(main_mod.bot, "add_cog", add_cog)
        monkeypatch.setattr(main_mod.bot, "load_extension", load_ext)
        monkeypatch.setattr(main_mod.auto_update, "is_running", lambda: False)
        start = MagicMock(); monkeypatch.setattr(main_mod.auto_update, "start", start)
        return add_cog, load_ext, start

    async def test_carrega_tudo_na_ordem(self, main_mod, bot_mock):
        add_cog, load_ext, start = bot_mock
        await main_mod.setup_hook()
        assert isinstance(add_cog.call_args.args[0], main_mod.EstoqueCog)
        assert [c.args[0] for c in load_ext.call_args_list] == ["ai", "racas"]
        start.assert_called_once()

    async def test_falha_na_ia_nao_impede_racas_nem_o_loop(self, main_mod, bot_mock, capsys):
        add_cog, load_ext, start = bot_mock
        load_ext.side_effect = [RuntimeError("sem groq"), None]
        await main_mod.setup_hook()
        assert load_ext.await_count == 2
        start.assert_called_once()
        assert "Erro ao carregar IA" in capsys.readouterr().out

    async def test_nao_inicia_loop_duas_vezes(self, main_mod, bot_mock, monkeypatch):
        _, _, start = bot_mock
        monkeypatch.setattr(main_mod.auto_update, "is_running", lambda: True)
        await main_mod.setup_hook()
        start.assert_not_called()

    def test_setup_hook_esta_ligado_ao_bot(self, main_mod):
        assert main_mod.bot.setup_hook is main_mod.setup_hook

    async def test_on_ready_carrega_estado_e_zera_backoff(self, main_mod, bot_user, capsys):
        main_mod._login_backoff_registrar_falha()
        with open(main_mod.ARQUIVO_MSGS, "w") as f:
            f.write('{"C": 5, "B": 6, "A": 7}')
        await main_mod.on_ready()
        assert main_mod.msg_ids == {"C": 5, "B": 6, "A": 7}
        assert main_mod._cache_load_sync()["login_backoff"]["falhas"] == 0
        assert "Online" in capsys.readouterr().out

    def test_bot_tem_prefixo_e_intents_corretos(self, main_mod):
        assert main_mod.bot.command_prefix == "doffy!"
        assert main_mod.bot.intents.message_content is True
        assert main_mod.bot.help_command is None
