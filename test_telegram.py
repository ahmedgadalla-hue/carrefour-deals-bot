"""
Simple Telegram Test
"""

import os
import requests

# Your credentials - paste them here
TELEGRAM_BOT_TOKEN = "8791585716:AAE-SEV2iACbYXMmymWeA1JJVyGFk5_Y1Jg"
TELEGRAM_CHAT_ID = "7420001477"

def send_test_message():
    """Send a test message"""
    
    message = "🤖 *TEST*\n\nIf you get this, your bot works!"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        print("Sending test message...")
        response = requests.post(
            url,
            json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'Markdown'
            }
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ SUCCESS!")
            return True
        else:
            print("❌ FAILED")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    send_test_message()
