from typing import Optional, List, Dict, Any
import aiohttp
import logging
import datetime
from .emby_client import StreamInfo  # Reusing the StreamInfo class since they're compatible

class JellyfinClient:
    def __init__(self, base_url: str, api_key: str, use_ssl: bool = True):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.verify_ssl = use_ssl
        self.session: Optional[aiohttp.ClientSession] = None
        self.user_id: Optional[str] = None

    async def _ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def _get(self, endpoint: str) -> Dict[str, Any]:
        await self._ensure_session()
        headers = {
            'X-MediaBrowser-Token': self.api_key
        }
        
        # Try both with and without /jellyfin prefix
        urls = [
            f"{self.base_url}{endpoint}",
            f"{self.base_url}/jellyfin{endpoint}"
        ]
        
        for url in urls:
            try:
                logging.info(f"Making request to Jellyfin: {url}")
                async with self.session.get(url, headers=headers, ssl=self.verify_ssl) as response:
                    if response.status == 401:
                        logging.error("Authentication failed. Check your API key.")
                        continue
                    response.raise_for_status()
                    data = await response.json()
                    logging.info(f"Successfully connected to Jellyfin at {url}")
                    # Update base_url to the working URL for future requests
                    self.base_url = url.split(endpoint)[0]
                    return data
            except Exception as e:
                logging.error(f"Error making GET request to Jellyfin at {url}: {e}")
                continue
        
        logging.error("Failed to connect to Jellyfin server")
        return {}

    async def get_user_id(self) -> Optional[str]:
        """Get the user ID for the API key."""
        data = await self._get('/Users')
        if not isinstance(data, list):
            logging.error(f"Unexpected response from Jellyfin when getting users: {data}")
            return None
            
        for user in data:
            if user.get('Policy', {}).get('IsAdministrator'):
                self.user_id = user.get('Id')
                return self.user_id
        return None

    async def get_sessions(self) -> List[StreamInfo]:
        data = await self._get('/Sessions')
        if not isinstance(data, list):
            logging.error(f"Unexpected sessions response from Jellyfin: {data}")
            return []
            
        sessions: List[StreamInfo] = []
        
        for session in data:
            if not session.get('NowPlayingItem'):
                continue

            now_playing = session['NowPlayingItem']
            playback_info = session.get('PlayState', {})
            
            stream_info = StreamInfo(
                username=session.get('UserName', 'Unknown User'),
                client=session.get('Client', 'Unknown Client'),
                device_name=session.get('DeviceName', 'Unknown Device'),
                media_type=now_playing.get('Type', 'Unknown'),
                title=now_playing.get('Name', 'Unknown'),
                transcoding="Transcode" if session.get('TranscodingInfo') else "Direct",
                progress=playback_info.get('PositionTicks', 0) / 10000000 if playback_info.get('PositionTicks') else 0,
                duration=now_playing.get('RunTimeTicks', 0) / 10000000 if now_playing.get('RunTimeTicks') else 0,
                bandwidth=session.get('TranscodingInfo', {}).get('Bitrate', 0) if session.get('TranscodingInfo') else 0,
                player=f"{session.get('Client', '')} {session.get('DeviceName', '')}".strip()
            )
            sessions.append(stream_info)
            
        return sessions

    async def get_library_stats(self) -> List[Dict]:
        """Get statistics for all libraries."""
        if not self.user_id:
            logging.error("No user ID available for Jellyfin client")
            return []
            
        # First get all libraries
        data = await self._get('/Library/MediaFolders')
        if not isinstance(data, dict) or 'Items' not in data:
            logging.error(f"Unexpected response from Jellyfin when getting libraries: {data}")
            return []
            
        library_stats = []
        
        # For each library, get its item counts
        for library in data.get('Items', []):
            try:
                library_id = library.get('Id')
                library_name = library.get('Name', '')
                if not library_id or not library_name:
                    continue
                
                # Skip collections library
                if library_name.lower() == 'collections':
                    continue
                    
                # Determine library flags
                is_4k = '4k' in library_name.lower()
                is_kids = 'kids' in library_name.lower()
                is_anime = 'anime' in library_name.lower()
                
                # Get item counts for this library
                counts = await self._get(f'/Items/Counts?ParentId={library_id}')
                if not isinstance(counts, dict):
                    continue
                    
                # Get the library type and count
                library_type = library.get('CollectionType', '').lower()
                if library_type == 'movies':
                    item_count = counts.get('MovieCount', 0)
                elif library_type == 'tvshows':
                    item_count = counts.get('SeriesCount', 0)
                elif library_type == 'music':
                    item_count = counts.get('SongCount', 0)
                else:
                    continue
                
                # Add library stats
                library_stats.append({
                    'name': library_name,
                    'type': library_type,
                    'count': item_count,
                    'is_4k': is_4k,
                    'is_kids': is_kids,
                    'is_anime': is_anime
                })
                
            except Exception as e:
                logging.error(f"Error getting stats for library {library.get('Name', 'Unknown')}: {e}")
                continue
                
        return library_stats

    async def get_recently_added(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently added items."""
        if not self.user_id:
            logging.error("No user ID available for Jellyfin client")
            return []
            
        params = {
            'Limit': limit,
            'Fields': 'Path,Overview,DateCreated',
            'ImageTypeLimit': 1,
            'EnableImageTypes': 'Primary',
            'SortBy': 'DateCreated,SortName',
            'SortOrder': 'Descending',
            'Recursive': True,
            'IncludeItemTypes': 'Movie,Episode'
        }
        
        # Convert params to query string
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        endpoint = f'/Users/{self.user_id}/Items?{query}'
        
        data = await self._get(endpoint)
        if not isinstance(data, dict) or 'Items' not in data:
            logging.error(f"Unexpected response from Jellyfin: {data}")
            return []
            
        items = []
        for item in data.get('Items', []):
            item_type = item.get('Type', '')
            if item_type not in ['Movie', 'Episode']:
                continue
                
            try:
                added_date = datetime.datetime.fromisoformat(item.get('DateCreated', '').replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                added_date = datetime.datetime.now()
            
            item_info = {
                'Id': item.get('Id', ''),
                'Name': item.get('Name', ''),
                'Overview': item.get('Overview', ''),
                'Type': item_type,
                'AddedDate': added_date,
                'ImageTags': item.get('ImageTags', {}),
                'SeriesName': item.get('SeriesName', '') if item_type == 'Episode' else None,
                'SeasonNumber': item.get('ParentIndexNumber', 0) if item_type == 'Episode' else None,
                'EpisodeNumber': item.get('IndexNumber', 0) if item_type == 'Episode' else None
            }
            items.append(item_info)
            
        return items[:limit]
