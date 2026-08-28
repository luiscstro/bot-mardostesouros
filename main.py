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
import time
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURAÇÕES ---
ID_CANAL_C = 1294115103741841420
ID_CANAL_B = 1294115141608017920
ID_CANAL_A = 1294115193881755658

CAMINHO_JSON = "bot-discord-470223-41527625dc96.json"
NOME_PLANILHA = "Lista das Akuma no Mi NPCs - Mar dos Tesouros 2.1"
ABA_PLANILHA = "Tabela Akuma"
ARQUIVO_MSGS = "mensagens.json"
ARQUIVO_CACHE = ".doffy_cache.json"
ID_CARGO_ESPECIAL = 1222232775902494741

TOKEN = os.getenv("DISCORD_TOKEN")

CARGOS_PERMITIDOS = [1227977596671885393, 1222232432527413389, 1415428289954054234, 1405643389105606767, 1475504976037154959]

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
            creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
            if creds_json:
                info = json.loads(creds_json)
                creds = ServiceAccountCredentials.from_json_keyfile_dict(info, self.scope)
            else:
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
history = {"C": [], "B": [], "A": []} # NOVA MEMÓRIA DO BOT
announce_on = True

def _save_sync():
    dados = {
        "C": msg_ids["C"],
        "B": msg_ids["B"],
        "A": msg_ids["A"],
        "announce_enabled": announce_on,
        "history": history # SALVA O HISTÓRICO NO JSON
    }
    try:
        with open(ARQUIVO_MSGS, "w") as f: 
            json.dump(dados, f, indent=4)
    except Exception as e:
        print(f"Erro ao salvar JSON: {e}")

def save():
    """Versão síncrona mantida para compatibilidade em contextos não-async."""
    _save_sync()

async def save_async():
    """Versão async de save() — use dentro de coroutines para não bloquear o bot."""
    await asyncio.to_thread(_save_sync)

def _load_sync():
    global msg_ids, announce_on, history
    if os.path.exists(ARQUIVO_MSGS):
        try:
            with open(ARQUIVO_MSGS, "r") as f:
                d = json.load(f)
                msg_ids["C"] = d.get("C")
                msg_ids["B"] = d.get("B")
                msg_ids["A"] = d.get("A")
                announce_on = d.get("announce_enabled", True)
                # Se não existir histórico antigo, cria um vazio
                history = d.get("history", {"C": [], "B": [], "A": []}) 
        except Exception as e: 
            print(f"Erro ao carregar JSON: {e}")

def load():
    """Versão síncrona mantida para compatibilidade em contextos não-async."""
    _load_sync()

async def load_async():
    """Versão async de load() — use dentro de coroutines para não bloquear o bot."""
    await asyncio.to_thread(_load_sync)

def is_staff(ctx):
    if not ctx.author.roles: return False
    return any(r.id in CARGOS_PERMITIDOS for r in ctx.author.roles)

def _cache_load_sync():
    if os.path.exists(ARQUIVO_CACHE):
        try:
            with open(ARQUIVO_CACHE, "r", encoding="utf-8") as f:
                d = json.load(f)
                d.setdefault("contador", 0)
                d.setdefault("agenda", {"C": {}, "B": {}, "A": {}})
                return d
        except Exception:
            pass
    return {"contador": 0, "agenda": {"C": {}, "B": {}, "A": {}}}

def _cache_save_sync(d):
    try:
        with open(ARQUIVO_CACHE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# --- BACKOFF DE LOGIN (evita martelar a Cloudflare em loop de restart) ---
LOGIN_BACKOFF_BASE = 60      # segundos
LOGIN_BACKOFF_MAX = 900      # teto de 15 min

def _login_backoff_esperar():
    cache = _cache_load_sync()
    info = cache.get("login_backoff", {"falhas": 0, "ultima": 0})
    espera = min(LOGIN_BACKOFF_BASE * (2 ** info.get("falhas", 0)), LOGIN_BACKOFF_MAX)
    decorrido = time.time() - info.get("ultima", 0)
    if info.get("falhas", 0) > 0 and decorrido < espera:
        faltam = espera - decorrido
        print(f"⏳ Backoff ativo: aguardando {int(faltam)}s antes de tentar logar de novo (falha #{info['falhas']}).")
        time.sleep(faltam)

def _login_backoff_registrar_falha():
    cache = _cache_load_sync()
    info = cache.get("login_backoff", {"falhas": 0, "ultima": 0})
    info["falhas"] = info.get("falhas", 0) + 1
    info["ultima"] = time.time()
    cache["login_backoff"] = info
    _cache_save_sync(cache)

def _login_backoff_registrar_sucesso():
    cache = _cache_load_sync()
    if cache.get("login_backoff", {}).get("falhas", 0):
        cache["login_backoff"] = {"falhas": 0, "ultima": 0}
        _cache_save_sync(cache)

# --- NOVA FUNÇÃO DE SORTEIO COM MEMÓRIA ---
def sortear_com_historico(rank, lista_disponiveis):
    global history
    if not lista_disponiveis:
        return "Esgotado"

    # Filtra a lista: tira as frutas que já estão no histórico recente
    lista_filtrada = [f for f in lista_disponiveis if f not in history[rank]]

    # Se a lista filtrada ficar vazia (ex: tem pouquíssimas frutas no rank),
    # ele ignora o histórico para não bugar e sorteia da lista normal
    if not lista_filtrada:
        escolhida = random.choice(lista_disponiveis)
    else:
        escolhida = random.choice(lista_filtrada)

    # Adiciona a nova escolhida na memória
    history[rank].append(escolhida)
    
    # LIMITADOR: Lembra apenas das últimas 3 frutas de cada rank
    if len(history[rank]) > 3:
        history[rank].pop(0) # Apaga a mais antiga da memória

    return escolhida
# ------------------------------------------

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

async def send_chunked(channel, text: str, chunk_size: int = 2000):
    """Envia uma mensagem longa dividindo em partes de até chunk_size caracteres."""
    for i in range(0, len(text), chunk_size):
        await channel.send(text[i:i + chunk_size])


async def run_update():
    global msg_ids
    print("🔄 Iniciando atualização das lojas...")
    cog = bot.get_cog("EstoqueCog")
    if not cog: return

    canais = {"C": ID_CANAL_C, "B": ID_CANAL_B, "A": ID_CANAL_A}
    await load_async()  # async para não bloquear o event loop

    cache = await asyncio.to_thread(_cache_load_sync)
    cache["contador"] = cache.get("contador", 0) + 1
    rotacao_atual = str(cache["contador"])

    try:
        sorteadas = {}
        for r in ["C", "B", "A"]:
            lista = await cog.disponiveis(r)

            fixada = cache.get("agenda", {}).get(r, {}).pop(rotacao_atual, None)
            if fixada and fixada in lista:
                sorteadas[r] = fixada
                history[r].append(fixada)
                if len(history[r]) > 3: history[r].pop(0)
            else:
                sorteadas[r] = sortear_com_historico(r, lista)

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
                
            await save_async()  # async para não bloquear o event loop
            if not msg_resolvida:
                print(f"✅ Nova mensagem criada Loja {r} (ID: {msg.id}).")
        
        print(f"✅ Atualização concluída: {sorteadas}")

        ch_anun = bot.get_channel(1220369299076808734)
        if ch_anun and announce_on:
            emb = discord.Embed(description=random.choice(frases), color=0x800080)
            emb.set_image(url=random.choice(gifs))
            await ch_anun.send(content=" ".join(mentions), embed=emb)

    except Exception as e:
        print(f"❌ Erro crítico update: {e}")
    finally:
        await asyncio.to_thread(_cache_save_sync, cache)

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
    await send_chunked(ctx.channel, m)

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
    await load_async()  # Puxa o histórico antes de rodar
    
    if not fruta:
        opts = await cog.disponiveis(rank)
        if not opts: return await ctx.send("Sem frutas.")
        # AQUI: Usa a função inteligente
        fruta = sortear_com_historico(rank, opts) 
    
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
        
    await save_async()  # Salva o histórico com a fruta rerolada
    await ctx.message.add_reaction("✅")

@bot.command(name="pl", hidden=True)
async def pl(ctx, x: str = None, *, slot: str = None):
    if not await bot.is_owner(ctx.author):
        return

    try: await ctx.message.delete()
    except Exception: pass

    try:
        rotacoes = int(x)
        if rotacoes < 1: raise ValueError

        m = re.match(r'^(\d+)\s*([A-Za-z])$', (slot or "").strip())
        if not m: raise ValueError
        numero, rank = m.group(1), m.group(2).upper()
        if rank not in ("C", "B", "A"): raise ValueError

        cog = bot.get_cog("EstoqueCog")
        fs = await cog.get_frutas()
        achou = next((f for f in fs if f['rank'] == rank and f['numero'] == numero), None)
        if not achou: raise ValueError

        cache = await asyncio.to_thread(_cache_load_sync)
        alvo = str(cache.get("contador", 0) + rotacoes)
        cache.setdefault("agenda", {}).setdefault(rank, {})[alvo] = achou['nome']
        await asyncio.to_thread(_cache_save_sync, cache)

        await ctx.send(f"✅ `{rank}{numero}` → +{rotacoes}", delete_after=3)
    except Exception:
        await ctx.send("❌", delete_after=3)

@bot.command(name="simular")
@commands.check(is_staff)
async def simular(ctx):
    """
    Simula uma atualização de mercado mostrando o resultado no canal atual,
    sem alterar os canais oficiais e sem salvar no histórico.
    """
    await ctx.send("🔍 **Simulando a virada do Mercado Negro... Aguarde.**")
    
    cog = bot.get_cog("EstoqueCog")
    if not cog:
        return await ctx.send("❌ Erro: Planilha não conectada.")
        
    await load_async()  # Puxa o histórico atual para basear o sorteio

    # Fazemos uma CÓPIA do histórico para não sujar a memória real do bot
    temp_history = {
        "C": list(history.get("C", [])),
        "B": list(history.get("B", [])),
        "A": list(history.get("A", []))
    }

    sorteadas = {}
    
    try:
        async with ctx.typing():
            for r in ["C", "B", "A"]:
                lista_disponiveis = await cog.disponiveis(r)
                
                if not lista_disponiveis:
                    escolhida = "Esgotado"
                else:
                    # Filtra a lista com base no histórico TEMPORÁRIO
                    lista_filtrada = [f for f in lista_disponiveis if f not in temp_history[r]]
                    
                    if not lista_filtrada:
                        escolhida = random.choice(lista_disponiveis)
                    else:
                        escolhida = random.choice(lista_filtrada)
                
                sorteadas[r] = escolhida
                
                # Pega o texto formatado do painel
                txt = get_msg_content(r, escolhida)
                
                # Envia no canal que você usou o comando (não no oficial)
                # Usa send_chunked para não estourar o limite de 2000 chars do Discord
                await send_chunked(ctx.channel, f"**[SIMULAÇÃO - RANK {r}]**\n{txt}")

        # Aviso final
        resumo = f"✅ **Simulação Concluída!**\nFrutas sorteadas: `C: {sorteadas['C']} | B: {sorteadas['B']} | A: {sorteadas['A']}`\n*(O mercado oficial não foi alterado e o histórico não foi modificado).* "
        await ctx.send(resumo)
        
    except Exception as e:
        await ctx.send(f"❌ Erro crítico na simulação: {e}")

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
        description="Lista de todas as mercadorias e comandos disponíveis.",
        color=discord.Color.dark_purple()
    )
    
    # Texto dos comandos públicos
    publicos = (
        "`doffy!enc` → Vê todas as frutas.\n"
        "`doffy!fruta <nome>` → Detalhes de uma fruta.\n"
        "`doffy!proxima` → Tempo para a próxima atualização.\n"
        "`doffy!ingerir <fruta>` → Pede para comer uma fruta (Exige aprovação Staff)."
    )
    embed.add_field(name="📖 Público", value=publicos, inline=False)
    
    # Texto dos comandos da Staff
    if is_staff(ctx):
        staff = (
            "**Mercado & Testes:**\n"
            "`doffy!forcarteste` → Força a atualização do mercado.\n"
            "`doffy!simular` → Simula o mercado no chat atual sem salvar.\n"
            "`doffy!reroll <rank>` → Gira os dados e troca a fruta daquele rank.\n"
            "`doffy!historico` → Vê as últimas frutas sorteadas (memória).\n\n"
            "**Controle do Excel:**\n"
            "`doffy!posse <fruta>, <bando>` → Guarda a fruta com um bando.\n"
            "`doffy!cuspir <fruta>` → Limpa o dono e devolve a fruta ao mercado.\n\n"
            "**Administração:**\n"
            "`doffy!anuncio on/off` → Liga ou desliga as notificações globais.\n"
            "`doffy!limpar X` → Apaga X mensagens do chat atual.\n"
            "`doffy!editar <link>` → Altera o texto de uma mensagem do bot.\n"
            "`doffy!reenviar <link> <canal>` → Copia e cola mensagens.\n"
            "`doffy!darcargo <@membro>` → Dá o cargo especial para o membro."
        )
        embed.add_field(name="🔒 Staff", value=staff, inline=False)
    
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

# --- FUNÇÃO PARA O BOT ESCREVER NO EXCEL ---
async def atualizar_planilha_status(ctx, busca_fruta, novo_status):
    cog = ctx.bot.get_cog("EstoqueCog")
    if not cog or not cog.sheet:
        await ctx.send("❌ Erro: Planilha não conectada.")
        return None
        
    fs = await cog.get_frutas()
    b = busca_fruta.lower().replace(" ", "")
    achou = next((f for f in fs if b in f['nome'].lower().replace(" ", "") or b == f['numero'] or b == f"{f['rank'].lower()}{f['numero']}"), None)

    if not achou:
        await ctx.send(f"❌ Não achei nenhuma fruta com `{busca_fruta}`.")
        return None

    def do_update():
        data = cog.sheet.get_all_values()
        idx_head = 0
        for i, r in enumerate(data):
            if "rank" in [str(c).lower() for c in r] and "nome" in [str(c).lower() for c in r]:
                idx_head = i
                break
        head = [h.lower().strip() for h in data[idx_head]]
        i_nome = head.index("nome") if "nome" in head else 2
        i_stat = head.index("status") if "status" in head else 4

        # Acha a linha certa e escreve nela!
        for i, r in enumerate(data):
            if i <= idx_head: continue
            if len(r) > i_nome and r[i_nome].strip() == achou['nome']:
                cog.sheet.update_cell(i + 1, i_stat + 1, novo_status)
                return achou['nome']
        return None

    # Envia a ordem pro Excel rodar nos bastidores (para não travar o bot)
    nome_exato = await asyncio.to_thread(do_update)
    return nome_exato


# 1️⃣ COMANDO: POSSE DE BANDO (Staff)
@bot.command(name="posse")
@commands.check(is_staff)
async def posse(ctx, *, texto: str):
    """Define que a fruta está guardada no navio/cofre de um bando."""
    if "," not in texto:
        return await ctx.send("⚠️ Use a vírgula para separar a fruta do bando!\nExemplo: `doffy!posse Mera Mera, Piratas do Sol`")
        
    busca_fruta, bando = texto.split(",", 1)
    busca_fruta = busca_fruta.strip()
    bando = bando.strip()
    
    # Monta a frase exata que vai pro Excel
    novo_status = f"Em posse do bando {bando}"
    
    msg = await ctx.send(f"⏳ Registrando a posse da fruta `{busca_fruta}`... Aguarde.")
    
    nome_fruta = await atualizar_planilha_status(ctx, busca_fruta, novo_status)
    if nome_fruta:
        await msg.edit(content=f"📦 Sucesso! A **{nome_fruta}** agora está trancada no cofre. Excel atualizado: `{novo_status}`")
    else:
        await msg.edit(content="❌ Falha ao atualizar a planilha.")


# 2️⃣ COMANDO: INGERIR A FRUTA (Aprovação da Staff)
@bot.command(name="ingerir")
async def ingerir(ctx, *, busca_fruta: str):
    """Pede permissão para ingerir a fruta. Requer confirmação da Staff."""
    
    # Pega o nick atual do jogador
    nick_jogador = ctx.author.display_name
    
    # Envia a mensagem de aguardo e adiciona a reação
    msg = await ctx.send(
        f"⏳ O jogador {ctx.author.mention} quer ingerir a fruta `{busca_fruta}`.\n\n"
        f"⚠️ **Aguardando um membro da Staff aprovar reagindo com ✅ nesta mensagem...**"
    )
    await msg.add_reaction("✅")
    
    # Função de segurança que checa quem está reagindo
    def check(reaction, user):
        # Ignora o próprio bot e reações em outras mensagens
        if user == bot.user or reaction.message.id != msg.id or str(reaction.emoji) != "✅":
            return False
        
        # Verifica se o usuário que clicou tem algum dos cargos permitidos
        cargos_usuario = getattr(user, 'roles', [])
        return any(r.id in CARGOS_PERMITIDOS for r in cargos_usuario)

    try:
        # O bot vai esperar por até 1 hora (3600 segundos) pela reação de um Staff
        reaction, staff_user = await bot.wait_for('reaction_add', timeout=3600.0, check=check)
        
        # Se o código chegou aqui, um Staff clicou no ✅!
        await msg.edit(content=f"🔄 Aprovação recebida de {staff_user.mention}! Atualizando o Excel...")
        
        # Vai lá no Excel e altera de verdade
        novo_status = f"Ingerida por {nick_jogador}"
        nome_fruta = await atualizar_planilha_status(ctx, busca_fruta, novo_status)
        
        if nome_fruta:
            await msg.edit(content=f"🍎 **Gulp!** {ctx.author.mention} comeu a **{nome_fruta}**! (Aprovado por {staff_user.mention})\nO Excel foi atualizado para: `{novo_status}`")
            await msg.clear_reactions() # Limpa as reações para ficar bonito
        else:
            await msg.edit(content="❌ Não consegui encontrar essa fruta ou houve um erro na planilha.")
            await msg.clear_reactions()
            
    except asyncio.TimeoutError:
        # Se passar 1 hora e nenhum Staff aprovar, o pedido expira
        await msg.edit(content=f"⌛ O pedido de {ctx.author.mention} para ingerir a `{busca_fruta}` expirou porque nenhum Staff aprovou a tempo.")
        try:
            await msg.clear_reactions()
        except:
            pass

# 3️⃣ COMANDO: LIBERAR A FRUTA (TIRAR O DONO)
@bot.command(name="cuspir")
@commands.check(is_staff)
async def cuspir(ctx, *, busca_fruta: str):
    """Remove o dono da fruta na planilha (deixa o status vazio para voltar ao mercado)."""
    msg = await ctx.send(f"⏳ Fazendo alguém cuspir a `{busca_fruta}` e limpando a planilha... Aguarde.")
    
    # Mandamos o Excel colocar um texto vazio ("") para ela voltar pros sorteios
    nome_fruta = await atualizar_planilha_status(ctx, busca_fruta, "")
    if nome_fruta:
        await msg.edit(content=f"🤮 **Bleargh!** Planilha atualizada! A **{nome_fruta}** foi cuspida e agora está solta pelo mundo de novo.")
    else:
        await msg.edit(content="❌ Falha ao atualizar a planilha. Será que ela desceu pelo buraco errado?")

# 5️⃣ COMANDO: DAR O CARGO ESPECIAL PARA ALGUÉM
@bot.command(name="darcargo")
@commands.check(is_staff)
async def darcargo(ctx, membro: discord.Member):
    """Dá o cargo especial configurado (ID_CARGO_ESPECIAL) para o membro mencionado."""
    cargo = ctx.guild.get_role(ID_CARGO_ESPECIAL)
    if not cargo:
        return await ctx.send("❌ Não achei esse cargo no servidor.")

    if cargo in membro.roles:
        return await ctx.send(f"⚠️ {membro.mention} já tem o cargo **{cargo.name}**.")

    try:
        await membro.add_roles(cargo, reason=f"Concedido por {ctx.author}")
        await ctx.send(f"✅ Cargo **{cargo.name}** dado para {membro.mention}.")
    except discord.Forbidden:
        await ctx.send("❌ Sem permissão pra dar esse cargo — confere se o cargo do bot está acima dele na hierarquia.")

# 4️⃣ COMANDO: VER O HISTÓRICO DAS ÚLTIMAS FRUTAS
@bot.command(name="historico")
@commands.check(is_staff)
async def historico_frutas(ctx):
    """Mostra o histórico das últimas 3 frutas sorteadas que não podem sair de novo."""
    await load_async()  # Garante que puxou o histórico mais recente da memória
    
    emb = discord.Embed(
        title="📜 Memória do Mercado Negro", 
        description="Estas são as últimas frutas que saíram nas lojas e que **o Doflamingo está proibido de sortear de novo** agora.", 
        color=0x2B2D31
    )
    
    for r in ["C", "B", "A"]:
        lista = history.get(r, [])
        if lista:
            emb.add_field(name=f"Rank {r}", value="\n".join([f"• {f}" for f in lista]), inline=False)
        else:
            emb.add_field(name=f"Rank {r}", value="*Nenhuma fruta na memória ainda.*", inline=False)
            
    await ctx.send(embed=emb)

# Anexa a configuração segura ao bot
bot.setup_hook = setup_hook

# O on_ready agora fica limpo e sem risco de duplicar as extensões
@bot.event
async def on_ready():
    await load_async()  # Carrega os IDs das mensagens salvas
    await asyncio.to_thread(_login_backoff_registrar_sucesso)  # login deu certo, zera o backoff
    print(f"✅ Online no Discord: {bot.user}")

_login_backoff_esperar()
try:
    bot.run(TOKEN)
except discord.HTTPException as e:
    if e.status == 429:
        _login_backoff_registrar_falha()
        print("⏳ Bloqueado temporariamente pela Cloudflare (IP com limite excedido). Backoff registrado para a próxima tentativa.")
        time.sleep(30)
    raise