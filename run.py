import asyncio
import logging
import sys
from modules.config import Config
from modules.bot import MediaBot
from modules.logs import init as init_logging

async def main():
    # Initialize logging
    init_logging("jellycord", "DEBUG")
    
    try:
        # Load configuration
        config = Config.from_yaml("jellycord.yaml")
        
        # Create and start the bot
        bot = MediaBot(config)
        await bot.start_bot()
        
    except Exception as e:
        logging.error(f"Error starting bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
