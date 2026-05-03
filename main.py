async def perform_move(self, interaction: discord.Interaction, count: int):
        if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
        for item in self.children: item.disabled = True
        await interaction.edit_original_response(view=self)

        try:
            # 1. Cleaner History Fetching
            # Fetch count-1 because we are manually inserting the target_msg
            messages_to_move = [m async for m in self.target_msg.channel.history(limit=count-1, before=self.target_msg)]
            messages_to_move.insert(0, self.target_msg)
            messages_to_move.reverse() # Chronological order

            dest = self.target_channel
            webhook_channel = dest.parent if isinstance(dest, discord.Thread) else dest
            webhooks = await webhook_channel.webhooks()
            webhook = discord.utils.get(webhooks, name="Movr Helper") or await webhook_channel.create_webhook(name="Movr Helper")

            moved_data = []
            total = len(messages_to_move)

            for i, m in enumerate(messages_to_move, 1):
                # 2. Optimized Progress Bar (Only updates every 5 msgs or on the last msg)
                if i % 5 == 0 or i == total:
                    await interaction.edit_original_response(content=f"Moving Messages\n{'■' * i + '□' * (total - i)} ({i}/{total})")
                
                current_author_name = m.author.display_name
                current_author_avatar = m.author.display_avatar.url
                
                files = [await a.to_file() for a in m.attachments]
                sent_msg = await webhook.send(
                    content=m.content, 
                    username=current_author_name, 
                    avatar_url=current_author_avatar,
                    files=files, 
                    thread=dest if isinstance(dest, discord.Thread) else discord.utils.MISSING, 
                    wait=True
                )
                
                moved_data.append({
                    "content": m.content, 
                    "author_name": current_author_name, 
                    "author_avatar": current_author_avatar, 
                    "new_msg_id": sent_msg.id, 
                    "original_channel": m.channel
                })
                
                # 3. Safe Reaction Copying
                for r in m.reactions:
                    try: 
                        await sent_msg.add_reaction(r.emoji)
                        await asyncio.sleep(0.25) # Reaction rate limit protection
                    except: 
                        continue

                # 0.4s sleep for sending messages remains to protect the webhook
                await asyncio.sleep(0.4)

            # 4. Bulk Delete the originals (1 API call instead of 50!)
            try:
                await self.target_msg.channel.delete_messages(messages_to_move)
            except discord.HTTPException:
                # Fallback: If messages are older than 14 days, bulk delete fails, so we loop
                for m in messages_to_move:
                    try: await m.delete()
                    except: pass

            await interaction.edit_original_response(content="Move Complete.", view=ReverseView(moved_data, dest))
            
        except Exception as e:
            print(f"Error during move: {e}")