"""save/load de mensagens.json, cache de agenda e backoff de login."""
import json
import os

import pytest


# ----------------------------------------------------------- mensagens.json ---
class TestSaveLoad:
    def test_round_trip(self, main_mod):
        main_mod.msg_ids.update({"C": 1, "B": 2, "A": 3})
        main_mod.history["C"].extend(["x", "y"])
        main_mod.announce_on = False
        main_mod.save()

        main_mod.msg_ids.update({"C": None, "B": None, "A": None})
        main_mod.history = {"C": [], "B": [], "A": []}
        main_mod.announce_on = True
        main_mod.load()

        assert main_mod.msg_ids == {"C": 1, "B": 2, "A": 3}
        assert main_mod.history["C"] == ["x", "y"]
        assert main_mod.announce_on is False

    def test_arquivo_salvo_tem_formato_esperado(self, main_mod):
        main_mod.msg_ids["C"] = 42
        main_mod.save()
        with open(main_mod.ARQUIVO_MSGS) as f:
            d = json.load(f)
        assert set(d) == {"C", "B", "A", "announce_enabled", "history"}
        assert d["C"] == 42 and d["announce_enabled"] is True

    def test_load_sem_arquivo_mantem_padroes(self, main_mod):
        main_mod.load()
        assert main_mod.msg_ids == {"C": None, "B": None, "A": None}
        assert main_mod.announce_on is True

    def test_load_arquivo_corrompido_nao_levanta(self, main_mod, capsys):
        with open(main_mod.ARQUIVO_MSGS, "w") as f:
            f.write("{ nao é json")
        main_mod.load()
        assert "Erro ao carregar JSON" in capsys.readouterr().out

    def test_load_arquivo_antigo_sem_historico(self, main_mod):
        with open(main_mod.ARQUIVO_MSGS, "w") as f:
            json.dump({"C": 1, "B": 2, "A": 3}, f)
        main_mod.load()
        assert main_mod.history == {"C": [], "B": [], "A": []}
        assert main_mod.announce_on is True

    def test_save_com_diretorio_inexistente_nao_levanta(self, main_mod, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(main_mod, "ARQUIVO_MSGS", str(tmp_path / "nao" / "existe" / "m.json"))
        main_mod.save()
        assert "Erro ao salvar JSON" in capsys.readouterr().out

    async def test_versoes_async(self, main_mod):
        main_mod.msg_ids["B"] = 77
        await main_mod.save_async()
        main_mod.msg_ids["B"] = None
        await main_mod.load_async()
        assert main_mod.msg_ids["B"] == 77

    def test_historico_com_acentos_sobrevive(self, main_mod):
        main_mod.history["C"].append("Fruta do Vaca: Modelo Cabra ✨")
        main_mod.save()
        main_mod.history = {"C": [], "B": [], "A": []}
        main_mod.load()
        assert main_mod.history["C"] == ["Fruta do Vaca: Modelo Cabra ✨"]

    @pytest.mark.xfail(strict=True, reason="BUG conhecido: histórico salvo sem a chave de um rank causa KeyError em sortear_com_historico")
    def test_historico_parcial_nao_deve_quebrar_sorteio(self, main_mod):
        with open(main_mod.ARQUIVO_MSGS, "w") as f:
            json.dump({"history": {"C": ["a"]}}, f)
        main_mod.load()
        main_mod.sortear_com_historico("B", ["x", "y"])


# -------------------------------------------------------------------- cache ---
class TestCache:
    def test_padrao_quando_nao_existe(self, main_mod):
        assert main_mod._cache_load_sync() == {"contador": 0, "agenda": {"C": {}, "B": {}, "A": {}}}

    def test_round_trip(self, main_mod):
        d = {"contador": 5, "agenda": {"C": {"7": "Fruta"}, "B": {}, "A": {}}}
        main_mod._cache_save_sync(d)
        assert main_mod._cache_load_sync() == d

    def test_completa_chaves_faltando(self, main_mod):
        with open(main_mod.ARQUIVO_CACHE, "w") as f:
            json.dump({"outra": 1}, f)
        d = main_mod._cache_load_sync()
        assert d["contador"] == 0 and d["agenda"] == {"C": {}, "B": {}, "A": {}} and d["outra"] == 1

    def test_corrompido_volta_ao_padrao(self, main_mod):
        with open(main_mod.ARQUIVO_CACHE, "w") as f:
            f.write("lixo")
        assert main_mod._cache_load_sync()["contador"] == 0

    def test_save_em_caminho_invalido_nao_levanta(self, main_mod, monkeypatch, tmp_path):
        monkeypatch.setattr(main_mod, "ARQUIVO_CACHE", str(tmp_path / "x" / "y" / "c.json"))
        main_mod._cache_save_sync({"contador": 1})

    def test_preserva_utf8(self, main_mod):
        main_mod._cache_save_sync({"contador": 1, "agenda": {"C": {"2": "Fruta do Zíper"}, "B": {}, "A": {}}})
        with open(main_mod.ARQUIVO_CACHE, encoding="utf-8") as f:
            assert "Zíper" in f.read()   # ensure_ascii=False


# ------------------------------------------------------------------ backoff ---
class TestBackoffLogin:
    @pytest.fixture
    def relogio(self, main_mod, monkeypatch):
        estado = {"agora": 10_000.0, "dormiu": []}
        monkeypatch.setattr(main_mod.time, "time", lambda: estado["agora"])
        monkeypatch.setattr(main_mod.time, "sleep", lambda s: estado["dormiu"].append(s))
        return estado

    def test_sem_falhas_nao_espera(self, main_mod, relogio):
        main_mod._login_backoff_esperar()
        assert relogio["dormiu"] == []

    def test_primeira_falha_espera_base_vezes_2(self, main_mod, relogio):
        """Fórmula atual: min(BASE * 2**falhas, MAX) -> 1ª falha = 120s."""
        main_mod._login_backoff_registrar_falha()
        main_mod._login_backoff_esperar()
        assert relogio["dormiu"] == [main_mod.LOGIN_BACKOFF_BASE * 2]

    @pytest.mark.parametrize("falhas,esperado", [(1, 120), (2, 240), (3, 480), (4, 900), (5, 900)])
    def test_espera_dobra_a_cada_falha_ate_o_teto(self, main_mod, relogio, falhas, esperado):
        for _ in range(falhas):
            main_mod._login_backoff_registrar_falha()
        main_mod._login_backoff_esperar()
        assert relogio["dormiu"] == [esperado]

    def test_espera_tem_teto(self, main_mod, relogio):
        for _ in range(20):
            main_mod._login_backoff_registrar_falha()
        main_mod._login_backoff_esperar()
        assert relogio["dormiu"] == [main_mod.LOGIN_BACKOFF_MAX]

    def test_desconta_o_tempo_ja_decorrido(self, main_mod, relogio):
        main_mod._login_backoff_registrar_falha()
        relogio["agora"] += 25
        main_mod._login_backoff_esperar()
        assert relogio["dormiu"] == [pytest.approx(main_mod.LOGIN_BACKOFF_BASE * 2 - 25)]

    def test_nao_espera_se_o_tempo_ja_passou(self, main_mod, relogio):
        main_mod._login_backoff_registrar_falha()
        relogio["agora"] += main_mod.LOGIN_BACKOFF_BASE * 2 + 1
        main_mod._login_backoff_esperar()
        assert relogio["dormiu"] == []

    def test_sucesso_zera_o_backoff(self, main_mod, relogio):
        main_mod._login_backoff_registrar_falha()
        main_mod._login_backoff_registrar_sucesso()
        main_mod._login_backoff_esperar()
        assert relogio["dormiu"] == []
        assert main_mod._cache_load_sync()["login_backoff"] == {"falhas": 0, "ultima": 0}

    def test_sucesso_sem_falhas_nao_cria_arquivo(self, main_mod, relogio):
        main_mod._login_backoff_registrar_sucesso()
        assert not os.path.exists(main_mod.ARQUIVO_CACHE)

    def test_falha_nao_apaga_o_resto_do_cache(self, main_mod, relogio):
        main_mod._cache_save_sync({"contador": 9, "agenda": {"C": {"1": "x"}, "B": {}, "A": {}}})
        main_mod._login_backoff_registrar_falha()
        d = main_mod._cache_load_sync()
        assert d["contador"] == 9 and d["agenda"]["C"] == {"1": "x"} and d["login_backoff"]["falhas"] == 1


class TestMain:
    """main(): fluxo de login e tratamento do 429 da Cloudflare."""

    def _http_exc(self, main_mod, status):
        import discord
        from unittest.mock import MagicMock
        resp = MagicMock(); resp.status = status; resp.reason = "x"
        return discord.HTTPException(resp, "msg")

    def test_429_registra_falha_dorme_e_repropaga(self, main_mod, monkeypatch):
        import discord
        dormiu = []
        monkeypatch.setattr(main_mod.time, "sleep", lambda s: dormiu.append(s))
        monkeypatch.setattr(main_mod, "_login_backoff_esperar", lambda: None)
        monkeypatch.setattr(main_mod.bot, "run", lambda t: (_ for _ in ()).throw(self._http_exc(main_mod, 429)))
        with pytest.raises(discord.HTTPException):
            main_mod.main()
        assert dormiu == [30]
        assert main_mod._cache_load_sync()["login_backoff"]["falhas"] == 1

    def test_outro_erro_http_repropaga_sem_registrar_falha(self, main_mod, monkeypatch):
        import discord
        monkeypatch.setattr(main_mod, "_login_backoff_esperar", lambda: None)
        monkeypatch.setattr(main_mod.bot, "run", lambda t: (_ for _ in ()).throw(self._http_exc(main_mod, 500)))
        with pytest.raises(discord.HTTPException):
            main_mod.main()
        assert "login_backoff" not in main_mod._cache_load_sync()

    def test_login_ok_usa_o_token_do_ambiente(self, main_mod, monkeypatch):
        chamadas = []
        monkeypatch.setattr(main_mod, "_login_backoff_esperar", lambda: chamadas.append("espera"))
        monkeypatch.setattr(main_mod.bot, "run", lambda t: chamadas.append(("run", t)))
        monkeypatch.setattr(main_mod, "TOKEN", "tok")
        main_mod.main()
        assert chamadas == ["espera", ("run", "tok")]

    def test_importar_main_nao_conecta_no_discord(self):
        """Regressão: bot.run rodava no import, impedindo qualquer teste."""
        import importlib, sys
        from unittest.mock import patch
        with patch("discord.ext.commands.Bot.run") as run:
            sys.modules.pop("main", None)
            importlib.import_module("main")
            run.assert_not_called()
