import os
import re
import logging
import asyncio
from typing import Optional
from dataclasses import dataclass, asdict
import html as pyhtml

from playwright.async_api import async_playwright
from playwright_stealth import stealth  # Fixed import
import requests

# ================= CONFIGURATION =================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") 
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DISCOUNT_THRESHOLD = int(os.environ.get("DISCOUNT_THRESHOLD", "50"))

BASE_URL = "https://shop.tamimimarkets.com"
HOT_DEALS_URL = f"{BASE_URL}/en/hot-deals"
# =================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class Product:
    name: str
    current_price: float
    original_price: Optional[float] = None
    discount_percent: int = 0
    url: str = ""

class TamimiScraper:
    def __init__(self):
        self.products = []
    
    async def fetch_page(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # Use the corrected stealth function
            await stealth(page)
            
            try:
                logger.info(f"Navigating to {HOT_DEALS_URL}")
                await page.goto(HOT_DEALS_URL, wait_until='networkidle', timeout=60000)
                
                # Scroll to load products
                for _ in range(5):
                    await page.mouse.wheel(0, 2000)
                    await page.wait_for_timeout(1000)
                
                page_html = await page.content()
                await page.screenshot(path="tamimi_deals.png")
                return page_html
                
            except Exception as e:
                logger.error(f"Error: {e}")
                return ""
            finally:
                await browser.close()
    
    def parse_products(self, page_html):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page_html, 'html.parser')
        found_products = []
        
        discount_badges = soup.find_all(string=re.compile(r'\d+%'))
        
        for badge in discount_badges:
            try:
                container = badge.parent
                for _ in range(6):
                    if container and ('SAR' in container.get_text().upper()):
                        break
                    container = container.parent
                
                if not container: continue

                text = container.get_text(separator=' ', strip=True)
                dist_match = re.search(r'(\d+)%', text)
                pct = int(dist_match.group(1)) if dist_match else 0
                
                price_match = re.search(r'SAR\s*(\d+\.?\d*)', text, re.IGNORECASE)
                if not price_match: continue
                price = float(price_match.group(1))

                name_tag = container.find(['h2', 'h3', 'h4', 'h5', 'strong'])
                name = name_tag.get_text(strip=True) if name_tag else "Unknown Product"
                
                link_tag = container.find('a', href=True)
                url = BASE_URL + link_tag['href'] if link_tag else ""

                original = round(price / (1 - pct/100), 2) if pct > 0 else None
                found_products.append(Product(name, price, original, pct, url))
            except:
                continue
        return found_products

    def send_telegram_alert(self, deals):
        if not deals:
            message = f"🔍 <b>Tamimi Run:</b> No products ≥{DISCOUNT_THRESHOLD}% found."
        else:
            deals.sort(key=lambda x: x.discount_percent, reverse=True)
            message = f"🔥 <b>TAMIMI HOT DEALS ({DISCOUNT_THRESHOLD}%+)</b> 🔥\n\n"
            for i, d in enumerate(deals[:15], 1):
                name = pyhtml.escape(d.name[:50])
                message += f"<b>{i}. {name}</b>\n"
                if d.original_price:
                    message += f"   <s>{d.original_price}</s> → "
                message += f"<b>{d.current_price} SAR</b> (-{d.discount_percent}%)\n"
                if d.url: message += f"   <a href='{d.url}'>Link</a>\n"
                message += "\n"

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML', 'disable_web_page_preview': True})

    async def run(self):
        html = await self.fetch_page()
        if html:
            all_items = self.parse_products(html)
            hot_deals = [p for p in all_items if p.discount_percent >= DISCOUNT_THRESHOLD]
            self.send_telegram_alert(hot_deals)

if __name__ == "__main__":
    asyncio.run(TamimiScraper().run())
