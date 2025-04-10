from dataclasses import dataclass
import yaml
from typing import Dict, Optional

@dataclass
class DisplayConfig:
    show_current_streams: bool = True
    show_transcoding_count: bool = False
    show_bandwidth: bool = False
    show_library_counts: bool = False
    show_stream_state: bool = True
    show_media_type: bool = True
    show_user: bool = True
    show_media_title: bool = True
    show_player_info: bool = True
    show_quality_profile: bool = True
    show_bandwidth_per_stream: bool = False
    show_transcoding_status: bool = True
    show_progress: bool = True
    show_eta: bool = True

@dataclass
class DiscordConfig:
    bot_token: str
    server_id: int
    library_stats_category_id: int
    channel_name: str = "now-playing"
    embed_color: str = "7289DA"

    def __post_init__(self):
        # Convert string ID to int if needed
        if isinstance(self.library_stats_category_id, str):
            self.library_stats_category_id = int(self.library_stats_category_id.strip("'"))

@dataclass
class EmbyConfig:
    """Emby configuration."""
    url: str
    api_key: str
    user_id: str
    verify_ssl: bool = True

@dataclass
class GeneralConfig:
    refresh_seconds: int = 5

@dataclass
class Config:
    discord: DiscordConfig
    emby: EmbyConfig
    display: DisplayConfig
    general: GeneralConfig

    @classmethod
    def from_yaml(cls, path: str) -> 'Config':
        """Load configuration from a YAML file."""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        discord_config = DiscordConfig(
            bot_token=data['Discord']['BotToken'],
            server_id=int(str(data['Discord']['ServerID']).strip("'")),  # Handle string or int
            library_stats_category_id=data['Discord'].get('LibraryStatsCategoryID', 0),
            channel_name=data['Discord'].get('ChannelName', "now-playing"),
            embed_color=data['Discord'].get('EmbedColor', "7289DA")
        )

        emby_config = EmbyConfig(
            url=data['Emby']['URL'],
            api_key=data['Emby']['APIKey'],
            user_id=data['Emby'].get('UserID', ''),
            verify_ssl=not data['Emby'].get('UseSelfSignedCert', False)
        )

        display_config = DisplayConfig(
            show_current_streams=data['Display']['ShowCurrentStreams'],
            show_transcoding_count=data['Display']['ShowTranscodingCount'],
            show_bandwidth=data['Display']['ShowBandwidth'],
            show_library_counts=data['Display']['ShowLibraryCounts'],
            show_stream_state=data['Display']['ShowStreamState'],
            show_media_type=data['Display']['ShowMediaType'],
            show_user=data['Display']['ShowUser'],
            show_media_title=data['Display']['ShowMediaTitle'],
            show_player_info=data['Display']['ShowPlayerInfo'],
            show_quality_profile=data['Display']['ShowQualityProfile'],
            show_bandwidth_per_stream=data['Display']['ShowBandwidthPerStream'],
            show_transcoding_status=data['Display']['ShowTranscodingStatus'],
            show_progress=data['Display']['ShowProgress'],
            show_eta=data['Display']['ShowETA']
        )

        general_config = GeneralConfig(
            refresh_seconds=data['General']['RefreshSeconds']
        )

        return cls(
            discord=discord_config,
            emby=emby_config,
            display=display_config,
            general=general_config
        )
