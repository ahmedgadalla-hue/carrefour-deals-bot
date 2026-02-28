"""
Tamimi Markets Hot Deals Monitor - COMPLETE FIX
Now finds ALL products on the page
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
        """Fetch page with PROPER waiting for all products to load"""
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
                
                # Go to page and wait for network to be idle
                await page.goto(HOT_DEALS_URL, wait_until='networkidle', timeout=60000)
                
                # Wait for products to start loading
                await page.wait_for_selector('[data-testid="product"]', timeout=10000)
                logger.info("✅ Products found on page")
                
                # Get initial product count
                initial_count = await page.evaluate("document.querySelectorAll('[data-testid=\"product\"]').length")
                logger.info(f"Initial product count: {initial_count}")
                
                # SCROLL MULTIPLE TIMES to load all products
                logger.info("Scrolling to load all products...")
                
                previous_count = 0
                scroll_attempts = 0
                max_scroll_attempts = 10
                
                while scroll_attempts < max_scroll_attempts:
                    # Scroll to bottom
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(3000)  # Wait for new products to load
                    
                    # Get current product count
                    current_count = await page.evaluate("document.querySelectorAll('[data-testid=\"product\"]').length")
                    logger.info(f"Scroll {scroll_attempts + 1}: Found {current_count} products")
                    
                    # Check if we've stopped getting new products
                    if current_count == previous_count:
                        logger.info(f"No new products after scroll {scroll_attempts + 1}")
                        break
                    
                    previous_count = current_count
                    scroll_attempts += 1
                
                # Final product count
                final_count = await page.evaluate("document.querySelectorAll('[data-testid=\"product\"]').length")
                logger.info(f"✅ Total products loaded: {final_count}")
                
                # Get ALL product data directly from the page using JavaScript
                products_data = await page.evaluate("""
                    () => {
                        const products = [];
                        const productElements = document.querySelectorAll('[data-testid="product"]');
                        
                        productElements.forEach((element) => {
                            try {
                                // Get discount
                                let discount = 0;
                                const discountElem = element.querySelector('[class*="Product__StyledDiscount"]');
                                if (discountElem) {
                                    const discountText = discountElem.innerText;
                                    const match = discountText.match(/(\\d+)%/);
                                    if (match) discount = parseInt(match[1]);
                                }
                                
                                // Get current price
                                let currentPrice = 0;
                                const priceElem = element.querySelector('[class*="Price__SellingPrice"]');
                                if (priceElem) {
                                    currentPrice = parseFloat(priceElem.innerText);
                                }
                                
                                // Get original price
                                let originalPrice = null;
                                const originalElem = element.querySelector('[class*="Price__SellingPriceOutDated"]');
                                if (originalElem) {
                                    originalPrice = parseFloat(originalElem.innerText);
                                }
                                
                                // Get name
                                let name = '';
                                const brandElem = element.querySelector('[class*="ebqvdy"]');
                                const nameElem = element.querySelector('[class*="Product__StyledNameText"]');
                                
                                if (brandElem && nameElem) {
                                    name = (brandElem.innerText + ' ' + nameElem.innerText).trim();
                                } else {
                                    const titleElem = element.querySelector('[class*="Product__StyledTitle"]');
                                    if (titleElem) name = titleElem.innerText.trim();
                                }
                                
                                // Get URL
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
                
                logger.info(f"✅ Extracted {len(products_data)} products via JavaScript")
                
                # Also get HTML for backup
                html_content = await page.content()
                
                # Save debug files
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                await page.screenshot(path=f"tamimi_deals_{timestamp}.png", full_page=True)
                
                with open(f"tamimi_page_{timestamp}.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                # Save the extracted products as JSON
                with open(f"products_{timestamp}.json", "w", encoding="utf-8") as f:
                    json.dump(products_data, f, indent=2)
                
                logger.info(f"✅ Page loaded with {len(products_data)} products")
                return products_data
                
            except Exception as e:
                logger.error(f"Error: {e}")
                return []
            finally:
                await browser.close()
    
    def parse_products(self, products_data):
        """Convert the JavaScript-extracted data to Product objects"""
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
                logger.info(f"✅ Found: {product.name[:30]}... - {product.discount_percent}% off - {product.current_price} SAR")
                
            except Exception as e:
                logger.debug(f"Error creating product: {e}")
                continue
        
        return products
    
    def send_telegram_alert(self, products):
        """Send alert to Telegram - ONLY for 69%+ discounts"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.error("Missing Telegram credentials")
            return
        
        # Filter for 69%+ discounts
        hot_deals = [p for p in products if p.discount_percent >= DISCOUNT_THRESHOLD]
        hot_deals.sort(key=lambda x: x.discount_percent, reverse=True)
        
        if not hot_deals:
            # No 69%+ deals - send detailed status with ALL products found
            message = f"🔍 <b>Tamimi Monitor - Complete Scan Results</b>\n\n"
            message += f"📊 Total products scanned: <b>{len(products)}</b>\n"
            
            if products:
                # Show discount distribution for ALL products
                ranges = [
                    (60, 69), (50, 59), (40, 49), (30, 39), 
                    (20, 29), (10, 19), (0, 9)
                ]
                
                message += "\n📈 <b>Discount Breakdown:</b>\n"
                for low, high in ranges:
                    count = len([p for p in products if low <= p.discount_percent <= high])
                    if count > 0:
                        message += f"  • {low}-{high}%: {count} items\n"
                
                # Show ALL products with their discounts
                sorted_products = sorted(products, key=lambda x: x.discount_percent, reverse=True)
                
                message += f"\n📋 <b>All Products Found ({len(products)}):</b>\n"
                for i, product in enumerate(sorted_products[:15], 1):  # Show first 15
                    safe_name = pyhtml.escape(product.name[:40])
                    message += f"  {i}. {safe_name}... - <b>{product.discount_percent}%</b> off\n"
                
                if len(products) > 15:
                    message += f"  ... and {len(products) - 15} more products\n"
                
                max_discount = max(p.discount_percent for p in products)
                message += f"\n✨ <b>Highest discount found: {max_discount}%</b>\n"
                
                # Check if there are any 70%+ deals
                high_deals = [p for p in products if p.discount_percent >= 70]
                if high_deals:
                    message += f"\n⚠️ <b>WARNING: Found {len(high_deals)} items with 70%+ discount but threshold is set to 69%!</b>\n"
                    for deal in high_deals[:3]:
                        message += f"  • {pyhtml.escape(deal.name[:30])}... - {deal.discount_percent}% off\n"
            
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
        
        products_data = await self.fetch_page()
        if not products_data:
            logger.error("❌ No products found")
            return
        
        self.products = self.parse_products(products_data)
        
        # Send alert
        self.send_telegram_alert(self.products)
        logger.info("=" * 60)


async def main():
    scraper = TamimiScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
