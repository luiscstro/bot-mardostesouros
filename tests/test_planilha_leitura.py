"""EstoqueCog: conexão com o Google Sheets e parsing da tabela de frutas."""
import json
from unittest.mock import MagicMock

import pytest

from conftest import FakeSheet, api_error, tabela


# ------------------------------------------------------------- _fetch_sync ---
class TestFetchSync:
    def test_le_frutas_basicas(self, cog_factory, frutas_basicas):
        cog, _ = cog_factory(frutas_basicas)
        frutas = cog._fetch_sync()
        assert len(frutas) == 7
        assert frutas[0] == {"rank": "C", "numero": "1", "nome": "Gomu Gomu no Mi", "status": ""}

    def test_status_vem_minusculo_e_sem_espacos(self, cog_factory):
        cog, _ = cog_factory(tabela(("C", 1, "X", "  Ingerida Por ACE  ")))
        assert cog._fetch_sync()[0]["status"] == "ingerida por ace"

    def test_rank_vem_maiusculo(self, cog_factory):
        cog, _ = cog_factory(tabela(("c", 1, "X", ""), ("b", 2, "Y", "")))
        assert [f["rank"] for f in cog._fetch_sync()] == ["C", "B"]

    def test_planilha_vazia_retorna_lista_vazia(self, cog_factory):
        cog, _ = cog_factory([])
        assert cog._fetch_sync() == []

    def test_so_cabecalho_retorna_lista_vazia(self, cog_factory):
        cog, _ = cog_factory(tabela())
        assert cog._fetch_sync() == []

    def test_ignora_linhas_totalmente_vazias(self, cog_factory):
        v = tabela(("C", 1, "A", ""))
        v.insert(2, ["", "", "", "", ""])
        v.insert(3, [])
        v.append(["C", "2", "B", "", ""])
        cog, _ = cog_factory(v)
        assert [f["nome"] for f in cog._fetch_sync()] == ["A", "B"]

    def test_acha_cabecalho_mesmo_com_linhas_de_titulo_antes(self, cog_factory):
        v = tabela(("C", 1, "A", ""), linhas_antes=[["LISTA DAS AKUMAS"], ["atualizado em 2026"]])
        cog, _ = cog_factory(v)
        frutas = cog._fetch_sync()
        assert [f["nome"] for f in frutas] == ["A"]

    def test_cabecalho_case_insensitive_e_com_espacos(self, cog_factory):
        v = tabela(("C", 1, "A", ""), cabecalho=["  RANK ", "N°", " Nome", "Desc", "STATUS "])
        cog, _ = cog_factory(v)
        assert cog._fetch_sync()[0]["nome"] == "A"

    @pytest.mark.parametrize("col_num", ["n°", "nº", "numero", "num"])
    def test_aceita_varios_nomes_para_coluna_numero(self, cog_factory, col_num):
        v = [["Rank", col_num, "Nome", "x", "Status"], ["C", "7", "Fruta", "", ""]]
        cog, _ = cog_factory(v)
        assert cog._fetch_sync()[0]["numero"] == "7"

    @pytest.mark.parametrize("bruto,esperado", [("12", "12"), ("#12", "12"), ("Nº 5", "5"), ("007", "007"), ("abc", "abc"), ("", "")])
    def test_extrai_digitos_do_numero(self, cog_factory, bruto, esperado):
        v = [["Rank", "N°", "Nome", "x", "Status"], ["C", bruto, "Fruta", "", ""]]
        cog, _ = cog_factory(v)
        assert cog._fetch_sync()[0]["numero"] == esperado

    def test_linha_curta_e_completada(self, cog_factory):
        v = [["Rank", "N°", "Nome", "x", "Status"], ["C", "1", "Fruta"]]  # sem coluna de status
        cog, _ = cog_factory(v)
        f = cog._fetch_sync()[0]
        assert f["nome"] == "Fruta" and f["status"] == ""

    def test_sem_cabecalho_usa_posicoes_padrao(self, cog_factory):
        v = [["C", "1", "Fruta A", "x", ""], ["B", "2", "Fruta B", "x", "ocupada"]]
        cog, _ = cog_factory(v)
        frutas = cog._fetch_sync()
        # sem cabeçalho a 1ª linha é tratada como cabeçalho; a 2ª vira dado
        assert frutas == [{"rank": "B", "numero": "2", "nome": "Fruta B", "status": "ocupada"}]

    def test_ordem_das_colunas_diferente(self, cog_factory):
        v = [["Status", "Nome", "Rank", "N°"], ["", "Fruta", "a", "3"]]
        cog, _ = cog_factory(v)
        assert cog._fetch_sync() == [{"rank": "A", "numero": "3", "nome": "Fruta", "status": ""}]

    @pytest.mark.parametrize("codigo", [400, 401, 403, 404, 500, 503])
    def test_erro_de_leitura_levanta_planilha_indisponivel(self, main_mod, cog_factory, codigo):
        """Antes o erro era engolido e virava '[]' (= nenhuma fruta), o que fazia as lojas virarem 'Esgotado'."""
        cog, _ = cog_factory(read_error=api_error(codigo, "boom"))
        with pytest.raises(main_mod.PlanilhaIndisponivel):
            cog._fetch_sync()

    def test_planilha_vazia_de_verdade_continua_sendo_lista_vazia(self, cog_factory):
        cog, _ = cog_factory([])
        assert cog._fetch_sync() == []

    def test_erro_inesperado_na_leitura_tambem_vira_planilha_indisponivel(self, main_mod, cog_factory):
        cog, _ = cog_factory(read_error=ConnectionError("rede caiu"))
        with pytest.raises(main_mod.PlanilhaIndisponivel):
            cog._fetch_sync()

    def test_formato_inesperado_vira_planilha_indisponivel(self, main_mod, cog_factory):
        cog, _ = cog_factory([["Rank", "N°", "Nome", "x", "Status"], None])   # linha None
        with pytest.raises(main_mod.PlanilhaIndisponivel):
            cog._fetch_sync()

    def test_sem_sheet_tenta_reconectar(self, cog_factory, monkeypatch):
        cog, _ = cog_factory(tabela(("C", 1, "A", "")))
        cog.sheet = None
        chamadas = []

        def reconectar():
            chamadas.append(1)
            cog.sheet = FakeSheet(tabela(("C", 1, "Reconectada", "")))

        monkeypatch.setattr(cog, "connect_gsheets", reconectar)
        assert cog._fetch_sync()[0]["nome"] == "Reconectada"
        assert chamadas == [1]

    def test_sem_sheet_e_reconexao_falha_levanta(self, main_mod, cog_factory, monkeypatch):
        cog, _ = cog_factory()
        cog.sheet = None
        monkeypatch.setattr(cog, "connect_gsheets", lambda: False)
        with pytest.raises(main_mod.PlanilhaIndisponivel):
            cog._fetch_sync()


class TestRetry:
    """Erros transitórios do Google (429/5xx) são repetidos; 403/404 não."""

    class SheetFlaky(FakeSheet):
        def __init__(self, valores, erros):
            super().__init__(valores)
            self.erros = list(erros)
            self.chamadas = 0

        def get_all_values(self):
            self.chamadas += 1
            if self.erros:
                raise self.erros.pop(0)
            return super().get_all_values()

    @pytest.mark.parametrize("codigo", [429, 500, 502, 503])
    def test_recupera_apos_erro_transitorio(self, cog_factory, codigo):
        cog, _ = cog_factory()
        cog.sheet = self.SheetFlaky(tabela(("C", 1, "A", "")), [api_error(codigo)])
        assert cog._fetch_sync()[0]["nome"] == "A"
        assert cog.sheet.chamadas == 2

    def test_desiste_depois_de_3_tentativas(self, main_mod, cog_factory):
        cog, _ = cog_factory()
        cog.sheet = self.SheetFlaky([], [api_error(503)] * 5)
        with pytest.raises(main_mod.PlanilhaIndisponivel):
            cog._fetch_sync()
        assert cog.sheet.chamadas == 3

    @pytest.mark.parametrize("codigo", [400, 401, 403, 404])
    def test_erro_permanente_nao_repete(self, main_mod, cog_factory, codigo):
        cog, _ = cog_factory()
        cog.sheet = self.SheetFlaky([], [api_error(codigo)] * 5)
        with pytest.raises(main_mod.PlanilhaIndisponivel):
            cog._fetch_sync()
        assert cog.sheet.chamadas == 1

    def test_espera_entre_tentativas(self, main_mod, cog_factory, monkeypatch):
        monkeypatch.setattr(main_mod, "SHEETS_ESPERA_RETRY", (1, 2))
        dormiu = []
        monkeypatch.setattr(main_mod.time, "sleep", dormiu.append)
        cog, _ = cog_factory()
        cog.sheet = self.SheetFlaky([], [api_error(503)] * 5)
        with pytest.raises(main_mod.PlanilhaIndisponivel):
            cog._fetch_sync()
        assert dormiu == [1, 2]


class TestGetFrutasEDisponiveis:
    async def test_get_frutas_roda_em_thread(self, cog_factory, frutas_basicas):
        cog, _ = cog_factory(frutas_basicas)
        assert len(await cog.get_frutas()) == 7

    async def test_disponiveis_filtra_por_rank_e_status_vazio(self, cog_factory, frutas_basicas):
        cog, _ = cog_factory(frutas_basicas)
        assert await cog.disponiveis("C") == ["Gomu Gomu no Mi", "Hana Hana no Mi"]
        assert await cog.disponiveis("A") == ["Netsu Netsu no Mi"]
        assert await cog.disponiveis("B") == ["Bara Bara no Mi"]

    async def test_disponiveis_rank_inexistente(self, cog_factory, frutas_basicas):
        cog, _ = cog_factory(frutas_basicas)
        assert await cog.disponiveis("Z") == []

    async def test_status_so_com_espacos_conta_como_disponivel(self, cog_factory):
        cog, _ = cog_factory(tabela(("C", 1, "A", "   ")))
        assert await cog.disponiveis("C") == ["A"]


# ----------------------------------------------------------- connect_gsheets ---
class TestConnectGsheets:
    @pytest.fixture
    def mocks(self, monkeypatch, main_mod):
        creds = MagicMock()
        creds.service_account_email = "bot@proj.iam.gserviceaccount.com"
        sac = MagicMock()
        sac.from_json_keyfile_name.return_value = creds
        sac.from_json_keyfile_dict.return_value = creds
        monkeypatch.setattr(main_mod, "ServiceAccountCredentials", sac)

        worksheet = MagicMock(name="worksheet")
        client = MagicMock()
        client.open.return_value.worksheet.return_value = worksheet
        authorize = MagicMock(return_value=client)
        monkeypatch.setattr(main_mod.gspread, "authorize", authorize)
        return SimpleNS(sac=sac, creds=creds, client=client, worksheet=worksheet, authorize=authorize)

    def _novo_cog(self, main_mod):
        return main_mod.EstoqueCog(main_mod.bot)

    def test_conecta_com_arquivo_json(self, main_mod, mocks):
        cog = self._novo_cog(main_mod)
        assert cog.sheet is mocks.worksheet
        mocks.sac.from_json_keyfile_name.assert_called_once()
        mocks.client.open.assert_called_with(main_mod.NOME_PLANILHA)
        mocks.client.open.return_value.worksheet.assert_called_with(main_mod.ABA_PLANILHA)

    def test_guarda_email_da_conta_de_servico(self, main_mod, mocks):
        assert self._novo_cog(main_mod).service_account_email == "bot@proj.iam.gserviceaccount.com"

    def test_credenciais_via_variavel_de_ambiente(self, main_mod, mocks, monkeypatch):
        info = {"client_email": "x@y.iam.gserviceaccount.com", "private_key": "k"}
        monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", json.dumps(info))
        cog = self._novo_cog(main_mod)
        mocks.sac.from_json_keyfile_dict.assert_called_once()
        assert mocks.sac.from_json_keyfile_dict.call_args.args[0] == info
        mocks.sac.from_json_keyfile_name.assert_not_called()
        assert cog.sheet is mocks.worksheet

    def test_json_invalido_na_variavel_nao_derruba_o_bot(self, main_mod, mocks, monkeypatch, capsys):
        monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", "{isto nao e json")
        cog = self._novo_cog(main_mod)
        assert cog.sheet is None
        assert "Erro GSheets" in capsys.readouterr().out

    def test_arquivo_de_credenciais_ausente_nao_derruba_o_bot(self, main_mod, mocks, capsys):
        mocks.sac.from_json_keyfile_name.side_effect = FileNotFoundError("sem json")
        cog = self._novo_cog(main_mod)
        assert cog.sheet is None
        assert "Erro GSheets" in capsys.readouterr().out

    def test_planilha_nao_encontrada(self, main_mod, mocks):
        mocks.client.open.side_effect = main_mod.gspread.exceptions.SpreadsheetNotFound
        assert self._novo_cog(main_mod).sheet is None

    def test_aba_nao_encontrada(self, main_mod, mocks):
        mocks.client.open.return_value.worksheet.side_effect = main_mod.gspread.exceptions.WorksheetNotFound
        assert self._novo_cog(main_mod).sheet is None

    def test_retorna_true_em_sucesso_e_false_em_falha(self, main_mod, mocks):
        cog = self._novo_cog(main_mod)
        assert cog.connect_gsheets() is True
        mocks.client.open.side_effect = RuntimeError("x")
        assert cog.connect_gsheets() is False
        assert cog.sheet is None

    def test_escopos_incluem_sheets_e_drive(self, main_mod, mocks):
        cog = self._novo_cog(main_mod)
        assert any("spreadsheets" in s for s in cog.scope)
        assert any("drive" in s for s in cog.scope)


class SimpleNS:
    def __init__(self, **kw):
        self.__dict__.update(kw)
