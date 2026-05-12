import discord
import os
import asyncio
from dotenv import load_dotenv 
from discord import app_commands
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN') 
OWNER_ID = int(os.getenv('OWNER_ID') or 1187154363622367285) 

class MoveBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True         
        intents.members = True         
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.tree.add_command(move_messages_context)
        self.tree.add_command(broadcast)
        self.tree.add_command(help_command)
        await self.tree.sync()
        print(f"Ctrl Kings: Movr Bot is online. Owner ID {OWNER_ID} recognized.")

bot = MoveBot()

# --- THE HELP COMMAND ---
@app_commands.command(name="help", description="Learn how to use Movr to clean up your channels")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Movr Help Guide",
        description="Movr is a specialized utility for moving conversations between channels while preserving the original user's identity.",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="How to Move Messages",
        value=(
            "1. Right-click any message.\n"
            "2. Select 'Apps'.\n"
            "3. Click 'Move Messages'.\n"
            "4. Follow the prompts to select a destination and message count."
        ),
        inline=False
    )
    
    embed.add_field(
        name="Key Features",
        value=(
            "• **Identity Mirroring**: Preserves avatars and names via webhooks.\n"
            "• **Reverse System**: Undo any move within 30 seconds (after completion).\n"
            "• **Context Retention**: Keep reactions and attachments intact."
        ),
        inline=False
    )
    
    embed.set_footer(text="A professional utility for moderators and streamers.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- THE BROADCAST COMMAND ---
@app_commands.command(name="broadcast", description="Sends an update DM to all server owners")
async def broadcast(interaction: discord.Interaction, message: str):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Access Denied: Owner Only Command.", ephemeral=True)

    await interaction.response.send_message(f"Initiating broadcast to {len(bot.guilds)} servers...", ephemeral=True)
    
    success, fail = 0, 0
    for guild in bot.guilds:
        try:
            owner = guild.owner or await guild.fetch_member(guild.owner_id)
            if owner:
                embed = discord.Embed(title="Movr Update", description=message, color=discord.Color.blue())
                embed.set_footer(text=f"Sent to: {guild.name}")
                await owner.send(embed=embed)
                success += 1
                await asyncio.sleep(1.5) 
            else: fail += 1
        except Exception as e:
            fail += 1

    await interaction.followup.send(f"Broadcast Complete! Sent to {success} owners. (Failed: {fail})")

# --- THE REVERSE/UNDO VIEW ---
class ReverseView(discord.ui.View):
    def __init__(self, data, current_channel):
        super().__init__(timeout=30)
        self.data = data
        self.current_channel = current_channel

    @discord.ui.button(label="Reverse Move (30s)", style=discord.ButtonStyle.secondary)
    async def reverse_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        button.disabled = True
        await interaction.edit_original_response(view=self)

        total = len(self.data)
        first_item = self.data[0]
        orig_channel = first_item["original_channel"]
        
        webhook_channel = orig_channel.parent if isinstance(orig_channel, discord.Thread) else orig_channel
        webhooks = await webhook_channel.webhooks()
        webhook = discord.utils.get(webhooks, name="Movr Helper") or await webhook_channel.create_webhook(name="Movr Helper")

        for i, item in enumerate(self.data, 1):
            await interaction.edit_original_response(content=f"Reversing Move\n{'■' * i + '□' * (total - i)} ({i}/{total})")
            
            # IDENTITY MIRRORING REPLIED TO REVERSE
            await webhook.send(
                content=item["content"],
                username=item["author_name"],
                avatar_url=item["author_avatar"],
                wait=True
            )

            try:
                msg_to_del = await self.current_channel.fetch_message(item["new_msg_id"])
                await msg_to_del.delete()
            except: pass
            
            await asyncio.sleep(0.4)
        await interaction.edit_original_response(content="Reverse Complete: Messages returned.", view=None)

# --- MODAL FOR CUSTOM INPUT ---
class CustomAmountModal(discord.ui.Modal, title='Move Custom Amount'):
    amount = discord.ui.TextInput(label='How many messages?', placeholder='1-100...', min_length=1, max_length=3)

    def __init__(self, target_msg, target_channel, parent_view):
        super().__init__()
        self.target_msg, self.target_channel, self.parent_view = target_msg, target_channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            count = int(self.amount.value)
            if 1 <= count <= 100:
                await self.parent_view.perform_move(interaction, count)
            else:
                await interaction.response.send_message("Enter a number between 1 and 100.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid number.", ephemeral=True)

# --- CONTEXT MENU COMMAND ---
@app_commands.context_menu(name="Move Messages")
@app_commands.default_permissions(manage_messages=True)
async def move_messages_context(interaction: discord.Interaction, message: discord.Message):
    view = ChannelSelectView(message)
    await interaction.response.send_message("1. Select destination channel:", view=view, ephemeral=True)

# --- CHANNEL SELECTION VIEW ---
class ChannelSelectView(discord.ui.View):
    def __init__(self, msg):
        super().__init__(timeout=180)
        self.msg = msg

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.public_thread, discord.ChannelType.private_thread])
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        target_channel = await self.msg.guild.fetch_channel(select.values[0].id)
        perms = target_channel.permissions_for(self.msg.guild.me)
        if not perms.manage_webhooks or not perms.send_messages:
            return await interaction.response.send_message(f"Error: Permissions missing in {target_channel.mention}", ephemeral=True)

        await interaction.response.edit_message(content=f"2. Target: {target_channel.mention}\nHow many messages?", view=MessageCountView(self.msg, target_channel))

# --- MESSAGE COUNT & EXECUTION VIEW ---
class MessageCountView(discord.ui.View):
    def __init__(self, target_msg, target_channel):
        super().__init__(timeout=180)
        self.target_msg, self.target_channel = target_msg, target_channel

    async def perform_move(self, interaction: discord.Interaction, count: int):
        if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
        for item in self.children: item.disabled = True
        await interaction.edit_original_response(view=self)

        try:
            # 1. TOP-TO-BOTTOM LOGIC (Chronological)
            messages_to_move = [self.target_msg]
            if count > 1:
                async for m in self.target_msg.channel.history(limit=count - 1, after=self.target_msg.created_at, oldest_first=True):
                    messages_to_move.append(m)

            dest = self.target_channel
            webhook_channel = dest.parent if isinstance(dest, discord.Thread) else dest
            webhooks = await webhook_channel.webhooks()
            webhook = discord.utils.get(webhooks, name="Movr Helper") or await webhook_channel.create_webhook(name="Movr Helper")

            moved_data = []
            total = len(messages_to_move)

            for i, m in enumerate(messages_to_move, 1):
                # 2. Optimized Progress Bar
                if i % 5 == 0 or i == total:
                    await interaction.edit_original_response(content=f"Moving Messages\n{'■' * i + '□' * (total - i)} ({i}/{total})")
                
                # Clean Original Author Details
                original_author_name = m.author.display_name
                current_author_avatar = m.author.display_avatar.url
                
                files = [await a.to_file() for a in m.attachments]
                sent_msg = await webhook.send(
                    content=m.content, 
                    username=original_author_name, # Clean name mirror
                    avatar_url=current_author_avatar, # Clean avatar mirror
                    files=files, 
                    thread=dest if isinstance(dest, discord.Thread) else discord.utils.MISSING, 
                    wait=True
                )
                
                moved_data.append({
                    "content": m.content, 
                    "author_name": original_author_name, 
                    "author_avatar": current_author_avatar, 
                    "new_msg_id": sent_msg.id, 
                    "original_channel": m.channel
                })
                
                # Safe Reaction Copying
                for r in m.reactions:
                    try: 
                        await sent_msg.add_reaction(r.emoji)
                        await asyncio.sleep(0.25) 
                    except: 
                        continue

                await asyncio.sleep(0.4)

            # 4. Bulk Delete the originals
            try:
                await self.target_msg.channel.delete_messages(messages_to_move)
            except discord.HTTPException:
                for m in messages_to_move:
                    try: await m.delete()
                    except: pass

            await interaction.edit_original_response(content="Move Complete.", view=ReverseView(moved_data, dest))
            
        except Exception as e:
            print(f"Error during move: {e}")

    @discord.ui.button(label="1", style=discord.ButtonStyle.gray)
    async def one(self, interaction, button): await self.perform_move(interaction, 1)
    @discord.ui.button(label="5", style=discord.ButtonStyle.primary)
    async def five(self, interaction, button): await self.perform_move(interaction, 5)
    @discord.ui.button(label="10", style=discord.ButtonStyle.danger)
    async def ten(self, interaction, button): await self.perform_move(interaction, 10)
    @discord.ui.button(label="Custom", style=discord.ButtonStyle.success)
    async def custom(self, interaction, button): await interaction.response.send_modal(CustomAmountModal(self.target_msg, self.target_channel, self))

bot.run(TOKEN)