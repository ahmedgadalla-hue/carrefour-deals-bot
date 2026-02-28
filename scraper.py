"""
Tamimimarkets Hot Deals Monitor - FIXED VERSION
Based on actual site structure from screenshot
"""

import os
import re
import json
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright
import requests

# ================= CONFIGURATION =================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8791585716:AAE-SEV2iACbYXMmymWeA1JJVyGFk5_Y1Jg")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "7420001477")
DISCOUNT_THRESHOLD = int(os.environ.get("DISCOUNT_THRESHOLD", "50"))

BASE_URL = "https://shop.tamimimarkets.com"
HOT_DEALS_URL = f"{BASE_URL}/ar/hot-deals"
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
    
    def to_dict(self):
        return asdict(self)


class TamimiScraper:
    def __init__(self):
        self.products = []
    
    async def fetch_page(self):
        """Fetch the hot deals page"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                logger.info(f"Navigating to {HOT_DEALS_URL}")
                await page.goto(HOT_DEALS_URL, wait_until='networkidle', timeout=30000)
                
                # Wait for content to load
                await page.wait_for_timeout(5000)
                
                # Scroll to load all deals
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
                
                # Get the HTML
                html = await page.content()
                logger.info(f"Page loaded, HTML length: {len(html)}")
                
                # Take screenshot for debugging
                await page.screenshot(path="tamimi_deals.png")
                
                return html
                
            except Exception as e:
                logger.error(f"Error fetching page: {e}")
                return ""
            finally:
                await browser.close()
    
    def parse_products(self, html):
        """Parse products based on the actual site structure"""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, 'html.parser')
        products = []
        
        # Look for discount badges - they show "% خصم"
        discount_elements = soup.find_all(text=re.compile(r'\d+%\s*خصم'))
        logger.info(f"Found {len(discount_elements)} discount badges")
        
        # For each discount badge, find the parent container that holds the product
        for discount_elem in discount_elements:
            try:
                # Get the parent element that contains the full product info
                parent = discount_elem.parent
                
                # Go up a few levels to find the product container
                for _ in range(5):
                    if parent:
                        # Check if this parent has product name and price
                        text = parent.get_text()
                        if 'ريال' in text and len(text) > 20:
                            break
                        parent = parent.parent
                    else:
                        break
                
                if not parent:
                    continue
                
                # Extract discount percentage
                discount_text = discount_elem.strip()
                discount_match = re.search(r'(\d+)', discount_text)
                if not discount_match:
                    continue
                discount_percent = int(discount_match.group(1))
                
                # Find product name - usually before the discount or after
                all_text = parent.get_text()
                
                # Look for price (ريال)
                price_match = re.search(r'(\d+\.?\d*)\s*ريال', all_text)
                if not price_match:
                    continue
                current_price = float(price_match.group(1))
                
                # Try to find product name (it's usually before the price)
                # Split by price and take the part before
                parts = all_text.split(str(current_price) + ' ريال')[0].strip()
                
                # Clean up the name - remove discount text
                name = parts.replace(discount_text, '').strip()
                
                # If name is too short, try to find heading elements
                if len(name) < 5:
                    headings = parent.find_all(['h2', 'h3', 'h4', 'h5', 'strong'])
                    if headings:
                        name = headings[0].get_text(strip=True)
                
                # Calculate original price based on discount
                original_price = None
                if discount_percent > 0:
                    original_price = round(current_price / (1 - discount_percent/100), 2)
                
                # Find product URL
                url = ""
                link = parent.find('a', href=True)
                if link:
                    href = link['href']
                    if href.startswith('http'):
                        url = href
                    elif href.startswith('/'):
                        url = BASE_URL + href
                
                if name and current_price and discount_percent >= 0:
                    product = Product(
                        name=name[:100],
                        current_price=current_price,
                        original_price=original_price,
                        discount_percent=discount_percent,
                        url=url
                    )
                    products.append(product)
                    logger.info(f"Found: {name[:30]}... - {discount_percent}% off - {current_price} SAR")
                    
            except Exception as e:
                logger.debug(f"Error parsing product: {e}")
                continue
        
        # Also look for products in grid/list format
        if len(products) < 5:
            logger.info("Trying alternative parsing method...")
            
            # Look for product containers (based on the screenshot)
            containers = soup.find_all(['div', 'article'], 
                                      class_=re.compile(r'product|item|card', re.I))
            
            for container in containers:
                try:
                    text = container.get_text()
                    
                    # Check if it has a price and discount
                    if 'ريال' not in text or '%' not in text:
                        continue
                    
                    # Extract discount
                    discount_match = re.search(r'(\d+)%\s*خصم', text)
                    if not discount_match:
                        continue
                    discount = int(discount_match.group(1))
                    
                    # Extract price
                    price_match = re.search(r'(\d+\.?\d*)\s*ريال', text)
                    if not price_match:
                        continue
                    price = float(price_match.group(1))
                    
                    # Extract name (first part before discount)
                    name = text.split('%')[0].strip()
                    if len(name) < 3:
                        continue
                    
                    # Calculate original price
                    original = round(price / (1 - discount/100), 2) if discount > 0 else None
                    
                    product = Product(
                        name=name,
                        current_price=price,
                        original_price=original,
                        discount_percent=discount
                    )
                    products.append(product)
                    logger.info(f"Found (alt): {name[:30]}... - {discount}% off")
                    
                except Exception as e:
                    continue
        
        return products
    
    def filter_hot_deals(self, products):
        """Filter products with discount >= threshold"""
        return [p for p in products if p.discount_percent >= DISCOUNT_THRESHOLD]
    
    def send_telegram_alert(self, products):
        """Send deals to Telegram"""
        if not products:
            # Send a message even when no deals found
            message = "🔍 *Tamimi Monitor Run*\n\n"
            message += "No products with ≥50% discount found this time.\n"
            message += "I'll keep watching for you! 🤖"
            
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            try:
                requests.post(url, json={
                    'chat_id': TELEGRAM_CHAT_ID,
                    'text': message,
                    'parse_mode': 'Markdown'
                })
                logger.info("Sent no-deals message to Telegram")
            except:
                pass
            return
        
        # Sort by discount percentage
        products.sort(key=lambda x: x.discount_percent, reverse=True)
        
        # Create message
        message = f"🔥 *تميمي ماركتس - عروض حصرية* 🔥\n"
        message += f"🔥 *TAMIMIMARKETS - HOT DEALS* 🔥\n\n"
        message += f"تم العثور على *{len(products)}* منتج بتخفيض ≥{DISCOUNT_THRESHOLD}%\n"
        message += f"Found *{len(products)}* items with ≥{DISCOUNT_THRESHOLD}% off\n\n"
        
        for i, product in enumerate(products[:10], 1):
            message += f"*{i}. {product.name[:50]}*\n"
            
            if product.original_price:
                message += f"   ~~{product.original_price:.2f}~~ → "
            message += f"*{product.current_price:.2f} SAR*"
            message += f"  (-{product.discount_percent}% 🔥)\n"
            
            if product.url:
                message += f"   [عرض المنتج]({product.url})\n"
            message += "\n"
        
        if len(products) > 10:
            message += f"...و {len(products)-10} عروض أخرى!"
        
        # Send to Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            response = requests.post(url, json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': False
            })
            
            if response.status_code == 200:
                logger.info(f"Sent {len(products)} deals to Telegram")
            else:
                logger.error(f"Telegram error: {response.text}")
                
        except Exception as e:
            logger.error(f"Failed to send: {e}")
    
    async def run(self):
        """Main execution"""
        logger.info("=" * 50)
        logger.info("Starting Tamimi Deals Monitor")
        logger.info("=" * 50)
        
        # Fetch page
        html = await self.fetch_page()
        if not html:
            logger.error("No HTML fetched")
            return
        
        # Parse products
        self.products = self.parse_products(html)
        logger.info(f"Total products found: {len(self.products)}")
        
        # Show discount distribution
        discounts = [p.discount_percent for p in self.products]
        logger.info(f"Discount range: {min(discounts) if discounts else 0}% - {max(discounts) if discounts else 0}%")
        
        # Filter hot deals
        hot_deals = self.filter_hot_deals(self.products)
        logger.info(f"Hot deals (≥{DISCOUNT_THRESHOLD}%): {len(hot_deals)}")
        
        # Send alerts
        self.send_telegram_alert(hot_deals)
        
        logger.info("=" * 50)


async def main():
    scraper = TamimiScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
