"""
Tamimi Markets Hot Deals Monitor - 69%+ DISCOUNTS ONLY
With improved scrolling to catch ALL products
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
DISCOUNT_THRESHOLD = 69  # Looking for 69%+

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
        """Fetch page with aggressive scrolling to load ALL products"""
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
                
                # Wait for initial content to load
                await page.wait_for_timeout(5000)
                
                # SCROLL MULTIPLE TIMES to load all products
                logger.info("Scrolling to load all products...")
                
                # Get initial height
                last_height = await page.evaluate("document.body.scrollHeight")
                
                for scroll_attempt in range(5):  # Try up to 5 scrolls
                    # Scroll to bottom
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(3000)  # Wait for content to load
                    
                    # Check if we've reached the end
                    new_height = await page.evaluate("document.body.scrollHeight")
                    if new_height == last_height:
                        logger.info(f"Reached bottom after {scroll_attempt + 1} scrolls")
                        break
                    last_height = new_height
                    logger.info(f"Scroll {scroll_attempt + 1} complete, new height: {new_height}")
                
                # Scroll back up slowly to trigger any lazy loading
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(2000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                await page.wait_for_timeout(2000)
                
                # Get page content
                html_content = await page.content()
                
                # Count products in the page
                product_count = await page.evaluate("""
                    () => {
                        return document.querySelectorAll('[data-testid="product"]').length
                    }
                """)
                logger.info(f"Found {product_count} products in DOM")
                
                # Save debug files
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                await page.screenshot(path=f"tamimi_deals_{timestamp}.png", full_page=True)
                
                with open(f"tamimi_page_{timestamp}.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                logger.info(f"✅ Page loaded: {len(html_content)} chars, {product_count} products visible")
                return html_content
                
            except Exception as e:
                logger.error(f"Error: {e}")
                return ""
            finally:
                await browser.close()
    
    def parse_products(self, html_content):
        """Parse products using multiple selectors to catch ALL products"""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html_content, 'html.parser')
        products = []
        
        # METHOD 1: Find by data-testid (primary method)
        product_containers = soup.find_all('div', attrs={'data-testid': 'product'})
        logger.info(f"Method 1 - Found {len(product_containers)} products with data-testid='product'")
        
        # METHOD 2: Find by product link class
        if len(product_containers) < 50:
            alt_containers = soup.find_all('a', class_=re.compile(r'Product__StyledA'))
            logger.info(f"Method 2 - Found {len(alt_containers)} products with Product__StyledA class")
            if len(alt_containers) > len(product_containers):
                product_containers = alt_containers
        
        # METHOD 3: Find any div with product in class
        if len(product_containers) < 50:
            generic_containers = soup.find_all('div', class_=re.compile(r'product|item|card', re.I))
            logger.info(f"Method 3 - Found {len(generic_containers)} generic product containers")
            if len(generic_containers) > len(product_containers):
                product_containers = generic_containers
        
        logger.info(f"Total unique product containers to parse: {len(product_containers)}")
        
        for container in product_containers:
            try:
                # Try multiple ways to find discount
                discount = 0
                
                # Method A: Find discount in Product__StyledDiscount class
                discount_elem = container.find('div', class_=re.compile(r'Product__StyledDiscount'))
                if discount_elem:
                    discount_text = discount_elem.get_text(strip=True)
                    discount_match = re.search(r'(\d+)%', discount_text)
                    if discount_match:
                        discount = int(discount_match.group(1))
                
                # Method B: Look for any element with % sign
                if discount == 0:
                    all_text = container.get_text()
                    percent_matches = re.findall(r'(\d+)%', all_text)
                    if percent_matches:
                        discount = max([int(m) for m in percent_matches])  # Take the highest percentage
                
                if discount == 0:
                    continue  # Skip if no discount found
                
                # Find current price
                current_price = None
                
                # Method A: Find in Price__SellingPrice class
                price_elem = container.find('span', class_=re.compile(r'Price__SellingPrice'))
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    try:
                        current_price = float(price_text)
                    except:
                        pass
                
                # Method B: Look for price pattern
                if not current_price:
                    all_text = container.get_text()
                    price_matches = re.findall(r'(\d+\.?\d*)\s*SAR', all_text)
                    if price_matches:
                        try:
                            current_price = float(price_matches[0])
                        except:
                            pass
                
                if not current_price:
                    continue
                
                # Find original price
                original_price = None
                original_elem = container.find('span', class_=re.compile(r'Price__SellingPriceOutDated'))
                if original_elem:
                    original_text = original_elem.get_text(strip=True)
                    try:
                        original_price = float(original_text)
                    except:
                        pass
                
                # Find product name
                name = ""
                
                # Try structured name first
                brand_elem = container.find('span', class_=re.compile(r'ebqvdy'))
                name_elem = container.find('span', class_=re.compile(r'Product__StyledNameText'))
                
                if brand_elem and name_elem:
                    brand = brand_elem.get_text(strip=True)
                    product_name = name_elem.get_text(strip=True)
                    name = f"{brand} {product_name}".strip()
                else:
                    # Fallback: get title from any heading or link
                    title_elem = container.find(['h2', 'h3', 'h4', 'h5', 'a'], class_=re.compile(r'title|name', re.I))
                    if title_elem:
                        name = title_elem.get_text(strip=True)
                    else:
                        # Last resort: get first long text
                        all_text = container.get_text()
                        lines = [line.strip() for line in all_text.split('\n') if len(line.strip()) > 10]
                        if lines:
                            name = lines[0]
                
                # Get product URL
                url = ""
                if container.name == 'a' and container.get('href'):
                    href = container['href']
                else:
                    link = container.find('a', href=True)
                    href = link['href'] if link else ""
                
                if href:
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
                    
            except Exception as e:
                logger.debug(f"Error parsing container: {e}")
                continue
        
        # Remove duplicates based on URL
        unique_products = []
        seen_urls = set()
        for p in products:
            if p.url not in seen_urls:
                seen_urls.add(p.url)
                unique_products.append(p)
        
        logger.info(f"✅ Successfully parsed {len(unique_products)} unique products")
        return unique_products
    
    def send_telegram_alert(self, products):
        """Send alert to Telegram - ONLY for 69%+ discounts"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.error("Missing Telegram credentials")
            return
        
        # Filter for 69%+ discounts
        hot_deals = [p for p in products if p.discount_percent >= DISCOUNT_THRESHOLD]
        hot_deals.sort(key=lambda x: x.discount_percent, reverse=True)
        
        if not hot_deals:
            # No 69%+ deals - send detailed status
            message = f"🔍 <b>Tamimi Monitor - Scan Results</b>\n\n"
            message += f"📊 Total products scanned: {len(products)}\n"
            
            if products:
                # Show discount distribution
                discount_ranges = {
                    "60-69%": len([p for p in products if 60 <= p.discount_percent < 70]),
                    "50-59%": len([p for p in products if 50 <= p.discount_percent < 60]),
                    "40-49%": len([p for p in products if 40 <= p.discount_percent < 50]),
                    "30-39%": len([p for p in products if 30 <= p.discount_percent < 40]),
                    "20-29%": len([p for p in products if 20 <= p.discount_percent < 30]),
                    "10-19%": len([p for p in products if 10 <= p.discount_percent < 20]),
                    "0-9%": len([p for p in products if p.discount_percent < 10]),
                }
                
                message += "\n📈 <b>Discount Breakdown:</b>\n"
                for range_name, count in discount_ranges.items():
                    if count > 0:
                        message += f"  • {range_name}: {count} items\n"
                
                max_discount = max(p.discount_percent for p in products)
                message += f"\n✨ Highest discount found: <b>{max_discount}%</b>\n"
                
                # Show top deals
                top_deals = sorted(products, key=lambda x: x.discount_percent, reverse=True)[:3]
                message += "\n🏆 <b>Top 3 Deals:</b>\n"
                for deal in top_deals:
                    safe_name = pyhtml.escape(deal.name[:40])
                    message += f"  • {safe_name}... - {deal.discount_percent}% off\n"
            
            message += "\nI'll keep watching for 69%+ deals! 🤖"
            
        else:
            # We have 69%+ deals
            message = f"🔥🔥🔥 <b>MASSIVE {DISCOUNT_THRESHOLD}%+ DISCOUNTS!</b> 🔥🔥🔥\n\n"
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
        
        # Send alert
        self.send_telegram_alert(self.products)
        logger.info("=" * 60)


async def main():
    scraper = TamimiScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
