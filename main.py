import discord
import os
import asyncio
from dotenv import load_dotenv 
from discord import app_commands
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN') 
OWNER_ID = int(os.getenv('OWNER_ID') or 1187154363622367285) 
LOG_CHANNEL_ID = 1500701120362713269 # <--- ADDED YOUR CHANNEL ID HERE

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

    # --- NEW: SERVER JOIN NOTIFICATION (CHANNEL LOG) ---
    async def on_guild_join(self, guild: discord.Guild):
        try:
            channel = self.get_channel(LOG_CHANNEL_ID) or await self.fetch_channel(LOG_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="🎉 New Server Joined!",
                    description=f"Movr was just added to **{guild.name}**!",
                    color=discord.Color.green()
                )
                embed.add_field(name="Server ID", value=guild.id)
                embed.add_field(name="Member Count", value=guild.member_count)
                embed.add_field(name="Total Servers Now", value=len(self.guilds))
                await channel.send(embed=embed)
        except Exception as e:
            print(f"Failed to send join notification: {e}")

    # --- NEW: SERVER LEAVE NOTIFICATION (CHANNEL LOG) ---
    async def on_guild_remove(self, guild: discord.Guild):
        try:
            channel = self.get_channel(LOG_CHANNEL_ID) or await self.fetch_channel(LOG_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="😢 Removed from Server",
                    description=f"Movr was removed from **{guild.name}**.",
                    color=discord.Color.red()
                )
                embed.add_field(name="Total Servers Now", value=len(self.guilds))
                await channel.send(embed=embed)
        except Exception as e:
            print(f"Failed to send leave notification: {e}")

bot = MoveBot()

# --- UNIVERSAL MOVE ENGINE (FORUMS, EMBEDS, LARGE FILES, NITRO SPLIT) ---
async def execute_move(interaction: discord.Interaction, target_msg: discord.Message, target_channel, count: int, forum_title: str = None):
    if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
    await interaction.edit_original_response(content="Preparing to move...", view=None)

    try:
        created_forum_thread = None
        
        # 1. FORUM POST CREATION HANDLING
        if forum_title and target_channel.type == discord.ChannelType.forum:
            embed = discord.Embed(description=f"💬 Conversation relocated from {target_msg.channel.mention}", color=discord.Color.blue())
            thread_with_msg = await target_channel.create_thread(name=forum_title, embed=embed)
            dest = thread_with_msg.thread 
            created_forum_thread = dest 
            webhook_channel = target_channel 
        else:
            dest = target_channel
            webhook_channel = dest.parent if isinstance(dest, discord.Thread) else dest

        # 2. TOP-TO-BOTTOM LOGIC
        messages_to_move = [target_msg]
        if count > 1:
            async for m in target_msg.channel.history(limit=count - 1, after=target_msg.created_at, oldest_first=True):
                messages_to_move.append(m)

        webhooks = await webhook_channel.webhooks()
        webhook = discord.utils.get(webhooks, name="Movr Helper") or await webhook_channel.create_webhook(name="Movr Helper")

        moved_data = []
        total = len(messages_to_move)

        for i, m in enumerate(messages_to_move, 1):
            if i % 5 == 0 or i == total:
                await interaction.edit_original_response(content=f"Moving Messages\n{'■' * i + '□' * (total - i)} ({i}/{total})")
            
            original_author_name = m.author.display_name
            current_author_avatar = m.author.display_avatar.url
            
            # --- NEW SAFETY CHECKS ---
            # A. HUGE FILE BYPASS (25MB LIMIT)
            safe_files = []
            large_file_urls = ""
            for a in m.attachments:
                if a.size <= 25 * 1024 * 1024:
                    safe_files.append(await a.to_file())
                else:
                    large_file_urls += f"\n📎 [Large Attachment Bypass: {a.filename}]({a.url})"

            # B. NITRO MESSAGE SPLITTING (2000 CHARACTERS)
            full_text = (m.content or "") + large_file_urls
            text_chunks = [full_text[idx:idx+2000] for idx in range(0, len(full_text), 2000)]
            if not text_chunks: text_chunks = [""] # Failsafe for empty messages with just files

            # C. EMBED SUPPORT (Only copy Rich embeds to avoid API crashes)
            valid_embeds = [e for e in m.embeds if e.type == 'rich']

            sent_msg_ids = []
            first_sent_msg = None

            # D. SEND CHUNKS
            for c_idx, chunk in enumerate(text_chunks):
                sent_msg = await webhook.send(
                    content=chunk, 
                    username=original_author_name, 
                    avatar_url=current_author_avatar, 
                    files=safe_files if c_idx == 0 else [], 
                    embeds=valid_embeds if c_idx == 0 else [], 
                    thread=dest if isinstance(dest, discord.Thread) else discord.utils.MISSING, 
                    wait=True
                )
                sent_msg_ids.append(sent_msg.id)
                if c_idx == 0: first_sent_msg = sent_msg
            
            moved_data.append({
                "content": m.content, 
                "author_name": original_author_name, 
                "author_avatar": current_author_avatar, 
                "new_msg_ids": sent_msg_ids, # Track all chunks for reversal
                "original_channel": m.channel
            })
            
            # Safe Reaction Copying (Applied to the first chunk)
            if first_sent_msg:
                for r in m.reactions:
                    try: 
                        await first_sent_msg.add_reaction(r.emoji)
                        await asyncio.sleep(0.25) 
                    except: continue

            await asyncio.sleep(0.4)

        # 3. BULK DELETE ORIGINALS
        try:
            await target_msg.channel.delete_messages(messages_to_move)
        except discord.HTTPException:
            for m in messages_to_move:
                try: await m.delete()
                except: pass

        await interaction.edit_original_response(content="Move Complete.", view=ReverseView(moved_data, dest, created_forum_thread))
        
    except Exception as e:
        print(f"Error during move: {e}")
        await interaction.edit_original_response(content=f"An error occurred: {e}", view=None)

# --- THE HELP COMMAND ---
@app_commands.command(name="help", description="Learn how to use Movr to clean up your channels")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Movr Help Guide",
        description="Movr is a specialized utility for moving conversations between standard channels and Forum posts.",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="How to Move Messages",
        value=(
            "1. Right-click any message -> 'Apps' -> 'Move Messages'.\n"
            "2. Select a destination channel (Text, Thread, or Forum).\n"
            "3. If a Forum is selected, you'll be prompted to create a Thread Title!"
        ),
        inline=False
    )
    embed.set_footer(text="A professional utility for moderators.")
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
                await owner.send(embed=embed)
                success += 1
                await asyncio.sleep(1.5) 
            else: fail += 1
        except Exception: fail += 1
    await interaction.followup.send(f"Broadcast Complete! Sent to {success} owners. (Failed: {fail})")

# --- THE REVERSE/UNDO VIEW ---
class ReverseView(discord.ui.View):
    def __init__(self, data, current_channel, created_forum_thread=None):
        super().__init__(timeout=30)
        self.data = data
        self.current_channel = current_channel
        self.created_forum_thread = created_forum_thread

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
            
            # Nitro split for reversed text just in case
            rev_content = item["content"] or ""
            rev_chunks = [rev_content[idx:idx+2000] for idx in range(0, max(1, len(rev_content)), 2000)]
            if not rev_chunks: rev_chunks = [""]

            for chunk in rev_chunks:
                await webhook.send(
                    content=chunk,
                    username=item["author_name"],
                    avatar_url=item["author_avatar"],
                    wait=True
                )

            # Clean up all chunks that were created during the move
            for msg_id in item.get("new_msg_ids", []):
                try:
                    msg_to_del = await self.current_channel.fetch_message(msg_id)
                    await msg_to_del.delete()
                except: pass
            
            await asyncio.sleep(0.4)
            
        # Clean up the forum post if we made one!
        if self.created_forum_thread:
            try: await self.created_forum_thread.delete()
            except: pass

        await interaction.edit_original_response(content="Reverse Complete: Messages returned.", view=None)

# --- FORUM SETUP MODAL ---
class ForumSetupModal(discord.ui.Modal, title='Setup New Forum Post'):
    thread_title = discord.ui.TextInput(label='Forum Post Title', placeholder='e.g. Server Rules Discussion', max_length=100)
    amount = discord.ui.TextInput(label='How many messages?', placeholder='1-100...', min_length=1, max_length=3)

    def __init__(self, target_msg, target_channel):
        super().__init__()
        self.target_msg = target_msg
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            count = int(self.amount.value)
            if 1 <= count <= 100:
                await execute_move(interaction, self.target_msg, self.target_channel, count, forum_title=self.thread_title.value)
            else:
                await interaction.response.send_message("Enter a number between 1 and 100.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid number.", ephemeral=True)

# --- STANDARD CUSTOM AMOUNT MODAL ---
class CustomAmountModal(discord.ui.Modal, title='Move Custom Amount'):
    amount = discord.ui.TextInput(label='How many messages?', placeholder='1-100...', min_length=1, max_length=3)

    def __init__(self, target_msg, target_channel):
        super().__init__()
        self.target_msg = target_msg
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            count = int(self.amount.value)
            if 1 <= count <= 100:
                await execute_move(interaction, self.target_msg, self.target_channel, count)
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

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.public_thread, discord.ChannelType.private_thread, discord.ChannelType.forum])
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        target_channel = await self.msg.guild.fetch_channel(select.values[0].id)
        perms = target_channel.permissions_for(self.msg.guild.me)
        
        if not perms.manage_webhooks or not perms.send_messages:
            return await interaction.response.send_message(f"Error: Permissions missing in {target_channel.mention}", ephemeral=True)

        if target_channel.type == discord.ChannelType.forum:
            await interaction.response.send_modal(ForumSetupModal(self.msg, target_channel))
        else:
            await interaction.response.edit_message(content=f"2. Target: {target_channel.mention}\nHow many messages?", view=MessageCountView(self.msg, target_channel))

# --- STANDARD MESSAGE COUNT VIEW ---
class MessageCountView(discord.ui.View):
    def __init__(self, target_msg, target_channel):
        super().__init__(timeout=180)
        self.target_msg = target_msg
        self.target_channel = target_channel

    @discord.ui.button(label="1", style=discord.ButtonStyle.gray)
    async def one(self, interaction, button): await execute_move(interaction, self.target_msg, self.target_channel, 1)
    @discord.ui.button(label="5", style=discord.ButtonStyle.primary)
    async def five(self, interaction, button): await execute_move(interaction, self.target_msg, self.target_channel, 5)
    @discord.ui.button(label="10", style=discord.ButtonStyle.danger)
    async def ten(self, interaction, button): await execute_move(interaction, self.target_msg, self.target_channel, 10)
    @discord.ui.button(label="Custom", style=discord.ButtonStyle.success)
    async def custom(self, interaction, button): await interaction.response.send_modal(CustomAmountModal(self.target_msg, self.target_channel))

bot.run(TOKEN)