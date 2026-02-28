"""
Tamimi Markets Hot Deals Monitor - FINAL WORKING VERSION
Uses exact selectors from the website HTML
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
DISCOUNT_THRESHOLD = int(os.environ.get("DISCOUNT_THRESHOLD", "50"))

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
        
        # Find all product containers - using the exact class from the HTML
        product_containers = soup.find_all('div', attrs={'data-testid': 'product'})
        logger.info(f"Found {len(product_containers)} products with data-testid='product'")
        
        # Also try finding by the link class if above fails
        if not product_containers:
            product_containers = soup.find_all('a', class_=re.compile(r'Product__StyledA'))
            logger.info(f"Found {len(product_containers)} products with Product__StyledA class")
        
        for container in product_containers:
            try:
                # Get the full container HTML for debugging
                container_html = str(container)
                
                # Find discount - looking for the discount badge
                discount_elem = container.find('div', class_=re.compile(r'Product__StyledDiscount'))
                if not discount_elem:
                    continue
                    
                discount_text = discount_elem.get_text(strip=True)
                discount_match = re.search(r'(\d+)%', discount_text)
                if not discount_match:
                    continue
                discount = int(discount_match.group(1))
                
                # Find current price - looking for the selling price
                current_price_elem = container.find('span', class_=re.compile(r'Price__SellingPrice'))
                if not current_price_elem:
                    continue
                    
                current_price_text = current_price_elem.get_text(strip=True)
                current_price = float(current_price_text)
                
                # Find original price (if discounted) - looking for strikethrough price
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
                
                # Combine name parts
                name = ' '.join(name_parts) if name_parts else ""
                
                # If we couldn't find structured name, try alternative
                if not name:
                    title_elem = container.find('div', class_=re.compile(r'Product__StyledTitle'))
                    if title_elem:
                        name = title_elem.get_text(separator=' ', strip=True)
                
                # Get product URL
                url = ""
                link = container if container.name == 'a' else container.find('a', href=True)
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
        
        # Count discounts by range
        if products:
            discount_ranges = {
                "0-10": 0, "11-20": 0, "21-30": 0, "31-40": 0, 
                "41-50": 0, "51-60": 0, "61-70": 0, "71+": 0
            }
            
            for p in products:
                if p.discount_percent <= 10:
                    discount_ranges["0-10"] += 1
                elif p.discount_percent <= 20:
                    discount_ranges["11-20"] += 1
                elif p.discount_percent <= 30:
                    discount_ranges["21-30"] += 1
                elif p.discount_percent <= 40:
                    discount_ranges["31-40"] += 1
                elif p.discount_percent <= 50:
                    discount_ranges["41-50"] += 1
                elif p.discount_percent <= 60:
                    discount_ranges["51-60"] += 1
                elif p.discount_percent <= 70:
                    discount_ranges["61-70"] += 1
                else:
                    discount_ranges["71+"] += 1
            
            logger.info(f"Discount distribution: {discount_ranges}")
        
        return products
    
    def send_telegram_alert(self, products):
        """Send alert to Telegram"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.error("Missing Telegram credentials")
            return
        
        # Sort by discount
        products.sort(key=lambda x: x.discount_percent, reverse=True)
        
        if not products:
            message = f"🔍 <b>Tamimi Monitor</b>\n\n"
            message += f"No products with ≥{DISCOUNT_THRESHOLD}% discount found.\n"
            message += "I'll keep watching! 🤖"
        else:
            # Show all products found with their discounts
            message = f"🛒 <b>TAMIMI MARKETS - ALL DEALS</b> 🛒\n\n"
            message += f"Found <b>{len(products)}</b> items with discounts\n\n"
            
            # Show discount distribution
            discount_counts = {}
            for p in products:
                range_key = f"{p.discount_percent//10*10}-{p.discount_percent//10*10+9}%"
                discount_counts[range_key] = discount_counts.get(range_key, 0) + 1
            
            message += "<b>Discount breakdown:</b>\n"
            for range_key in sorted(discount_counts.keys()):
                message += f"• {range_key}: {discount_counts[range_key]} items\n"
            message += "\n"
            
            # Show top 10 deals
            message += "<b>Top 10 deals:</b>\n\n"
            for i, product in enumerate(products[:10], 1):
                safe_name = pyhtml.escape(product.name[:60])
                message += f"<b>{i}. {safe_name}</b>\n"
                
                if product.original_price:
                    message += f"   <s>{product.original_price:.2f} SAR</s> → "
                message += f"<b>{product.current_price:.2f} SAR</b>"
                message += f"  (-{product.discount_percent}% 🔥)\n"
                
                if product.url:
                    message += f"   <a href='{product.url}'>View Product</a>\n"
                message += "\n"
            
            # Specifically highlight deals >=50%
            hot_deals = [p for p in products if p.discount_percent >= 50]
            if hot_deals:
                message += f"🔥 <b>HOT DEALS (≥50% off): {len(hot_deals)} items</b> 🔥\n\n"
                for i, deal in enumerate(hot_deals[:5], 1):
                    message += f"<b>{i}. {pyhtml.escape(deal.name[:50])}</b> - {deal.discount_percent}% off\n"
        
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
            else:
                logger.error(f"❌ Telegram error: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Failed to send: {e}")
    
    async def run(self):
        """Main execution"""
        logger.info("=" * 60)
        logger.info("🚀 Starting Tamimi Markets Monitor")
        logger.info("=" * 60)
        
        html = await self.fetch_page()
        if not html:
            logger.error("❌ Failed to fetch page")
            return
        
        self.products = self.parse_products(html)
        logger.info(f"📦 Total products found: {len(self.products)}")
        
        # Count deals by discount threshold
        if self.products:
            hot_deals = [p for p in self.products if p.discount_percent >= 50]
            logger.info(f"🔥 Deals ≥50%: {len(hot_deals)}")
            logger.info(f"📊 Deals 40-49%: {len([p for p in self.products if 40 <= p.discount_percent < 50])}")
            logger.info(f"📊 Deals 30-39%: {len([p for p in self.products if 30 <= p.discount_percent < 40])}")
            logger.info(f"📊 Deals 20-29%: {len([p for p in self.products if 20 <= p.discount_percent < 30])}")
            logger.info(f"📊 Deals 10-19%: {len([p for p in self.products if 10 <= p.discount_percent < 20])}")
            logger.info(f"📊 Deals 1-9%: {len([p for p in self.products if p.discount_percent < 10])}")
        
        self.send_telegram_alert(self.products)
        logger.info("=" * 60)


async def main():
    scraper = TamimiScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
