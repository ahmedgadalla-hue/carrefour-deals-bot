"""
Tamimi Markets Hot Deals Monitor - 69%+ DISCOUNTS ONLY
Sends alerts only for items with 69% or more discount
"""

import os
import re
import json
import logging
import asyncio
import random
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, asdict
import html as pyhtml

from playwright.async_api import async_playwright
import requests

# ================= CONFIGURATION =================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DISCOUNT_THRESHOLD = 69  # CHANGED: Now 69% (will catch 69%, 70%, 71%, etc.)

BASE_URL = "https://shop.tamimimarkets.com"
HOT_DEALS_URL = f"{BASE_URL}/en/hot-deals"
# =================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Product:
    name: str
    current_price: float
    original_price: Optional[float] = None
    discount_percent: int = 0
    url: str = ""
    
    def to_dict(self):
        return asdict(self)


class TamimiScraper:
    def __init__(self):
        self.products = []
    
    async def fetch_page(self):
        """Fetch page with stealth techniques"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                ]
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
            )
            
            page = await context.new_page()
            
            try:
                logger.info(f"Navigating to {HOT_DEALS_URL}")
                
                await asyncio.sleep(random.uniform(2, 4))
                await page.goto(HOT_DEALS_URL, wait_until='domcontentloaded', timeout=60000)
                await page.wait_for_timeout(5000)
                
                # Scroll to load all products
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(3000)
                
                # Get page content
                html_content = await page.content()
                
                # Save debug files
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                await page.screenshot(path=f"tamimi_deals_{timestamp}.png")
                
                with open(f"tamimi_page_{timestamp}.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                logger.info(f"✅ Page loaded: {len(html_content)} chars")
                return html_content
                
            except Exception as e:
                logger.error(f"Error: {e}")
                return ""
            finally:
                await browser.close()
    
    def parse_products(self, html_content):
        """Parse products using exact selectors from the website"""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html_content, 'html.parser')
        products = []
        
        # Find all product containers
        product_containers = soup.find_all('div', attrs={'data-testid': 'product'})
        logger.info(f"Found {len(product_containers)} products with data-testid='product'")
        
        for container in product_containers:
            try:
                # Find discount
                discount_elem = container.find('div', class_=re.compile(r'Product__StyledDiscount'))
                if not discount_elem:
                    continue
                    
                discount_text = discount_elem.get_text(strip=True)
                discount_match = re.search(r'(\d+)%', discount_text)
                if not discount_match:
                    continue
                discount = int(discount_match.group(1))
                
                # Find current price
                current_price_elem = container.find('span', class_=re.compile(r'Price__SellingPrice'))
                if not current_price_elem:
                    continue
                    
                current_price_text = current_price_elem.get_text(strip=True)
                current_price = float(current_price_text)
                
                # Find original price
                original_price = None
                original_price_elem = container.find('span', class_=re.compile(r'Price__SellingPriceOutDated'))
                if original_price_elem:
                    original_price_text = original_price_elem.get_text(strip=True)
                    original_price = float(original_price_text)
                
                # Find product name
                name_parts = []
                
                # Look for brand name
                brand_elem = container.find('span', class_=re.compile(r'ebqvdy'))
                if brand_elem:
                    brand_text = brand_elem.get_text(strip=True)
                    if brand_text:
                        name_parts.append(brand_text)
                
                # Look for product name
                name_elem = container.find('span', class_=re.compile(r'Product__StyledNameText'))
                if name_elem:
                    name_text = name_elem.get_text(strip=True)
                    if name_text:
                        name_parts.append(name_text)
                
                name = ' '.join(name_parts) if name_parts else ""
                
                # Get product URL
                url = ""
                link = container.find('a', href=True)
                if link and link.get('href'):
                    href = link['href']
                    if href.startswith('http'):
                        url = href
                    elif href.startswith('/'):
                        url = BASE_URL + href
                
                if name and current_price and discount > 0:
                    product = Product(
                        name=name[:100],
                        current_price=current_price,
                        original_price=original_price,
                        discount_percent=discount,
                        url=url
                    )
                    products.append(product)
                    logger.info(f"✅ Found: {name[:30]}... - {discount}% off - {current_price} SAR")
                    
            except Exception as e:
                logger.debug(f"Error parsing product: {e}")
                continue
        
        return products
    
    def send_telegram_alert(self, products):
        """Send alert to Telegram - ONLY for 69%+ discounts"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.error("Missing Telegram credentials")
            return
        
        # Filter for 69%+ discounts (catches 69%, 70%, 71%, etc.)
        hot_deals = [p for p in products if p.discount_percent >= DISCOUNT_THRESHOLD]
        
        # Sort by discount (highest first)
        hot_deals.sort(key=lambda x: x.discount_percent, reverse=True)
        
        if not hot_deals:
            # No 69%+ deals found - send a simple status update
            message = f"🔍 <b>Tamimi Monitor</b>\n\n"
            message += f"No items with ≥{DISCOUNT_THRESHOLD}% discount found.\n"
            message += f"Total deals scanned: {len(products)}\n"
            
            # Show the highest discount found
            if products:
                max_discount = max(p.discount_percent for p in products)
                message += f"Highest discount found: {max_discount}%\n"
            
            message += "\nI'll keep watching! 🤖"
            
        else:
            # We have 69%+ deals - send detailed alert
            message = f"🔥🔥🔥 <b>MASSIVE DISCOUNTS ALERT! ({DISCOUNT_THRESHOLD}%+)</b> 🔥🔥🔥\n\n"
            message += f"Found <b>{len(hot_deals)}</b> items with ≥{DISCOUNT_THRESHOLD}% OFF!\n\n"
            
            for i, product in enumerate(hot_deals[:10], 1):
                safe_name = pyhtml.escape(product.name[:60])
                message += f"<b>{i}. {safe_name}</b>\n"
                
                if product.original_price:
                    message += f"   <s>{product.original_price:.2f} SAR</s> → "
                message += f"<b>{product.current_price:.2f} SAR</b>"
                message += f"  <b>(-{product.discount_percent}% OFF!)</b> 🔥\n"
                
                if product.url:
                    message += f"   <a href='{product.url}'>View Product</a>\n"
                message += "\n"
            
            if len(hot_deals) > 10:
                message += f"...and {len(hot_deals)-10} more massive deals!"
        
        # Send to Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        try:
            response = requests.post(url, json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }, timeout=30)
            
            if response.status_code == 200:
                logger.info(f"✅ Telegram alert sent")
                if hot_deals:
                    logger.info(f"🔥 Found {len(hot_deals)} deals with ≥{DISCOUNT_THRESHOLD}% off")
            else:
                logger.error(f"❌ Telegram error: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Failed to send: {e}")
    
    async def run(self):
        """Main execution"""
        logger.info("=" * 60)
        logger.info(f"🚀 Starting Tamimi Markets Monitor")
        logger.info(f"🎯 Looking for discounts ≥ {DISCOUNT_THRESHOLD}%")
        logger.info("=" * 60)
        
        html = await self.fetch_page()
        if not html:
            logger.error("❌ Failed to fetch page")
            return
        
        self.products = self.parse_products(html)
        logger.info(f"📦 Total products found: {len(self.products)}")
        
        if self.products:
            # Log all discount statistics
            hot_deals = [p for p in self.products if p.discount_percent >= DISCOUNT_THRESHOLD]
            logger.info(f"🔥 Deals ≥{DISCOUNT_THRESHOLD}%: {len(hot_deals)}")
            
            # Show discount distribution in relevant ranges
            ranges = [
                (90, 100), 
                (DISCOUNT_THRESHOLD, 89),  # This will show 69-89%
                (50, 68), 
                (40, 49), 
                (30, 39), 
                (20, 29), 
                (10, 19), 
                (0, 9)
            ]
            
            for high, low in ranges:
                count = len([p for p in self.products if low <= p.discount_percent <= high])
                if count > 0:
                    logger.info(f"📊 Deals {low}-{high}%: {count}")
            
            # Show top 5 deals overall
            sorted_products = sorted(self.products, key=lambda x: x.discount_percent, reverse=True)
            logger.info("🏆 Top 5 deals overall:")
            for i, p in enumerate(sorted_products[:5], 1):
                logger.info(f"   {i}. {p.name[:30]}... - {p.discount_percent}% off")
        
        # Send alert (will only send if there are 69%+ deals)
        self.send_telegram_alert(self.products)
        logger.info("=" * 60)


async def main():
    scraper = TamimiScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
