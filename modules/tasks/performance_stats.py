from typing import Dict, Optional

import discord
import psutil

import modules.settings.models as settings_models
from modules.emojis import EmojiManager
from modules.utils import quote


class PerformanceMonitor:
    """
    A cron-based service loop that updates the performance stats voice channels.
    """

    def __init__(self,
                 discord_client,
                 emby_client,
                 settings: settings_models.PerformanceStats,
                 guild_id: int,
                 emoji_manager: EmojiManager,
                 voice_category: discord.CategoryChannel = None):
        self.discord_client = discord_client
        self.emby = emby_client
        self.settings = settings
        self.guild_id = guild_id
        self.emoji_manager = emoji_manager
        self.voice_category = voice_category

    async def get_cpu_usage(self) -> float:
        """Get CPU usage percentage."""
        try:
            return psutil.cpu_percent(interval=1)
        except Exception as e:
            logging.error(f"Error getting CPU usage: {e}")
            return 0.0

    async def get_memory_usage(self) -> Dict[str, float]:
        """Get memory usage in GB."""
        try:
            memory = psutil.virtual_memory()
            return {
                'total': memory.total / (1024 ** 3),  # Convert to GB
                'used': memory.used / (1024 ** 3),
                'percent': memory.percent
            }
        except Exception as e:
            logging.error(f"Error getting memory usage: {e}")
            return {'total': 0, 'used': 0, 'percent': 0}

    async def get_disk_usage(self, path: str = '/') -> Dict[str, float]:
        """Get disk usage in GB for a given path."""
        try:
            disk = psutil.disk_usage(path)
            return {
                'total': disk.total / (1024 ** 3),  # Convert to GB
                'used': disk.used / (1024 ** 3),
                'percent': disk.percent
            }
        except Exception as e:
            logging.error(f"Error getting disk usage for {path}: {e}")
            return {'total': 0, 'used': 0, 'percent': 0}

    async def update_performance_stats(self) -> None:
        """Update performance statistics."""
        try:
            # CPU Usage
            if self.settings.cpu.enable:
                cpu_percent = await self.get_cpu_usage()
                await self.edit_stat_voice_channel(
                    voice_channel_settings=self.settings.cpu,
                    stat=cpu_percent)

            # Memory Usage
            if self.settings.memory.enable:
                memory = await self.get_memory_usage()
                await self.edit_stat_voice_channel(
                    voice_channel_settings=self.settings.memory,
                    stat=memory['percent'])

            # Disk Space
            if self.settings.disk_space.enable:
                for path_settings in self.settings.disk_space.paths:
                    if path_settings.enable and os.path.exists(path_settings.path):
                        disk = await self.get_disk_usage(path_settings.path)
                        await self.edit_stat_voice_channel(
                            voice_channel_settings=path_settings,
                            stat=disk['percent'])

            # Get Emby server info for stream bandwidth
            if self.settings.stream_bandwidth.enable:
                stats = await self.emby.get_all_stream_info()
                if stats:
                    await self.edit_stat_voice_channel(
                        voice_channel_settings=self.settings.stream_bandwidth,
                        stat=stats.total_bandwidth / 1024)  # Convert to Mbps

        except Exception as e:
            logging.error(f"Error updating performance stats: {e}")

    async def edit_stat_voice_channel(self,
                                      voice_channel_settings: settings_models.VoiceChannelSettings,
                                      stat: Optional[float] = None) -> None:
        """Edit a voice channel with a given stat."""
        if not voice_channel_settings.voice_channel_id:
            logging.error(f"No voice channel ID found for {quote(voice_channel_settings.name)}")
            return

        voice_channel = self.discord_client.get_channel(voice_channel_settings.voice_channel_id)
        if not voice_channel:
            logging.error(f"Could not find voice channel {voice_channel_settings.voice_channel_id} for {quote(voice_channel_settings.name)}")
            return

        if stat is None:
            logging.error(f"No stat found for {quote(voice_channel_settings.name)}")
            return

        try:
            await voice_channel.edit(name=voice_channel_settings.format_name(stat))
        except Exception as e:
            logging.error(f"Error editing voice channel {voice_channel_settings.voice_channel_id} for {quote(voice_channel_settings.name)}: {e}")
