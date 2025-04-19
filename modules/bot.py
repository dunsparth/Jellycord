import discord
from discord.ext import tasks
import logging
from typing import Optional, List, Union
from .config import Config
from api.clients.emby_client import EmbyClient, StreamInfo
from api.clients.jellyfin_client import JellyfinClient
from .media_server import ServerStats
import datetime
import asyncio

class MediaBot(discord.Client):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(intents=intents)
        self.config = config
        self.status_message: Optional[discord.Message] = None
        self.recently_added_message: Optional[discord.Message] = None
        self.emby_client: Optional[EmbyClient] = None
        self.jellyfin_client: Optional[JellyfinClient] = None
        self.active_client = None

    async def setup_hook(self) -> None:
        """Set up the bot."""
        # Initialize API clients based on configuration
        if self.config.emby.enabled:
            self.emby_client = EmbyClient(
                base_url=self.config.emby.url,
                api_key=self.config.emby.api_key,
                user_id='',  # We'll get this automatically
                use_ssl=self.config.emby.verify_ssl
            )
            
            # Get user ID if not provided
            if not self.config.emby.user_id:
                user_id = await self.emby_client.get_user_id()
                if user_id:
                    self.emby_client.user_id = user_id
                    logging.info(f"Got Emby user ID: {user_id}")
                else:
                    logging.error("Could not get Emby user ID")
            else:
                self.emby_client.user_id = self.config.emby.user_id
                logging.info(f"Using configured Emby user ID: {self.config.emby.user_id}")
            
            self.active_client = self.emby_client
            logging.info("Using Emby as active media server")

        elif self.config.jellyfin.enabled:
            self.jellyfin_client = JellyfinClient(
                base_url=self.config.jellyfin.url,
                api_key=self.config.jellyfin.api_key,
                use_ssl=self.config.jellyfin.verify_ssl
            )
            
            # Get user ID
            user_id = await self.jellyfin_client.get_user_id()
            if user_id:
                self.jellyfin_client.user_id = user_id
                logging.info(f"Got Jellyfin user ID: {user_id}")
            else:
                logging.error("Could not get Jellyfin user ID")
            
            self.active_client = self.jellyfin_client
            logging.info("Using Jellyfin as active media server")
        else:
            logging.error("No media server enabled in configuration!")
            return

        # Start background tasks
        self.bg_task = self.loop.create_task(self.status_update_loop())
        logging.info("Started status update loop")

    async def close(self):
        """Close the bot and cleanup clients."""
        if self.emby_client:
            await self.emby_client.close()
        if self.jellyfin_client:
            await self.jellyfin_client.close()
        await super().close()

    async def status_update_loop(self):
        """Background task to update status periodically."""
        logging.info("Status update loop starting...")
        await self.wait_until_ready()
        
        # Run status updates directly
        await self._run_status_updates()

    async def _run_status_updates(self):
        """Run the status update loop."""
        while not self.is_closed():
            try:
                await self.update_status()
                await self.update_library_stats()
                await self.update_recently_added()
                await asyncio.sleep(self.config.general.refresh_seconds)
            except Exception as e:
                logging.error(f"Error in status update loop: {e}")
                await asyncio.sleep(5)  # Wait a bit before retrying

    async def on_ready(self):
        """Called when the bot is ready."""
        logging.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logging.info(f'Connected to {len(self.guilds)} guilds:')
        for guild in self.guilds:
            logging.info(f'- {guild.name} (ID: {guild.id})')
            logging.info('Available text channels:')
            for channel in guild.text_channels:
                logging.info(f'  - {channel.name} (ID: {channel.id})')
                # Delete the old media-status channel if it exists
                if channel.name == 'media-status':
                    try:
                        logging.info(f"Deleting old media-status channel: {channel.id}")
                        await channel.delete()
                        logging.info("Successfully deleted old channel")
                    except Exception as e:
                        logging.error(f"Error deleting old channel: {e}")

    async def check_permissions(self, guild: discord.Guild) -> bool:
        """Check if the bot has required permissions."""
        me = guild.me
        permissions = me.guild_permissions
        
        required_permissions = {
            'manage_channels': True,
            'view_channel': True,
            'send_messages': True,
            'manage_messages': True,
            'embed_links': True,
            'read_message_history': True
        }
        
        missing_permissions = []
        for perm, required in required_permissions.items():
            if not getattr(permissions, perm) == required:
                missing_permissions.append(perm)
        
        if missing_permissions:
            logging.error(f"Missing required permissions: {', '.join(missing_permissions)}")
            return False
            
        logging.info("Bot has all required permissions")
        return True

    async def ensure_channel_exists(self):
        """Ensure the status channel exists."""
        try:
            logging.info("Checking for status channel...")
            guild = self.get_guild(int(self.config.discord.server_id))
            if not guild:
                logging.error(f'Could not find server with ID {self.config.discord.server_id}')
                return None

            # Check permissions first
            if not await self.check_permissions(guild):
                logging.error("Bot does not have required permissions")
                return None

            # Add emoji to channel name
            base_channel_name = self.config.discord.channel_name
            channel_name_with_emoji = f"🎬-{base_channel_name}"
            normalized_name = channel_name_with_emoji.lower().replace(' ', '-')
            logging.info(f"Looking for channel with normalized name '{normalized_name}'")
            
            # Look for existing channel with any variant of the name
            channel = None
            for ch in guild.text_channels:
                normalized_ch_name = ch.name.lower().replace(' ', '-')
                if normalized_ch_name == normalized_name:
                    channel = ch
                    break
            
            if not channel:
                logging.info(f"Channel not found, creating new channel: {channel_name_with_emoji}")
                try:
                    # Create new channel if it doesn't exist
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(send_messages=False),
                        guild.me: discord.PermissionOverwrite(
                            send_messages=True,
                            manage_messages=True,
                            embed_links=True,
                            read_message_history=True
                        )
                    }
                    
                    channel = await guild.create_text_channel(
                        name=channel_name_with_emoji,
                        reason="Created by Tauticord for stream status",
                        overwrites=overwrites
                    )
                    logging.info(f"Successfully created channel: {channel.name} (ID: {channel.id})")
                except discord.Forbidden:
                    logging.error("Bot does not have permission to create channels")
                    return None
                except Exception as e:
                    logging.error(f"Error creating channel: {e}")
                    return None

            return channel
        except Exception as e:
            logging.error(f"Error ensuring channel exists: {e}", exc_info=True)
            return None

    async def get_status_channel(self) -> Optional[discord.TextChannel]:
        """Get the status channel."""
        try:
            guild = self.get_guild(int(self.config.discord.server_id))
            if not guild:
                logging.error(f'Could not find server with ID {self.config.discord.server_id}')
                return None

            # Create or get the channel
            channel = await self.ensure_channel_exists()
            if not channel:
                logging.error('Could not find or create status channel')
                return None

            return channel
        except Exception as e:
            logging.error(f"Error getting status channel: {e}", exc_info=True)
            return None

    async def update_status(self):
        """Update the status message with current stream information."""
        if not self.active_client:
            return

        try:
            channel = await self.get_status_channel()
            if not channel:
                return

            sessions = await self.active_client.get_sessions()
            logging.info(f"Got {len(sessions)} active sessions")
            
            # Create embed
            embed = discord.Embed(
                title="🎬 Now Playing",
                color=int(self.config.discord.embed_color, 16)
            )
            
            if not sessions:
                embed.description = "🎵 No active streams"
            else:
                # Add stream count to embed
                stream_count = len(sessions)
                embed.description = f"📊 **Active Streams:** {stream_count}"
                
                # Add each stream as a field
                for session in sessions:
                    # Format title with emoji based on media type
                    title_emoji = "🎬" if session.media_type == "movie" else "📺" if session.media_type == "episode" else "🎵"
                    
                    # Format title with show name for episodes
                    if session.media_type == "episode":
                        title = f"{title_emoji} {session.series_name} - {session.media_title}"
                    else:
                        title = f"{title_emoji} {session.media_title}"
                    
                    # Format user with emoji
                    user_line = f"👤 **User:** {session.user}"
                    
                    # Format player info with emoji
                    player_line = f"🎮 **Player:** {session.product} ({session.player})"
                    
                    # Format progress with emoji
                    progress = f"⏱️ **Progress:** {session.progress}"
                    if session.eta:
                        progress += f" (⌛ {session.eta} remaining)"
                    
                    # Format quality with emoji
                    quality_line = f"🎯 **Quality:** {session.quality_profile}"
                    
                    # Format stream state with emoji
                    state_emoji = "▶️" if session.stream_state == "playing" else "⏸️" if session.stream_state == "paused" else "⏹️"
                    state_line = f"{state_emoji} **State:** {session.stream_state.title()}"
                    
                    # Format transcoding status with emoji
                    transcode_line = ""
                    if session.transcoding:
                        transcode_line = f"\n⚡ **Transcoding:** Yes"
                    
                    # Combine all lines
                    value = f"{user_line}\n{player_line}\n{quality_line}\n{progress}\n{state_line}{transcode_line}"
                    
                    embed.add_field(name=title, value=value, inline=False)
            
            # Add timestamp
            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
            embed.set_footer(text="Last updated")
            
            if not self.status_message:
                # Find the bot's last message or create new one
                async for message in channel.history(limit=10):
                    if message.author == self.user:
                        self.status_message = message
                        break
                
                if not self.status_message:
                    self.status_message = await channel.send(embed=embed)
            else:
                # Update existing message
                await self.status_message.edit(embed=embed)
                
            logging.info("Updated status message")
                
        except Exception as e:
            logging.error(f"Error updating status: {e}", exc_info=True)

    def create_status_embed(self, stats: ServerStats) -> Optional[discord.Embed]:
        """Create status embed only if there are active streams."""
        if not stats.streams:
            return None

        embed = discord.Embed(
            title="Media Server Status",
            color=int(self.config.discord.embed_color, 16)
        )

        # Add stream information
        for stream in stats.streams:
            stream_info = []
            if self.config.display.show_media_type:
                stream_info.append(f"Type: {stream.media_type}")
            if self.config.display.show_user:
                stream_info.append(f"User: {stream.user}")
            if self.config.display.show_player_info:
                stream_info.append(f"Player: {stream.player}")
            if self.config.display.show_quality_profile:
                stream_info.append(f"Quality: {stream.quality_profile}")
            if self.config.display.show_progress and stream.duration > 0:
                progress_pct = (stream.progress / stream.duration) * 100
                stream_info.append(f"Progress: {progress_pct:.1f}%")
                
            title = stream.media_title
            value = "\n".join(stream_info)
            embed.add_field(name=title, value=value, inline=False)

        return embed

    def create_stream_embed(self, streams: List[StreamInfo]) -> discord.Embed:
        """Create an embed for the current streams."""
        embed = discord.Embed(
            title="Now Playing",
            color=int(self.config.discord.embed_color, 16)
        )

        for stream in streams:
            # Add stream information
            embed.add_field(
                name=stream.media_title,
                value=(
                    f"{stream.time_display}\n"
                    f"Stream\n"
                    f"{stream.quality_profile}"
                ),
                inline=False
            )

        return embed

    async def update_library_stats(self):
        """Update library statistics in voice channels."""
        if not self.active_client:
            return

        try:
            logging.info("Starting library stats update...")
            guild = self.get_guild(self.config.discord.server_id)
            if not guild:
                logging.error(f'Could not find server with ID {self.config.discord.server_id}')
                return
            
            # Get the category for library stats
            category_id = self.config.discord.library_stats_category_id
            logging.info(f"Looking for category with ID: {category_id}")
            category = guild.get_channel(category_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                logging.error(f'Could not library stats category with ID {category_id}')
                return
            
            # Get library stats from media server
            logging.info("Getting library stats...")
            stats = await self.active_client.get_library_stats()
            if not stats:
                logging.error("No library stats returned")
                return
            
            # Keep track of valid channel names to clean up old ones
            valid_channel_names = set()
            
            # Define emojis using Unicode characters
            MOVIE_EMOJI = "🎬"
            TV_EMOJI = "📺"
            KIDS_EMOJI = "🏠"
            ANIME_EMOJI = "👾"
            MUSIC_EMOJI = "🎵"
            
            # Create or update channels for each library
            for library in stats:
                try:
                    # Format channel name based on library type
                    library_name = library['name']
                    library_type = library['type']
                    item_count = library['count']
                    
                    # Remove "4K" from library name if we'll add it with emoji
                    display_name = library_name
                    if library['is_4k']:
                        display_name = display_name.replace('4K', '').replace('4k', '')
                        display_name = ' '.join(display_name.split())  # Clean up extra spaces
                    
                    # Choose emoji based on library type and flags
                    if library_type == 'movies':
                        if library['is_4k']:
                            emoji = f"{MOVIE_EMOJI} 4K"
                        else:
                            emoji = MOVIE_EMOJI
                    elif library_type == 'tvshows':
                        if library['is_kids']:
                            emoji = KIDS_EMOJI
                        elif library['is_anime']:
                            emoji = ANIME_EMOJI
                        elif library['is_4k']:
                            emoji = f"{TV_EMOJI} 4K"
                        else:
                            emoji = TV_EMOJI
                    elif library_type == 'music':
                        emoji = MUSIC_EMOJI
                    else:
                        emoji = "📚"
                    
                    # Create channel name
                    channel_name = f"{emoji} {display_name}: {self.format_number(item_count)}"
                    channel_name = channel_name[:100]  # Discord's limit
                    valid_channel_names.add(channel_name)
                    
                    # Update or create channel
                    await self.update_or_create_channel(category, channel_name)
                    
                except Exception as e:
                    logging.error(f"Error creating channel for library {library.get('name', 'Unknown')}: {e}")
                    continue
            
            # Clean up old channels
            for channel in category.voice_channels:
                if channel.name not in valid_channel_names:
                    logging.info(f"Deleting old channel: {channel.name}")
                    try:
                        await channel.delete()
                        logging.info(f"Deleted old channel: {channel.name}")
                    except Exception as e:
                        logging.error(f"Error deleting channel {channel.name}: {e}")
                    
        except Exception as e:
            logging.error(f"Error updating library stats: {e}", exc_info=True)

    async def update_or_create_channel(self, category: discord.CategoryChannel, channel_name: str):
        """Update or create a voice channel with the given name."""
        # Truncate to Discord's limit
        channel_name = channel_name[:100]
        
        # Find or create channel
        channel = discord.utils.get(category.voice_channels, name=channel_name)
        if not channel:
            logging.info(f"Creating channel: {channel_name}")
            try:
                await category.create_voice_channel(name=channel_name)
                logging.info(f"Created channel: {channel_name}")
            except Exception as e:
                logging.error(f"Error creating channel {channel_name}: {e}")
        else:
            logging.info(f"Channel already exists: {channel_name}")

    async def get_recently_added_channel(self) -> Optional[discord.TextChannel]:
        """Get the recently added channel, create it if it doesn't exist."""
        guild = self.get_guild(self.config.discord.server_id)
        if not guild:
            return None
            
        # Look for existing channel
        channel_name = "📥-recently-added"
        # First try to find the channel with emoji
        channel = discord.utils.get(guild.text_channels, name=channel_name)
        if not channel:
            # Try without emoji
            channel = discord.utils.get(guild.text_channels, name="recently-added")
        
        if not channel:
            # Create the channel in the library stats category
            category = guild.get_channel(self.config.discord.library_stats_category_id)
            if not category:
                return None
                
            try:
                # Create with emoji in name
                channel = await category.create_text_channel(name=channel_name)
                logging.info(f"Created recently added channel: {channel.name}")
            except Exception as e:
                logging.error(f"Error creating recently added channel: {e}")
                return None
        else:
            # If channel exists but doesn't have emoji, update it
            if channel.name != channel_name:
                try:
                    await channel.edit(name=channel_name)
                    logging.info(f"Updated channel name to include emoji: {channel_name}")
                except Exception as e:
                    logging.error(f"Error updating channel name: {e}")
                
        return channel

    async def update_recently_added(self):
        """Update the recently added channel with latest media."""
        try:
            channel = await self.get_recently_added_channel()
            if not channel:
                logging.error("Could not get recently added channel")
                return

            logging.info("Getting recently added items...")
            items = await self.active_client.get_recently_added(limit=10)
            logging.info(f"Got {len(items)} recently added items")

            if not items:
                logging.info("No recently added items to display")
                return

            # Split items by type
            movies = [item for item in items if item['Type'] == 'Movie']
            episodes = [item for item in items if item['Type'] == 'Episode']

            # Create embed
            embed = discord.Embed(
                title="📥 Recently Added",
                color=int(self.config.discord.embed_color, 16)
            )

            # Add movies section
            if movies:
                movie_list = []
                for movie in movies[:5]:  # Limit to 5 movies
                    added_date = movie['AddedDate']
                    relative_time = discord.utils.format_dt(added_date, 'R')
                    movie_list.append(f"• **{movie['Name']}** ({relative_time})")
                
                embed.add_field(
                    name="🎬 Movies",
                    value="\n".join(movie_list) if movie_list else "No movies added recently",
                    inline=False
                )

            # Add episodes section
            if episodes:
                episode_list = []
                for episode in episodes[:5]:  # Limit to 5 episodes
                    added_date = episode['AddedDate']
                    relative_time = discord.utils.format_dt(added_date, 'R')
                    series_info = f"{episode['SeriesName']} - S{episode['SeasonNumber']:02d}E{episode['EpisodeNumber']:02d}"
                    episode_list.append(f"• **{series_info}** - {episode['Name']} ({relative_time})")
                
                embed.add_field(
                    name="📺 Episodes",
                    value="\n".join(episode_list) if episode_list else "No episodes added recently",
                    inline=False
                )

            # Update or send message
            if self.recently_added_message:
                await self.recently_added_message.edit(embed=embed)
            else:
                self.recently_added_message = await channel.send(embed=embed)

        except Exception as e:
            logging.error(f"Error updating recently added items: {e}")

    def format_number(self, num: int) -> str:
        """Format a number with K/M suffix if large enough."""
        if num >= 1_000_000:
            return f"{num/1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num/1_000:.1f}K"
        return str(num)

    async def start_bot(self):
        """Start the bot."""
        await self.start(self.config.discord.bot_token)
