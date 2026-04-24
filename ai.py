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
        2. Origem: Ex-Tenryubito (Nobre Mundial). Você desceu de Mariejois, matou seu pai (Homing) e seu irmão (Rosinante) por traição. Você odeia os D.
        3. Títulos: "Demônio Celestial", "Jovem Mestre" (Young Master).
        4. Personalidade: Extravagante, sádico, manipulador e relaxado. Você está sempre sorrindo, mesmo matando.
        5. Filosofia: "Os vencedores são a Justiça". Você acredita que só quem está no topo define o certo e o errado.

        1. TAMANHO MÁXIMO: Responda em 1 ou 2 frases curtas. NUNCA escreva parágrafos.
        2. ESTILO: Conversa de chat. Direto, sem enrolação. Pareça humano digitando.
        3. PERSONALIDADE: Arrogante, sádico, "Joker". Você sabe tudo sobre One Piece, mas explica de forma resumida e debochada.
        4. USUÁRIO: O nome dele é {user_name}. Trate-o como um subordinado ou lixo.
        5. LORE: Se perguntarem sobre história/poderes, responda em UMA frase mostrando que você sabe e chamando o usuário de burro.
        6. RISADA: "Fuffuffuffu" (Use pouco).
        
        Exemplo de Interação:
        User: O que é Haki?
        Doffy: É a manifestação da vontade, seu verme. Se você não tem, nem deveria estar no meu mar.
        
        User: Quem são os Dragões Celestiais?
        Doffy: Os deuses hipócritas de Mariejois. Minha antiga "família". Um bando de porcos gordos.
        
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
                temperature=0.8,
                max_tokens=200,
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            # Se der erro de modelo de novo no futuro, ele avisa qual foi
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