"""Sistema de raças (racas.py): ticket, rolagem d100, race conditions e permissões."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

import racas
from conftest import make_role


@pytest.fixture(autouse=True)
def limpa_travas(monkeypatch):
    racas._tickets_reservados.clear()
    racas._rolagens_em_andamento.clear()
    # nenhum teste espera de verdade pelos asyncio.sleep da narrativa
    sleep = AsyncMock()
    monkeypatch.setattr(racas, "asyncio", SimpleNamespace(sleep=sleep))
    yield sleep
    racas._tickets_reservados.clear()
    racas._rolagens_em_andamento.clear()


def make_interaction(user_id=1, roles=(), com_log=True):
    it = MagicMock()
    it.user = MagicMock(id=user_id, roles=list(roles), mention=f"<@{user_id}>")
    it.user.name = f"user{user_id}"
    it.user.add_roles = AsyncMock()
    ja_rolou = make_role(racas.ROLE_JA_ROLOU_ID)
    lunar = make_role(racas.ROLE_LUNARIANO_ID)
    it.guild.get_role.side_effect = lambda rid: {racas.ROLE_JA_ROLOU_ID: ja_rolou, racas.ROLE_LUNARIANO_ID: lunar}.get(
        rid, make_role(rid))
    it.guild.default_role = make_role(0, "@everyone")
    canal_log = MagicMock(); canal_log.send = AsyncMock()
    it.guild.get_channel.return_value = canal_log if com_log else None
    it.guild.create_text_channel = AsyncMock()
    it.response.send_message = AsyncMock(); it.response.edit_message = AsyncMock()
    it.followup.send = AsyncMock()
    it.channel.send = AsyncMock(); it.channel.delete = AsyncMock()
    it.message.edit = AsyncMock()
    it._ja_rolou, it._lunar, it._canal_log = ja_rolou, lunar, canal_log
    return it


# ------------------------------------------------------------------ RollView ---
class TestRolagem:
    @pytest.mark.parametrize("resultado", [90, 91, 99, 100])
    async def test_90_ou_mais_vira_lunariano(self, resultado):
        it = make_interaction()
        with patch.object(racas.random, "randint", return_value=resultado):
            await racas.RollView().rolar_btn.callback(it)
        it.user.add_roles.assert_awaited_once_with(it._lunar, it._ja_rolou)
        textos = " ".join(str(c) for c in it.channel.send.call_args_list)
        assert "LUNARIANO" in textos and str(resultado) in textos
        it._canal_log.send.assert_awaited_once()

    @pytest.mark.parametrize("resultado", [1, 50, 89])
    async def test_ate_89_nao_e_lunariano_mas_marca_que_ja_rolou(self, resultado):
        it = make_interaction()
        with patch.object(racas.random, "randint", return_value=resultado):
            await racas.RollView().rolar_btn.callback(it)
        it.user.add_roles.assert_awaited_once_with(it._ja_rolou)
        assert str(resultado) in it.followup.send.call_args.args[0]
        it._canal_log.send.assert_not_awaited()

    async def test_dado_e_d100(self):
        with patch.object(racas.random, "randint", return_value=1) as r:
            await racas.RollView().rolar_btn.callback(make_interaction())
        r.assert_called_once_with(1, 100)

    async def test_sempre_oferece_apagar_o_canal_no_final(self):
        it = make_interaction()
        with patch.object(racas.random, "randint", return_value=10):
            await racas.RollView().rolar_btn.callback(it)
        kw = it.channel.send.call_args.kwargs
        assert isinstance(kw["view"], racas.DeleteTicketView) and kw["embed"].title == "Destino Selado"

    async def test_desabilita_o_botao_ao_rolar(self):
        it = make_interaction()
        view = racas.RollView()
        with patch.object(racas.random, "randint", return_value=10):
            await view.rolar_btn.callback(it)
        assert view.rolar_btn.disabled is True
        it.response.edit_message.assert_awaited_once()

    async def test_quem_ja_tem_o_cargo_ja_rolou_e_bloqueado(self):
        it = make_interaction()
        it.user.roles = [it._ja_rolou]
        await racas.RollView().rolar_btn.callback(it)
        assert "já tentou" in it.response.send_message.call_args.args[0]
        assert it.response.send_message.call_args.kwargs["ephemeral"] is True
        it.user.add_roles.assert_not_awaited()

    async def test_duplo_clique_simultaneo_rola_so_uma_vez(self):
        """Regressão da race condition: 2 cliques do mesmo usuário ao mesmo tempo."""
        it1, it2 = make_interaction(user_id=7), make_interaction(user_id=7)
        view = racas.RollView()
        with patch.object(racas.random, "randint", return_value=95):
            await asyncio.gather(view.rolar_btn.callback(it1), view.rolar_btn.callback(it2))
        total_roles = it1.user.add_roles.await_count + it2.user.add_roles.await_count
        assert total_roles == 1
        assert it1.response.send_message.await_count + it2.response.send_message.await_count == 1  # um foi barrado

    async def test_usuarios_diferentes_nao_se_bloqueiam(self):
        a, b = make_interaction(user_id=1), make_interaction(user_id=2)
        with patch.object(racas.random, "randint", return_value=10):
            await asyncio.gather(racas.RollView().rolar_btn.callback(a), racas.RollView().rolar_btn.callback(b))
        a.user.add_roles.assert_awaited_once(); b.user.add_roles.assert_awaited_once()

    async def test_sem_canal_de_log_nao_quebra(self):
        it = make_interaction(com_log=False)
        with patch.object(racas.random, "randint", return_value=99):
            await racas.RollView().rolar_btn.callback(it)
        it.user.add_roles.assert_awaited_once()

    def test_custom_id_persistente(self):
        assert racas.RollView().rolar_btn.custom_id == "btn_rolar_d100"
        assert racas.RollView().timeout is None


# ---------------------------------------------------------------- TicketView ---
class TestTicket:
    async def test_cria_canal_privado_com_permissoes(self):
        it = make_interaction(user_id=5)
        canal = MagicMock(mention="#teste", send=AsyncMock())
        it.guild.create_text_channel.return_value = canal
        await racas.TicketView().criar_ticket.callback(it)
        kw = it.guild.create_text_channel.call_args.kwargs
        assert kw["name"] == "teste-lunariano-user5"
        ow = kw["overwrites"]
        assert ow[it.guild.default_role].read_messages is False
        assert ow[it.user].read_messages is True and ow[it.user].send_messages is True
        for rid in racas.ROLE_STAFF_IDS:
            assert any(getattr(k, "id", None) == rid and v.read_messages for k, v in ow.items())
        assert isinstance(canal.send.call_args.kwargs["view"], racas.RollView)

    async def test_responde_ao_usuario_de_forma_efemera(self):
        it = make_interaction()
        it.guild.create_text_channel.return_value = MagicMock(mention="#t", send=AsyncMock())
        await racas.TicketView().criar_ticket.callback(it)
        assert it.response.send_message.call_args.kwargs["ephemeral"] is True

    async def test_bloqueia_quem_ja_fez_o_teste(self):
        it = make_interaction()
        it.user.roles = [it._ja_rolou]
        await racas.TicketView().criar_ticket.callback(it)
        it.guild.create_text_channel.assert_not_awaited()
        assert "Apenas uma oportunidade" in it.response.send_message.call_args.args[0]

    async def test_duplo_clique_cria_um_unico_canal(self):
        """Regressão da race condition de tickets."""
        it1, it2 = make_interaction(user_id=9), make_interaction(user_id=9)
        criados = []

        async def criar(**kw):
            await asyncio.sleep(0)   # cede o controle, como uma chamada de rede faria
            c = MagicMock(mention="#t", send=AsyncMock()); criados.append(c); return c

        for it in (it1, it2):
            it.guild.create_text_channel = AsyncMock(side_effect=criar)
        view = racas.TicketView()
        await asyncio.gather(view.criar_ticket.callback(it1), view.criar_ticket.callback(it2))
        assert len(criados) == 1

    async def test_falha_ao_criar_libera_a_reserva_para_tentar_de_novo(self):
        it = make_interaction(user_id=3)
        it.guild.create_text_channel.side_effect = discord.Forbidden(MagicMock(status=403, reason="x"), "x")
        with pytest.raises(discord.Forbidden):
            await racas.TicketView().criar_ticket.callback(it)
        assert 3 not in racas._tickets_reservados
        # segunda tentativa funciona
        it.guild.create_text_channel.side_effect = None
        it.guild.create_text_channel.return_value = MagicMock(mention="#t", send=AsyncMock())
        await racas.TicketView().criar_ticket.callback(it)
        it.guild.create_text_channel.assert_awaited()

    async def test_cargo_staff_inexistente_no_servidor_e_ignorado(self):
        it = make_interaction()
        base = it.guild.get_role.side_effect
        it.guild.get_role.side_effect = lambda rid: None if rid in racas.ROLE_STAFF_IDS else base(rid)
        it.guild.create_text_channel.return_value = MagicMock(mention="#t", send=AsyncMock())
        await racas.TicketView().criar_ticket.callback(it)   # não levanta
        assert len(it.guild.create_text_channel.call_args.kwargs["overwrites"]) == 2


# ----------------------------------------------------------- DeleteTicketView ---
class TestApagarCanal:
    async def test_apaga_o_canal_apos_5s(self, limpa_travas):
        it = make_interaction()
        view = racas.DeleteTicketView()
        await view.apagar_btn.callback(it)
        limpa_travas.assert_awaited_once_with(5)
        it.channel.delete.assert_awaited_once()
        assert view.apagar_btn.disabled is True


# ------------------------------------------------------------------ RacasCog ---
class TestCog:
    async def test_registra_as_3_views_persistentes(self):
        bot = MagicMock()
        racas.RacasCog(bot)
        tipos = {type(c.args[0]) for c in bot.add_view.call_args_list}
        assert tipos == {racas.TicketView, racas.RollView, racas.DeleteTicketView}

    async def test_setup_adiciona_o_cog(self):
        bot = MagicMock(); bot.add_cog = AsyncMock()
        await racas.setup(bot)
        assert isinstance(bot.add_cog.call_args.args[0], racas.RacasCog)

    async def test_painel_envia_embed_com_botao_e_apaga_o_comando(self):
        from conftest import make_ctx
        cog = racas.RacasCog(MagicMock())
        ctx = make_ctx(); ctx.send = AsyncMock()
        await cog.painel_racas.callback(cog, ctx)
        assert isinstance(ctx.send.call_args.kwargs["view"], racas.TicketView)
        ctx.message.delete.assert_awaited_once()

    async def test_painel_so_staff(self):
        from conftest import make_ctx
        cog = racas.RacasCog(MagicMock())
        ctx = make_ctx(roles=[make_role(1)])
        ctx.author.get_role = lambda rid: None   # membro sem nenhum cargo staff
        ctx.command = cog.painel_racas
        with pytest.raises(commands.MissingAnyRole):
            await cog.painel_racas.can_run(ctx)

    @pytest.mark.parametrize("rid", racas.ROLE_STAFF_IDS)
    async def test_painel_liberado_para_cada_cargo_staff(self, rid):
        from conftest import make_ctx
        cog = racas.RacasCog(MagicMock())
        ctx = make_ctx()
        ctx.author.get_role = lambda x, rid=rid: make_role(x) if x == rid else None
        ctx.command = cog.painel_racas
        assert await cog.painel_racas.can_run(ctx) is True

    def test_custom_ids_sao_unicos(self):
        ids = [racas.TicketView().criar_ticket.custom_id, racas.RollView().rolar_btn.custom_id,
               racas.DeleteTicketView().apagar_btn.custom_id]
        assert len(set(ids)) == 3

    def test_probabilidade_de_lunariano_e_11_por_cento(self):
        """Documenta a regra: d100 >= 90 -> 11 faces vencedoras em 100."""
        assert sum(1 for n in range(1, 101) if n >= 90) == 11
