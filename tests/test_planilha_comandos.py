"""Comandos de consulta do EstoqueCog: enc, fruta, check_pool."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from conftest import api_error, make_ctx, make_role, tabela


def embeds_enviados(ctx):
    return [c.kwargs["embed"] for c in ctx.send.call_args_list if "embed" in c.kwargs]


@pytest.fixture
def msg_paginada(ctx):
    msg = AsyncMock()
    ctx.send.return_value = msg
    return msg


# --------------------------------------------------------------------- enc ---
class TestEnc:
    async def test_lista_com_resumo_e_primeira_pagina(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        await cog.enc.callback(cog, ctx)
        emb = embeds_enviados(ctx)[0]
        assert "C: `3`" in emb.description and "B: `1`" in emb.description
        assert "A: `2`" in emb.description and "S: `1`" in emb.description
        assert "Rank C" in emb.title

    async def test_indicador_disponivel_e_ocupada(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        await cog.enc.callback(cog, ctx)
        nomes = [f.name for f in embeds_enviados(ctx)[0].fields]
        assert any(n.startswith("🟢") and "Gomu" in n for n in nomes)
        assert any(n.startswith("⚫") and "Mera" in n for n in nomes)

    async def test_filtra_por_rank(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        await cog.enc.callback(cog, ctx, busca="a")
        emb = embeds_enviados(ctx)[0]
        assert "Rank A" in emb.title and "Lista Completa" in emb.title
        assert len(emb.fields) == 2

    async def test_busca_por_nome_sem_espacos(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        await cog.enc.callback(cog, ctx, busca="ope ope")
        fields = embeds_enviados(ctx)[0].fields
        assert len(fields) == 1 and "Ope Ope" in fields[0].name

    async def test_busca_por_rank_e_numero(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        await cog.enc.callback(cog, ctx, busca="b1")
        fields = embeds_enviados(ctx)[0].fields
        assert [f.name for f in fields] == ["🟢 #1 Bara Bara no Mi"]

    async def test_sem_resultado(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        await cog.enc.callback(cog, ctx, busca="inexistente")
        assert "Nenhuma fruta" in ctx.send.call_args.args[0]

    async def test_planilha_vazia(self, cog_factory, ctx):
        cog, _ = cog_factory([])
        await cog.enc.callback(cog, ctx)
        assert "Nenhuma fruta" in ctx.send.call_args.args[0]

    async def test_ordena_por_numero_e_nao_por_texto(self, cog_factory, ctx):
        v = tabela(("C", 10, "Dez", ""), ("C", 2, "Dois", ""), ("C", 1, "Um", ""))
        cog, _ = cog_factory(v)
        await cog.enc.callback(cog, ctx)
        assert [f.name for f in embeds_enviados(ctx)[0].fields] == ["🟢 #1 Um", "🟢 #2 Dois", "🟢 #10 Dez"]

    async def test_pagina_de_6_em_6(self, cog_factory, ctx, msg_paginada, main_mod, monkeypatch):
        v = tabela(*[("C", i, f"F{i}", "") for i in range(1, 14)])  # 13 -> 3 páginas
        cog, _ = cog_factory(v)
        monkeypatch.setattr(main_mod.bot, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError))
        await cog.enc.callback(cog, ctx)
        primeira = embeds_enviados(ctx)[0]
        assert "(1/3)" in primeira.title and len(primeira.fields) == 6
        msg_paginada.add_reaction.assert_any_await("◀️")
        msg_paginada.add_reaction.assert_any_await("▶️")

    async def test_uma_pagina_nao_adiciona_reacoes(self, cog_factory, ctx, msg_paginada):
        cog, _ = cog_factory(tabela(("C", 1, "A", ""), ("C", 2, "B", "")))
        await cog.enc.callback(cog, ctx)
        msg_paginada.add_reaction.assert_not_awaited()

    async def test_navegacao_por_reacoes(self, cog_factory, ctx, msg_paginada, main_mod, monkeypatch):
        v = tabela(*[("C", i, f"F{i}", "") for i in range(1, 14)])
        cog, _ = cog_factory(v)

        def r(emoji):
            x = MagicMock()
            x.emoji = emoji
            return (x, MagicMock())

        monkeypatch.setattr(
            main_mod.bot, "wait_for",
            AsyncMock(side_effect=[r("◀️"), r("▶️"), r("▶️"), r("▶️"), r("◀️"), asyncio.TimeoutError]),
        )
        await cog.enc.callback(cog, ctx)
        titulos = [c.kwargs["embed"].title for c in msg_paginada.edit.call_args_list]
        # ◀ na pág.1 fica; ▶ ▶ ▶ para na última; ◀ volta uma
        assert [t.split("(")[1] for t in titulos] == ["1/3)", "2/3)", "3/3)", "3/3)", "2/3)"]

    async def test_check_da_reacao_so_aceita_autor_e_emojis_de_navegacao(self, cog_factory, ctx, msg_paginada, main_mod, monkeypatch):
        v = tabela(*[("C", i, f"F{i}", "") for i in range(1, 14)])
        cog, _ = cog_factory(v)
        msg_paginada.id = 5
        capturado = {}

        async def fake(evento, timeout, check):
            capturado["check"] = check
            raise asyncio.TimeoutError

        monkeypatch.setattr(main_mod.bot, "wait_for", fake)
        await cog.enc.callback(cog, ctx)
        check = capturado["check"]
        r = MagicMock(); r.emoji = "▶️"; r.message.id = 5
        assert check(r, ctx.author) is True
        assert check(r, MagicMock()) is False        # outro usuário
        r.emoji = "😀"
        assert check(r, ctx.author) is False         # outro emoji
        r.emoji = "▶️"; r.message.id = 6
        assert check(r, ctx.author) is False         # outra mensagem

    async def test_falha_ao_remover_reacao_nao_quebra(self, cog_factory, ctx, msg_paginada, main_mod, monkeypatch):
        v = tabela(*[("C", i, f"F{i}", "") for i in range(1, 14)])
        cog, _ = cog_factory(v)
        msg_paginada.remove_reaction.side_effect = Exception("sem permissão")
        r = MagicMock(); r.emoji = "▶️"
        monkeypatch.setattr(main_mod.bot, "wait_for", AsyncMock(side_effect=[(r, MagicMock()), asyncio.TimeoutError]))
        await cog.enc.callback(cog, ctx)  # não levanta

    async def test_erro_ao_ler_planilha_nao_levanta(self, cog_factory, ctx):
        cog, _ = cog_factory(read_error=api_error(403))
        await cog.enc.callback(cog, ctx)
        assert "Nenhuma fruta" in ctx.send.call_args.args[0]

    async def test_fruta_com_rank_desconhecido_nao_quebra(self, cog_factory, ctx):
        """Regressão: rank fora de C/B/A/S deixava 'pages' vazio -> IndexError."""
        cog, _ = cog_factory(tabela(("X", 1, "Fruta sem rank valido", "")))
        await cog.enc.callback(cog, ctx)
        assert "Nenhuma fruta" in ctx.send.call_args.args[0]

    async def test_rank_desconhecido_misturado_com_validos_so_mostra_os_validos(self, cog_factory, ctx):
        cog, _ = cog_factory(tabela(("X", 1, "Invalida", ""), ("C", 1, "Valida", "")))
        await cog.enc.callback(cog, ctx)
        nomes = [f.name for f in ctx.send.call_args.kwargs["embed"].fields]
        assert nomes == ["🟢 #1 Valida"]


# ------------------------------------------------------------------- fruta ---
class TestFruta:
    async def test_disponivel(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        await cog.fruta.callback(cog, ctx, busca="gomu")
        emb = embeds_enviados(ctx)[0]
        assert "🟢" in emb.title and "Gomu Gomu" in emb.title
        assert {f.name: f.value for f in emb.fields}["Status"] == "Disponível"

    async def test_ocupada_mostra_status_capitalizado(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        await cog.fruta.callback(cog, ctx, busca="mera")
        emb = embeds_enviados(ctx)[0]
        assert "⚫" in emb.title
        assert {f.name: f.value for f in emb.fields}["Status"] == "Ingerida por ace"

    @pytest.mark.parametrize("busca", ["Ope Ope", "opeope", "a1", "A1"])
    async def test_formas_de_busca(self, cog_factory, frutas_basicas, ctx, busca):
        cog, _ = cog_factory(frutas_basicas)
        await cog.fruta.callback(cog, ctx, busca=busca)
        assert "Ope Ope" in embeds_enviados(ctx)[0].title

    async def test_nao_encontrada(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        await cog.fruta.callback(cog, ctx, busca="zzz")
        assert "zzz" in ctx.send.call_args.args[0]

    async def test_mostra_rank_e_numero(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        await cog.fruta.callback(cog, ctx, busca="bara")
        campos = {f.name: f.value for f in embeds_enviados(ctx)[0].fields}
        assert campos["Rank"] == "**B**" and campos["Nº"] == "**1**"


# -------------------------------------------------------------- check_pool ---
class TestCheckPool:
    async def test_sem_permissao(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        ctx.author.roles = [make_role(123)]
        await cog.check_pool.callback(cog, ctx)
        assert "não tem permissão" in ctx.send.call_args.args[0]
        assert not embeds_enviados(ctx)

    async def test_sem_nenhum_cargo(self, cog_factory, frutas_basicas, ctx):
        cog, _ = cog_factory(frutas_basicas)
        ctx.author.roles = []
        await cog.check_pool.callback(cog, ctx)
        assert "não tem permissão" in ctx.send.call_args.args[0]

    async def test_lista_so_disponiveis(self, cog_factory, frutas_basicas, staff_ctx):
        cog, _ = cog_factory(frutas_basicas)
        await cog.check_pool.callback(cog, staff_ctx)
        emb = embeds_enviados(staff_ctx)[0]
        assert "Total disponível: **5**" in emb.description
        campos = {f.name: f.value for f in emb.fields}
        assert "Rank C (2 frutas)" in campos
        assert "Mera Mera" not in "".join(campos.values())    # ocupada
        assert "Ope Ope" not in "".join(campos.values())      # em posse

    async def test_rank_esgotado_mostra_aviso(self, cog_factory, staff_ctx):
        cog, _ = cog_factory(tabela(("C", 1, "A", "ocupada"), ("B", 1, "B", "")))
        await cog.check_pool.callback(cog, staff_ctx)
        campos = {f.name: f.value for f in embeds_enviados(staff_ctx)[0].fields}
        assert "Nenhuma fruta disponível" in campos["Rank C"]

    async def test_lista_longa_e_truncada_para_caber_no_embed(self, cog_factory, staff_ctx):
        v = tabela(*[("C", i, f"Fruta com nome bem comprido numero {i}", "") for i in range(1, 80)])
        cog, _ = cog_factory(v)
        await cog.check_pool.callback(cog, staff_ctx)
        for f in embeds_enviados(staff_ctx)[0].fields:
            assert len(f.value) <= 1024   # limite do Discord por campo

    async def test_planilha_vazia(self, cog_factory, staff_ctx):
        cog, _ = cog_factory([])
        await cog.check_pool.callback(cog, staff_ctx)
        assert "vazia" in staff_ctx.send.call_args.args[0]
