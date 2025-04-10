from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

@dataclass
class StreamInfo:
    """Information about a media stream."""
    user: str
    media_type: str
    media_title: str
    product: str
    player: str
    quality_profile: str
    progress: str
    eta: Optional[str]
    stream_state: str
    transcoding: bool

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)

@dataclass
class ServerStats:
    """Statistics about the media server."""
    total_streams: int
    transcoding_streams: int
    total_bandwidth: float
    lan_bandwidth: float
    remote_bandwidth: float
    streams: List[StreamInfo]

    def __getitem__(self, key: str):
        """Make the class subscriptable."""
        return getattr(self, key)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'total_streams': self.total_streams,
            'transcoding_streams': self.transcoding_streams,
            'total_bandwidth': self.total_bandwidth,
            'lan_bandwidth': self.lan_bandwidth,
            'remote_bandwidth': self.remote_bandwidth,
            'streams': [stream.to_dict() for stream in self.streams]
        }

class MediaServer(ABC):
    """Abstract base class for media server implementations."""
    
    @abstractmethod
    async def get_server_info(self) -> Dict:
        """Get basic server information."""
        pass
    
    @abstractmethod
    async def get_libraries(self) -> List[Dict]:
        """Get all media libraries."""
        pass
    
    @abstractmethod
    async def get_library_items_count(self, library_id: str) -> Dict:
        """Get item count for a specific library."""
        pass
    
    @abstractmethod
    async def get_sessions(self) -> List[Dict]:
        """Get all active sessions."""
        pass
    
    @abstractmethod
    async def get_transcoding_info(self) -> List[Dict]:
        """Get information about current transcoding sessions."""
        pass
    
    @abstractmethod
    async def get_all_stream_info(self) -> ServerStats:
        """Get comprehensive streaming information."""
        pass
