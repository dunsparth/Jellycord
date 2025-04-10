import discord
import consts
import modules.logs as logging
import modules.settings.models
from modules import emojis
from modules.discord import discord_utils
from modules.media_server import ServerStats, StreamInfo
from modules.emojis import EmojiManager
from modules.tasks.voice_category_stats import VoiceCategoryStatsMonitor
from modules.emby import EmbyClient
from modules.versioning import VersionChecker


class ActivityStatsAndSummaryMessage(VoiceCategoryStatsMonitor):
    """
    A cron-based service loop that updates the live activity voice channel stats and summary text message.
    """

    def __init__(self,
                 discord_client,
                 settings: modules.settings.models.ActivityStats,
                 emby_client: EmbyClient,
                 guild_id: int,
                 message: discord.Message,
                 enable_stream_termination_if_possible: bool,
                 discord_status_settings: modules.settings.models.DiscordStatusMessage,
                 emoji_manager: EmojiManager,
                 version_checker: VersionChecker,
                 voice_category: discord.CategoryChannel = None):
        super().__init__(discord_client=discord_client,
                         guild_id=guild_id,
                         service_entrypoint=self.update_activity_details,
                         voice_category=voice_category)
        self.message = message
        self.enable_stream_termination_if_possible = enable_stream_termination_if_possible
        self.stats_settings = settings
        self.discord_status_settings = discord_status_settings
        self.emby = emby_client
        self.emoji_manager = emoji_manager
        self.version_checker = version_checker

    async def update_activity_stats(self,
                                    stats: ServerStats) -> None:

        logging.info("Updating activity stats...")

        # Only got here because activity stats are enabled, no need to check

        if self.stats_settings.plex_availability.enable:
            settings = self.stats_settings.plex_availability
            status_emoji = self.emoji_manager.get_emoji(key="online" if stats.is_online else "offline")
            logging.debug(f"Updating {settings.name} voice channel with new status: {status_emoji}")
            await self.edit_stat_voice_channel(voice_channel_settings=settings,
                                               stat=status_emoji)  # Always use an emoji for status

        # Only proceed if activity information was returned from Emby (server could be offline)
        if stats:
            if self.stats_settings.stream_count.enable:
                settings = self.stats_settings.stream_count
                count = len(stats.streams)
                logging.debug(f"Updating {settings.name} voice channel with new stream count: {count}")
                await self.edit_stat_voice_channel(voice_channel_settings=settings,
                                                   stat=count)

            if self.stats_settings.transcode_count.enable:
                settings = self.stats_settings.transcode_count
                count = sum(1 for s in stats.streams if s.is_transcoding)
                logging.debug(f"Updating {settings.name} voice channel with new transcode count: {count}")
                await self.edit_stat_voice_channel(voice_channel_settings=settings,
                                                   stat=count)

            if self.stats_settings.bandwidth.enable:
                settings = self.stats_settings.bandwidth
                bandwidth = stats.total_bandwidth
                logging.debug(f"Updating {settings.name} voice channel with new bandwidth: {bandwidth}")
                await self.edit_stat_voice_channel(voice_channel_settings=settings,
                                                   stat=bandwidth)

            if self.stats_settings.local_bandwidth.enable:
                settings = self.stats_settings.local_bandwidth
                bandwidth = stats.lan_bandwidth
                logging.debug(f"Updating {settings.name} voice channel with new local bandwidth: {bandwidth}")
                await self.edit_stat_voice_channel(voice_channel_settings=settings,
                                                   stat=bandwidth)

            if self.stats_settings.remote_bandwidth.enable:
                settings = self.stats_settings.remote_bandwidth
                bandwidth = stats.remote_bandwidth
                logging.debug(f"Updating {settings.name} voice channel with new remote bandwidth: {bandwidth}")
                await self.edit_stat_voice_channel(voice_channel_settings=settings,
                                                   stat=bandwidth)

    async def add_stream_number_emoji_reactions(self,
                                                count: int,
                                                emoji_manager: EmojiManager):
        """
        Add reactions to a message for user interaction
        :param count: how many emojis to add
        :param emoji_manager: EmojiManager
        :return: None
        """
        # Only add reactions if necessary, and remove unnecessary reactions
        cache_msg = await self.message.channel.fetch_message(self.message.id)
        msg_emoji = [str(r.emoji) for r in cache_msg.reactions]

        # thanks twilsonco
        if count <= 0:
            if len(msg_emoji) > 0:
                await self.message.clear_reactions()
            return

        if count > emojis.max_controllable_stream_count_supported():
            logging.debug(
                f"""Jellycord supports controlling a maximum of {emojis.max_controllable_stream_count_supported()} streams.
            Stats will be displayed correctly, but any additional streams will not be able to be terminated.""")
            count = emojis.max_controllable_stream_count_supported()

        emoji_to_remove = []

        for i, e in enumerate(msg_emoji):
            if i >= count:  # ex. 5 streams, 6 reactions
                emoji_to_remove.append(e)
            elif not emoji_manager.is_valid_emoji_for_stream_number(emoji=e,
                                                                    number=i + 1):  # "6" emoji used for stream 5
                emoji_to_remove.append(e)

        # if all reactions need to be removed, do it all at once
        if len(emoji_to_remove) == len(msg_emoji):
            await self.message.clear_reactions()
            msg_emoji = []
        else:
            for e in emoji_to_remove:
                await self.message.clear_reaction(e)
                del (msg_emoji[msg_emoji.index(e)])

        for i in range(1, count + 1):
            emoji = emoji_manager.reaction_from_stream_number(i)
            if emoji not in msg_emoji:
                await self.message.add_reaction(emoji)

    async def update_activity_summary_message(self,
                                              stats: ServerStats) -> None:
        """
        For performance and aesthetics, edit the old message if:
        1) the old message is the newest message in the channel, or
        2) if the only messages that are newer were written by this bot
        (which would be stream stop messages that have already been deleted)
        """
        await self.message.clear_reactions()

        if not stats:
            # error when refreshing Emby data, new_message is string (i.e. "Connection lost")
            logging.debug("Editing old message with Emby error...")
        else:
            logging.debug('Editing old message...')

        # update the message regardless of whether the content has changed
        self.message = await discord_utils.send_embed_message(embed=self.format_activity_message(stats=stats), message=self.message)

        if self.emby.plex_pass_feature_is_allowed(feature=self.enable_stream_termination_if_possible,
                                                  warning="Stream termination control requires Plex Pass, ignoring setting..."):
            await self.add_stream_number_emoji_reactions(count=len(stats.streams),
                                                         emoji_manager=self.emoji_manager)
            # on_raw_reaction_add will handle the rest

    async def update_activity_details(self) -> None:
        """
        Collect new summary info, replace old message with new one (if enabled), update stats voice channels (if enabled)
        """

        embed_fields = []
        if self.version_checker.is_new_version_available():
            embed_fields.append(
                {"name": "🔔 New Version Available",
                 "value": f"A new version of Jellycord is available! [Click here]({consts.GITHUB_REPO_FULL_LINK}) to download it."})

        stats = await self.emby.get_all_stream_info()

        if self.stats_settings.enable:
            await self.update_activity_stats(stats=stats)

        if self.discord_status_settings.should_update_with_activity:
            activity_name = self.discord_status_settings.activity_name
            message = self.discord_status_settings.message(stream_count=0)
            await discord_utils.update_presence(client=self.discord_client,
                                                activity_name=activity_name,
                                                line_one=message)

        if self.message:  # Set in the constructor, indicates that a summary message should be sent
            await self.update_activity_summary_message(stats=stats)

    def format_activity_message(self, stats: ServerStats) -> discord.Embed:
        embed = discord.Embed(title="Activity Summary", color=0x3498db)

        if not stats:
            embed.add_field(name="Error", value="Unable to get server stats", inline=False)
            return embed

        stream_count = len(stats.streams)
        if stream_count > 0:
            embed.add_field(name="Active Streams", value=str(stream_count), inline=False)

            transcode_count = sum(1 for s in stats.streams if s.is_transcoding)
            if transcode_count > 0:
                embed.add_field(name="Transcoding", value=str(transcode_count), inline=False)

            if stats.total_bandwidth > 0:
                embed.add_field(name="Total Bandwidth", value=f"{stats.total_bandwidth / 1024:.1f} Mbps", inline=False)
                if stats.lan_bandwidth > 0:
                    embed.add_field(name="LAN Bandwidth", value=f"{stats.lan_bandwidth / 1024:.1f} Mbps", inline=False)
                if stats.remote_bandwidth > 0:
                    embed.add_field(name="Remote Bandwidth", value=f"{stats.remote_bandwidth / 1024:.1f} Mbps", inline=False)

            embed.add_field(name="Current Streams", value="\n".join(self.format_stream_info(stream) for stream in stats.streams), inline=False)
        else:
            embed.add_field(name="Active Streams", value="0", inline=False)

        return embed

    def format_stream_info(self, stream: StreamInfo) -> str:
        try:
            # Format media info
            if stream.media_type == "episode":
                media_title = f"{stream.series_name} - S{stream.season_number:02d}E{stream.episode_number:02d}"
                if stream.episode_name:
                    media_title += f" - {stream.episode_name}"
            else:
                media_title = stream.title

            # Get state emoji
            state_emoji = "▶️" if stream.state == "playing" else "⏸️" if stream.state == "paused" else "⏹️"

            # Format quality info
            quality_info = []
            if stream.video_resolution:
                quality_info.append(stream.video_resolution)
            if stream.video_codec:
                quality_info.append(stream.video_codec)
            if stream.audio_codec:
                quality_info.append(stream.audio_codec)

            # Build lines
            lines = [
                f"{state_emoji} **{stream.username}** is watching:",
                f"📺 **{media_title}**",
                f"🎯 **Quality:** {' '.join(quality_info) if quality_info else 'Unknown'}"
            ]

            # Add progress if available
            if stream.progress and stream.duration:
                progress_pct = (stream.progress / stream.duration) * 100
                lines.append(f"⏱️ **Progress:** {progress_pct:.1f}%")

            # Add player info
            if stream.player:
                lines.append(f"📱 **Player:** {stream.player}")

            # Add bandwidth info if available
            if stream.bandwidth:
                lines.append(f"📊 **Bandwidth:** {stream.bandwidth / 1024:.1f} Mbps")

            # Add transcoding info
            if stream.is_transcoding:
                lines.append("🔄 **Transcoding:** Yes")

            return "\n".join(lines)

        except Exception as e:
            logging.error(f"Error formatting stream info: {e}")
            return "Error formatting stream info"
