"""
Tamimimarkets Hot Deals Monitor - ENGLISH VERSION
"""

import os
import re
import logging
import asyncio
from typing import Optional
from dataclasses import dataclass, asdict
import html as pyhtml

from playwright.async_api import async_playwright
import requests

# ================= CONFIGURATION =================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") 
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DISCOUNT_THRESHOLD = int(os.environ.get("DISCOUNT_THRESHOLD", "50"))

BASE_URL = "https://shop.tamimimarkets.com"
# FIX: Switched to the English deals page
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
                
                # Give the page plenty of time to load the Javascript products
                await page.wait_for_timeout(5000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(3000)
                
                page_html = await page.content()
                logger.info(f"Page loaded, HTML length: {len(page_html)}")
                
                # Save screenshot and HTML for debugging just in case!
                await page.screenshot(path="tamimi_deals.png")
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
        
        # Look for any text containing a percentage sign (e.g., "50% OFF", "-50%")
        discount_elements = soup.find_all(string=re.compile(r'\d+%'))
        logger.info(f"Found {len(discount_elements)} potential discount badges")
        
        for discount_elem in discount_elements:
            try:
                parent = discount_elem.parent
                
                # Go up the HTML tree to find the whole product card
                for _ in range(6):
                    if parent:
                        parent_text = parent.get_text(separator=' ', strip=True).upper()
                        # Check if this container has the currency "SAR"
                        if 'SAR' in parent_text and len(parent_text) > 10:
                            break
                        parent = parent.parent
                    else:
                        break
                
                if not parent:
                    continue
                
                # 1. Get Discount
                discount_text = discount_elem.strip()
                discount_match = re.search(r'(\d+)%', discount_text)
                if not discount_match:
                    continue
                discount_percent = int(discount_match.group(1))
                
                # 2. Get Price
                all_text = parent.get_text(separator=' ', strip=True)
                
                # Look for "SAR 15.50" or "15.50 SAR"
                price_match = re.search(r'SAR\s*(\d+\.?\d*)', all_text, re.IGNORECASE)
                if not price_match:
                    price_match = re.search(r'(\d+\.?\d*)\s*SAR', all_text, re.IGNORECASE)
                    
                if not price_match:
                    continue
                current_price = float(price_match.group(1))
                
                # 3. Get Name (Look for standard heading tags)
                name = ""
                name_tags = parent.find_all(['h2', 'h3', 'h4', 'h5', 'strong'])
                if name_tags:
                    # Grab the longest text from headings, likely the product name
                    name = max([tag.get_text(strip=True) for tag in name_tags], key=len)
                else:
                    # Fallback: take first part of text
                    name = all_text.split('SAR')[0].replace(discount_text, '').strip()
                
                if len(name) < 3:
                    continue
                
                # 4. Calculate original price
                original_price = None
                if discount_percent > 0:
                    original_price = round(current_price / (1 - discount_percent/100), 2)
                
                # 5. Get URL
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
        
        # 6. Alternative parsing method fallback
        if len(products) < 5:
            logger.info("Trying alternative parsing method...")
            containers = soup.find_all(['div', 'article'], class_=re.compile(r'product|item|card', re.I))
            
            for container in containers:
                try:
                    text = container.get_text(separator=' ', strip=True)
                    
                    if 'SAR' not in text.upper() or '%' not in text:
                        continue
                    
                    discount_match = re.search(r'(\d+)%', text)
                    if not discount_match:
                        continue
                    discount = int(discount_match.group(1))
                    
                    price_match = re.search(r'SAR\s*(\d+\.?\d*)', text, re.IGNORECASE)
                    if not price_match:
                        price_match = re.search(r'(\d+\.?\d*)\s*SAR', text, re.IGNORECASE)
                        
                    if not price_match:
                        continue
                    price = float(price_match.group(1))
                    
                    name_tags = container.find_all(['h2', 'h3', 'h4', 'h5', 'strong'])
                    if name_tags:
                        name = max([tag.get_text(strip=True) for tag in name_tags], key=len)
                    else:
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
            except:
                pass
            return
        
        products.sort(key=lambda x: x.discount_percent, reverse=True)
        
        message = f"🔥 <b>TAMIMI MARKETS - HOT DEALS</b> 🔥\n\n"
        message += f"Found <b>{len(products)}</b> items with ≥{DISCOUNT_THRESHOLD}% off\n\n"
        
        for i, product in enumerate(products[:10], 1):
            safe_name = pyhtml.escape(product.name[:50])
            message += f"<b>{i}. {safe_name}</b>\n"
            
            if product.original_price:
                message += f"   <s>{product.original_price:.2f}</s> → "
            message += f"<b>{product.current_price:.2f} SAR</b>"
            message += f"  (-{product.discount_percent}% 🔥)\n"
            
            if product.url:
                message += f"   <a href='{product.url}'>View Product</a>\n"
            message += "\n"
        
        if len(products) > 10:
            message += f"...and {len(products)-10} more deals!"
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            })
        except Exception as e:
            logger.error(f"Failed to send: {e}")
    
    async def run(self):
        logger.info("=" * 50)
        logger.info("Starting Tamimi Deals Monitor (English)")
        logger.info("=" * 50)
        
        page_html = await self.fetch_page()
        if not page_html:
            return
        
        self.products = self.parse_products(page_html)
        hot_deals = self.filter_hot_deals(self.products)
        self.send_telegram_alert(hot_deals)
        logger.info("=" * 50)

async def main():
    scraper = TamimiScraper()
    await scraper.run()

if __name__ == "__main__":
    asyncio.run(main())
