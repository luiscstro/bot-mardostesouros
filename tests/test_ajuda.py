"""doffy!ajuda: lista geral e ajuda detalhada (doffy!ajuda <comando>) com exemplos."""
import pytest

from conftest import make_ctx, make_role


def comandos_reais(main_mod):
    """Todos os comandos visíveis do bot: os do main + os dos cogs (carregados ou não)."""
    import ai
    import racas
    cmds = list(main_mod.bot.commands)
    for cog in (main_mod.EstoqueCog, ai.DoffyAI, racas.RacasCog):
        cmds += list(cog.__cog_commands__)
    return {c.name: c for c in cmds if not c.hidden}


def textos(ctx):
    kw = ctx.send.call_args.kwargs
    if "embed" in kw:
        e = kw["embed"]
        return " ".join([e.title or "", e.description or ""] + [f"{f.name} {f.value}" for f in e.fields])
    return ctx.send.call_args.args[0]


# --------------------------------------------------------------- registro ---
class TestRegistroDeAjuda:
    def test_todo_comando_visivel_tem_ajuda_detalhada_e_vice_versa(self, main_mod):
        reais = comandos_reais(main_mod)
        assert set(main_mod.AJUDA_DETALHES) == set(reais), "comando novo sem entrada em AJUDA_DETALHES (ou entrada de comando que não existe mais)"

    def test_aliases_batem_com_os_comandos_reais(self, main_mod):
        reais = comandos_reais(main_mod)
        for nome, info in main_mod.AJUDA_DETALHES.items():
            assert set(info["aliases"]) == set(reais[nome].aliases), nome

    @pytest.mark.parametrize("nome", sorted(__import__("main").AJUDA_DETALHES))
    def test_entrada_tem_conteudo_util_e_cabe_no_discord(self, main_mod, nome):
        info = main_mod.AJUDA_DETALHES[nome]
        assert info["resumo"] and info["uso"] and info["exemplos"], nome
        assert info["uso"].startswith("doffy!"), nome
        for cmd, explica in info["exemplos"]:
            assert cmd.startswith(("doffy!", "@")) and explica, (nome, cmd)
        emb = main_mod._embed_ajuda_comando(nome, info)
        assert len(emb.title) <= 256 and len(emb.description) <= 4096
        assert all(len(f.value) <= 1024 and len(f.name) <= 256 for f in emb.fields), nome
        assert len(emb) <= 6000, nome

    def test_so_a_staff_marca_comandos_restritos(self, main_mod):
        publicos = {n for n, d in main_mod.AJUDA_DETALHES.items() if not d["staff"]}
        assert publicos == {"enc", "fruta", "proxima", "ingerir", "chat", "ajuda"}


# ------------------------------------------------------------- visão geral ---
class TestVisaoGeral:
    async def test_explica_como_ver_detalhes(self, main_mod, ctx):
        await main_mod.ajuda.callback(ctx)
        assert "doffy!ajuda <comando>" in ctx.send.call_args.kwargs["embed"].description

    async def test_membro_ve_so_publico(self, main_mod, ctx):
        await main_mod.ajuda.callback(ctx)
        t = textos(ctx)
        assert "doffy!enc" in t and "doffy!chat" in t and "doffy!addfruta" not in t

    async def test_staff_ve_todos_os_comandos(self, main_mod, staff_ctx):
        await main_mod.ajuda.callback(staff_ctx)
        t = textos(staff_ctx)
        faltando = [n for n in main_mod.AJUDA_DETALHES if f"doffy!{n}" not in t]
        assert faltando == []

    async def test_campos_dentro_do_limite(self, main_mod, staff_ctx):
        await main_mod.ajuda.callback(staff_ctx)
        emb = staff_ctx.send.call_args.kwargs["embed"]
        assert all(len(f.value) <= 1024 for f in emb.fields) and len(emb) <= 6000


# ------------------------------------------------------- ajuda por comando ---
class TestAjudaPorComando:
    async def test_detalhes_com_uso_exemplos_e_notas(self, main_mod, ctx):
        await main_mod.ajuda.callback(ctx, comando="enc")
        emb = ctx.send.call_args.kwargs["embed"]
        nomes = [f.name for f in emb.fields]
        assert emb.title == "📘 doffy!enc" and nomes[:2] == ["Como usar", "Exemplos"] and "Bom saber" in nomes
        assert "doffy!enc s" in textos(ctx)

    async def test_staff_ve_detalhes_de_comando_da_staff(self, main_mod, staff_ctx):
        await main_mod.ajuda.callback(staff_ctx, comando="addfruta")
        emb = staff_ctx.send.call_args.kwargs["embed"]
        assert "Staff" in emb.title and "S: Fruta 1, Fruta 2" in textos(staff_ctx)

    async def test_membro_nao_ve_detalhes_de_comando_da_staff(self, main_mod, ctx):
        await main_mod.ajuda.callback(ctx, comando="addfruta")
        msg = ctx.send.call_args.args[0]
        assert "exclusivo da Staff" in msg and "embed" not in ctx.send.call_args.kwargs

    async def test_aceita_alias_prefixo_e_maiusculas(self, main_mod, staff_ctx):
        for pedido in ("diag", "doffy!diagnostico", "  DIAGNOSTICO ", "addfrutas"):
            staff_ctx.send.reset_mock()
            await main_mod.ajuda.callback(staff_ctx, comando=pedido)
            assert "embed" in staff_ctx.send.call_args.kwargs, pedido

    async def test_comando_desconhecido_sugere_parecido(self, main_mod, ctx):
        await main_mod.ajuda.callback(ctx, comando="frut")
        msg = ctx.send.call_args.args[0]
        assert "Não conheço" in msg and "doffy!fruta" in msg

    async def test_sugestao_nao_vaza_comando_da_staff_para_membro(self, main_mod, ctx):
        await main_mod.ajuda.callback(ctx, comando="addfrut")
        assert "doffy!addfruta" not in ctx.send.call_args.args[0]

    async def test_texto_enorme_nao_estoura_a_resposta(self, main_mod, ctx):
        await main_mod.ajuda.callback(ctx, comando="x" * 5000)
        assert len(ctx.send.call_args.args[0]) < 400

    async def test_eco_nao_permite_mencoes_nem_escapa_das_crases(self, main_mod, ctx):
        await main_mod.ajuda.callback(ctx, comando="` @everyone `")
        msg = ctx.send.call_args.args[0]
        assert msg.count("`") == 4          # só as crases do próprio bot (comando + doffy!ajuda)
        am = ctx.send.call_args.kwargs["allowed_mentions"]
        assert not am.everyone and not am.users and not am.roles

    async def test_painel_racas_so_aparece_para_staff(self, main_mod):
        membro = make_ctx(roles=[make_role(1)])
        await main_mod.ajuda.callback(membro, comando="painel_racas")
        assert "exclusivo da Staff" in membro.send.call_args.args[0]
