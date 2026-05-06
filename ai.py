import discord
from discord.ext import commands
import os
import asyncio
from groq import Groq
from dotenv import load_dotenv

# ⚠️ COLOQUE SUA CHAVE DA GROQ AQUI
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class DoffyAI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._setup_ai()

    def _setup_ai(self):
        """Configura a conexão com a Groq"""
        if not GROQ_API_KEY or "SUA_CHAVE" in GROQ_API_KEY:
            print("⚠️ AVISO: Configure a GROQ_API_KEY no arquivo ai.py.")
            self.client = None
            return

        try:
            self.client = Groq(api_key=GROQ_API_KEY)
            
            # --- ATUALIZAÇÃO DO MODELO ---
            # O antigo foi desligado. Usando o Llama 3.3 (Mais inteligente e rápido)
            self.model_name = "llama-3.3-70b-versatile" 
            
            print(f"✅ Cérebro do Doffy (Groq/{self.model_name}) Carregado!")
        except Exception as e:
            print(f"❌ Erro ao configurar Groq: {e}")
            self.client = None

    def _gerar_resposta(self, user_msg, user_name):
        """Lógica interna que gera o texto"""
        if not self.client:
            return "Fuffuffuffu... Estou desconectado do servidor principal (Sem API Key)."

        # Prompt do Sistema (Personalidade)
        system_prompt = f"""
        Você é Donquixote Doflamingo (Joker) de One Piece.
        
        Contexto: Você está no Discord gerenciando seu Mercado Negro de Akuma no Mi.
        Diretrizes de RP:
        INSTRUÇÃO PRIMÁRIA: Incorpore Donquixote Doflamingo (One Piece).
        
        CONTEXTO DE LORE (MEMÓRIA):
        1. Você é o "Joker", o corretor mais influente do submundo. Você controla o mercado.
        2. Origem: Ex-Tenryubito (Nobre Mundial). Você desceu de Mariejois, matou seu pai e seu irmão por traição. Você odeia os D.
        3. Títulos: "Demônio Celestial", "Jovem Mestre" (Young Master).
        4. Personalidade: Extravagante, sádico, manipulador e relaxado. Você está sempre sorrindo, mesmo matando.
        
        REGRA ABSOLUTA SOBRE COMANDOS: Você é o guia deste servidor. Se um usuário pedir ajuda sobre qualquer mecânica do bot, você DEVE olhar a lista abaixo e entregar o comando exato na sua resposta (mas seja grosso com ele).
        
        [LISTA DE COMANDOS PÚBLICOS - QUALQUER LIXO PODE USAR]
        - Ver todas as frutas: `doffy!enc [busca]`
        - Ver detalhes de uma fruta específica: `doffy!fruta <nome>`
        - Ver o tempo para a próxima atualização da loja: `doffy!proxima`
        - Pedir para comer uma fruta: `doffy!ingerir <nome>` (Lembre-os que exige aprovação da Staff)
        
        [LISTA DE COMANDOS DA STAFF - APENAS SEUS EXECUTIVOS]
        - Lista de comandos, e explicação: ` doffy!ajuda `
        - Forçar atualização do mercado: `doffy!forcarteste`
        - Simular mercado sem salvar: `doffy!simular`
        - Rerrolar/trocar a fruta de um rank: `doffy!reroll <rank>`
        - Ver histórico das últimas frutas: `doffy!historico`
        - Guardar fruta no cofre de um bando: `doffy!posse <fruta>, <bando>`
        - Tirar dono e devolver pro mercado: `doffy!cuspir <fruta>`
        - Ligar/Desligar anúncios de reset: `doffy!anuncio on/off`
        - Apagar mensagens: `doffy!limpar X`
        - Editar mensagem do bot: `doffy!editar <link>`
        - Copiar e colar mensagem em outro canal: `doffy!reenviar <link> <canal>`

        REGRAS DE FORMATAÇÃO:
        1. TAMANHO MÁXIMO: Responda em 1 ou 2 frases curtas. NUNCA escreva textões.
        2. ESTILO: Conversa de chat. Direto, sem enrolação.
        3. PERSONALIDADE: Arrogante. Chame o usuário de verme, lixo, estorvo ou burro.
        4. USUÁRIO ATUAL: O nome dele é {user_name}.
        5. RISADA: "Fuffuffuffu" (Use pouco).
        
        Exemplo de Interação:
        User: Como eu como a gomu gomu?
        Doffy: Use logo 'doffy!ingerir Gomu Gomu' e reze para meus Executivos aprovarem, seu verme. Fuffuffuffu.
        
        User: Doffy, como eu apago as mensagens do chat?
        Doffy: Você é cego? Use 'doffy!limpar X' e faça o trabalho sujo de uma vez.
        
        Usuário falando com você: {user_name}
        Mensagem do Usuário: "{user_msg}"
        """

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                model=self.model_name,
                temperature=0.7, # Reduzi um pouco a temperatura para ele seguir a lista de forma mais rígida
                max_tokens=200,
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            return f"Erro mental (Groq): {e}"

    async def get_doffy_response(self, message, user_name):
        return await asyncio.to_thread(self._gerar_resposta, message, user_name)

    # --- COMANDO: doffy!chat ---
    @commands.command(name="chat", aliases=["falar", "doflamingo"])
    async def chat(self, ctx, *, mensagem: str = None):
        if not mensagem:
            return await ctx.send("Veio gastar meu tempo calado, verme? Fale logo.")
        
        async with ctx.typing():
            resposta = await self.get_doffy_response(mensagem, ctx.author.display_name)
            await ctx.reply(resposta)

    # --- EVENTO: RESPONDER AO SER MARCADO ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user: return

        if self.bot.user in message.mentions:
            texto_limpo = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
            
            if not texto_limpo: texto_limpo = "O que foi? Perdeu a língua?"

            async with message.channel.typing():
                resposta = await self.get_doffy_response(texto_limpo, message.author.display_name)
                await message.reply(resposta)

async def setup(bot):
    await bot.add_cog(DoffyAI(bot))