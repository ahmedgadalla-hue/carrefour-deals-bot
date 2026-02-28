"""
Tamimi Markets Hot Deals Monitor - ULTIMATE FIXED VERSION
With correct import order
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

# ================= SETUP LOGGING FIRST =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# ======================================================

# ================= TRY STEALTH IMPORTS =================
STEALTH_AVAILABLE = False

try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
    logger.info("✅ Successfully imported stealth_async")
except ImportError:
    try:
        import playwright_stealth
        STEALTH_AVAILABLE = True
        logger.info("✅ Successfully imported playwright_stealth module")
    except ImportError as e:
        STEALTH_AVAILABLE = False
        logger.warning(f"⚠️ Playwright stealth not available: {e}")
        logger.warning("Using manual stealth techniques instead")
# =======================================================

# ================= CONFIGURATION =================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DISCOUNT_THRESHOLD = int(os.environ.get("DISCOUNT_THRESHOLD", "50"))

BASE_URL = "https://shop.tamimimarkets.com"
HOT_DEALS_URL = f"{BASE_URL}/en/hot-deals"
# =================================================


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
    
    async def apply_stealth(self, page):
        """Apply stealth techniques"""
        
        if STEALTH_AVAILABLE:
            try:
                # Try different stealth methods
                if 'stealth_async' in dir():
                    await stealth_async(page)
                    logger.info("✅ Applied stealth via stealth_async")
                else:
                    import playwright_stealth
                    await playwright_stealth.stealth_async(page)
                    logger.info("✅ Applied stealth via playwright_stealth.stealth_async")
                return
            except Exception as e:
                logger.warning(f"⚠️ Stealth package failed: {e}, using manual")
        
        # Manual stealth fallback
        logger.info("Applying manual stealth techniques...")
        await page.add_init_script("""
            // Override navigator properties
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // Add chrome object
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: 'prompt' }) :
                    originalQuery(parameters)
            );
            
            // Remove webdriver trace
            delete navigator.__proto__.webdriver;
        """)
    
    async def fetch_page(self):
        """Fetch page with stealth techniques"""
        async with async_playwright() as p:
            # Launch browser with anti-detection args
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                ]
            )
            
            # Create context with realistic settings
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='Asia/Riyadh',
            )
            
            page = await context.new_page()
            
            # Apply stealth
            await self.apply_stealth(page)
            
            try:
                logger.info(f"Navigating to {HOT_DEALS_URL}")
                
                # Add random delay
                await asyncio.sleep(random.uniform(2, 5))
                
                # Navigate
                await page.goto(
                    HOT_DEALS_URL, 
                    wait_until='domcontentloaded', 
                    timeout=60000
                )
                
                # Wait for page to load
                await page.wait_for_timeout(5000)
                
                # Check page
                page_title = await page.title()
                logger.info(f"Page title: {page_title}")
                
                # Scroll
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(3000)
                
                # Get content
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
        """Parse products from HTML"""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html_content, 'html.parser')
        products = []
        
        # Find product containers
        containers = soup.find_all(['div', 'article', 'li'], 
                                  class_=re.compile(r'product|item|card|offer', re.I))
        
        logger.info(f"Found {len(containers)} product containers")
        
        for container in containers[:50]:
            try:
                container_text = container.get_text(separator=' ', strip=True)
                
                # Must have price and discount
                if 'SAR' not in container_text.upper():
                    continue
                    
                if '%' not in container_text:
                    continue
                
                # Extract discount
                discount_match = re.search(r'(\d+)%', container_text)
                if not discount_match:
                    continue
                discount = int(discount_match.group(1))
                
                # Extract price
                price_match = re.search(r'SAR\s*(\d+\.?\d*)', container_text, re.IGNORECASE)
                if not price_match:
                    price_match = re.search(r'(\d+\.?\d*)\s*SAR', container_text, re.IGNORECASE)
                if not price_match:
                    continue
                price = float(price_match.group(1))
                
                # Extract name
                name = ""
                
                # Try headings
                headings = container.find_all(['h2', 'h3', 'h4', 'h5'])
                if headings:
                    for h in headings:
                        h_text = h.get_text(strip=True)
                        if h_text and len(h_text) > len(name):
                            name = h_text
                
                # Try title classes
                if not name or len(name) < 3:
                    title = container.find(class_=re.compile(r'title|name', re.I))
                    if title:
                        name = title.get_text(strip=True)
                
                # Try links
                if not name or len(name) < 3:
                    link = container.find('a', href=True)
                    if link:
                        link_text = link.get_text(strip=True)
                        if link_text and len(link_text) > 3:
                            name = link_text
                
                # Clean name
                name = re.sub(r'\s+', ' ', name).strip()
                
                if name and price and discount > 0:
                    # Calculate original price
                    original = round(price / (1 - discount/100), 2) if discount < 100 else None
                    
                    # Get URL
                    url = ""
                    link = container.find('a', href=True)
                    if link:
                        href = link['href']
                        if href.startswith('http'):
                            url = href
                        elif href.startswith('/'):
                            url = BASE_URL + href
                    
                    product = Product(
                        name=name[:100],
                        current_price=price,
                        original_price=original,
                        discount_percent=discount,
                        url=url
                    )
                    products.append(product)
                    logger.info(f"✅ Found: {name[:30]}... - {discount}% off - {price} SAR")
                    
            except Exception as e:
                logger.debug(f"Error parsing: {e}")
                continue
        
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
            message = f"🔥 <b>TAMIMI MARKETS - HOT DEALS</b> 🔥\n\n"
            message += f"Found <b>{len(products)}</b> items with ≥{DISCOUNT_THRESHOLD}% off\n\n"
            
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
            
            if len(products) > 10:
                message += f"...and {len(products)-10} more deals!"
        
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
        
        hot_deals = [p for p in self.products if p.discount_percent >= DISCOUNT_THRESHOLD]
        logger.info(f"🔥 Hot deals (≥{DISCOUNT_THRESHOLD}%): {len(hot_deals)}")
        
        self.send_telegram_alert(hot_deals)
        logger.info("=" * 60)


async def main():
    scraper = TamimiScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
