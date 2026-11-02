"""Testes baseados em propriedades (hypothesis): entradas aleatórias, invariantes fixos."""
import asyncio
import datetime
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from conftest import FakeSheet, make_ctx, make_role

pytestmark = pytest.mark.property
cfg = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])

texto = st.text(max_size=40)
celula = st.one_of(texto, st.integers().map(str), st.just(""))
linha = st.lists(celula, max_size=8)
tabela_qualquer = st.lists(linha, max_size=25)


class TestParsingDaPlanilha:
    @cfg
    @given(tabela_qualquer)
    def test_nunca_levanta_com_qualquer_conteudo(self, cog_factory, valores):
        cog, _ = cog_factory(valores)
        assert isinstance(cog._fetch_sync(), list)

    @cfg
    @given(st.lists(st.tuples(st.sampled_from(["c", "B", " a ", "S", "x", ""]), celula, texto, texto), max_size=30))
    def test_formato_dos_campos_retornados(self, cog_factory, linhas):
        valores = [["Rank", "N°", "Nome", "Desc", "Status"]] + [[r, n, nome, "", st_] for r, n, nome, st_ in linhas]
        cog, _ = cog_factory(valores)
        for f in cog._fetch_sync():
            assert set(f) == {"rank", "numero", "nome", "status"}
            assert f["rank"] == f["rank"].upper() == f["rank"].strip()
            assert f["status"] == f["status"].lower() == f["status"].strip()
            assert f["nome"] == f["nome"].strip()

    @cfg
    @given(st.lists(st.tuples(st.sampled_from(["C", "B", "A"]), st.integers(1, 999), st.text(min_size=1, max_size=20, alphabet="abcdefghij "),
                              st.sampled_from(["", "ocupada"])), max_size=40))
    def test_disponiveis_sao_exatamente_as_sem_status(self, cog_factory, linhas):
        valores = [["Rank", "N°", "Nome", "x", "Status"]] + [[r, str(n), nome, "", s] for r, n, nome, s in linhas]
        cog, _ = cog_factory(valores)
        for rank in "CBA":
            esperado = [nome.strip() for r, n, nome, s in linhas if r == rank and not s]
            got = asyncio.run(cog.disponiveis(rank))
            assert got == esperado


class TestSorteio:
    @cfg
    @given(st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=15, unique=True),
           st.lists(st.text(min_size=1, max_size=10), max_size=3))
    def test_sempre_escolhe_da_lista_e_historico_fica_limitado(self, main_mod, pool, historico):
        main_mod.history["C"] = list(historico)
        escolhida = main_mod.sortear_com_historico("C", pool)
        assert escolhida in pool
        assert len(main_mod.history["C"]) <= 3
        assert main_mod.history["C"][-1] == escolhida

    @cfg
    @given(st.lists(st.text(min_size=1, max_size=10), min_size=4, max_size=15, unique=True))
    def test_com_pool_maior_que_o_historico_nunca_repete(self, main_mod, pool):
        main_mod.history["B"] = list(pool[:3])
        assert main_mod.sortear_com_historico("B", pool) not in pool[:3]

    @cfg
    @given(st.integers(0, 60))
    def test_historico_nunca_passa_de_3_depois_de_n_sorteios(self, main_mod, n):
        main_mod.history["A"] = []
        for _ in range(n):
            main_mod.sortear_com_historico("A", ["a", "b", "c", "d", "e"])
        assert len(main_mod.history["A"]) == min(n, 3)


class TestTextos:
    @cfg
    @given(st.text(max_size=300))
    def test_get_msg_content_sempre_termina_com_o_nome(self, main_mod, nome):
        for rank in ["C", "B", "A", "?"]:
            assert main_mod.get_msg_content(rank, nome).endswith(f"# {nome}")

    @cfg
    @given(st.text(max_size=12000), st.integers(1, 2000))
    def test_send_chunked_preserva_texto_e_respeita_limite(self, main_mod, txt, tamanho):
        ch = MagicMock(); ch.send = AsyncMock()
        asyncio.run(main_mod.send_chunked(ch, txt, tamanho))
        partes = [c.args[0] for c in ch.send.call_args_list]
        assert "".join(partes) == txt
        assert all(0 < len(p) <= tamanho for p in partes)


class TestPersistencia:
    chaves_id = st.one_of(st.none(), st.integers(0, 2**63))

    @cfg
    @given(chaves_id, chaves_id, chaves_id, st.booleans(),
           st.lists(st.text(max_size=30), max_size=3), st.lists(st.text(max_size=30), max_size=3))
    def test_save_load_round_trip(self, main_mod, c, b, a, anuncio, hc, hb):
        main_mod.msg_ids.update({"C": c, "B": b, "A": a})
        main_mod.announce_on = anuncio
        main_mod.history = {"C": hc, "B": hb, "A": []}
        main_mod.save()
        main_mod.msg_ids.update({"C": 0, "B": 0, "A": 0})
        main_mod.history = {"C": [], "B": [], "A": []}
        main_mod.load()
        assert main_mod.msg_ids == {"C": c, "B": b, "A": a}
        assert main_mod.announce_on is anuncio
        assert main_mod.history["C"] == hc and main_mod.history["B"] == hb

    @cfg
    @given(st.dictionaries(st.text(min_size=1, max_size=8), st.one_of(st.integers(), st.text(max_size=10), st.booleans()), max_size=6))
    def test_cache_nao_perde_chaves_desconhecidas(self, main_mod, extra):
        d = {**extra, "contador": 3, "agenda": {"C": {}, "B": {}, "A": {}}}
        main_mod._cache_save_sync(d)
        assert main_mod._cache_load_sync() == d

    @cfg
    @given(st.binary(max_size=200))
    def test_cache_com_bytes_aleatorios_nunca_levanta(self, main_mod, lixo):
        with open(main_mod.ARQUIVO_CACHE, "wb") as f:
            f.write(lixo)
        d = main_mod._cache_load_sync()
        assert "contador" in d and "agenda" in d

    @cfg
    @given(st.binary(max_size=200))
    def test_mensagens_json_com_bytes_aleatorios_nunca_levanta(self, main_mod, lixo):
        with open(main_mod.ARQUIVO_MSGS, "wb") as f:
            f.write(lixo)
        main_mod.load()   # só não pode levantar


class TestBackoff:
    @cfg
    @given(st.integers(0, 40))
    def test_espera_limitada_e_monotonica(self, main_mod, monkeypatch, falhas):
        esperas = []
        monkeypatch.setattr(main_mod.time, "sleep", esperas.append)
        monkeypatch.setattr(main_mod.time, "time", lambda: 5_000.0)
        main_mod._cache_save_sync({"contador": 0, "agenda": {}, "login_backoff": {"falhas": falhas, "ultima": 5_000.0}})
        main_mod._login_backoff_esperar()
        if falhas == 0:
            assert esperas == []
        else:
            assert esperas == [min(main_mod.LOGIN_BACKOFF_BASE * 2 ** falhas, main_mod.LOGIN_BACKOFF_MAX)]
            assert 0 < esperas[0] <= main_mod.LOGIN_BACKOFF_MAX


class TestPermissoes:
    @cfg
    @given(st.lists(st.integers(0, 2**62), max_size=10))
    def test_is_staff_sse_tem_algum_cargo_permitido(self, main_mod, ids):
        ctx = make_ctx(roles=[make_role(i) for i in ids])
        esperado = bool(set(ids) & set(main_mod.CARGOS_PERMITIDOS))
        assert bool(main_mod.is_staff(ctx)) is esperado


class TestProxima:
    @cfg
    @given(st.datetimes(min_value=datetime.datetime(2025, 1, 1), max_value=datetime.datetime(2035, 12, 31)))
    def test_sempre_entre_0_e_7_dias_e_cai_num_domingo_15h(self, main_mod, monkeypatch, dt):
        agora = dt.replace(tzinfo=datetime.timezone.utc)

        class FakeDT(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromtimestamp(agora.timestamp(), tz=datetime.timezone.utc)

        monkeypatch.setattr(main_mod, "datetime", SimpleNamespace(
            datetime=FakeDT, timezone=datetime.timezone, timedelta=datetime.timedelta, time=datetime.time))
        ctx = make_ctx()
        asyncio.run(main_mod.proxima.callback(ctx))
        d, h, m = map(int, re.search(r"(\d+)d (\d+)h (\d+)m", ctx.send.call_args.kwargs["embed"].description).groups())

        # oráculo independente: primeiro domingo 15:00 UTC que seja >= agora
        alvo = next(
            c for c in (
                datetime.datetime.combine(agora.date() + datetime.timedelta(days=i), datetime.time(15, 0), tzinfo=datetime.timezone.utc)
                for i in range(0, 9)
            ) if c.weekday() == 6 and c >= agora
        )
        diff = alvo - agora
        assert (d, h, m) == (diff.days, diff.seconds // 3600, (diff.seconds % 3600) // 60)
