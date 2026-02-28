"""
Tamimi Markets Hot Deals Monitor - ULTIMATE VERSION
Uses stealth techniques to bypass bot detection
"""

import os
import re
import json
import logging
import asyncio
import random
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import html as pyhtml

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from fake_useragent import UserAgent
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
        self.ua = UserAgent()
    
    async def fetch_page(self):
        """Fetch page with multiple stealth techniques"""
        async with async_playwright() as p:
            # Launch with anti-detection args
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-site-isolation-trials',
                    '--disable-features=BlockInsecurePrivateNetworkRequests',
                    '--disable-features=OutOfBlinkCors'
                ]
            )
            
            # Create context with realistic viewport and random user agent
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=self.ua.random,
                locale='en-US',
                timezone_id='Asia/Riyadh',
                permissions=['geolocation'],
                geolocation={'longitude': 46.6753, 'latitude': 24.7136},  # Riyadh coordinates
            )
            
            page = await context.new_page()
            
            # Apply stealth scripts
            await stealth_async(page)
            
            # Add more stealth scripts
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
                
                // Add chrome property
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
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)
            
            try:
                logger.info(f"Navigating to {HOT_DEALS_URL}")
                
                # Add random delay before navigation
                await asyncio.sleep(random.uniform(2, 5))
                
                # Navigate with longer timeout
                response = await page.goto(
                    HOT_DEALS_URL,
                    wait_until='domcontentloaded',
                    timeout=60000
                )
                
                if not response:
                    logger.error("No response received")
                    return ""
                
                logger.info(f"Response status: {response.status}")
                
                # Wait for page to stabilize
                await page.wait_for_timeout(random.uniform(5000, 8000))
                
                # Check if we're being blocked
                page_title = await page.title()
                page_content = await page.content()
                
                if any(term in page_title.lower() or term in page_content.lower() 
                       for term in ['cloudflare', 'ddos', 'blocked', 'access denied', 'captcha']):
                    logger.warning("⚠️ Bot protection detected!")
                    await page.screenshot(path="blocked.png")
                    return ""
                
                # Scroll slowly like a human
                for i in range(3):
                    await page.evaluate(f"window.scrollTo(0, {i * 500})")
                    await page.wait_for_timeout(random.uniform(1000, 2000))
                
                # Get page content
                html_content = await page.content()
                
                # Save debug files
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                await page.screenshot(path=f"tamimi_deals_{timestamp}.png")
                
                with open(f"tamimi_page_{timestamp}.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                logger.info(f"✅ Page loaded successfully: {len(html_content)} chars")
                return html_content
                
            except Exception as e:
                logger.error(f"Error during page fetch: {e}")
                return ""
            finally:
                await browser.close()
    
    def parse_products(self, html_content):
        """Parse products from HTML"""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html_content, 'html.parser')
        products = []
        
        # Method 1: Find by discount badges
        logger.info("Searching for discount badges...")
        
        # Look for percentage patterns
        discount_patterns = [
            r'(\d+)%\s*OFF',
            r'(\d+)%',
            r'-(\d+)%',
            r'SAVE\s*(\d+)%'
        ]
        
        all_text = soup.get_text()
        
        for pattern in discount_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            if matches:
                logger.info(f"Found {len(matches)} discounts using pattern: {pattern}")
        
        # Find product containers
        containers = soup.find_all(['div', 'article'], class_=re.compile(
            r'product|item|card|offer|grid|tile', re.I
        ))
        
        logger.info(f"Found {len(containers)} potential product containers")
        
        for container in containers[:50]:  # Limit to first 50
            try:
                container_text = container.get_text(separator=' ', strip=True)
                
                # Check if container has price and percentage
                if 'SAR' not in container_text.upper() and 'ر.س' not in container_text:
                    continue
                    
                if '%' not in container_text:
                    continue
                
                # Extract discount percentage
                discount_match = re.search(r'(\d+)%', container_text)
                if not discount_match:
                    continue
                    
                discount = int(discount_match.group(1))
                
                # Extract price
                price_match = re.search(r'SAR\s*(\d+\.?\d*)', container_text, re.IGNORECASE)
                if not price_match:
                    price_match = re.search(r'(\d+\.?\d*)\s*SAR', container_text, re.IGNORECASE)
                if not price_match:
                    price_match = re.search(r'(\d+\.?\d*)\s*ر\.س', container_text)
                
                if not price_match:
                    continue
                    
                price = float(price_match.group(1))
                
                # Extract product name
                name = ""
                
                # Try headings first
                headings = container.find_all(['h2', 'h3', 'h4', 'h5', 'h6', 'strong'])
                if headings:
                    # Get the longest heading as name
                    name = max([h.get_text(strip=True) for h in headings if h.get_text(strip=True)], 
                              key=len, default="")
                
                # If no headings, try other elements
                if not name or len(name) < 5:
                    title_elem = container.find(class_=re.compile(r'title|name', re.I))
                    if title_elem:
                        name = title_elem.get_text(strip=True)
                
                # Last resort: get text before price
                if not name or len(name) < 5:
                    parts = container_text.split('SAR')[0].split('%')[0]
                    name = parts.strip()
                    if len(name) > 50:
                        name = name[:50]
                
                # Clean up name
                name = re.sub(r'\s+', ' ', name).strip()
                
                if name and price and discount > 0:
                    # Calculate original price
                    original_price = round(price / (1 - discount/100), 2) if discount < 100 else None
                    
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
                        original_price=original_price,
                        discount_percent=discount,
                        url=url
                    )
                    products.append(product)
                    logger.info(f"✅ Found: {name[:30]}... - {discount}% off - {price} SAR")
                    
            except Exception as e:
                logger.debug(f"Error parsing container: {e}")
                continue
        
        return products
    
    def send_telegram_alert(self, products):
        """Send alert to Telegram"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.error("Telegram credentials missing")
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
                logger.info(f"✅ Telegram alert sent for {len(products)} products")
            else:
                logger.error(f"❌ Telegram error: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram: {e}")
    
    async def run(self):
        """Main execution"""
        logger.info("=" * 60)
        logger.info("🚀 Starting Tamimi Markets Monitor")
        logger.info(f"📊 Looking for discounts ≥ {DISCOUNT_THRESHOLD}%")
        logger.info("=" * 60)
        
        # Fetch page
        html = await self.fetch_page()
        if not html:
            logger.error("❌ Failed to fetch page")
            return
        
        # Parse products
        self.products = self.parse_products(html)
        logger.info(f"📦 Total products found: {len(self.products)}")
        
        # Show discount distribution
        if self.products:
            discounts = [p.discount_percent for p in self.products]
            logger.info(f"📈 Discount range: {min(discounts)}% - {max(discounts)}%")
            logger.info(f"📊 Average discount: {sum(discounts)/len(discounts):.1f}%")
        
        # Filter hot deals
        hot_deals = [p for p in self.products if p.discount_percent >= DISCOUNT_THRESHOLD]
        logger.info(f"🔥 Hot deals (≥{DISCOUNT_THRESHOLD}%): {len(hot_deals)}")
        
        # Send alerts
        self.send_telegram_alert(hot_deals)
        
        logger.info("=" * 60)
        logger.info("✅ Monitor run completed")
        logger.info("=" * 60)


async def main():
    scraper = TamimiScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
