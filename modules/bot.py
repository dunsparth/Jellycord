import discord
from discord.ext import tasks
import logging
from typing import Optional, List
from .config import Config
from api.clients.emby_client import EmbyClient, StreamInfo
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
        self.emby_client = None  # Will be initialized in setup_hook

    async def setup_hook(self) -> None:
        """Set up the bot."""
        # Initialize API clients
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
        
        # Start background tasks
        self.bg_task = self.loop.create_task(self.status_update_loop())
        logging.info("Started status update loop")

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
        try:
            channel = await self.get_status_channel()
            if not channel:
                return

            sessions = await self.emby_client.get_sessions()
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
                logging.error(f'Could not find library stats category with ID {category_id}')
                return
            
            # Get library stats from Emby
            logging.info("Getting library stats from Emby...")
            library_stats = await self.emby_client.get_library_stats()
            if not library_stats:
                logging.error("No library stats returned from Emby")
                return
            
            # Keep track of valid channel names to clean up old ones
            valid_channel_names = set()
            
            # Define emojis using Unicode characters
            MOVIE_EMOJI = "🎬"
            TV_EMOJI = "📺"
            MUSIC_EMOJI = "🎵"
            KIDS_EMOJI = "🏠"
            ANIME_EMOJI = "👾"
            
            # Update or create voice channels for each library
            for stats in library_stats:
                # Format channel name based on library type
                if stats['Type'] == 'movies':
                    if stats.get('Is4K'):
                        channel_name = f"{MOVIE_EMOJI} 4K Movies: {self.format_number(stats['ItemCount'])}"
                    else:
                        channel_name = f"{MOVIE_EMOJI} Movies: {self.format_number(stats['ItemCount'])}"
                elif stats['Type'] == 'tvshows':
                    if stats.get('IsKids'):
                        channel_name = f"{KIDS_EMOJI} Kids TV: {self.format_number(stats['ItemCount'])}"
                    elif stats.get('IsAnime'):
                        channel_name = f"{ANIME_EMOJI} Anime: {self.format_number(stats['ItemCount'])}"
                    elif stats.get('Is4K'):
                        channel_name = f"{TV_EMOJI} 4K TV Shows: {self.format_number(stats['ItemCount'])}"
                    else:
                        channel_name = f"{TV_EMOJI} TV Shows: {self.format_number(stats['ItemCount'])}"
                elif stats['Type'] == 'music':
                    channel_name = f"{MUSIC_EMOJI} Music: {self.format_number(stats['ItemCount'])}"
                else:
                    channel_name = f"{stats['Name']}: {self.format_number(stats['ItemCount'])}"
                
                # Truncate to Discord's limit
                channel_name = channel_name[:100]
                valid_channel_names.add(channel_name)
                
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
                    logging.info(f"Updating channel: {channel_name}")
                    try:
                        await channel.edit(name=channel_name)
                        logging.info(f"Updated channel: {channel_name}")
                    except Exception as e:
                        logging.error(f"Error updating channel {channel_name}: {e}")
            
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
            items = await self.emby_client.get_recently_added(limit=10)
            logging.info(f"Got {len(items)} recently added items")

            if not items:
                logging.info("No recently added items to display")
                return

            # Create embed
            embed = discord.Embed(
                title="📥 Recently Added Media",
                color=int(self.config.discord.embed_color, 16),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )

            # Group items by type
            movies = [item for item in items if item['type'] == 'movie']
            episodes = [item for item in items if item['type'] == 'episode']
            series = [item for item in items if item['type'] == 'series']
            seasons = [item for item in items if item['type'] == 'season']
            music_videos = [item for item in items if item['type'] == 'musicvideo']
            audio = [item for item in items if item['type'] == 'audio']

            # Add movies
            if movies:
                movie_text = "\n".join([f"• {item['title']} ({item['added']})" for item in movies])
                embed.add_field(name="🎬 Movies", value=movie_text, inline=False)

            # Add episodes
            if episodes:
                episode_text = "\n".join([f"• {item['title']} ({item['added']})" for item in episodes])
                embed.add_field(name="📺 Episodes", value=episode_text, inline=False)
                
            # Add series
            if series:
                series_text = "\n".join([f"• {item['title']} ({item['added']})" for item in series])
                embed.add_field(name="📺 Series", value=series_text, inline=False)
                
            # Add seasons
            if seasons:
                season_text = "\n".join([f"• {item['title']} ({item['added']})" for item in seasons])
                embed.add_field(name="🗂️ Seasons", value=season_text, inline=False)
                
            # Add music videos
            if music_videos:
                mv_text = "\n".join([f"• {item['title']} ({item['added']})" for item in music_videos])
                embed.add_field(name="🎵 Music Videos", value=mv_text, inline=False)
                
            # Add audio
            if audio:
                audio_text = "\n".join([f"• {item['title']} ({item['added']})" for item in audio])
                embed.add_field(name="🎧 Audio", value=audio_text, inline=False)

            # Update the channel
            if not self.recently_added_message:
                # Find the bot's last message or create new one
                async for message in channel.history(limit=10):
                    if message.author == self.user:
                        self.recently_added_message = message
                        break
                
                if not self.recently_added_message:
                    self.recently_added_message = await channel.send(embed=embed)
            else:
                # Update existing message
                await self.recently_added_message.edit(embed=embed)

            logging.info("Updated recently added channel")

        except Exception as e:
            logging.error(f"Error updating recently added: {e}", exc_info=True)

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
