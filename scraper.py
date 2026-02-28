"""
Tamimi Markets Hot Deals Monitor - 50-99% DISCOUNTS
Checks ALL products on the hot deals page and notifies for any between 50-99%
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
MIN_DISCOUNT = 50  # Minimum discount to report (50%)
MAX_DISCOUNT = 99  # Maximum discount to report (99%)

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
        """Fetch the hot deals page and extract ALL products"""
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
                
                # Go to page and wait for content
                await page.goto(HOT_DEALS_URL, wait_until='networkidle', timeout=60000)
                
                # Wait for products to appear
                await page.wait_for_selector('[data-testid="product"]', timeout=10000)
                logger.info("✅ Products found on page")
                
                # SCROLL TO LOAD ALL PRODUCTS
                logger.info("Scrolling to load all products...")
                
                previous_count = 0
                scroll_attempts = 0
                max_scroll_attempts = 15  # Increased to ensure we get everything
                
                while scroll_attempts < max_scroll_attempts:
                    # Scroll to bottom
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(3000)  # Wait for new products
                    
                    # Check how many products we have now
                    current_count = await page.evaluate("document.querySelectorAll('[data-testid=\"product\"]').length")
                    logger.info(f"Scroll {scroll_attempts + 1}: Found {current_count} products")
                    
                    # Stop if no new products
                    if current_count == previous_count:
                        logger.info(f"No new products after {scroll_attempts + 1} scrolls")
                        break
                    
                    previous_count = current_count
                    scroll_attempts += 1
                
                # Final product count
                final_count = await page.evaluate("document.querySelectorAll('[data-testid=\"product\"]').length")
                logger.info(f"✅ Total products loaded: {final_count}")
                
                # EXTRACT ALL PRODUCTS USING JAVASCRIPT
                products_data = await page.evaluate("""
                    () => {
                        const products = [];
                        const productElements = document.querySelectorAll('[data-testid="product"]');
                        
                        productElements.forEach((element) => {
                            try {
                                // Get discount percentage
                                let discount = 0;
                                const discountElem = element.querySelector('[class*="Product__StyledDiscount"]');
                                if (discountElem) {
                                    const discountText = discountElem.innerText;
                                    const match = discountText.match(/(\\d+)%/);
                                    if (match) discount = parseInt(match[1]);
                                }
                                
                                // If no discount badge, try to find percentage in text
                                if (discount === 0) {
                                    const text = element.innerText;
                                    const matches = text.match(/(\\d+)%\\s*OFF/);
                                    if (matches) discount = parseInt(matches[1]);
                                }
                                
                                // Get current price
                                let currentPrice = 0;
                                const priceElem = element.querySelector('[class*="Price__SellingPrice"]');
                                if (priceElem) {
                                    currentPrice = parseFloat(priceElem.innerText);
                                }
                                
                                // Get original price (if discounted)
                                let originalPrice = null;
                                const originalElem = element.querySelector('[class*="Price__SellingPriceOutDated"]');
                                if (originalElem) {
                                    originalPrice = parseFloat(originalElem.innerText);
                                }
                                
                                // Get product name
                                let name = '';
                                const brandElem = element.querySelector('[class*="ebqvdy"]');
                                const nameElem = element.querySelector('[class*="Product__StyledNameText"]');
                                
                                if (brandElem && nameElem) {
                                    name = (brandElem.innerText + ' ' + nameElem.innerText).trim();
                                } else {
                                    const titleElem = element.querySelector('[class*="Product__StyledTitle"]');
                                    if (titleElem) name = titleElem.innerText.trim();
                                }
                                
                                // Get product URL
                                let url = '';
                                const link = element.closest('a');
                                if (link && link.href) url = link.href;
                                
                                if (name && currentPrice > 0 && discount > 0) {
                                    products.push({
                                        name: name,
                                        current_price: currentPrice,
                                        original_price: originalPrice,
                                        discount_percent: discount,
                                        url: url
                                    });
                                }
                            } catch (e) {
                                console.error('Error parsing product:', e);
                            }
                        });
                        
                        return products;
                    }
                """)
                
                logger.info(f"✅ Successfully extracted {len(products_data)} products")
                
                # Save debug files
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                await page.screenshot(path=f"tamimi_deals_{timestamp}.png", full_page=True)
                
                with open(f"tamimi_products_{timestamp}.json", "w", encoding="utf-8") as f:
                    json.dump(products_data, f, indent=2)
                
                return products_data
                
            except Exception as e:
                logger.error(f"Error: {e}")
                return []
            finally:
                await browser.close()
    
    def process_products(self, products_data):
        """Convert data to Product objects"""
        products = []
        
        for item in products_data:
            try:
                product = Product(
                    name=item.get('name', '')[:100],
                    current_price=item.get('current_price', 0),
                    original_price=item.get('original_price'),
                    discount_percent=item.get('discount_percent', 0),
                    url=item.get('url', '')
                )
                products.append(product)
                
            except Exception as e:
                logger.debug(f"Error creating product: {e}")
                continue
        
        # Sort by discount (highest first)
        products.sort(key=lambda x: x.discount_percent, reverse=True)
        
        return products
    
    def send_telegram_alert(self, products):
        """Send alert for products with 50-99% discounts"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.error("Missing Telegram credentials")
            return
        
        # Filter for 50-99% discounts
        hot_deals = [p for p in products if MIN_DISCOUNT <= p.discount_percent <= MAX_DISCOUNT]
        
        if not hot_deals:
            # No 50-99% deals - send summary of all deals
            message = f"🔍 <b>Tamimi Monitor - Hot Deals Summary</b>\n\n"
            message += f"📊 Total products found: <b>{len(products)}</b>\n\n"
            
            if products:
                # Show discount distribution
                ranges = [
                    (90, 99), (80, 89), (70, 79), (60, 69), 
                    (50, 59), (40, 49), (30, 39), (20, 29), 
                    (10, 19), (0, 9)
                ]
                
                message += "📈 <b>Discount Breakdown:</b>\n"
                for high, low in ranges:
                    count = len([p for p in products if low <= p.discount_percent <= high])
                    if count > 0:
                        message += f"  • {low}-{high}%: {count} items\n"
                
                # Show top 5 deals overall
                message += f"\n🏆 <b>Top 5 Deals Today:</b>\n"
                for i, product in enumerate(products[:5], 1):
                    safe_name = pyhtml.escape(product.name[:40])
                    message += f"  {i}. {safe_name}... - <b>{product.discount_percent}%</b> off\n"
                
                # Check if there are any 50%+ deals
                fifty_plus = [p for p in products if p.discount_percent >= 50]
                if fifty_plus:
                    message += f"\n⚠️ Found {len(fifty_plus)} items with 50%+ discount!\n"
                    message += f"   Highest: {fifty_plus[0].discount_percent}%"
            
            message += f"\n\nI'll alert you when {MIN_DISCOUNT}-{MAX_DISCOUNT}% deals appear! 🤖"
            
        else:
            # We have 50-99% deals - send detailed alert
            message = f"🔥🔥🔥 <b>HOT DEALS ALERT! ({MIN_DISCOUNT}-{MAX_DISCOUNT}% OFF)</b> 🔥🔥🔥\n\n"
            message += f"Found <b>{len(hot_deals)}</b> items with {MIN_DISCOUNT}-{MAX_DISCOUNT}% discounts!\n\n"
            
            # Group by discount range
            ranges = [(90,99), (80,89), (70,79), (60,69), (50,59)]
            for high, low in ranges:
                range_deals = [p for p in hot_deals if low <= p.discount_percent <= high]
                if range_deals:
                    message += f"<b>{low}-{high}% OFF ({len(range_deals)} items):</b>\n"
                    for product in range_deals[:3]:  # Show up to 3 per range
                        safe_name = pyhtml.escape(product.name[:40])
                        message += f"  • {safe_name}... - {product.discount_percent}%\n"
                    if len(range_deals) > 3:
                        message += f"  ... and {len(range_deals)-3} more\n"
                    message += "\n"
            
            # Show all deals in detail
            message += f"<b>Complete List ({len(hot_deals)} items):</b>\n\n"
            for i, product in enumerate(hot_deals[:20], 1):  # Show up to 20 deals
                safe_name = pyhtml.escape(product.name[:50])
                message += f"<b>{i}. {safe_name}</b>\n"
                
                if product.original_price:
                    message += f"   <s>{product.original_price:.2f} SAR</s> → "
                message += f"<b>{product.current_price:.2f} SAR</b>"
                message += f"  <b>(-{product.discount_percent}%)</b>\n"
                
                if product.url:
                    message += f"   <a href='{product.url}'>View Product</a>\n"
                message += "\n"
            
            if len(hot_deals) > 20:
                message += f"...and {len(hot_deals)-20} more deals!"
        
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
                    logger.info(f"🔥 Found {len(hot_deals)} deals with {MIN_DISCOUNT}-{MAX_DISCOUNT}% off")
            else:
                logger.error(f"❌ Telegram error: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Failed to send: {e}")
    
    async def run(self):
        """Main execution"""
        logger.info("=" * 60)
        logger.info(f"🚀 Starting Tamimi Markets Hot Deals Monitor")
        logger.info(f"🎯 Looking for discounts between {MIN_DISCOUNT}% and {MAX_DISCOUNT}%")
        logger.info("=" * 60)
        
        products_data = await self.fetch_page()
        if not products_data:
            logger.error("❌ No products found")
            return
        
        self.products = self.process_products(products_data)
        
        # Log summary
        logger.info(f"📦 Total products: {len(self.products)}")
        
        # Count by discount range
        ranges = [(90,99), (80,89), (70,79), (60,69), (50,59), (40,49), (30,39), (20,29), (10,19), (0,9)]
        for high, low in ranges:
            count = len([p for p in self.products if low <= p.discount_percent <= high])
            if count > 0:
                logger.info(f"📊 {low}-{high}%: {count} items")
        
        # Send alert
        self.send_telegram_alert(self.products)
        logger.info("=" * 60)


async def main():
    scraper = TamimiScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
