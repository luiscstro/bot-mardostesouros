import discord
from discord.ext import tasks, commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import random
import json
import os
import datetime
import math
import asyncio
import re
import io
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURAÇÕES ---
ID_CANAL_C = 1294115103741841420
ID_CANAL_B = 1294115141608017920
ID_CANAL_A = 1294115193881755658

CAMINHO_JSON = "bot-discord-470223-41527625dc96.json"
NOME_PLANILHA = "Lista das Akuma no Mi - Mar dos Tesouros"
ABA_PLANILHA = "Teste"
ARQUIVO_MSGS = "mensagens.json"

TOKEN = os.getenv("DISCORD_TOKEN")

CARGOS_PERMITIDOS = [1227977596671885393, 1222232432527413389, 1415428289954054234, 1405643389105606767]

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="doffy!", intents=intents, help_command=None)

# --- GOOGLE SHEETS ---
class EstoqueCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sheet = None
        self.scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets', "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        self.connect_gsheets()

    def connect_gsheets(self):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(CAMINHO_JSON, self.scope)
            client = gspread.authorize(creds)
            self.sheet = client.open(NOME_PLANILHA).worksheet(ABA_PLANILHA)
            print("✅ GSheets Conectado!")
            return True
        except Exception as e:
            print(f"❌ Erro GSheets: {e}")
            self.sheet = None
            return False

    def _fetch_sync(self):
        if not self.sheet: self.connect_gsheets()
        try:
            data = self.sheet.get_all_values()
            if not data: return []
            
            idx_head = 0
            for i, r in enumerate(data):
                r_low = [str(c).lower() for c in r]
                if "rank" in r_low and "nome" in r_low:
                    idx_head = i
                    break
            
            head = [h.lower().strip() for h in data[idx_head]]
            rows = data[idx_head+1:]
            
            i_rank = head.index("rank") if "rank" in head else 0
            i_nome = head.index("nome") if "nome" in head else 2
            i_stat = head.index("status") if "status" in head else 4
            i_num = 1
            for x in ["n°", "nº", "numero", "num"]:
                if x in head: 
                    i_num = head.index(x)
                    break

            frutas = []
            for r in rows:
                if not any(r): continue
                if len(r) <= max(i_rank, i_nome, i_stat, i_num): r += [""] * 10
                
                raw_num = r[i_num].strip()
                num_match = re.search(r'\d+', raw_num)
                clean_num = num_match.group() if num_match else raw_num

                frutas.append({
                    "rank": r[i_rank].strip().upper(),
                    "numero": clean_num, 
                    "nome": r[i_nome].strip(),
                    "status": r[i_stat].strip().lower()
                })
            return frutas
        except Exception as e:
            print(f"Erro leitura: {e}")
            return []

    async def get_frutas(self):
        return await asyncio.to_thread(self._fetch_sync)

    async def disponiveis(self, rank):
        all_f = await self.get_frutas()
        return [f['nome'] for f in all_f if f['rank'] == rank and not f['status'].strip()]
    
    @commands.command(name="enc")
    async def enc(self, ctx, *, busca: str = None):
        try: 
            fs = await self.get_frutas()
        except: 
            return await ctx.send("Erro ao ler planilha.")
        
        tot = {"C":0, "B":0, "A":0, "S":0}
        for f in fs: 
            if f['rank'] in tot: tot[f['rank']] += 1
            
        resumo = f"📊 **Frutas Existentes**\nC: `{tot['C']}` | B: `{tot['B']}` | A: `{tot['A']}` | S: `{tot['S']}`"

        if busca:
            b_raw = busca.lower().strip()
            b_clean = b_raw.replace(" ", "")
            
            if b_raw in ["c", "b", "a", "s"]:
                fs = [f for f in fs if f['rank'].lower() == b_raw]
            else:
                fs = [f for f in fs if 
                      b_clean in f['nome'].lower().replace(" ", "") or 
                      b_clean in f['rank'].lower() or 
                      b_clean in f['numero'] or 
                      b_clean == f"{f['rank'].lower()}{f['numero']}"]
        
        if not fs: return await ctx.send("❌ Nenhuma fruta encontrada.")

        peso_rank = {"C": 1, "B": 2, "A": 3, "S": 4}
        def sort_key(f):
            try: num = int(f['numero'])
            except: num = 99999
            return (peso_rank.get(f['rank'], 99), num)
        
        fs.sort(key=sort_key)

        por_rank = {"C":[], "B":[], "A":[], "S":[]}
        for f in fs:
            r = f['rank']
            if r in por_rank: por_rank[r].append(f)

        pages = []
        cor_rank = {"C": 0x57F287, "B": 0x3498DB, "A": 0xE74C3C, "S": 0x9B59B6}
        
        for r in ["C", "B", "A", "S"]:
            lista = por_rank[r]
            if not lista: continue
            total_p = math.ceil(len(lista)/6)
            for i in range(total_p):
                titulo = f"📖 Enciclopédia - Rank {r} ({i+1}/{total_p})"
                if busca and busca.lower() in ["c", "b", "a", "s"]:
                    titulo = f"📦 Lista Completa - Rank {r} ({i+1}/{total_p})"

                emb = discord.Embed(title=titulo, description=resumo, color=cor_rank.get(r, 0xFFFFFF))
                
                for item in lista[i*6:(i+1)*6]:
                    status_celula = item['status'].strip()
                    if not status_celula:
                        icon = "🟢"
                        status_txt = "Disponível"
                    else:
                        icon = "⚫"
                        status_txt = status_celula.capitalize() 

                    emb.add_field(
                        name=f"{icon} #{item['numero']} {item['nome']}", 
                        value=f"**Status:** {status_txt}", 
                        inline=False
                    )
                pages.append(emb)

        msg = await ctx.send(embed=pages[0])
        
        if len(pages) > 1:
            await msg.add_reaction("◀️")
            await msg.add_reaction("▶️")
            
            def check(react, user):
                return user == ctx.author and str(react.emoji) in ["◀️", "▶️"] and react.message.id == msg.id
            
            curr = 0
            while True:
                try:
                    react, user = await bot.wait_for("reaction_add", timeout=60, check=check)
                    if str(react.emoji) == "▶️" and curr < len(pages)-1: curr += 1
                    elif str(react.emoji) == "◀️" and curr > 0: curr -= 1
                    
                    await msg.edit(embed=pages[curr])
                    try: await msg.remove_reaction(react, user)
                    except: pass
                except asyncio.TimeoutError: break

    @commands.command(name="fruta")
    async def fruta(self, ctx, *, busca: str):
        try: 
            fs = await self.get_frutas()
        except: 
            return await ctx.send("Erro ao ler dados.")
        
        b = busca.lower().replace(" ", "")
        achou = next((f for f in fs if 
                      b in f['nome'].lower().replace(" ", "") or 
                      b == f['numero'] or 
                      b == f"{f['rank'].lower()}{f['numero']}"
                      ), None)
        
        if not achou: 
            return await ctx.send(f"❌ Não achei nenhuma fruta com `{busca}`.")
        
        status_celula = achou['status'].strip()
        
        if not status_celula:
            status_txt = "Disponível"
            cor_embed = 0x57F287
            icon = "🟢"
        else:
            status_txt = status_celula.capitalize()
            cor_embed = 0x2B2D31
            icon = "⚫"

        emb = discord.Embed(
            title=f"{icon} {achou['nome']}", 
            color=cor_embed
        )
        emb.add_field(name="Rank", value=f"**{achou['rank']}**", inline=True)
        emb.add_field(name="Nº", value=f"**{achou['numero']}**", inline=True)
        emb.add_field(name="Status", value=status_txt, inline=False)
        
        await ctx.send(embed=emb)

    @commands.command(name="check_pool")
    async def check_pool(self, ctx):
        if not ctx.author.roles or not any(r.id in CARGOS_PERMITIDOS for r in ctx.author.roles):
            return await ctx.send("❌ Você não tem permissão para usar este comando.")

        try:
            await ctx.send("🔍 Analisando pool de frutas na planilha... Aguarde.")
            todas_as_frutas = await self.get_frutas()
            if not todas_as_frutas:
                return await ctx.send("⚠️ A planilha parece estar vazia ou não foi carregada corretamente.")
        except Exception as e:
            return await ctx.send(f"❌ Erro ao acessar os dados: {e}")

        pool = {"C": [], "B": [], "A": [], "S": []}
        for f in todas_as_frutas:
            rank = f['rank'].upper()
            status = f['status'].strip()
            if not status and rank in pool:
                pool[rank].append(f['nome'])

        total_pool = sum(len(lista) for lista in pool.values())

        embed = discord.Embed(
            title="🛠️ Pool de Sorteio (Disponíveis)",
            description=(
                f"Estas são as frutas que podem aparecer na atualização semanal.\n"
                f"Para uma fruta sair desta lista, escreva qualquer coisa na coluna **Status** do Excel.\n\n"
                f"Total disponível: **{total_pool}**"
            ),
            color=0x3498DB
        )

        for rank, lista in pool.items():
            if lista:
                texto_lista = ", ".join(lista)
                if len(texto_lista) > 1000:
                    texto_lista = texto_lista[:997] + "..."
                embed.add_field(name=f"Rank {rank} ({len(lista)} frutas)", value=f"```\n{texto_lista}\n```", inline=False)
            else:
                embed.add_field(name=f"Rank {rank}", value="*⚠️ Nenhuma fruta disponível neste rank!*", inline=False)

        await ctx.send(embed=embed)

# --- SISTEMA DE LOJA E SAVE ---
msg_ids = {"C": None, "B": None, "A": None}
announce_on = True

def save():
    dados = {
        "C": msg_ids["C"],
        "B": msg_ids["B"],
        "A": msg_ids["A"],
        "announce_enabled": announce_on
    }
    try:
        with open(ARQUIVO_MSGS, "w") as f: 
            json.dump(dados, f, indent=4)
    except Exception as e:
        print(f"Erro ao salvar JSON: {e}")

def load():
    global msg_ids, announce_on
    if os.path.exists(ARQUIVO_MSGS):
        try:
            with open(ARQUIVO_MSGS, "r") as f:
                d = json.load(f)
                msg_ids["C"] = d.get("C")
                msg_ids["B"] = d.get("B")
                msg_ids["A"] = d.get("A")
                announce_on = d.get("announce_enabled", True)
        except Exception as e: 
            print(f"Erro ao carregar JSON: {e}")

def is_staff(ctx):
    if not ctx.author.roles: return False
    return any(r.id in CARGOS_PERMITIDOS for r in ctx.author.roles)

def get_msg_content(rank, nome):
    config = {
        "C": {"precos": ("30.000.000", "60.000.000"), "emoji": "🍐"},
        "B": {"precos": ("150.000.000", "300.000.000"), "emoji": "🍇"},
        "A": {"precos": ("800.000.000", "1.600.000.000"), "emoji": "🍎"}
    }
    
    dados = config.get(rank, {"precos": ("???", "???"), "emoji": "🍒"})
    p_rand, p_anunc = dados["precos"]
    emoji_fruta = dados["emoji"]
    berry = "<:berry:1222990525372563539>"

    return f"""# **AKUMAS NO MI ({rank})** {emoji_fruta}

*Aqui poderá encontrar diversas frutas poderosas.*

▶️ **AKUMA ALEATÓRIA:** {p_rand}{berry}
▶️ **AKUMA ANUNCIADA:** {p_anunc}{berry}

🔸 Ao comprar, só haverá 2 jeitos de descobrir qual Akuma é: ou um Arqueólogo descobre ou um PJ deverá comê-la.
# 🍒 FRUTA ANUNCIADA
🔸 Todo Domingo será feita uma rolagem de Akuma e ficará aqui até a próxima semana.
# {nome}"""

frases = [
    "🦩 Fuffuffuffu... O Mercado Negro tem novidades! [Confira no salão principal](https://discord.com/channels/1220345032079572993/1294114646067904593)",
    "🦩 Fuffuffuffu... Remessa nova chegando no Submundo! [Confira no salão principal](https://discord.com/channels/1220345032079572993/1294114646067904593)",
    "🦩 Fuffuffuffu... O jogo mudou! Confiram as frutas! [Confira no salão principal](https://discord.com/channels/1220345032079572993/1294114646067904593)"
]
gifs = [
    "https://i.imgur.com/1mAZZnJ.gif",
    "https://i.imgur.com/XgTABvl.gif",
    "https://i.imgur.com/JST1arc.gif",
    "https://i.imgur.com/XnRfg2I.gif"
]
mentions = ["<@&1221255954708959324>", "<@&1283492761039011851>", "<@&1220345032079572995>", "<@&1221454578025762926>"]

async def run_update():
    global msg_ids
    print("🔄 Iniciando atualização das lojas...")
    cog = bot.get_cog("EstoqueCog")
    if not cog: return
    
    canais = {"C": ID_CANAL_C, "B": ID_CANAL_B, "A": ID_CANAL_A}
    load() 

    try:
        sorteadas = {}
        for r in ["C", "B", "A"]:
            lista = await cog.disponiveis(r)
            sorteadas[r] = random.choice(lista) if lista else "Esgotado"
            
            ch = bot.get_channel(canais[r])
            if not ch: 
                print(f"❌ Canal da Loja {r} não encontrado.")
                continue

            txt = get_msg_content(r, sorteadas[r])
            msg_resolvida = False 

            if msg_ids.get(r):
                try:
                    msg = await ch.fetch_message(msg_ids[r])
                    await msg.edit(content=txt)
                    msg_resolvida = True
                except discord.NotFound:
                    msg_ids[r] = None
                except discord.Forbidden:
                    continue
            
            if not msg_resolvida:
                msg = await ch.send(txt)
                msg_ids[r] = msg.id
                save() 
                print(f"✅ Nova mensagem criada Loja {r} (ID: {msg.id}).")
        
        print(f"✅ Atualização concluída: {sorteadas}")

        ch_anun = bot.get_channel(1220369299076808734)
        if ch_anun and announce_on:
            emb = discord.Embed(description=random.choice(frases), color=0x800080)
            emb.set_image(url=random.choice(gifs))
            await ch_anun.send(content=" ".join(mentions), embed=emb)

    except Exception as e:
        print(f"❌ Erro crítico update: {e}")

@tasks.loop(time=datetime.time(hour=15, minute=0, tzinfo=datetime.timezone.utc))
async def auto_update():
    if datetime.datetime.now(datetime.timezone.utc).weekday() == 6:
        await run_update()

# --- COMANDOS STAFF ---
@bot.command()
@commands.check(is_staff)
async def say(ctx, *, m):
    try: await ctx.message.delete()
    except: pass
    await ctx.send(m)

@bot.command()
@commands.check(is_staff)
async def forcarteste(ctx):
    await ctx.message.add_reaction("🔄")
    await run_update()
    await ctx.send("✅ Feito!", delete_after=5)

@bot.command()
@commands.check(is_staff)
async def anuncio(ctx, acao=None):
    global announce_on
    if acao == "on": announce_on = True
    elif acao == "off": announce_on = False
    save()
    await ctx.send(f"Anúncios: **{announce_on}**")

@bot.command()
@commands.check(is_staff)
async def reroll(ctx, rank: str, *, fruta: str = None):
    rank = rank.upper()
    if rank not in ["C", "B", "A"]: return
    
    cog = bot.get_cog("EstoqueCog")
    if not fruta:
        opts = await cog.disponiveis(rank)
        if not opts: return await ctx.send("Sem frutas.")
        fruta = random.choice(opts)
    
    load()
    ch = bot.get_channel({"C": ID_CANAL_C, "B": ID_CANAL_B, "A": ID_CANAL_A}[rank])
    txt = get_msg_content(rank, fruta)
    msg_resolvida = False
    
    if msg_ids.get(rank):
        try:
            m = await ch.fetch_message(msg_ids[rank])
            await m.edit(content=txt)
            msg_resolvida = True
        except discord.NotFound:
            pass 

    if not msg_resolvida:
        m = await ch.send(txt)
        msg_ids[rank] = m.id
        save()
    
    await ctx.message.add_reaction("✅")

@bot.command(name="limpar")
@commands.check(is_staff)
async def limpar(ctx, quantidade: int = 100):
    await ctx.channel.purge(limit=quantidade + 1)
    await ctx.send(f"🧹 Limpei as últimas {quantidade} mensagens.", delete_after=3)

@bot.command(name="editar")
@commands.check(is_staff)
async def editar(ctx, link_ou_id: str, *, novo_texto: str):
    try:
        converter = commands.MessageConverter()
        msg = await converter.convert(ctx, link_ou_id)
    except commands.MessageNotFound:
        return await ctx.send("❌ Não encontrei essa mensagem.")
    except Exception as e:
        return await ctx.send(f"❌ Erro ao buscar mensagem: {e}")

    if msg.author != bot.user:
        return await ctx.send("❌ Só edito minhas próprias mensagens.")

    try:
        await msg.edit(content=novo_texto)
        await ctx.message.delete()
        await ctx.send(f"✅ Mensagem editada!", delete_after=3)
    except Exception as e:
        await ctx.send(f"❌ Erro ao editar: {e}")

@bot.command(name="reenviar")
@commands.check(is_staff)
async def reenviar(ctx, link_msg: str, link_canal: str):
    try:
        converter_msg = commands.MessageConverter()
        msg_original = await converter_msg.convert(ctx, link_msg)
    except:
        return await ctx.send("❌ Não consegui ler a mensagem original.")

    canal_destino = None
    if "discord.com/channels/" in link_canal:
        try:
            canal_id = int(link_canal.split("/")[-1])
            canal_destino = bot.get_channel(canal_id)
        except: pass
    
    if not canal_destino:
        try:
            converter_canal = commands.TextChannelConverter()
            canal_destino = await converter_canal.convert(ctx, link_canal)
        except:
            return await ctx.send("❌ Canal destino inválido.")

    arquivos_para_enviar = []
    embeds_para_enviar = []

    async with ctx.typing():
        if msg_original.attachments:
            for anexo in msg_original.attachments:
                try:
                    dados = await anexo.read()
                    arquivos_para_enviar.append(discord.File(io.BytesIO(dados), filename=anexo.filename))
                except: pass

        for embed in msg_original.embeds:
            if embed.type == 'rich':
                embeds_para_enviar.append(embed)

    try:
        await canal_destino.send(
            content=msg_original.content,
            embeds=embeds_para_enviar,
            files=arquivos_para_enviar
        )
        await ctx.message.delete()
        await ctx.send(f"✅ Reenviado para {canal_destino.mention}!", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ Erro ao enviar: {e}")
         
# --- AJUDA E EVENTOS ---
@bot.command(name="ajuda")
async def ajuda(ctx):
    embed = discord.Embed(
        title="🧶 Guia do Doflamingo",
        description="Lista de comandos disponíveis.",
        color=discord.Color.dark_purple()
    )
    embed.add_field(name="📖 Público", value="`doffy!enc [busca]` → Vê todas as frutas.\n`doffy!fruta <nome>` → Detalhes de uma fruta.\n`doffy!proxima` → Tempo para atualização.", inline=False)
    
    if is_staff(ctx):
        embed.add_field(name="🔒 Staff", value="`doffy!forcarteste` → Força atualização.\n`doffy!reroll <rank>` → Rerrola mercado.\n`doffy!anuncio on/off` → Liga/Desliga anúncio.\n `doffy!limpar X` → Limpa mensagens. \n `doffy!editar <link>` → Edita uma mensagem do bot.\n `doffy!reenviar <link> <canal>` → Copia e cola mensagens.", inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def proxima(ctx):
    now = datetime.datetime.now(datetime.timezone.utc)
    target = now.replace(hour=15, minute=0, second=0, microsecond=0)
    days = 6 - now.weekday()
    if days < 0 or (days==0 and now > target): days += 7
    target += datetime.timedelta(days=days)
    diff = target - now
    d, s = diff.days, diff.seconds
    h, m = s//3600, (s%3600)//60
    await ctx.send(embed=discord.Embed(title="⏳ Próxima Atualização", description=f"Faltam: **{d}d {h}h {m}m**", color=0xFFD700))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"⚠️ Faltou algo! Use: `doffy!ajuda` para ver como usar.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("🚫 Sem permissão.")
    else:
        print(f"Erro: {error}")

# ==========================================
# NOVA FORMA SEGURA DE CARREGAR AS EXTENSÕES
# ==========================================
async def setup_hook():
    print("🔄 Carregando as engrenagens do Jovem Mestre...")
    
    # 1. Carrega o Cog do GSheets (Planilha)
    await bot.add_cog(EstoqueCog(bot))
    
    # 2. Carrega a Inteligência Artificial (ai.py)
    try:
        await bot.load_extension("ai")
        print("✅ Módulo de IA (ai.py) carregado!")
    except Exception as e:
        print(f"❌ Erro ao carregar IA: {e}")
        
    # 3. Carrega o Sistema de Raças (racas.py)
    try:
        await bot.load_extension("racas")
        print("✅ Módulo de Raças (racas.py) carregado!")
    except Exception as e:
        print(f"❌ Erro ao carregar Raças: {e}")

    # 4. Inicia a rotina semanal de atualização
    if not auto_update.is_running(): 
        auto_update.start()

# Anexa a configuração segura ao bot
bot.setup_hook = setup_hook

# O on_ready agora fica limpo e sem risco de duplicar as extensões
@bot.event
async def on_ready():
    load() # Carrega os IDs das mensagens salvas
    print(f"✅ Online no Discord: {bot.user}")

bot.run(TOKEN)