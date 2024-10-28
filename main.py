import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import Config, load_config
from utils import (
    scrape_forex_factory, 
    filter_events, 
    escape_markdown, 
    NewsTracker
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load config
config = load_config()

# Initialize bot and dispatcher
bot = Bot(token=config.tg_bot.token)
dp = Dispatcher()

# Initialize news tracker
news_tracker = NewsTracker()

# Define GMT+5 timezone
TIMEZONE = pytz.timezone('Asia/Tashkent')

def get_upcoming_events(hours: int = 24) -> List[Dict]:
    """Get news events for the next specified hours"""
    try:
        events = scrape_forex_factory()
        filtered_events = filter_events(events, config.currency.currencies)
        
        now = datetime.now(TIMEZONE)
        
        upcoming_events = []
        for event in filtered_events:
            try:
                event_date = datetime.strptime(f"{event['date']} {event['time']}", '%b %d %I:%M%p')
                event_date = event_date.replace(year=now.year)
                event_date = TIMEZONE.localize(event_date)
                
                if event_date.date() == now.date() and event_date.time() < now.time():
                    event_date = event_date.replace(year=now.year + 1)
                
                time_diff = event_date - now
                if timedelta(0) <= time_diff <= timedelta(hours=hours):
                    event['datetime'] = event_date
                    upcoming_events.append(event)
            except ValueError as e:
                logger.error(f"Error parsing date/time for event: {event}")
                continue
        
        upcoming_events.sort(key=lambda x: x['datetime'])
        return upcoming_events
    except Exception as e:
        logger.error(f"Error getting upcoming events: {e}")
        return []

def format_event_message(event: Dict) -> str:
    """Format a single event message"""
    impact_emoji = {
        "Low": "🟢",
        "Medium": "🟡",
        "High": "🔴",
        "Holiday": "🏁"
    }.get(event['impact'], "⚪")
    
    event_time = escape_markdown(event['time'])
    currency = escape_markdown(event['currency'])
    impact = escape_markdown(str(event['impact']))
    event_name = escape_markdown(event['event'])
    
    return (
        f"*Time:* {event_time}\n"
        f"*Currency:* {currency}\n"
        f"*Impact:* {impact_emoji} {impact}\n"
        f"*Event:* {event_name}\n"
    )

async def send_weekly_schedule():
    """Send full week's schedule every Monday at 7 AM GMT+5"""
    logger.info("Sending weekly schedule")
    try:
        events = scrape_forex_factory()
        filtered_events = filter_events(events, config.currency.currencies)
        
        if filtered_events:
            message = "📅 *Weekly Economic Calendar*\n\n"
            current_date = None
            
            for event in filtered_events:
                if event.get('date') != current_date:
                    current_date = event['date']
                    message += f"\n📌 *{escape_markdown(current_date)}*\n\n"
                
                message += format_event_message(event) + "\n"
            
            await bot.send_message(
                chat_id=config.tg_bot.channel_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
            logger.info("Weekly schedule sent successfully")
    except Exception as e:
        logger.error(f"Error sending weekly schedule: {e}")

async def check_upcoming_news():
    """Check for upcoming news events and send notifications"""
    try:
        upcoming_events = get_upcoming_events(2)  # Get events for next 2 hours
        now = datetime.now(TIMEZONE)
        
        for event in upcoming_events:
            try:
                time_diff = (event['datetime'] - now).total_seconds() / 60
                
                # Define notification thresholds
                thresholds = [60, 30, 15, 5, 1]
                
                for threshold in thresholds:
                    notification_id = f"{event['id']}_t{threshold}"
                    
                    if threshold - 1 <= time_diff <= threshold and not news_tracker.is_news_sent(notification_id):
                        message = (
                            f"⚠️ *Event in {threshold} minute{'s' if threshold > 1 else ''}*\n\n"
                            f"{format_event_message(event)}"
                        )
                        
                        await bot.send_message(
                            chat_id=config.tg_bot.channel_id,
                            text=message,
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                        
                        news_tracker.mark_as_sent(notification_id)
                
                # Send "News started" message
                if 0 <= time_diff < 1 and not news_tracker.is_news_sent(f"{event['id']}_started"):
                    message = (
                        "🚨 *Event Starting Now*\n\n"
                        f"{format_event_message(event)}"
                    )
                    
                    await bot.send_message(
                        chat_id=config.tg_bot.channel_id,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                    
                    news_tracker.mark_as_sent(f"{event['id']}_started")
                    
            except Exception as e:
                logger.error(f"Error processing event notification: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error checking upcoming news: {e}")

@dp.message(Command(commands=["upcoming"]))
async def cmd_upcoming(message: types.Message):
    """Show upcoming events (admin only)"""
    if message.from_user.id != config.tg_bot.admin_id:
        await message.answer(
            "You don't have permission to use this command\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    try:
        parts = message.text.split()
        hours = int(parts[1]) if len(parts) > 1 else 24
        hours = min(max(hours, 1), 72)
        
        upcoming_events = get_upcoming_events(hours)
        
        if upcoming_events:
            message_text = f"📊 *Upcoming Events \\(Next {hours} hours\\)*\n\n"
            
            for event in upcoming_events:
                message_text += format_event_message(event) + "\n"
                
            await message.answer(
                text=message_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await message.answer(
                "No upcoming events found\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
    except ValueError:
        await message.answer(
            "Please use a valid number of hours \\(1\\-72\\)\\.\n"
            "Example: /upcoming 12",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error in cmd_upcoming: {e}")
        await message.answer(
            "Error fetching upcoming events\\. Please try again later\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

@dp.message(Command(commands=["start"]))
async def cmd_start(message: types.Message):
    """Handle the start command"""
    welcome_text = (
        "👋 *Welcome to Forex News Bot\\!*\n\n"
        "I will help you track important forex news events\\.\n\n"
        "*Available Commands:*\n"
        "🔹 /help \\- Show all commands\n\n"
        "All times are shown in GMT\\+5 timezone\\.\n\n"
        "I will automatically post updates to the channel\\."
    )
    
    try:
        await message.answer(
            text=welcome_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error sending start message: {e}")
        await message.answer(
            "Welcome to Forex News Bot! Use /help to see available commands."
        )

@dp.message(Command(commands=["help"]))
async def cmd_help(message: types.Message):
    """Show help message"""
    help_text = (
        "📱 *Forex News Bot Commands*\n\n"
        "👑 *Admin Commands:*\n"
        "🔸 /upcoming \\- Show upcoming events \\(1\\-72 hours\\)\n\n"
        "Bot automatically sends:\n"
        "📅 Weekly schedule every Monday at 7 AM\n"
        "⏰ Notifications at 60, 30, 15, 5, and 1 minute before events\n"
        "🚨 Event start notifications\n\n"
        "All times are shown in GMT\\+5 timezone\\."
    )
    
    try:
        await message.answer(
            text=help_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error sending help message: {e}")
        fallback_text = (
            "Forex News Bot Commands\n\n"
            "Admin Commands:\n"
            "/upcoming - Show upcoming events (1-72 hours)\n\n"
            "Bot automatically sends:\n"
            "- Weekly schedule every Monday at 7 AM\n"
            "- Notifications before events\n"
            "- Event start notifications\n\n"
            "All times are shown in GMT+5 timezone."
        )
        await message.answer(text=fallback_text)

async def main():
    """Main function to start the bot"""
    logger.info("Starting bot")
    
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    
    # Schedule weekly update every Monday at 7 AM GMT+5
    scheduler.add_job(
        send_weekly_schedule,
        CronTrigger(day_of_week='mon', hour=7, minute=0, timezone=TIMEZONE)
    )
    
    # Schedule checks for upcoming events every 5 minutes
    scheduler.add_job(
        check_upcoming_news,
        'interval',
        minutes=5
    )
    
    try:
        scheduler.start()
        
        # Send initial weekly schedule if it's Monday and between 7 AM and 8 AM
        now = datetime.now(TIMEZONE)
        if now.weekday() == 0 and 7 <= now.hour < 8:
            await send_weekly_schedule()
            
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())