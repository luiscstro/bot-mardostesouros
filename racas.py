import discord
from discord.ext import commands
import random
import asyncio

# ================= CONFIGURAÇÕES =================
ROLE_LUNARIANO_ID = 1315357629853204562
ROLE_JA_ROLOU_ID = 1285273687695822898
CANAL_LOG_ID = 1285274769503158374

# Coloque aqui os IDs dos 3 cargos da Staff separados por vírgula
ROLE_STAFF_IDS = [
    1222232432527413389,  # Cargo Staff 1
    1227977596671885393,  # Cargo Staff 2
    1405643389105606767   # Cargo Staff 3
]
# =================================================

class DeleteTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Selar a Fenda (Apagar Canal)", style=discord.ButtonStyle.danger, custom_id="btn_apagar_canal", emoji="💥")
    async def apagar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔥 *As chamas estão consumindo este canal... Desaparecendo em 5 segundos.*", ephemeral=False)
        button.disabled = True
        await interaction.message.edit(view=self)
        await asyncio.sleep(5)
        await interaction.channel.delete(reason="Teste de raça concluído.")

class RollView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Rolar d100", style=discord.ButtonStyle.primary, custom_id="btn_rolar_d100", emoji="🎲")
    async def rolar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ja_rolou = interaction.guild.get_role(ROLE_JA_ROLOU_ID)
        lunariano = interaction.guild.get_role(ROLE_LUNARIANO_ID)
        
        if ja_rolou in interaction.user.roles:
            await interaction.response.send_message("Você já tentou rolar para esta raça!", ephemeral=True)
            return

        resultado = random.randint(1, 100)
        
        button.disabled = True
        await interaction.response.edit_message(view=self)
        
        if resultado >= 90:
            await interaction.user.add_roles(lunariano, ja_rolou)
            
            await interaction.followup.send("*Muito antes dos Dragões Celestiais erguerem Mary Geoise...*")
            await asyncio.sleep(3.5)
            await interaction.channel.send("*O topo da Red Line era o lar de seres descritos como divindades.*")
            await asyncio.sleep(3.5)
            await interaction.channel.send("*Eles possuíam asas negras impenetráveis, cabelos prateados e uma chama inextinguível ardendo em suas costas...*")
            await asyncio.sleep(4.0)
            await interaction.channel.send("*Capazes de sobreviver a qualquer ambiente extremo, eles foram caçados pelo Governo Mundial até a quase extinção. Mas a linhagem sobreviveu... no seu sangue.*")
            await asyncio.sleep(4.5)
            
            gif_lunariano = "|| https://c.tenor.com/FKL7MQuy-yUAAAAC/tenor.gif||"
            await interaction.channel.send(f"👑 **O FOGO DOS LUNARIANS DESPERTOU!** 👑\n\n{interaction.user.mention}, você tirou **{resultado}** no d100! As chamas ancestrais agora queimam em você.\n**VOCÊ É UM LUNARIANO!**\n{gif_lunariano}")
            
            canal_log = interaction.guild.get_channel(CANAL_LOG_ID)
            if canal_log:
                embed_log = discord.Embed(title="🔥 Um Novo Lunariano Despertou!", color=discord.Color.red())
                embed_log.add_field(name="Jogador", value=interaction.user.mention)
                embed_log.add_field(name="Raça", value="Lunariano")
                embed_log.add_field(name="Rolagem", value=f"**{resultado}**")
                await canal_log.send(embed=embed_log)
                
        else:
            await interaction.user.add_roles(ja_rolou)
            await interaction.followup.send(f"🎲 Você rolou **{resultado}**.")
            await asyncio.sleep(2.0)
            await interaction.channel.send(f"💨 *As chamas não acenderam. Suas costas permanecem vazias e o sangue em suas veias é comum.* \nInfelizmente, {interaction.user.mention}, você **não** possui a lendária linhagem dos Lunarianos.")

        await asyncio.sleep(2.0)
        embed_fim = discord.Embed(
            title="Destino Selado",
            description="A fenda cumpriu o seu propósito. Quando estiver pronto, clique no botão abaixo para apagar este canal definitivamente.",
            color=discord.Color.dark_gray()
        )
        await interaction.channel.send(embed=embed_fim, view=DeleteTicketView())

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Teste de Linhagem (Lunariano)", style=discord.ButtonStyle.success, custom_id="btn_criar_ticket", emoji="🔥")
    async def criar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        ja_rolou = interaction.guild.get_role(ROLE_JA_ROLOU_ID)
        
        if ja_rolou in interaction.user.roles:
            await interaction.response.send_message("Você já fez o teste para esta raça. Apenas uma oportunidade por jogador!", ephemeral=True)
            return

        categoria = interaction.channel.category
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        for staff_id in ROLE_STAFF_IDS:
            staff_role = interaction.guild.get_role(staff_id)
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        canal = await interaction.guild.create_text_channel(
            name=f"teste-lunariano-{interaction.user.name}",
            category=categoria,
            overwrites=overwrites
        )

        await interaction.response.send_message(f"A fenda abriu-se! Faça o seu teste em {canal.mention}", ephemeral=True)
        
        embed = discord.Embed(
            title="O Teste Decisivo", 
            description="Role os dados para descobrir se carrega a lendária linhagem Lunariana.\n**Condição de Sucesso:** 90 ou mais no d100.",
            color=discord.Color.dark_theme()
        )
        await canal.send(f"{interaction.user.mention}", embed=embed, view=RollView())

# =================================================
# O COG (Extensão para o Bot Principal)
# =================================================
class RacasCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # O discord.py exige que os botões persistentes sejam adicionados ao bot
        # Isso garante que se o bot reiniciar, os botões antigos não morrem
        self.bot.add_view(TicketView())
        self.bot.add_view(RollView())
        self.bot.add_view(DeleteTicketView())

    # Comando doffy!painel_racas (Para você gerar o botão)
    @commands.command(name="painel_racas")
    @commands.has_any_role(*ROLE_STAFF_IDS) # Apenas staff pode usar esse comando
    async def painel_racas(self, ctx):
        embed = discord.Embed(
            title="🧬 Despertar de Raças", 
            description="Clique no botão abaixo para abrir um canal privado e tentar a sorte para despertar como um **Lunariano**."
        )
        await ctx.send(embed=embed, view=TicketView())
        # Apaga a mensagem do staff para ficar limpo
        try: await ctx.message.delete()
        except: pass

async def setup(bot):
    await bot.add_cog(RacasCog(bot))