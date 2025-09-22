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

# Modal para UMA imagem
class SingleImageURLModal(ui.Modal, title="Upar Imagem no Imgur"):
    image_url = ui.TextInput(label="Forneça a URL da Imagem", placeholder="https://exemplo.com/minha_imagem.png (ou .webp, .jpg...)", style=discord.TextStyle.short, required=True)

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
                embed.add_field(name="Link do Imgur", value=f"``{upload_link}``")
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("Ocorreu um erro ao enviar para o Imgur.", ephemeral=True)

# View Secundária para processamento em massa
class ProcessingChoiceView(ui.View):
    def __init__(self, original_message: discord.Message):
        super().__init__(timeout=300)
        # Mantemos a referência à mensagem original, mas não vamos mais usá-la para apagar
        self.original_message = original_message

    async def wait_for_images(self, interaction: discord.Interaction) -> Union[discord.Message, None]:
        await interaction.response.send_message("Aguardando... Por favor, envie suas imagens em uma única mensagem.", ephemeral=True)
        def check(m: discord.Message):
            return m.author == interaction.user and m.channel == interaction.channel and m.attachments
        try:
            message_with_images = await bot.wait_for('message', check=check, timeout=300.0)
            return message_with_images
        except asyncio.TimeoutError:
            await interaction.followup.send("Tempo esgotado. Por favor, comece o processo novamente.", ephemeral=True)
            return None

    async def cleanup(self, interaction_message: discord.Message, user_message: discord.Message):
        try:
            await interaction_message.delete()
            await user_message.delete()
            # A linha que apagava a embed principal foi REMOVIDA daqui.
        except discord.Forbidden:
            print("Não tenho permissão para apagar mensagens.")
        except Exception as e:
            print(f"Erro ao apagar mensagens: {e}")

    @ui.button(label="Arredondar e Upar", style=discord.ButtonStyle.success, emoji="☁️")
    async def round_and_upload(self, interaction: discord.Interaction, button: ui.Button):
        user_message = await self.wait_for_images(interaction)
        if user_message is None: 
            await interaction.message.delete()
            return
        processing_msg = await interaction.followup.send("Processando e fazendo upload...", ephemeral=True)
        links = []
        image_bytes_list = [await att.read() for att in user_message.attachments if att.content_type.startswith('image/')]
        async with aiohttp.ClientSession() as session:
            for image_bytes in image_bytes_list:
                rounded_buffer = round_corners_logic(image_bytes)
                link = await upload_to_imgur_logic(session, rounded_buffer.read())
                if link: links.append(link)
        if links:
            links_string = "\n".join(links)
            embed = discord.Embed(title="Upload Concluído", description=f"``{links_string}``", color=0x5865F2)
            await processing_msg.edit(content=None, embed=embed)
        else:
            await processing_msg.edit(content="Ocorreu um erro ao fazer o upload das imagens.")
        await self.cleanup(interaction.message, user_message)
        self.stop()

    @ui.button(label="Arredondar", style=discord.ButtonStyle.primary, emoji="🖼️")
    async def round_only(self, interaction: discord.Interaction, button: ui.Button):
        user_message = await self.wait_for_images(interaction)
        if user_message is None:
            await interaction.message.delete()
            return
        processing_msg = await interaction.followup.send("Arredondando imagens...", ephemeral=True)
        processed_files = []
        image_bytes_list = [await att.read() for att in user_message.attachments if att.content_type.startswith('image/')]
        for image_bytes in image_bytes_list:
            rounded_buffer = round_corners_logic(image_bytes)
            processed_files.append(discord.File(fp=rounded_buffer, filename=f"rounded_{len(processed_files)}.png"))
        try:
            await processing_msg.edit(content=f"Enviando {len(processed_files)} imagem(ns) para o seu privado...")
            for file in processed_files:
                await interaction.user.send(file=file)
                file.fp.seek(0)
            await processing_msg.edit(content=f"Todas as imagens foram enviadas no seu privado! ✔️")
        except discord.Forbidden:
            for file in processed_files: file.fp.seek(0)
            await interaction.followup.send(content="Não consegui enviar no seu privado (suas DMs podem estar desativadas). Aqui estão suas imagens:", files=processed_files, ephemeral=True)
        await self.cleanup(interaction.message, user_message)
        self.stop()
    
    @ui.button(label="", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.message.delete()
        # A linha que apagava a embed principal foi REMOVIDA daqui.
        await interaction.response.send_message("Processo cancelado.", ephemeral=True)
        self.stop()

# View Principal
class DesignerToolsView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Arredondar Borda", style=discord.ButtonStyle.primary, emoji="🖼️", custom_id="main_round_button")
    async def round_button(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="<:4_:1416148634554077276> Arredondar Imagens",
            description=("<:9_:1416148650433970216> Escolha uma opção conforme o desejado.\n "
                         "<:9_:1416148650433970216> Após clicar, envie no chat as imagens desejadas."),
            color=0xfe0155
        )
        # Voltamos a passar a mensagem original para a View, mas agora ela não será usada para apagar.
        # Apenas mantemos a estrutura que já funcionava.
        await interaction.response.send_message(embed=embed, view=ProcessingChoiceView(original_message=interaction.message))

    @ui.button(label="Upar no Imgur", style=discord.ButtonStyle.secondary, emoji="☁️", custom_id="main_upload_button")
    async def upload_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SingleImageURLModal())

# Setup do Bot e Comando Principal
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
        title="<:4_:1415749694755307550> Designer Tools",
        description=(
            "<:9_:1415749674786361354> Para arredondar ou upar uma imagem, selecione o botão desejado;\n"
            "<:9_:1415749674786361354> Ao clicar no botão, forneça os itens conforme solicitado.\n"
            "\n"
"<:8_:1227304249197727905> ___Obs:___\n"
"<:9_:1415749674786361354> Após arredondar, o bot irá enviar pela dm a(s) imagem(ns) solicitada(s). Caso o seu privado esteja fechado ele irá enviar uma mensagem efêmera no canal com a(s) imagem(ns).\n"
"<:9_:1415749674786361354> Ao solicitar que o bot upe a(s) imagem(ns) no imgur, ele irá enviar uma mensagem efêmera no canal atual com o link da(s) imagem(ns)."
        ),
        color=0xfe0155
    )
    embed.set_image(url="https://i.imgur.com/8dylYAD.png")
    await ctx.send(embed=embed, view=DesignerToolsView())

# --- INICIALIZAÇÃO DO BOT ---
bot.run(DISCORD_TOKEN)