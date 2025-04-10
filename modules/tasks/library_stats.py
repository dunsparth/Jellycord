import discord
import asyncio
import logging
from typing import Dict, List

import modules.settings.models as settings_models
from modules.emojis import EmojiManager
from modules.discord.services.base_service import BaseService
import modules.logs as logging


class LibraryStats(BaseService):
    """
    A cron-based service loop that updates the library stats voice channels.
    """

    def __init__(self,
                 discord_client,
                 emby_client,
                 settings: settings_models.LibraryStats,
                 guild_id: int,
                 emoji_manager: EmojiManager,
                 voice_category: discord.CategoryChannel = None):
        super().__init__(discord_client=discord_client)
        self.emby = emby_client
        self.settings = settings
        self.guild_id = guild_id
        self.emoji_manager = emoji_manager
        self.voice_category = voice_category

    async def update_library_stats_for_library(self,
                                               library_settings: settings_models.BaseLibrary,
                                               item_counts: Dict[str, int]) -> None:
        """
        Update the individual stat voice channels for a single library/combined library
        (e.g. "My Library" - Movies, Shows, Episodes, Artists, Albums, Tracks)
        """
        if not item_counts:
            return

        for library_type, item_count in item_counts.items():
            if library_type == 'movies':
                if library_settings.voice_channels.movie.enable:
                    await self.edit_stat_voice_channel(voice_channel_settings=library_settings.voice_channels.movie,
                                                       stat=item_count)
            elif library_type == 'tvshows':
                if library_settings.voice_channels.series.enable:
                    await self.edit_stat_voice_channel(voice_channel_settings=library_settings.voice_channels.series,
                                                       stat=item_count)
                if library_settings.voice_channels.episode.enable:
                    await self.edit_stat_voice_channel(voice_channel_settings=library_settings.voice_channels.episode,
                                                       stat=item_count)
            elif library_type == 'music':
                if library_settings.voice_channels.artist.enable:
                    await self.edit_stat_voice_channel(voice_channel_settings=library_settings.voice_channels.artist,
                                                       stat=item_count)
                if library_settings.voice_channels.album.enable:
                    await self.edit_stat_voice_channel(voice_channel_settings=library_settings.voice_channels.album,
                                                       stat=item_count)
                if library_settings.voice_channels.track.enable:
                    await self.edit_stat_voice_channel(voice_channel_settings=library_settings.voice_channels.track,
                                                       stat=item_count)

    async def update_library_stats(self) -> None:
        """
        Update the individual stat voice channels for each regular library and each combined library
        """
        logging.info("Updating library stats...")

        # Only got here because library stats are enabled, no need to check

        # Regular libraries
        for library_settings in self.settings.libraries:
            item_counts: Dict[str, int] = await self.emby.get_library_item_counts(library_name=library_settings.name)

            await self.update_library_stats_for_library(library_settings=library_settings, item_counts=item_counts)

            if library_settings.voice_channels.recently_added.enable:
                minutes = library_settings.voice_channels.recently_added.hours * 60
                recently_added_count: int = await self.emby.get_recently_added_count_for_library(
                    library_name=library_settings.name,
                    minutes=minutes)

                await self.edit_stat_voice_channel(
                    voice_channel_settings=library_settings.voice_channels.recently_added,
                    stat=recently_added_count)

        # Combined libraries
        for library_settings in self.settings.combined_libraries:
            item_counts: Dict[str, int] = await self.emby.get_library_item_counts_for_multiple_combined_libraries(
                combined_library_name=library_settings.name,
                sub_libraries=library_settings.libraries)

            await self.update_library_stats_for_library(library_settings=library_settings, item_counts=item_counts)

            if library_settings.voice_channels.recently_added.enable:
                minutes = library_settings.voice_channels.recently_added.hours * 60
                recently_added_count: int = await self.emby.get_recently_added_count_for_combined_libraries(
                    sub_libraries=library_settings.libraries,
                    minutes=minutes)

                await self.edit_stat_voice_channel(
                    voice_channel_settings=library_settings.voice_channels.recently_added,
                    stat=recently_added_count)

    async def run(self) -> None:
        """Run the library stats update loop."""
        while not self.is_closed():
            try:
                if self.settings.enable:
                    await self.update_library_stats()
                await asyncio.sleep(self.settings.refresh_interval_seconds)
            except Exception as e:
                logging.error(f"Error in library stats loop: {e}")
                await asyncio.sleep(5)  # Wait a bit before retrying
