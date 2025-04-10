import aiohttp
import logging
from typing import Dict, List, Optional
from modules.media_server import StreamInfo, ServerStats
import datetime
from dataclasses import dataclass

@dataclass
class StreamInfo:
    """Information about a media stream."""
    user: str
    media_type: str
    media_title: str
    series_name: str
    product: str
    player: str
    quality_profile: str
    progress: str
    eta: Optional[str]
    stream_state: str
    transcoding: bool

class EmbyClient:
    def __init__(self, base_url: str, api_key: str, user_id: str, use_ssl: bool = False):
        """Initialize the Emby API client.
        
        Args:
            base_url: Base URL of the Emby server (e.g., http://localhost:8096)
            api_key: API key for authentication
            user_id: User ID for authentication
            use_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.user_id = user_id
        self.verify_ssl = use_ssl
        self.headers = {
            'X-Emby-Token': api_key,
            'Accept': 'application/json'
        }

    async def _make_request(self, endpoint: str, method: str = 'GET', params: Dict = None, data: Dict = None) -> Dict:
        """Make a request to the Emby API."""
        url = f"{self.base_url}{endpoint}"
        headers = {
            'X-Emby-Token': self.api_key,
            'Accept': 'application/json'
        }

        try:
            async with aiohttp.ClientSession() as session:
                logging.info(f"Making {method} request to {url}")
                if params:
                    logging.info(f"With params: {params}")
                if data:
                    logging.info(f"With data: {data}")
                    
                async with session.request(method, url, headers=headers, params=params, json=data, ssl=self.verify_ssl) as response:
                    if response.status == 204:  # No content
                        logging.info("Received 204 No Content response")
                        return {}
                        
                    if response.status >= 400:
                        text = await response.text()
                        logging.error(f"API request failed: {response.status} - {text}")
                        raise Exception(f"API request failed: {response.status} - {text}")
                    
                    response_data = await response.json()
                    logging.info(f"Response data: {response_data}")
                    return response_data
        except Exception as e:
            logging.error(f"Error making request to {url}: {e}", exc_info=True)
            raise

    async def get_sessions(self) -> List[StreamInfo]:
        """Get active (Now Playing) sessions only."""
        try:
            logging.info("Getting sessions from Emby...")
            sessions = await self._make_request('/Sessions')
            logging.info(f"Raw Emby sessions response: {sessions}")
            
            active_sessions = []
            for session in sessions:
                # Check if session has NowPlayingItem and is not idle
                now_playing = session.get('NowPlayingItem')
                play_state = session.get('PlayState', {})
                
                if now_playing and play_state.get('PositionTicks', 0) > 0:
                    logging.info(f"Found active session with NowPlayingItem: {now_playing}")
                    parsed_session = self.parse_session_info(session)
                    if parsed_session:
                        logging.info(f"Successfully parsed session: {parsed_session}")
                        active_sessions.append(parsed_session)
                    else:
                        logging.error("Failed to parse session")
                else:
                    logging.info("Skipping inactive or empty session")
            
            logging.info(f"Found {len(active_sessions)} active sessions")
            return active_sessions
        except Exception as e:
            logging.error(f"Error getting sessions: {e}", exc_info=True)
            return []

    def parse_session_info(self, session: Dict) -> StreamInfo:
        """Parse session information into a standardized format."""
        try:
            logging.info(f"Parsing session: {session}")
            transcoding = session.get('TranscodingInfo', {})
            playback_info = session.get('PlayState', {})
            now_playing = session.get('NowPlayingItem', {})
            
            # Get series and episode info
            series_name = now_playing.get('SeriesName', '')
            season_number = now_playing.get('ParentIndexNumber', 0)
            episode_number = now_playing.get('IndexNumber', 0)
            episode_name = now_playing.get('Name', 'unknown')
            
            # Format media title based on type
            media_type = now_playing.get('Type', '').lower()
            if media_type == 'episode':
                media_title = f"{series_name} - S{season_number:02d}E{episode_number:02d} - {episode_name}"
            else:
                media_title = now_playing.get('Name', 'Unknown')

            # Get progress information
            position_ticks = playback_info.get('PositionTicks', 0)
            runtime_ticks = now_playing.get('RunTimeTicks', 0)
            
            # Convert ticks to seconds (1 tick = 10,000 nanoseconds)
            position_seconds = position_ticks / 10_000_000 if position_ticks else 0
            runtime_seconds = runtime_ticks / 10_000_000 if runtime_ticks else 0
            
            # Format progress
            if position_seconds and runtime_seconds:
                position_time = str(datetime.timedelta(seconds=int(position_seconds)))
                total_time = str(datetime.timedelta(seconds=int(runtime_seconds)))
                progress = f"{position_time}/{total_time}"
                
                # Calculate ETA
                remaining_seconds = runtime_seconds - position_seconds
                if remaining_seconds > 0:
                    eta = str(datetime.timedelta(seconds=int(remaining_seconds)))
                else:
                    eta = None
            else:
                progress = "Unknown"
                eta = None
            
            # Get quality profile
            if transcoding:
                video_codec = transcoding.get('VideoCodec', '')
                audio_codec = transcoding.get('AudioCodec', '')
                width = transcoding.get('Width', 0)
                height = transcoding.get('Height', 0)
                bitrate = transcoding.get('Bitrate', 0)
                
                if width and height:
                    quality = f"{width}x{height}"
                    if bitrate:
                        quality += f" {bitrate/1000:.1f}Mbps"
                    if video_codec:
                        quality += f" ({video_codec})"
                else:
                    quality = "Unknown"
            else:
                # Direct play
                width = now_playing.get('Width', 0)
                height = now_playing.get('Height', 0)
                bitrate = now_playing.get('Bitrate', 0)
                
                if width and height:
                    quality = f"{width}x{height}"
                    if bitrate:
                        quality += f" {bitrate/1000:.1f}Mbps"
                    quality += " (direct)"
                else:
                    quality = "Direct"
            
            # Create StreamInfo object
            stream_info = StreamInfo(
                user=session.get('UserName', 'Unknown'),
                media_type=media_type,
                media_title=media_title,
                series_name=series_name,
                product=session.get('Client', 'Unknown'),
                player=session.get('DeviceName', 'Unknown'),
                quality_profile=quality,
                progress=progress,
                eta=eta,
                stream_state=playback_info.get('PlayState', 'playing').lower(),
                transcoding=bool(transcoding)
            )
            
            logging.info(f"Created StreamInfo: {stream_info}")
            return stream_info
            
        except Exception as e:
            logging.error(f"Error parsing session info: {e}", exc_info=True)
            return None

    async def get_server_info(self) -> Dict:
        """Get server information."""
        return await self._make_request('/System/Info')

    async def get_libraries(self) -> Dict:
        """Get all libraries from Emby."""
        try:
            response = await self._make_request('/Library/MediaFolders')
            logging.debug(f"Got libraries response: {response}")
            return response
        except Exception as e:
            logging.error(f"Error getting libraries: {e}")
            return {'Items': []}

    async def get_library_items_count(self, library_id: str) -> Dict:
        """Get item count for a specific library."""
        return await self._make_request(f'/Items/Counts')

    async def get_transcoding_info(self) -> List[Dict]:
        """Get information about current transcoding sessions."""
        sessions = await self.get_sessions()
        return [
            session for session in sessions
            if session.get('TranscodingInfo') is not None
        ]

    async def get_all_stream_info(self) -> ServerStats:
        """Get comprehensive streaming information.
        
        Returns:
            ServerStats object containing all stream information
        """
        sessions = await self.get_sessions()
        
        total_bandwidth = 0
        lan_bandwidth = 0
        remote_bandwidth = 0
        
        for session in sessions:
            bandwidth = session.get('TranscodingInfo', {}).get('Bitrate', 0)
            if bandwidth:
                total_bandwidth += bandwidth
                if session.get('RemoteEndPoint', '').startswith(('10.', '172.16.', '192.168.')):
                    lan_bandwidth += bandwidth
                else:
                    remote_bandwidth += bandwidth
        
        return ServerStats(
            current_streams=len(sessions),
            transcoding_streams=len([s for s in sessions if s.get('TranscodingInfo') is not None]),
            total_bandwidth=total_bandwidth,
            lan_bandwidth=lan_bandwidth,
            remote_bandwidth=remote_bandwidth,
            streams=sessions
        )

    async def get_library_stats(self) -> List[Dict]:
        """Get statistics for all libraries."""
        try:
            # Get all libraries
            libraries = await self.get_libraries()
            logging.debug(f"Got libraries: {libraries}")
            library_stats = []
            
            for library in libraries['Items']:
                try:
                    # Skip collections
                    if library['Name'].lower() == 'collections':
                        continue
                        
                    logging.debug(f"Processing library: {library['Name']}")
                    
                    # Determine library flags
                    is_4k = '4k' in library['Name'].lower()
                    is_kids = 'kids' in library['Name'].lower()
                    is_anime = 'anime' in library['Name'].lower()
                    
                    # Build query based on library type and 4K status
                    base_query = {
                        'ParentId': library['Id'],
                        'Recursive': 'true',
                        'Fields': 'Width',
                        'ImageTypeLimit': 0
                    }
                    
                    if is_4k:
                        base_query['MinWidth'] = 3840  # Filter for 4K content
                    elif not (is_kids or is_anime):  # Don't apply width filter to kids or anime content
                        base_query['MaxWidth'] = 3839  # Filter for non-4K content
                    
                    if library['CollectionType'] == 'movies':
                        base_query['IncludeItemTypes'] = 'Movie'
                    elif library['CollectionType'] == 'tvshows':
                        base_query['IncludeItemTypes'] = 'Series'
                    elif library['CollectionType'] == 'music':
                        base_query['IncludeItemTypes'] = 'Audio,MusicAlbum'
                    else:
                        continue  # Skip other library types
                    
                    # Get items with the specific query
                    items = await self._make_request('/Items', params=base_query)
                    total_count = items.get('TotalRecordCount', 0)
                    logging.debug(f"Got items for {library['Name']}: Total={total_count}")
                    
                    if total_count == 0 and library['CollectionType'] == 'tvshows':
                        # Try alternative query for TV shows
                        alt_query = {
                            'ParentId': library['Id'],
                            'Recursive': 'true',
                            'IncludeItemTypes': 'Series',
                            'ImageTypeLimit': 0
                        }
                        items = await self._make_request('/Items', params=alt_query)
                        total_count = items.get('TotalRecordCount', 0)
                        logging.debug(f"Retry TV shows query for {library['Name']}: Total={total_count}")
                    
                    # Extract relevant counts
                    stats = {
                        'Name': library['Name'],
                        'Type': library['CollectionType'],
                        'ItemCount': total_count,
                        'Is4K': is_4k,
                        'IsKids': is_kids,
                        'IsAnime': is_anime
                    }
                    
                    library_stats.append(stats)
                    logging.debug(f"Added stats for library {library['Name']}: {stats}")
                    
                except Exception as e:
                    logging.error(f"Error getting stats for library {library['Name']}: {e}")
                    continue
            
            logging.info(f"Final library stats: {library_stats}")
            return library_stats
            
        except Exception as e:
            logging.error(f"Error getting library stats: {e}")
            return []

    async def get_recently_added(self, limit: int = 10) -> List[Dict]:
        """Get recently added items across all libraries."""
        try:
            params = {
                'Limit': str(limit),
                'Fields': 'DateCreated,Overview,Path,PremiereDate',
                'SortBy': 'DateCreated,SortName',
                'SortOrder': 'Descending',
                'Recursive': 'true',
                'IncludeItemTypes': 'Movie,Episode,Series,Season,MusicVideo,Audio',
                'ImageTypeLimit': '1',
                'EnableImageTypes': 'Primary'
            }
            
            # First try with Latest endpoint
            logging.info("Trying Latest endpoint...")
            url = '/Users/{UserId}/Items/Latest'.format(UserId=self.user_id)
            items = await self._make_request(url, params=params)
            
            if not items:
                # If Latest endpoint returns nothing, try Items endpoint
                logging.info("Latest endpoint returned no items, trying Items endpoint...")
                params['SortBy'] = 'DateCreated'
                url = '/Users/{UserId}/Items'.format(UserId=self.user_id)
                items = await self._make_request(url, params=params)
                if isinstance(items, dict) and 'Items' in items:
                    items = items['Items']
            
            logging.info("Raw response from recently added endpoint: %s", items)
            
            if not items:
                logging.warning("No items returned from any endpoint")
                return []
                
            recent_items = []
            for item in items:
                try:
                    # Log the raw item for debugging
                    logging.info("Processing recently added item: %s", item)
                    
                    # Get basic item info
                    name = item.get('Name', 'Unknown')
                    item_type = item.get('Type', 'Unknown').lower()
                    
                    # Format title based on type
                    if item_type == 'episode':
                        series_name = item.get('SeriesName', '')
                        season_number = item.get('ParentIndexNumber', 0)
                        episode_number = item.get('IndexNumber', 0)
                        title = f"{series_name} - S{season_number:02d}E{episode_number:02d} - {name}"
                        logging.info("Formatted episode title: %s", title)
                    else:
                        title = name
                        logging.info("Using movie title: %s", title)
                    
                    # Get date added
                    date_created = item.get('DateCreated', '')
                    if date_created:
                        # Convert to relative time
                        date_created = datetime.datetime.fromisoformat(date_created.replace('Z', '+00:00'))
                        now = datetime.datetime.now(datetime.timezone.utc)
                        delta = now - date_created
                        
                        if delta.days > 0:
                            time_ago = f"{delta.days}d ago"
                        elif delta.seconds >= 3600:
                            hours = delta.seconds // 3600
                            time_ago = f"{hours}h ago"
                        else:
                            minutes = delta.seconds // 60
                            time_ago = f"{minutes}m ago"
                        logging.info("Calculated time ago: %s for date: %s", time_ago, date_created)
                    else:
                        time_ago = "Unknown"
                        logging.warning("No DateCreated found for item: %s", name)
                    
                    recent_items.append({
                        'title': title,
                        'type': item_type,
                        'added': time_ago
                    })
                    logging.info("Added item to recent_items: %s", recent_items[-1])
                    
                except Exception as e:
                    logging.error(f"Error parsing recently added item: {e}", exc_info=True)
                    continue
            
            logging.info("Final recently added items list: %s", recent_items)
            return recent_items
            
        except Exception as e:
            logging.error(f"Error getting recently added items: {e}", exc_info=True)
            return []

    async def get_user_id(self) -> str:
        """Get the user ID for the API key."""
        try:
            # Try to get current user info
            user_info = await self._make_request('/Users/Me')
            if user_info and 'Id' in user_info:
                return user_info['Id']
                
            # If that fails, try to list users and find admin
            users = await self._make_request('/Users')
            for user in users:
                if user.get('Policy', {}).get('IsAdministrator'):
                    return user['Id']
                    
            # If no admin found, take the first user
            if users:
                return users[0]['Id']
                
        except Exception as e:
            logging.error(f"Error getting user ID: {e}", exc_info=True)
            
        return ''
