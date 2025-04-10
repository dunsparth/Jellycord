# Jellycord

A Discord bot that displays real-time information from your Emby or Jellyfin media server.

## Features

### 🎬 Now Playing
Shows active streams in a dedicated channel with:
- Media title and progress
- User watching and player info
- Stream quality and transcoding status
- Progress bar and ETA

### 📥 Recently Added
Displays latest additions to your server:
- Shows 10 most recent items
- Groups by Movies/TV Shows
- Updates automatically
- Includes relative timestamps

### 📚 Library Statistics
Creates voice channels to display media counts:
- Total movies and TV shows
- Updates automatically every hour
- Custom channel names and emojis
- Separate counts per library

## Setup

### Using Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone https://github.com/dunsparth/jellycord.git
   cd jellycord
   ```

2. **Configure the bot**
   ```bash
   cp jellycord.yaml.example jellycord.yaml
   ```
   Edit `jellycord.yaml` with your settings:
   - Emby/Jellyfin server details
   - Discord bot token
   - Display preferences

3. **Start with Docker Compose**
   ```bash
   docker-compose up -d
   ```

   To view logs:
   ```bash
   docker-compose logs -f
   ```

### Manual Setup

1. **Requirements**
   - Python 3.8 or higher
   - Emby or Jellyfin server
   - Discord Bot Token

2. **Installation**
   ```bash
   # Clone the repository
   git clone https://github.com/dunsparth/jellycord.git
   cd jellycord

   # Install dependencies
   pip install -r requirements.txt
   ```

3. **Configuration**
   ```bash
   # Copy example config
   cp jellycord.yaml.example jellycord.yaml
   ```
   
   Edit `jellycord.yaml` and set:
   - Your Emby/Jellyfin server URL and API key
   - Discord bot token and server ID
   - Display preferences

4. **Run the Bot**
   ```bash
   python run.py
   ```

## Configuration Options

### Media Server
- Choose between Emby or Jellyfin
- Set server URL and API key
- Configure user ID for library access

### Discord Settings
- Bot token and server ID
- Channel names and category IDs
- Custom embed colors

### Display Options
- Stream information detail level
- Recently added items count
- Update frequency

## Support

If you encounter any issues or have questions, please open an issue on GitHub.
