import json
import os
import requests
import time
import logging
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ForexFactoryCalendar:
    def __init__(self):
        self.api_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        self.session = requests.Session()
        self.timezone = pytz.timezone('Asia/Tashkent')  # GMT+5

    def _get_headers(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9'
        }

    def get_calendar(self) -> List[Dict]:
        """Get calendar data from Forex Factory API"""
        try:
            response = self.session.get(
                self.api_url,
                headers=self._get_headers(),
                timeout=15
            )
            response.raise_for_status()
            
            events = response.json()
            return self._process_events(events)
            
        except Exception as e:
            logger.error(f"Error getting Forex Factory calendar: {e}")
            return []

    def _process_events(self, events: List[Dict]) -> List[Dict]:
        """Process and format events from Forex Factory"""
        formatted_events = []
        
        try:
            for event in events:
                try:
                    # Parse datetime
                    event_date = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
                    event_date = event_date.astimezone(self.timezone)
                    
                    # Map impact levels
                    impact_map = {
                        'Low': 1,
                        'Medium': 2,
                        'High': 3,
                        'Holiday': 0
                    }
                    
                    event_data = {
                        'date': event_date.strftime('%b %d'),
                        'time': event_date.strftime('%I:%M%p'),
                        'currency': event['country'],
                        'impact': impact_map.get(event['impact'], 1),
                        'event': event['title'],
                        'forecast': event.get('forecast', 'N/A'),
                        'previous': event.get('previous', 'N/A')
                    }
                    
                    # Generate unique ID
                    event_data['id'] = f"{event_data['date']}_{event_data['time']}_{event_data['currency']}_{event_data['event']}"
                    formatted_events.append(event_data)
                    
                except Exception as e:
                    logger.error(f"Error processing event: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error processing events: {e}")
            
        return formatted_events

class NewsTracker:
    def __init__(self, filename: str = "sent_news.json"):
        self.filename = filename
        self.sent_news: Set[str] = self._load_sent_news()

    def _load_sent_news(self) -> Set[str]:
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as f:
                return set(json.load(f))
        return set()

    def _save_sent_news(self):
        with open(self.filename, 'w') as f:
            json.dump(list(self.sent_news), f)

    def is_news_sent(self, news_id: str) -> bool:
        return news_id in self.sent_news

    def mark_as_sent(self, news_id: str):
        self.sent_news.add(news_id)
        self._save_sent_news()

def escape_markdown(text: str) -> str:
    """Escape special characters for MARKDOWN_V2"""
    if not text:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = str(text).replace(char, f'\\{char}')
    return text

# Initialize calendar handler
forex_factory = ForexFactoryCalendar()

def get_forex_events() -> List[Dict]:
    """Get forex calendar data"""
    try:
        events = forex_factory.get_calendar()
        logger.info(f"Retrieved {len(events)} events from Forex Factory")
        return events
    except Exception as e:
        logger.error(f"Error getting calendar data: {e}")
        return []

def filter_events(events: List[Dict], currencies: Optional[List[str]] = None) -> List[Dict]:
    """Filter events by currency and convert impact to text"""
    if currencies is None:
        currencies = ['USD', 'EUR', 'CAD']
    
    filtered_events = []
    impact_map = {0: "Holiday", 1: "Low", 2: "Medium", 3: "High"}
    
    for event in events:
        if event['currency'] in currencies:
            event_copy = event.copy()
            event_copy['impact'] = impact_map.get(event_copy['impact'], "Unknown")
            
            # Add values only if they're available and not 'N/A'
            values = []
            if event_copy['forecast'] != 'N/A' and event_copy['forecast']:
                values.append(f"F: {event_copy['forecast']}")
            if event_copy['previous'] != 'N/A' and event_copy['previous']:
                values.append(f"P: {event_copy['previous']}")
            
            if values:
                event_copy['event'] = f"{event_copy['event']} ({', '.join(values)})"
            
            filtered_events.append(event_copy)
    
    return filtered_events

# For compatibility with existing code
def scrape_forex_factory() -> List[Dict]:
    """Compatibility function for existing code"""
    return get_forex_events()