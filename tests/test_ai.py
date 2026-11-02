"""Módulo de IA (ai.py): configuração do Groq, geração de resposta, comando chat e menções."""
import importlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from conftest import make_ctx


@pytest.fixture
def ai(monkeypatch):
    import ai as ai_mod
    importlib.reload(ai_mod)
    return ai_mod


def cog_com_cliente(ai, resposta="Fuffuffuffu, verme."):
    cog = ai.DoffyAI.__new__(ai.DoffyAI)
    cog.bot = MagicMock()
    cog.model_name = "llama-3.3-70b-versatile"
    cog.client = MagicMock()
    cog.client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content=resposta))]
    return cog


class TestSetup:
    def test_sem_chave_desativa_cliente(self, ai, monkeypatch, capsys):
        monkeypatch.setattr(ai, "GROQ_API_KEY", None)
        cog = ai.DoffyAI(MagicMock())
        assert cog.client is None
        assert "AVISO" in capsys.readouterr().out

    def test_chave_placeholder_e_tratada_como_ausente(self, ai, monkeypatch):
        monkeypatch.setattr(ai, "GROQ_API_KEY", "COLE_SUA_CHAVE_AQUI")
        assert ai.DoffyAI(MagicMock()).client is None

    def test_chave_valida_cria_cliente_e_modelo(self, ai, monkeypatch):
        groq = MagicMock()
        monkeypatch.setattr(ai, "GROQ_API_KEY", "gsk_teste")
        monkeypatch.setattr(ai, "Groq", groq)
        cog = ai.DoffyAI(MagicMock())
        groq.assert_called_once_with(api_key="gsk_teste")
        assert cog.client is groq.return_value and cog.model_name == "llama-3.3-70b-versatile"

    def test_erro_ao_criar_cliente_nao_derruba_o_bot(self, ai, monkeypatch, capsys):
        monkeypatch.setattr(ai, "GROQ_API_KEY", "gsk_teste")
        monkeypatch.setattr(ai, "Groq", MagicMock(side_effect=RuntimeError("x")))
        assert ai.DoffyAI(MagicMock()).client is None
        assert "Erro ao configurar Groq" in capsys.readouterr().out

    async def test_setup_registra_o_cog(self, ai, monkeypatch):
        monkeypatch.setattr(ai, "GROQ_API_KEY", None)
        bot = MagicMock(); bot.add_cog = AsyncMock()
        await ai.setup(bot)
        assert isinstance(bot.add_cog.call_args.args[0], ai.DoffyAI)


class TestGerarResposta:
    def test_sem_cliente_responde_sem_api_key(self, ai):
        cog = ai.DoffyAI.__new__(ai.DoffyAI); cog.client = None
        assert "Sem API Key" in cog._gerar_resposta("oi", "Luis")

    def test_retorna_texto_do_modelo(self, ai):
        assert cog_com_cliente(ai, "Resposta X")._gerar_resposta("oi", "Luis") == "Resposta X"

    def test_envia_modelo_system_e_user(self, ai):
        cog = cog_com_cliente(ai)
        cog._gerar_resposta("como como a gomu gomu?", "Luis")
        kw = cog.client.chat.completions.create.call_args.kwargs
        assert kw["model"] == "llama-3.3-70b-versatile"
        assert kw["max_tokens"] == 200 and 0 <= kw["temperature"] <= 1
        assert kw["messages"][0]["role"] == "system" and "Luis" in kw["messages"][0]["content"]
        assert kw["messages"][1] == {"role": "user", "content": "como como a gomu gomu?"}

    def test_erro_da_api_vira_mensagem_em_personagem(self, ai):
        cog = cog_com_cliente(ai)
        cog.client.chat.completions.create.side_effect = RuntimeError("rate limit")
        assert cog._gerar_resposta("oi", "Luis").startswith("Erro mental (Groq)")

    def test_prompt_lista_todos_os_comandos_documentados_do_bot(self, ai, main_mod):
        """Se um comando público/staff novo for criado, o prompt precisa ensinar a IA."""
        cog = cog_com_cliente(ai)
        cog._gerar_resposta("oi", "x")
        prompt = cog.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        # comandos que o prompt deve conhecer (os mesmos listados no doffy!ajuda)
        for nome in ["enc", "fruta", "proxima", "ingerir", "ajuda", "forcarteste", "simular",
                     "reroll", "historico", "posse", "cuspir", "anuncio", "limpar", "editar", "reenviar"]:
            assert f"doffy!{nome}" in prompt, nome
            assert nome in {c.name for c in main_mod.bot.commands} | {"enc", "fruta"}

    def test_nome_com_aspas_e_chaves_nao_quebra_o_prompt(self, ai):
        cog = cog_com_cliente(ai)
        assert cog._gerar_resposta('he said "{oi}" {}', 'N"o{m}e') == "Fuffuffuffu, verme."

    async def test_get_doffy_response_nao_bloqueia_o_loop(self, ai):
        assert await cog_com_cliente(ai, "ok").get_doffy_response("oi", "x") == "ok"


class TestComandoChat:
    async def test_sem_mensagem_pede_para_falar(self, ai):
        ctx = make_ctx()
        await cog_com_cliente(ai).chat.callback(cog_com_cliente(ai), ctx, mensagem=None)
        assert "Fale logo" in ctx.send.call_args.args[0]

    async def test_responde_com_reply(self, ai):
        cog = cog_com_cliente(ai, "Cale-se.")
        ctx = make_ctx(author_name="Luis")
        await cog.chat.callback(cog, ctx, mensagem="oi")
        ctx.reply.assert_awaited_once_with("Cale-se.")

    def test_aliases(self, ai):
        assert set(ai.DoffyAI.chat.aliases) == {"falar", "doflamingo"}


class TestOnMessage:
    def _msg(self, bot, content, mentions=(), autor=None):
        m = MagicMock()
        m.content = content
        m.mentions = list(mentions)
        m.author = autor or MagicMock(display_name="Luis")
        m.reply = AsyncMock()
        typing = MagicMock(); typing.__aenter__ = AsyncMock(); typing.__aexit__ = AsyncMock(return_value=False)
        m.channel.typing = MagicMock(return_value=typing)
        return m

    async def test_ignora_as_proprias_mensagens(self, ai):
        cog = cog_com_cliente(ai); cog.bot.user = MagicMock(id=1)
        # o bot se marcando a si mesmo: sem a guarda, ele responderia em loop infinito
        m = self._msg(cog.bot, "<@1> oi", mentions=[cog.bot.user], autor=cog.bot.user)
        await cog.on_message(m)
        m.reply.assert_not_awaited()

    async def test_ignora_mensagem_sem_mencao(self, ai):
        cog = cog_com_cliente(ai); cog.bot.user = MagicMock(id=1)
        m = self._msg(cog.bot, "oi gente", mentions=[])
        await cog.on_message(m)
        m.reply.assert_not_awaited()

    async def test_responde_quando_marcado_e_remove_a_mencao_do_texto(self, ai):
        cog = cog_com_cliente(ai, "Fuffuffuffu"); cog.bot.user = MagicMock(id=42)
        cog.get_doffy_response = AsyncMock(return_value="Fuffuffuffu")
        m = self._msg(cog.bot, "<@42> qual fruta?", mentions=[cog.bot.user])
        await cog.on_message(m)
        cog.get_doffy_response.assert_awaited_once_with("qual fruta?", "Luis")
        m.reply.assert_awaited_once_with("Fuffuffuffu")

    async def test_so_mencao_usa_frase_padrao(self, ai):
        cog = cog_com_cliente(ai); cog.bot.user = MagicMock(id=42)
        cog.get_doffy_response = AsyncMock(return_value="x")
        m = self._msg(cog.bot, "<@42>", mentions=[cog.bot.user])
        await cog.on_message(m)
        assert "Perdeu a língua" in cog.get_doffy_response.call_args.args[0]
