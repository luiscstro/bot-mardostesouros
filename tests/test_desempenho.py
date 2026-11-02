"""Limites de tempo generosos (evitam regressões de complexidade sem serem flaky no CI)."""
import asyncio
import time

import pytest

from conftest import FakeSheet, tabela

pytestmark = pytest.mark.performance


def medir(fn, *a, **kw):
    t = time.perf_counter()
    r = fn(*a, **kw)
    return time.perf_counter() - t, r


def test_parsing_de_20_mil_linhas(cog_factory):
    valores = tabela(*[("CBA"[i % 3], i, f"Fruta {i}", "" if i % 2 else "ocupada") for i in range(20_000)])
    cog, _ = cog_factory(valores)
    dt, frutas = medir(cog._fetch_sync)
    assert len(frutas) == 20_000 and dt < 2.0


def test_sorteio_em_pool_de_100_mil(main_mod):
    pool = [f"f{i}" for i in range(100_000)]
    dt, _ = medir(main_mod.sortear_com_historico, "C", pool)
    assert dt < 1.0


def test_montar_10_mil_textos_de_loja(main_mod):
    dt, _ = medir(lambda: [main_mod.get_msg_content("C", f"Fruta {i}") for i in range(10_000)])
    assert dt < 1.0


async def test_enc_com_500_frutas(cog_factory, ctx):
    cog, _ = cog_factory(tabela(*[("CBA"[i % 3], i, f"Fruta {i}", "") for i in range(500)]))
    t = time.perf_counter()
    await cog.enc.callback(cog, ctx)
    assert time.perf_counter() - t < 2.0


async def test_disponiveis_nao_bloqueia_o_event_loop(cog_factory):
    """get_frutas roda em thread: outra corrotina continua andando durante a leitura lenta."""
    class Lenta(FakeSheet):
        def get_all_values(self):
            time.sleep(0.3)
            return super().get_all_values()

    cog, _ = cog_factory()
    cog.sheet = Lenta(tabela(("C", 1, "A", "")))
    ticks = 0

    async def contador():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    tarefa = asyncio.create_task(contador())
    await cog.disponiveis("C")
    tarefa.cancel()
    assert ticks >= 10   # se bloqueasse o loop, ticks seria ~0


async def test_run_update_com_planilha_grande(main_mod, cog_registrado, monkeypatch):
    from conftest import make_channel
    await cog_registrado(tabela(*[("CBA"[i % 3], i, f"Fruta {i}", "") for i in range(3_000)]))
    ch, _ = make_channel()
    monkeypatch.setattr(main_mod.bot, "get_channel", lambda cid: ch)
    t = time.perf_counter()
    await main_mod.run_update()
    assert time.perf_counter() - t < 3.0
