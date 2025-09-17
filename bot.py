import discord
from discord.ext import commands
from discord import ui
from typing import Union, List
import asyncio
from PIL import Image, ImageDraw
import aiohttp
import io
import os

# --- CONFIGURAÇÃO ---
# No servidor, use os.getenv("NOME_DA_VARIAVEL")
# Para testes locais, pode definir diretamente:
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

# 2. Modals e Views

# Modal para UMA imagem (usado pelo botão de Upload)
class SingleImageURLModal(ui.Modal, title="Upar Imagem no Imgur"):
    image_url = ui.TextInput(label="Cole o link da imagem para upload", style=discord.TextStyle.short, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.image_url.value) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("Não consegui baixar a imagem dessa URL.", ephemeral=True)
                        return
                    image_data = await resp.read()
            except Exception:
                await interaction.followup.send("URL inválida.", ephemeral=True)
                return

            try:
                with Image.open(io.BytesIO(image_data)) as image:
                    output_buffer = io.BytesIO()
                    image.save(output_buffer, format="PNG")
                    output_buffer.seek(0)
                    image_bytes_as_png = output_buffer.read()
            except Exception:
                await interaction.followup.send("O link não parece ser de uma imagem válida que eu consiga ler.", ephemeral=True)
                return
            
            upload_link = await upload_to_imgur_logic(session, image_bytes_as_png)
            if upload_link:
                embed = discord.Embed(title="Upload Concluído", color=0xfe0155)
                embed.add_field(name="Link do Imgur", value=f"```{upload_link}```")
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("Ocorreu um erro ao enviar para o Imgur.", ephemeral=True)

# View Secundária para processamento em massa
class ProcessingChoiceView(ui.View):
    def __init__(self):
        # Esta View é temporária, então definimos um timeout de 5 minutos
        super().__init__(timeout=120)

    async def wait_for_images(self, interaction: discord.Interaction) -> Union[discord.Message, None]:
        await interaction.response.send_message("Aguardando... Por favor, envie suas imagens em uma única mensagem agora.", ephemeral=True)
        def check(m: discord.Message):
            return m.author == interaction.user and