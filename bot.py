import discord
from discord.ext import commands
from discord import ui
from PIL import Image, ImageDraw
import aiohttp
import io
import os
from typing import Union

# --- CONFIGURAÇÃO ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID")

# --- LÓGICA DO BOT ---

# 1. Funções de Processamento

def round_corners_logic(image_bytes: bytes) -> io.BytesIO:
    with Image.open(io.BytesIO(image_bytes)).convert("RGBA") as image:
        radius = 12
        mask = Image.new('L', image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, image.width, image.height), radius, fill=255)
        output_image = Image.new('RGBA', image.size)
        output_image.paste(image, (0, 0), mask=mask)
        final_buffer = io.BytesIO()
        output_image.save(final_buffer, 'PNG')
        final_buffer.seek(0)
        return final_buffer

async def upload_to_imgur_logic(session: aiohttp.ClientSession, image_bytes: bytes) -> Union[str, None]:
    url = "https://api.imgur.com/3/upload"
    headers = {'Authorization': f'Client-ID {IMGUR_CLIENT_ID}'}
    data = {'image': image_bytes}
    
    async with session.post(url, headers=headers, data=data) as response:
        if response.status == 200:
            result = await response.json()
            return result['data']['link']
        else:
            print(f"Erro no Imgur: {response.status}")
            print(await response.json())
            return None

# 2. Componentes da Interface (Modal e View)

class ImageURLModal(ui.Modal, title="Forneça a URL da Imagem"):
    image_url = ui.TextInput(
        label="Link da Imagem",
        placeholder="https://exemplo.com/minha_imagem.png (ou .webp, .jpg...)",
        style=discord.TextStyle.short,
        required=True
    )

    def __init__(self, action: str):
        super().__init__()
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        url = self.image_url.value
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("Não consegui baixar a imagem dessa URL. Verifique o link.", ephemeral=True)
                        return
                    image_data = await resp.read()

                if self.action == 'arredondar':
                    processed_image_buffer = round_corners_logic(image_data)
                    file_to_send = discord.File(fp=processed_image_buffer, filename="rounded_image.png")
                    
                    try:
                        await interaction.user.send("Aqui está sua imagem com bordas arredondadas:", file=file_to_send)
                        await interaction.followup.send("Sua imagem foi enviada no seu privado! ✔️", ephemeral=True)
                    except discord.Forbidden:
                        processed_image_buffer.seek(0)
                        file_for_fallback = discord.File(fp=processed_image_buffer, filename="rounded_image.png")
                        await interaction.followup.send("Não consegui enviar a imagem no seu privado (suas DMs podem estar desativadas). Aqui está ela:", file=file_for_fallback, ephemeral=True)

                elif self.action == 'upload':
                    # ***** A CORREÇÃO ESTÁ AQUI *****
                    # Abrimos a imagem baixada (seja qual for o formato) com o Pillow
                    # e a salvamos em memória como PNG para garantir a compatibilidade.
                    try:
                        with Image.open(io.BytesIO(image_data)) as image:
                            output_buffer = io.BytesIO()
                            image.save(output_buffer, format="PNG")
                            output_buffer.seek(0)
                            image_bytes_as_png = output_buffer.read()
                    except Exception as e:
                         await interaction.followup.send(f"O link não parece ser de uma imagem válida que eu consiga ler. Erro: {e}", ephemeral=True)
                         return

                    upload_link = await upload_to_imgur_logic(session, image_bytes_as_png)
                    
                    if upload_link:
                        embed = discord.Embed(
                            title="Upload Concluído",
                            color=0x5865F2
                        )
                        embed.add_field(name="Link do Imgur", value=f"`{upload_link}`")
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        await interaction.followup.send("Ocorreu um erro ao enviar sua imagem para o Imgur. A API pode estar instável.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"Ocorreu um erro inesperado: {e}", ephemeral=True)
            print(e)


class DesignerToolsView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Arredondar Borda", style=discord.ButtonStyle.primary, emoji="🖼️", custom_id="round_button")
    async def round_button(self, interaction: discord.Interaction, button: ui.Button):
        modal = ImageURLModal(action='arredondar')
        await interaction.response.send_modal(modal)

    @ui.button(label="Upar no Imgur", style=discord.ButtonStyle.secondary, emoji="☁️", custom_id="upload_button")
    async def upload_button(self, interaction: discord.Interaction, button: ui.Button):
        modal = ImageURLModal(action='upload')
        await interaction.response.send_modal(modal)


# 3. Setup do Bot e Comando Principal (continua o mesmo)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    bot.add_view(DesignerToolsView())
    print(f'Bot {bot.user} está online e pronto!')

@bot.command()
async def designer(ctx):
    embed = discord.Embed(
        title="<:4_:1415749694755307550> Designer Tools - Arredondar & Upar imagem",
        description=(
            "<:9_:1415749674786361354> Para arredondar ou upar uma imagem, selecione o botão desejado;\n"
            "<:9_:1415749674786361354> Ao clicar no botão, forneça o link da imagem conforme solicitado."
        ),
        color=0x2b2d31
    )
    embed.set_image(url="https://i.imgur.com/8dylYAD.png")

    await ctx.send(embed=embed, view=DesignerToolsView())

# --- INICIALIZAÇÃO DO BOT ---

bot.run(DISCORD_TOKEN)


