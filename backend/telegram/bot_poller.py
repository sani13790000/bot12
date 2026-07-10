"""
Telegram Bot Polling Implementation
Enables the bot to receive and process messages
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramBotPoller:
    """Handles polling for incoming Telegram messages"""
    
    def __init__(self, bot, polling_interval: int = 1):
        self.bot = bot
        self.polling_interval = polling_interval
        self.is_running = False
        self.last_update_id = 0
    
    async def start_polling(self):
        """Start polling for updates"""
        self.is_running = True
        logger.info("[telegram] Started polling for messages")
        
        try:
            while self.is_running:
                try:
                    # Get updates from Telegram
                    updates = await self.bot.get_updates(
                        offset=self.last_update_id + 1,
                        timeout=30
                    )
                    
                    for update in updates:
                        try:
                            await self._handle_update(update)
                            self.last_update_id = update.update_id
                        except Exception as e:
                            logger.exception("[telegram] Error processing update: %s", e)
                    
                    # Small delay between polls
                    await asyncio.sleep(self.polling_interval)
                
                except asyncio.CancelledError:
                    logger.info("[telegram] Polling cancelled")
                    break
                except Exception as e:
                    logger.error("[telegram] Polling error: %s", e)
                    await asyncio.sleep(5)  # Backoff on error
        
        finally:
            self.is_running = False
            logger.info("[telegram] Polling stopped")
    
    async def stop_polling(self):
        """Stop polling"""
        self.is_running = False
    
    async def _handle_update(self, update):
        """Handle incoming update"""
        if update.message:
            message = update.message
            
            # Handle text messages
            if message.text:
                logger.info(f"[telegram] Message from {message.chat.id}: {message.text}")
                
                # Dispatch to handler
                if message.text.startswith('/'):
                    await self._handle_command(message)
                else:
                    await self._handle_message(message)
    
    async def _handle_command(self, message):
        """Handle bot commands"""
        command = message.text.split()[0]
        
        if command == '/status':
            await self.bot.send_message(
                chat_id=message.chat.id,
                text="Bot is running"
            )
        elif command == '/positions':
            # Will be implemented with API integration
            await self.bot.send_message(
                chat_id=message.chat.id,
                text="Fetching positions..."
            )
    
    async def _handle_message(self, message):
        """Handle regular messages"""
        # Echo for now, will be replaced with real logic
        logger.debug(f"[telegram] Received message: {message.text}")
