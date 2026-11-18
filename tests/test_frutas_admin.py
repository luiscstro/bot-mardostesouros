"""Cadastro/remoção de frutas: parser em massa, escrita na planilha, comandos do bot."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from conftest import api_error, tabela


# ---------------------------------------------------------------- parse_lote ---
class TestParseLote:
    def test_um_rank_varias_frutas(self, main_mod):
        itens, erros = main_mod.parse_lote("S Mera Mera no Mi, Goro Goro no Mi")
        assert erros == []
        assert itens == [{"rank": "S", "nome": "Mera Mera no Mi"}, {"rank": "S", "nome": "Goro Goro no Mi"}]

    def test_varios_ranks_uma_linha_por_rank(self, main_mod):
        itens, erros = main_mod.parse_lote("S: Fruta 1, Fruta 2\nA: Fruta 3\nb - Fruta 4\nRank C Fruta 5")
        assert erros == []
        assert [(i["rank"], i["nome"]) for i in itens] == [
            ("S", "Fruta 1"), ("S", "Fruta 2"), ("A", "Fruta 3"), ("B", "Fruta 4"), ("C", "Fruta 5")]

    def test_linhas_sem_rank_herdam_o_ultimo(self, main_mod):
        itens, _ = main_mod.parse_lote("A:\nFruta 1\nFruta 2")
        assert [(i["rank"], i["nome"]) for i in itens] == [("A", "Fruta 1"), ("A", "Fruta 2")]

    def test_rank_padrao(self, main_mod):
        itens, erros = main_mod.parse_lote("Fruta 1\nFruta 2, Fruta 3", rank_padrao="b")
        assert erros == [] and [i["rank"] for i in itens] == ["B", "B", "B"]

    def test_sem_rank_gera_erro(self, main_mod):
        itens, erros = main_mod.parse_lote("Fruta sem rank")
        assert itens == [] and len(erros) == 1

    def test_nome_que_comeca_com_letra_de_rank_nao_e_confundido(self, main_mod):
        itens, _ = main_mod.parse_lote("Bara Bara no Mi, Ope Ope no Mi", rank_padrao="A")
        assert [i["nome"] for i in itens] == ["Bara Bara no Mi", "Ope Ope no Mi"]

    def test_ponto_e_virgula_e_espacos_extras(self, main_mod):
        itens, _ = main_mod.parse_lote("S:   Fruta   1 ;  Fruta 2 ,, ")
        assert [i["nome"] for i in itens] == ["Fruta 1", "Fruta 2"]

    def test_vazio(self, main_mod):
        assert main_mod.parse_lote("") == ([], [])
        assert main_mod.parse_lote(None) == ([], [])


# ------------------------------------------------------------ leitura nova ---
class TestLeituraTolerante:
    def test_rank_vazio_herda_o_de_cima(self, cog_factory):
        v = tabela(("S", 1, "A", ""), ("", 2, "B", ""))
        cog, _ = cog_factory(v)
        assert [f["rank"] for f in cog._fetch_sync()] == ["S", "S"]

    def test_rank_com_a_palavra_rank(self, cog_factory):
        cog, _ = cog_factory(tabela(("Rank S", 1, "A", ""), (" a ", 2, "B", "")))
        assert [f["rank"] for f in cog._fetch_sync()] == ["S", "A"]

    def test_cabecalho_repetido_no_meio_e_ignorado(self, cog_factory):
        v = tabela(("C", 1, "A", ""))
        v.append(["Rank", "N°", "Nome", "Descrição", "Status"])
        v.append(["B", "1", "B", "", ""])
        cog, _ = cog_factory(v)
        assert [f["nome"] for f in cog._fetch_sync()] == ["A", "B"]

    def test_tabela_traz_numero_da_linha_e_linhas_acima_do_cabecalho(self, cog_factory):
        v = tabela(("C", 1, "A", ""), linhas_antes=[["TÍTULO"]])
        t = cog_factory(v)[0]._tabela_sync()
        assert t["frutas"][0]["linha"] == 3 and t["idx_head"] == 2
        assert t["acima"] == [(1, ["TÍTULO"])]


# ------------------------------------------------------------------- escrita ---
class TestAdicionar:
    def test_numera_por_rank_a_partir_do_maior(self, cog_factory, frutas_basicas):
        cog, sheet = cog_factory(frutas_basicas)
        r = cog.adicionar_sync([{"rank": "S", "nome": "Nova S"}, {"rank": "C", "nome": "Nova C"}, {"rank": "S", "nome": "Outra S"}])
        assert [(f["rank"], f["numero"]) for f in r["adicionadas"]] == [("S", "2"), ("C", "4"), ("S", "3")]
        assert sheet.appended == [["S", "2", "Nova S", "", ""], ["C", "4", "Nova C", "", ""], ["S", "3", "Outra S", "", ""]]

    def test_rank_novo_comeca_em_1(self, cog_factory):
        cog, sheet = cog_factory(tabela(("C", 1, "X", "")))
        cog.adicionar_sync([{"rank": "S", "nome": "Nova"}])
        assert sheet.appended[0][:3] == ["S", "1", "Nova"]

    def test_mantem_formato_do_numero(self, cog_factory):
        cog, sheet = cog_factory([["Rank", "N°", "Nome", "x", "Status"], ["C", "Nº 7", "X", "", ""]])
        cog.adicionar_sync([{"rank": "C", "nome": "Nova"}])
        assert sheet.appended[0][1] == "Nº 8"

    def test_respeita_ordem_das_colunas(self, cog_factory):
        cog, sheet = cog_factory([["Status", "Nome", "Rank", "N°"], ["", "X", "A", "3"]])
        cog.adicionar_sync([{"rank": "A", "nome": "Nova"}])
        assert sheet.appended[0] == ["", "Nova", "A", "4"]

    def test_duplicada_ignora_maiusculas_e_espacos(self, cog_factory, frutas_basicas):
        cog, sheet = cog_factory(frutas_basicas)
        r = cog.adicionar_sync([{"rank": "S", "nome": "gomu  gomu NO mi"}, {"rank": "A", "nome": "Nova"}, {"rank": "B", "nome": "nova"}])
        assert r["duplicadas"] == ["gomu gomu NO mi", "nova"] and len(r["adicionadas"]) == 1
        assert len(sheet.appended) == 1

    def test_rejeita_rank_invalido_nome_vazio_e_formula(self, cog_factory, frutas_basicas):
        cog, sheet = cog_factory(frutas_basicas)
        r = cog.adicionar_sync([{"rank": "Z", "nome": "X"}, {"rank": "S", "nome": ""}, {"rank": "S", "nome": "=IMPORTXML(1)"}, {"rank": "S", "nome": "x" * 101}])
        assert len(r["rejeitadas"]) == 4 and r["adicionadas"] == []
        assert not hasattr(sheet, "appended")

    def test_planilha_vazia_gera_erro(self, main_mod, cog_factory):
        cog, _ = cog_factory([])
        with pytest.raises(main_mod.ErroPlanilha):
            cog.adicionar_sync([{"rank": "S", "nome": "X"}])

    def test_403_vira_erro_com_email_da_conta(self, main_mod, cog_factory, frutas_basicas):
        cog, _ = cog_factory(frutas_basicas, write_error=api_error(403))
        cog.service_account_email = "bot@proj.iam"
        with pytest.raises(main_mod.ErroPlanilha, match="bot@proj.iam"):
            cog.adicionar_sync([{"rank": "S", "nome": "Nova"}])

    def test_fruta_nova_aparece_na_leitura(self, cog_factory, frutas_basicas):
        cog, _ = cog_factory(frutas_basicas)
        cog.adicionar_sync([{"rank": "S", "nome": "Nova S"}])
        assert {"rank": "S", "numero": "2", "nome": "Nova S", "status": ""} in cog._fetch_sync()


class TestRemoverEEditar:
    def test_remove_a_linha_certa(self, cog_factory, frutas_basicas):
        cog, sheet = cog_factory(frutas_basicas)
        alvo = next(f for f in cog._tabela_sync()["frutas"] if f["nome"] == "Hana Hana no Mi")
        cog.remover_sync(alvo["linha"], "Hana Hana no Mi")
        assert "Hana Hana no Mi" not in [f["nome"] for f in cog._fetch_sync()]
        assert len(cog._fetch_sync()) == 6

    def test_nao_remove_se_a_planilha_mudou(self, main_mod, cog_factory, frutas_basicas):
        cog, _ = cog_factory(frutas_basicas)
        with pytest.raises(main_mod.ErroPlanilha):
            cog.remover_sync(2, "Nome Errado")
        assert len(cog._fetch_sync()) == 7

    def test_edita_status_e_limpa(self, cog_factory, frutas_basicas):
        cog, _ = cog_factory(frutas_basicas)
        f = cog._tabela_sync()["frutas"][0]
        cog.editar_sync(f["linha"], f["nome"], status="Ingerida por Zoro")
        assert cog._fetch_sync()[0]["status"] == "ingerida por zoro"
        cog.editar_sync(f["linha"], f["nome"], status="")
        assert cog._fetch_sync()[0]["status"] == ""

    def test_status_nao_vira_formula(self, cog_factory, frutas_basicas):
        cog, sheet = cog_factory(frutas_basicas)
        f = cog._tabela_sync()["frutas"][0]
        cog.editar_sync(f["linha"], f["nome"], status="=1+1")
        assert sheet.updates[-1][2] == "'=1+1"

    def test_renomear_e_bloquear_duplicado(self, main_mod, cog_factory, frutas_basicas):
        cog, _ = cog_factory(frutas_basicas)
        f = cog._tabela_sync()["frutas"][0]
        cog.editar_sync(f["linha"], f["nome"], nome="Gomu Novo")
        assert cog._fetch_sync()[0]["nome"] == "Gomu Novo"
        with pytest.raises(main_mod.ErroPlanilha):
            cog.editar_sync(f["linha"], "Gomu Novo", nome="mera mera no mi")


# ------------------------------------------------------------ comandos do bot ---
class TestComandos:
    async def test_addfruta_cadastra_varios_ranks(self, main_mod, staff_ctx, cog_registrado, frutas_basicas):
        _, sheet = await cog_registrado(frutas_basicas)
        await main_mod.addfruta.callback(staff_ctx, texto="S: Nova S1, Nova S2\nA: Nova A")
        assert len(sheet.appended) == 3
        txt = staff_ctx.send.return_value.edit.await_args.kwargs["content"]
        assert "3 fruta(s)" in txt and "Nova A" in txt

    async def test_addfruta_sem_rank_mostra_ajuda_e_nao_escreve(self, main_mod, staff_ctx, cog_registrado, frutas_basicas):
        _, sheet = await cog_registrado(frutas_basicas)
        await main_mod.addfruta.callback(staff_ctx, texto="Sem rank aqui")
        assert not hasattr(sheet, "appended")
        assert "Sem rank" in staff_ctx.send.await_args.args[0]

    async def test_addfruta_informa_erro_de_permissao(self, main_mod, staff_ctx, cog_registrado, frutas_basicas):
        cog, _ = await cog_registrado(frutas_basicas, write_error=api_error(403))
        cog.service_account_email = "bot@proj.iam"
        await main_mod.addfruta.callback(staff_ctx, texto="S Nova")
        assert "bot@proj.iam" in staff_ctx.send.return_value.edit.await_args.kwargs["content"]

    async def test_rmfruta_pede_confirmacao_e_remove(self, main_mod, staff_ctx, cog_registrado, frutas_basicas, monkeypatch):
        cog, _ = await cog_registrado(frutas_basicas)
        monkeypatch.setattr(main_mod.bot, "wait_for", AsyncMock(return_value=(MagicMock(), staff_ctx.author)))
        await main_mod.rmfruta.callback(staff_ctx, busca_fruta="hana hana")
        assert "Hana Hana no Mi" not in [f["nome"] for f in cog._fetch_sync()]

    async def test_rmfruta_sem_confirmacao_nao_remove(self, main_mod, staff_ctx, cog_registrado, frutas_basicas):
        cog, _ = await cog_registrado(frutas_basicas)  # wait_for padrão = timeout
        await main_mod.rmfruta.callback(staff_ctx, busca_fruta="hana hana")
        assert len(cog._fetch_sync()) == 7
        assert "cancelada" in staff_ctx.send.return_value.edit.await_args.kwargs["content"]

    async def test_rmfruta_ambigua_lista_opcoes(self, main_mod, staff_ctx, cog_registrado, frutas_basicas):
        cog, _ = await cog_registrado(frutas_basicas)
        await main_mod.rmfruta.callback(staff_ctx, busca_fruta="no mi")
        assert "Seja mais específico" in staff_ctx.send.await_args.args[0]
        assert len(cog._fetch_sync()) == 7

    async def test_rmfruta_nao_achou(self, main_mod, staff_ctx, cog_registrado, frutas_basicas):
        await cog_registrado(frutas_basicas)
        await main_mod.rmfruta.callback(staff_ctx, busca_fruta="inexistente")
        assert "Não achei" in staff_ctx.send.await_args.args[0]

    async def test_diagnostico_aponta_rank_invalido_e_linhas_acima(self, main_mod, staff_ctx, cog_registrado):
        v = tabela(("C", 1, "Boa", ""), ("Z", 2, "Rank Estranho", ""), linhas_antes=[["TÍTULO"]])
        await cog_registrado(v)
        await main_mod.diagnostico.callback(staff_ctx)
        emb = staff_ctx.send.await_args.kwargs["embed"]
        texto = " ".join(f.name + f.value for f in emb.fields)
        assert "Rank Estranho" in texto and "ACIMA" in texto and "total `2`" in texto

    async def test_enc_avisa_de_rank_invalido(self, main_mod, cog_factory, ctx):
        cog, _ = cog_factory(tabela(("C", 1, "Boa", ""), ("Z", 2, "Estranha", "")))
        await cog.enc.callback(cog, ctx, busca=None)
        assert "diagnostico" in ctx.send.await_args.kwargs["embed"].description
