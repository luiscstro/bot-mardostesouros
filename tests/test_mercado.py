"""Sorteio com histórico, texto das lojas, run_update e auto_update."""
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from conftest import http_exc, make_channel, tabela


# ------------------------------------------------------ sortear_com_historico ---
class TestSortear:
    def test_lista_vazia_esgotado_e_nao_mexe_no_historico(self, main_mod):
        assert main_mod.sortear_com_historico("C", []) == "Esgotado"
        assert main_mod.history["C"] == []

    def test_escolha_vem_da_lista(self, main_mod):
        assert main_mod.sortear_com_historico("C", ["a", "b", "c"]) in {"a", "b", "c"}

    def test_registra_no_historico(self, main_mod):
        f = main_mod.sortear_com_historico("B", ["unica"])
        assert main_mod.history["B"] == [f]

    def test_evita_frutas_do_historico(self, main_mod):
        main_mod.history["C"] = ["a", "b", "c"]
        for _ in range(50):
            main_mod.history["C"] = ["a", "b", "c"]
            assert main_mod.sortear_com_historico("C", ["a", "b", "c", "d"]) == "d"

    def test_se_tudo_esta_no_historico_sorteia_mesmo_assim(self, main_mod):
        main_mod.history["C"] = ["a", "b"]
        assert main_mod.sortear_com_historico("C", ["a", "b"]) in {"a", "b"}

    def test_historico_guarda_no_maximo_3(self, main_mod):
        for i in range(10):
            main_mod.sortear_com_historico("A", [f"f{i}"])
        assert main_mod.history["A"] == ["f7", "f8", "f9"]

    def test_historicos_por_rank_sao_independentes(self, main_mod):
        main_mod.sortear_com_historico("C", ["x"])
        assert main_mod.history["B"] == [] and main_mod.history["A"] == []

    def test_uma_unica_fruta_repetida_sempre_sai(self, main_mod):
        for _ in range(5):
            assert main_mod.sortear_com_historico("C", ["so_essa"]) == "so_essa"

    def test_sem_repeticao_nas_ultimas_3_com_pool_grande(self, main_mod):
        pool = [f"f{i}" for i in range(10)]
        saidas = [main_mod.sortear_com_historico("C", pool) for _ in range(200)]
        for i in range(3, len(saidas)):
            assert saidas[i] not in saidas[i - 3:i]


# ---------------------------------------------------------- get_msg_content ---
class TestMsgContent:
    @pytest.mark.parametrize("rank,p1,p2,emoji", [
        ("C", "30.000.000", "60.000.000", "🍐"),
        ("B", "150.000.000", "300.000.000", "🍇"),
        ("A", "800.000.000", "1.600.000.000", "🍎"),
    ])
    def test_precos_e_emoji_por_rank(self, main_mod, rank, p1, p2, emoji):
        txt = main_mod.get_msg_content(rank, "Fruta")
        assert f"AKUMAS NO MI ({rank})" in txt and emoji in txt
        assert f"AKUMA ALEATÓRIA:** {p1}" in txt and f"AKUMA ANUNCIADA:** {p2}" in txt

    def test_nome_da_fruta_no_final(self, main_mod):
        assert main_mod.get_msg_content("C", "Gomu Gomu no Mi").rstrip().endswith("# Gomu Gomu no Mi")

    def test_rank_desconhecido_usa_valores_padrao(self, main_mod):
        txt = main_mod.get_msg_content("Z", "X")
        assert "???" in txt and "🍒" in txt

    @pytest.mark.parametrize("rank", ["C", "B", "A"])
    def test_cabe_no_limite_do_discord(self, main_mod, rank):
        assert len(main_mod.get_msg_content(rank, "N" * 200)) <= 2000

    def test_inclui_emoji_berry(self, main_mod):
        assert "<:berry:" in main_mod.get_msg_content("C", "X")

    def test_snapshot_estavel(self, main_mod):
        """Protege contra mudança acidental do texto publicado nas lojas."""
        assert main_mod.get_msg_content("C", "Fruta") == (
            "# **AKUMAS NO MI (C)** 🍐\n\n"
            "*Aqui poderá encontrar diversas frutas poderosas.*\n\n"
            "▶️ **AKUMA ALEATÓRIA:** 30.000.000<:berry:1222990525372563539>\n"
            "▶️ **AKUMA ANUNCIADA:** 60.000.000<:berry:1222990525372563539>\n\n"
            "🔸 Ao comprar, só haverá 2 jeitos de descobrir qual Akuma é: ou um Arqueólogo descobre ou um PJ deverá comê-la.\n"
            "# 🍒 FRUTA ANUNCIADA\n"
            "🔸 Todo Domingo será feita uma rolagem de Akuma e ficará aqui até a próxima semana.\n"
            "# Fruta"
        )


# ------------------------------------------------------------- send_chunked ---
class TestSendChunked:
    @pytest.mark.parametrize("tamanho,partes", [(0, 0), (1, 1), (2000, 1), (2001, 2), (4000, 2), (4001, 3), (9999, 5)])
    async def test_quantidade_de_partes(self, main_mod, tamanho, partes):
        ch = MagicMock(); ch.send = AsyncMock()
        await main_mod.send_chunked(ch, "x" * tamanho)
        assert ch.send.await_count == partes

    async def test_nenhuma_parte_passa_do_limite_e_nada_se_perde(self, main_mod):
        ch = MagicMock(); ch.send = AsyncMock()
        texto = "".join(chr(97 + i % 26) for i in range(5555))
        await main_mod.send_chunked(ch, texto)
        partes = [c.args[0] for c in ch.send.call_args_list]
        assert all(len(p) <= 2000 for p in partes)
        assert "".join(partes) == texto

    async def test_chunk_size_customizado(self, main_mod):
        ch = MagicMock(); ch.send = AsyncMock()
        await main_mod.send_chunked(ch, "abcdef", chunk_size=4)
        assert [c.args[0] for c in ch.send.call_args_list] == ["abcd", "ef"]


# ---------------------------------------------------------------- run_update ---
@pytest.fixture
def mercado(main_mod, cog_registrado, monkeypatch):
    """Cog com frutas + canais C/B/A + canal de anúncio falsos."""

    async def _make(valores=None, canais_ausentes=()):
        valores = valores or tabela(
            ("C", 1, "Fruta C1", ""), ("C", 2, "Fruta C2", ""),
            ("B", 1, "Fruta B1", ""), ("A", 1, "Fruta A1", ""),
        )
        cog, sheet = await cog_registrado(valores)
        canais = {}
        ids = {"C": main_mod.ID_CANAL_C, "B": main_mod.ID_CANAL_B, "A": main_mod.ID_CANAL_A, "anuncio": 1220369299076808734}
        msgs = {}
        for chave, cid in ids.items():
            if chave in canais_ausentes:
                continue
            canais[cid], msgs[chave] = make_channel(msg_id=hash(chave) % 10_000)
        monkeypatch.setattr(main_mod.bot, "get_channel", lambda cid: canais.get(cid))
        ns = SimpleNamespace(cog=cog, sheet=sheet, canais=canais, msgs=msgs, ids=ids)
        return ns

    return _make


class TestRunUpdate:
    async def test_primeira_execucao_cria_3_mensagens_e_salva_ids(self, main_mod, mercado):
        m = await mercado()
        await main_mod.run_update()
        for r in "CBA":
            m.canais[m.ids[r]].send.assert_awaited_once()
        assert all(main_mod.msg_ids[r] is not None for r in "CBA")
        # persistiu em disco
        main_mod.msg_ids.update({"C": None, "B": None, "A": None})
        main_mod.load()
        assert all(main_mod.msg_ids[r] is not None for r in "CBA")

    async def test_texto_publicado_tem_fruta_do_rank_certo(self, main_mod, mercado):
        m = await mercado()
        await main_mod.run_update()
        txt_c = m.canais[m.ids["C"]].send.call_args.args[0]
        txt_b = m.canais[m.ids["B"]].send.call_args.args[0]
        assert "AKUMAS NO MI (C)" in txt_c and ("Fruta C1" in txt_c or "Fruta C2" in txt_c)
        assert "AKUMAS NO MI (B)" in txt_b and "Fruta B1" in txt_b

    async def test_edita_mensagem_existente_em_vez_de_criar(self, main_mod, mercado):
        m = await mercado()
        main_mod.msg_ids.update({"C": 11, "B": 22, "A": 33})
        main_mod.save()
        await main_mod.run_update()
        for r in "CBA":
            m.canais[m.ids[r]].send.assert_not_awaited()
            m.msgs[r].edit.assert_awaited_once()
        m.canais[m.ids["C"]].fetch_message.assert_awaited_with(11)

    async def test_mensagem_apagada_cria_nova(self, main_mod, mercado):
        m = await mercado()
        main_mod.msg_ids.update({"C": 11, "B": 22, "A": 33})
        main_mod.save()
        m.canais[m.ids["C"]].fetch_message.side_effect = http_exc(discord.NotFound)
        await main_mod.run_update()
        m.canais[m.ids["C"]].send.assert_awaited_once()
        assert main_mod.msg_ids["C"] == m.msgs["C"].id

    async def test_sem_permissao_pula_o_canal_sem_criar_duplicata(self, main_mod, mercado):
        m = await mercado()
        main_mod.msg_ids.update({"C": 11, "B": 22, "A": 33})
        main_mod.save()
        m.canais[m.ids["B"]].fetch_message.side_effect = http_exc(discord.Forbidden, 403)
        await main_mod.run_update()
        m.canais[m.ids["B"]].send.assert_not_awaited()
        m.msgs["A"].edit.assert_awaited_once()   # os outros ranks continuam

    async def test_canal_inexistente_nao_derruba_os_outros(self, main_mod, mercado, capsys):
        m = await mercado(canais_ausentes=("B",))
        await main_mod.run_update()
        assert "Loja B não encontrado" in capsys.readouterr().out
        m.canais[m.ids["C"]].send.assert_awaited_once()
        m.canais[m.ids["A"]].send.assert_awaited_once()

    async def test_rank_sem_frutas_publica_esgotado(self, main_mod, mercado):
        m = await mercado(tabela(("C", 1, "C1", "ocupada"), ("B", 1, "B1", ""), ("A", 1, "A1", "")))
        await main_mod.run_update()
        assert "# Esgotado" in m.canais[m.ids["C"]].send.call_args.args[0]

    async def test_anuncio_enviado_com_embed_e_mencoes(self, main_mod, mercado):
        m = await mercado()
        await main_mod.run_update()
        kw = m.canais[m.ids["anuncio"]].send.call_args.kwargs
        assert kw["content"] == " ".join(main_mod.mentions)
        assert kw["embed"].description in main_mod.frases
        assert kw["embed"].image.url in main_mod.gifs

    async def test_anuncio_desligado(self, main_mod, mercado):
        m = await mercado()
        main_mod.announce_on = False
        main_mod.save()
        await main_mod.run_update()
        m.canais[m.ids["anuncio"]].send.assert_not_awaited()

    async def test_contador_de_rotacao_incrementa_e_persiste(self, main_mod, mercado):
        await mercado()
        await main_mod.run_update()
        await main_mod.run_update()
        assert main_mod._cache_load_sync()["contador"] == 2

    async def test_agenda_forca_fruta_na_rotacao_e_consome_a_entrada(self, main_mod, mercado):
        m = await mercado()
        main_mod._cache_save_sync({"contador": 0, "agenda": {"C": {"1": "Fruta C2"}, "B": {}, "A": {}}})
        await main_mod.run_update()
        assert "# Fruta C2" in m.canais[m.ids["C"]].send.call_args.args[0]
        assert main_mod._cache_load_sync()["agenda"]["C"] == {}
        assert "Fruta C2" in main_mod.history["C"]

    async def test_agenda_de_rotacao_futura_nao_e_consumida(self, main_mod, mercado):
        await mercado()
        main_mod._cache_save_sync({"contador": 0, "agenda": {"C": {"5": "Fruta C2"}, "B": {}, "A": {}}})
        await main_mod.run_update()
        assert main_mod._cache_load_sync()["agenda"]["C"] == {"5": "Fruta C2"}

    async def test_agenda_com_fruta_indisponivel_cai_no_sorteio(self, main_mod, mercado):
        m = await mercado()
        main_mod._cache_save_sync({"contador": 0, "agenda": {"C": {"1": "Fruta que ja foi comida"}, "B": {}, "A": {}}})
        await main_mod.run_update()
        txt = m.canais[m.ids["C"]].send.call_args.args[0]
        assert "Fruta que ja foi comida" not in txt and ("Fruta C1" in txt or "Fruta C2" in txt)

    async def test_historico_impede_repeticao_entre_rodadas(self, main_mod, mercado):
        m = await mercado()
        await main_mod.run_update()
        primeira = m.canais[m.ids["C"]].send.call_args.args[0] if m.canais[m.ids["C"]].send.await_count else ""
        main_mod.msg_ids.update({"C": 1, "B": 2, "A": 3})
        await main_mod.run_update()
        editado = m.msgs["C"].edit.call_args.kwargs["content"]
        escolhida_1 = "Fruta C1" if "# Fruta C1" in primeira else "Fruta C2"
        assert f"# {escolhida_1}" not in editado   # só 2 frutas: a outra tem que sair

    async def test_sem_cog_nao_faz_nada(self, main_mod, monkeypatch, capsys):
        monkeypatch.setattr(main_mod.bot, "get_cog", lambda n: None)
        await main_mod.run_update()   # não levanta
        assert "Iniciando" in capsys.readouterr().out

    async def test_erro_da_planilha_e_logado_e_cache_ainda_e_salvo(self, main_mod, mercado, capsys):
        m = await mercado()
        m.cog.disponiveis = AsyncMock(side_effect=RuntimeError("planilha caiu"))
        await main_mod.run_update()   # engole o erro
        assert "Erro crítico update" in capsys.readouterr().out
        assert main_mod._cache_load_sync()["contador"] == 1   # finally salvou

    async def test_mensagem_ruim_do_discord_nao_impede_cache(self, main_mod, mercado):
        m = await mercado()
        m.canais[m.ids["C"]].send.side_effect = http_exc(discord.HTTPException, 500)
        await main_mod.run_update()
        assert main_mod._cache_load_sync()["contador"] == 1


class TestRetornoDoRunUpdate:
    async def test_true_em_sucesso(self, main_mod, mercado):
        await mercado()
        assert await main_mod.run_update() is True

    async def test_false_quando_planilha_indisponivel(self, main_mod, mercado):
        from conftest import api_error
        m = await mercado()
        m.sheet.read_error = api_error(503)
        assert await main_mod.run_update() is False


# --------------------------------------------------------------- auto_update ---
def _fake_datetime_module(main_mod, ano, mes, dia, hora=15, minuto=0):
    real = datetime.datetime

    class FakeDT(real):
        @classmethod
        def now(cls, tz=None):
            return cls(ano, mes, dia, hora, minuto, tzinfo=tz or datetime.timezone.utc)

    return SimpleNamespace(
        datetime=FakeDT, timezone=datetime.timezone, timedelta=datetime.timedelta, time=datetime.time
    )


class TestAutoUpdate:
    async def test_roda_no_domingo(self, main_mod, monkeypatch):
        monkeypatch.setattr(main_mod, "datetime", _fake_datetime_module(main_mod, 2026, 11, 8))  # domingo
        run = AsyncMock(); monkeypatch.setattr(main_mod, "run_update", run)
        await main_mod.auto_update.coro()
        run.assert_awaited_once()

    @pytest.mark.parametrize("dia", [2, 3, 4, 5, 6, 7])  # seg..sáb
    async def test_nao_roda_em_outros_dias(self, main_mod, monkeypatch, dia):
        monkeypatch.setattr(main_mod, "datetime", _fake_datetime_module(main_mod, 2026, 11, dia))
        run = AsyncMock(); monkeypatch.setattr(main_mod, "run_update", run)
        await main_mod.auto_update.coro()
        run.assert_not_awaited()

    async def test_tenta_de_novo_quando_planilha_indisponivel(self, main_mod, monkeypatch):
        monkeypatch.setattr(main_mod, "datetime", _fake_datetime_module(main_mod, 2026, 11, 8))
        run = AsyncMock(side_effect=[False, False, True]); monkeypatch.setattr(main_mod, "run_update", run)
        await main_mod.auto_update.coro()
        assert run.await_count == 3     # parou assim que deu certo

    async def test_desiste_depois_do_limite_e_avisa_no_log(self, main_mod, monkeypatch, capsys):
        monkeypatch.setattr(main_mod, "datetime", _fake_datetime_module(main_mod, 2026, 11, 8))
        run = AsyncMock(return_value=False); monkeypatch.setattr(main_mod, "run_update", run)
        await main_mod.auto_update.coro()
        assert run.await_count == main_mod.AUTO_UPDATE_TENTATIVAS
        assert "forcarteste" in capsys.readouterr().out

    async def test_erro_generico_do_update_nao_gera_retentativa(self, main_mod, monkeypatch):
        monkeypatch.setattr(main_mod, "datetime", _fake_datetime_module(main_mod, 2026, 11, 8))
        run = AsyncMock(return_value=None); monkeypatch.setattr(main_mod, "run_update", run)
        await main_mod.auto_update.coro()
        run.assert_awaited_once()

    def test_agendada_para_15h_utc(self, main_mod):
        assert main_mod.auto_update.time == [datetime.time(15, 0, tzinfo=datetime.timezone.utc)]


# ------------------------------------------------------------------ proxima ---
class TestProxima:
    @pytest.mark.parametrize("dia,hora,minuto,esperado", [
        ((2026, 11, 4), 12, 0, "4d 3h 0m"),     # quarta 12:00 -> domingo 15:00
        ((2026, 11, 8), 10, 0, "0d 5h 0m"),     # domingo antes das 15h
        ((2026, 11, 8), 15, 0, "0d 0h 0m"),     # exatamente na hora
        ((2026, 11, 8), 16, 30, "6d 22h 30m"),  # domingo depois das 15h -> próximo domingo
        ((2026, 11, 7), 15, 1, "0d 23h 59m"),   # sábado 15:01
        ((2026, 11, 2), 0, 0, "6d 15h 0m"),     # segunda 00:00
    ])
    async def test_contagem_regressiva(self, main_mod, monkeypatch, ctx, dia, hora, minuto, esperado):
        monkeypatch.setattr(main_mod, "datetime", _fake_datetime_module(main_mod, *dia, hora, minuto))
        await main_mod.proxima.callback(ctx)
        assert esperado in ctx.send.call_args.kwargs["embed"].description


class TestFalhaDeLeituraNaVirada:
    """Se o Google falhar na leitura, as lojas NÃO podem ser trocadas por 'Esgotado'."""

    async def test_erro_de_leitura_nao_publica_esgotado(self, main_mod, mercado):
        from conftest import api_error
        m = await mercado()
        main_mod.msg_ids.update({"C": 11, "B": 22, "A": 33})
        main_mod.save()
        m.sheet.read_error = api_error(403)
        await main_mod.run_update()
        for r in "CBA":
            m.msgs[r].edit.assert_not_awaited()
            m.canais[m.ids[r]].send.assert_not_awaited()
        m.canais[m.ids["anuncio"]].send.assert_not_awaited()   # nem anuncia uma troca que não houve

    async def test_erro_de_leitura_nao_consome_a_rotacao_nem_a_agenda(self, main_mod, mercado):
        from conftest import api_error
        m = await mercado()
        main_mod._cache_save_sync({"contador": 4, "agenda": {"C": {"5": "Fruta C2"}, "B": {}, "A": {}}})
        m.sheet.read_error = api_error(500, "boom")
        await main_mod.run_update()
        cache = main_mod._cache_load_sync()
        assert cache["agenda"]["C"] == {"5": "Fruta C2"}
        assert cache["contador"] == 4   # a rotação que falhou será tentada de novo
