"""
Tamimimarkets Hot Deals Monitor - FULLY UPDATED
Includes HTML debug saving and HTML parsing for Telegram
"""

import os
import re
import logging
import asyncio
from typing import Optional
from dataclasses import dataclass, asdict
import html as pyhtml  # Safely escape text for Telegram

from playwright.async_api import async_playwright
import requests

# ================= CONFIGURATION =================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") 
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
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
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                logger.info(f"Navigating to {HOT_DEALS_URL}")
                await page.goto(HOT_DEALS_URL, wait_until='networkidle', timeout=30000)
                
                await page.wait_for_timeout(5000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
                
                page_html = await page.content()
                logger.info(f"Page loaded, HTML length: {len(page_html)}")
                
                # Save screenshot for debugging
                await page.screenshot(path="tamimi_deals.png")
                
                # Save HTML for debugging
                with open("tamimi_page.html", "w", encoding="utf-8") as f:
                    f.write(page_html)
                
                return page_html
                
            except Exception as e:
                logger.error(f"Error fetching page: {e}")
                return ""
            finally:
                await browser.close()
    
    def parse_products(self, page_html):
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(page_html, 'html.parser')
        products = []
        
        # Using 'string' instead of 'text' for newer BeautifulSoup versions
        discount_elements = soup.find_all(string=re.compile(r'\d+%\s*خصم'))
        logger.info(f"Found {len(discount_elements)} discount badges")
        
        for discount_elem in discount_elements:
            try:
                parent = discount_elem.parent
                
                for _ in range(5):
                    if parent:
                        parent_text = parent.get_text()
                        if 'ريال' in parent_text and len(parent_text) > 20:
                            break
                        parent = parent.parent
                    else:
                        break
                
                if not parent:
                    continue
                
                discount_text = discount_elem.strip()
                discount_match = re.search(r'(\d+)', discount_text)
                if not discount_match:
                    continue
                discount_percent = int(discount_match.group(1))
                
                all_text = parent.get_text()
                price_match = re.search(r'(\d+\.?\d*)\s*ريال', all_text)
                if not price_match:
                    continue
                current_price = float(price_match.group(1))
                
                parts = all_text.split(str(current_price) + ' ريال')[0].strip()
                name = parts.replace(discount_text, '').strip()
                
                if len(name) < 5:
                    headings = parent.find_all(['h2', 'h3', 'h4', 'h5', 'strong'])
                    if headings:
                        name = headings[0].get_text(strip=True)
                
                original_price = None
                if discount_percent > 0:
                    original_price = round(current_price / (1 - discount_percent/100), 2)
                
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
        
        if len(products) < 5:
            logger.info("Trying alternative parsing method...")
            containers = soup.find_all(['div', 'article'], class_=re.compile(r'product|item|card', re.I))
            
            for container in containers:
                try:
                    text = container.get_text()
                    
                    if 'ريال' not in text or '%' not in text:
                        continue
                    
                    discount_match = re.search(r'(\d+)%\s*خصم', text)
                    if not discount_match:
                        continue
                    discount = int(discount_match.group(1))
                    
                    price_match = re.search(r'(\d+\.?\d*)\s*ريال', text)
                    if not price_match:
                        continue
                    price = float(price_match.group(1))
                    
                    name = text.split('%')[0].strip()
                    if len(name) < 3:
                        continue
                    
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
        return [p for p in products if p.discount_percent >= DISCOUNT_THRESHOLD]
    
    def send_telegram_alert(self, products):
        if not products:
            message = "🔍 <b>Tamimi Monitor Run</b>\n\n"
            message += f"No products with ≥{DISCOUNT_THRESHOLD}% discount found this time.\n"
            message += "I'll keep watching for you! 🤖"
            
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            try:
                requests.post(url, json={
                    'chat_id': TELEGRAM_CHAT_ID,
                    'text': message,
                    'parse_mode': 'HTML'
                })
                logger.info("Sent no-deals message to Telegram")
            except:
                pass
            return
        
        products.sort(key=lambda x: x.discount_percent, reverse=True)
        
        message = f"🔥 <b>تميمي ماركتس - عروض حصرية</b> 🔥\n"
        message += f"🔥 <b>TAMIMIMARKETS - HOT DEALS</b> 🔥\n\n"
        message += f"تم العثور على <b>{len(products)}</b> منتج بتخفيض ≥{DISCOUNT_THRESHOLD}%\n"
        message += f"Found <b>{len(products)}</b> items with ≥{DISCOUNT_THRESHOLD}% off\n\n"
        
        for i, product in enumerate(products[:10], 1):
            # Escape the product name so rogue characters don't break Telegram HTML
            safe_name = pyhtml.escape(product.name[:50])
            message += f"<b>{i}. {safe_name}</b>\n"
            
            if product.original_price:
                message += f"   <s>{product.original_price:.2f}</s> → "
            message += f"<b>{product.current_price:.2f} SAR</b>"
            message += f"  (-{product.discount_percent}% 🔥)\n"
            
            if product.url:
                message += f"   <a href='{product.url}'>عرض المنتج</a>\n"
            message += "\n"
        
        if len(products) > 10:
            message += f"...و {len(products)-10} عروض أخرى!"
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            response = requests.post(url, json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            })
            
            if response.status_code == 200:
                logger.info(f"Sent {len(products)} deals to Telegram")
            else:
                logger.error(f"Telegram error: {response.text}")
                
        except Exception as e:
            logger.error(f"Failed to send: {e}")
    
    async def run(self):
        logger.info("=" * 50)
        logger.info("Starting Tamimi Deals Monitor")
        logger.info("=" * 50)
        
        page_html = await self.fetch_page()
        if not page_html:
            logger.error("No HTML fetched")
            return
        
        self.products = self.parse_products(page_html)
        logger.info(f"Total products found: {len(self.products)}")
        
        discounts = [p.discount_percent for p in self.products]
        logger.info(f"Discount range: {min(discounts) if discounts else 0}% - {max(discounts) if discounts else 0}%")
        
        hot_deals = self.filter_hot_deals(self.products)
        logger.info(f"Hot deals (≥{DISCOUNT_THRESHOLD}%): {len(hot_deals)}")
        
        self.send_telegram_alert(hot_deals)
        logger.info("=" * 50)


async def main():
    scraper = TamimiScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
