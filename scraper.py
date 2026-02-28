"""
Tamimimarkets Hot Deals Monitor
Scrapes https://shop.tamimimarkets.com/ar/hot-deals for big discounts
Sends Telegram alerts for items with ≥50% discount
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
# Telegram (you provided this)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "7420001477")  # Your ID
DISCOUNT_THRESHOLD = int(os.environ.get("DISCOUNT_THRESHOLD", "50"))

# Tamimimarkets URLs
BASE_URL = "https://shop.tamimimarkets.com"
HOT_DEALS_URL = f"{BASE_URL}/ar/hot-deals"

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
]
# =================================================

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Product:
    """Data class for product information"""
    name: str
    current_price: float
    original_price: Optional[float] = None
    discount_percent: float = 0
    url: str = ""
    image_url: str = ""
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class TamimiScraper:
    """Main scraper class for Tamimimarkets hot deals"""
    
    def __init__(self):
        self.products: List[Product] = []
        self.session_data = {
            "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "products_found": 0,
            "big_discounts": 0
        }
    
    async def fetch_page(self) -> str:
        """
        Fetch the hot deals page using Playwright with anti-detection
        """
        async with async_playwright() as p:
            # Launch browser with stealth settings for GitHub Actions
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process'
                ]
            )
            
            # Create context with Arabic locale
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=USER_AGENTS[0],
                locale='ar-SA',  # Arabic locale
                timezone_id='Asia/Riyadh'
            )
            
            page = await context.new_page()
            
            # Add stealth scripts to avoid detection
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                window.chrome = { runtime: {} };
            """)
            
            try:
                logger.info(f"Navigating to {HOT_DEALS_URL}")
                
                # Navigate with timeout
                response = await page.goto(
                    HOT_DEALS_URL,
                    wait_until='domcontentloaded',
                    timeout=60000
                )
                
                if not response or not response.ok:
                    logger.error(f"Failed to load page: {response.status if response else 'No response'}")
                    return ""
                
                # Wait for page to stabilize
                await page.wait_for_timeout(5000)
                
                # Scroll to load lazy content
                await page.evaluate("""
                    window.scrollTo({
                        top: document.body.scrollHeight,
                        behavior: 'smooth'
                    });
                """)
                
                await page.wait_for_timeout(3000)
                
                # Try to find product elements - Tamimimarkets specific selectors
                # Based on typical e-commerce structures in the region
                selectors = [
                    '.product-item',  # Common class
                    '.product-card',  # Common class
                    '[class*="product"]',  # Any class containing "product"
                    '.item',  # Generic item class
                    '.grid-item',  # Grid items
                    '.col',  # Column items
                    'article',  # Article elements
                ]
                
                found = False
                for selector in selectors:
                    try:
                        elements = await page.locator(selector).count()
                        if elements > 0:
                            logger.info(f"Found {elements} elements with selector: {selector}")
                            found = True
                            break
                    except:
                        continue
                
                if not found:
                    logger.warning("Could not find product elements with any selector")
                    # Take screenshot for debugging
                    await page.screenshot(path="debug_screenshot.png")
                
                # Get page content
                html = await page.content()
                logger.info(f"Successfully fetched page, length: {len(html)} characters")
                
                return html
                
            except Exception as e:
                logger.error(f"Error during page fetch: {str(e)}")
                # Try to take screenshot on error
                try:
                    await page.screenshot(path="error_screenshot.png")
                except:
                    pass
                return ""
            finally:
                await browser.close()
    
    def extract_price_sar(self, text: str) -> Optional[float]:
        """
        Extract price in SAR from text
        Handles formats like: "ر.س 12.99", "12.99 ر.س", "12,99", etc.
        """
        if not text:
            return None
        
        # Remove Arabic currency symbol and whitespace
        cleaned = text.replace('ر.س', '').replace('ر.س', '').strip()
        cleaned = re.sub(r'\s+', '', cleaned)
        
        # Convert Arabic numbers if present (optional, but good to handle)
        arabic_to_english = {
            '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
            '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
        }
        for ar, en in arabic_to_english.items():
            cleaned = cleaned.replace(ar, en)
        
        # Replace comma with dot for decimal
        cleaned = cleaned.replace(',', '.')
        
        # Extract number pattern
        match = re.search(r'(\d+(?:\.\d{1,2})?)', cleaned)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None
    
    def parse_products(self, html: str) -> List[Product]:
        """
        Parse HTML to extract product information
        Uses multiple selector strategies for Tamimimarkets
        """
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, 'html.parser')
        products = []
        
        # Tamimimarkets specific selectors for product containers
        container_selectors = [
            '.product-item',
            '.product-card',
            '.item-product',
            '.grid-product',
            '[class*="product"]',
            '.item',
            '.col-6',  # Common in grid layouts
            '.col-md-4',
            '.col-sm-6',
            'article',
            'li.product',
            'div.product'
        ]
        
        product_elements = []
        for selector in container_selectors:
            elements = soup.select(selector)
            if elements:
                logger.info(f"Found {len(elements)} elements with selector: {selector}")
                product_elements = elements
                break
        
        if not product_elements:
            # Fallback: look for any div with product-related classes
            product_elements = soup.find_all('div', class_=re.compile(r'product|item|card', re.I))
        
        logger.info(f"Total potential product elements found: {len(product_elements)}")
        
        # Limit to first 50 products to avoid overwhelming
        for element in product_elements[:50]:
            try:
                # Extract product name - try multiple selectors
                name = None
                name_selectors = [
                    'h2', 'h3', 'h4', 'h5',
                    '.product-name', 
                    '.product-title',
                    '.name',
                    '.title',
                    '[class*="name"]',
                    '[class*="title"]'
                ]
                
                for selector in name_selectors:
                    name_elem = element.select_one(selector) if '.' in selector or '[' in selector else element.find(selector)
                    if name_elem:
                        name = name_elem.get_text(strip=True)
                        if name and len(name) > 2:
                            break
                
                if not name:
                    # Try any heading or strong element
                    for heading in ['h2', 'h3', 'h4', 'h5', 'strong']:
                        elem = element.find(heading)
                        if elem:
                            name = elem.get_text(strip=True)
                            if name:
                                break
                
                if not name:
                    continue
                
                # Extract prices
                current_price = None
                original_price = None
                
                # Look for current price
                price_selectors = [
                    '.price',
                    '.current-price',
                    '.sale-price',
                    '.special-price',
                    '.product-price',
                    '[class*="price"]',
                    '.amount',
                    '.regular-price'
                ]
                
                for selector in price_selectors:
                    price_elem = element.select_one(selector) if '.' in selector or '[' in selector else element.find(class_=re.compile(r'price|amount', re.I))
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        current_price = self.extract_price_sar(price_text)
                        if current_price:
                            break
                
                # If no price found with specific selectors, look for any element containing SAR
                if not current_price:
                    all_spans = element.find_all(['span', 'div', 'p', 'ins'])
                    for span in all_spans:
                        if 'ر.س' in span.get_text():
                            price_text = span.get_text(strip=True)
                            current_price = self.extract_price_sar(price_text)
                            if current_price:
                                break
                
                # Look for original price (strikethrough or old price)
                old_price_selectors = [
                    '.old-price',
                    '.strikethrough',
                    's',
                    'del',
                    '.regular-price',
                    '.old',
                    '[class*="old"]',
                    '.was-price'
                ]
                
                for selector in old_price_selectors:
                    old_elem = element.select_one(selector) if '.' in selector or '[' in selector else element.find(['del', 's'])
                    if old_elem:
                        old_text = old_elem.get_text(strip=True)
                        original_price = self.extract_price_sar(old_text)
                        if original_price:
                            break
                
                # If no original price found, check if there are multiple prices
                if not original_price and current_price:
                    # Look for any other price element that might be the original
                    all_prices = element.find_all(class_=re.compile(r'price|amount', re.I))
                    if len(all_prices) >= 2:
                        # Assume the higher price is the original
                        prices = []
                        for price_elem in all_prices:
                            p_text = price_elem.get_text(strip=True)
                            p_val = self.extract_price_sar(p_text)
                            if p_val:
                                prices.append(p_val)
                        
                        if len(prices) >= 2:
                            prices.sort()
                            current_price = prices[0]  # Lower price is current
                            original_price = prices[-1]  # Higher price is original
                
                # Calculate discount percentage
                discount = 0
                if original_price and current_price and original_price > 0:
                    discount = round(((original_price - current_price) / original_price) * 100, 1)
                
                # Extract product URL
                url = ""
                link = element.find('a', href=True)
                if link:
                    href = link['href']
                    if href.startswith('http'):
                        url = href
                    elif href.startswith('/'):
                        url = BASE_URL + href
                
                # Extract image URL
                img_url = ""
                img = element.find('img')
                if img:
                    for attr in ['src', 'data-src', 'data-lazy-src']:
                        if img.get(attr):
                            img_url = img[attr]
                            if not img_url.startswith('http'):
                                img_url = BASE_URL + img_url
                            break
                
                # Only add if we have at least name and current price
                if name and current_price:
                    product = Product(
                        name=name[:100],  # Limit name length
                        current_price=current_price,
                        original_price=original_price,
                        discount_percent=discount,
                        url=url,
                        image_url=img_url
                    )
                    products.append(product)
                    logger.debug(f"Found product: {name[:30]}... - Price: {current_price} SAR, Discount: {discount}%")
                    
            except Exception as e:
                logger.debug(f"Error parsing product: {str(e)}")
                continue
        
        return products
    
    def filter_big_discounts(self, products: List[Product]) -> List[Product]:
        """Return products with discount >= threshold"""
        return [p for p in products if p.discount_percent >= DISCOUNT_THRESHOLD]
    
    def format_telegram_message(self, products: List[Product]) -> str:
        """Format product list for Telegram message"""
        if not products:
            return ""
        
        # Sort by discount percentage (highest first)
        products.sort(key=lambda x: x.discount_percent, reverse=True)
        
        # Create message header (bilingual Arabic/English for clarity)
        message = f"🔥 *تخفيضات كبيرة في تميمي ماركتس* 🔥\n"
        message += f"🔥 *TAMIMIMARKETS BIG DISCOUNTS* 🔥\n\n"
        message += f"📊 تم العثور على *{len(products)}* منتج بتخفيض ≥{DISCOUNT_THRESHOLD}%\n"
        message += f"📊 Found *{len(products)}* items with ≥{DISCOUNT_THRESHOLD}% off\n\n"
        
        # Add top deals
        for i, product in enumerate(products[:8], 1):
            # Product name (could be Arabic)
            message += f"*{i}. {product.name[:60]}*"
            if len(product.name) > 60:
                message += "..."
            message += "\n"
            
            # Prices
            if product.original_price:
                message += f"   ~~{product.original_price:.2f} SAR~~ → "
            message += f"*{product.current_price:.2f} SAR*"
            
            if product.discount_percent > 0:
                message += f"  (-{product.discount_percent:.1f}% 🔥)\n"
            else:
                message += "\n"
            
            # Link
            if product.url:
                message += f"   [عرض المنتج]({product.url}) | [View Product]({product.url})\n"
            message += "\n"
        
        if len(products) > 8:
            message += f"\n...و {len(products) - 8} عروض أخرى! تفضل بزيارة الموقع للمزيد\n"
            message += f"...and {len(products) - 8} more deals! Check the website for more."
        
        return message
    
    def send_telegram_alert(self, products: List[Product]):
        """Send alert via Telegram"""
        if not products:
            logger.info("No products to send")
            return
        
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN":
            logger.error("Telegram bot token not configured!")
            return
        
        message = self.format_telegram_message(products)
        
        if not message:
            return
        
        # Split message if too long
        if len(message) > 4000:
            message = message[:4000] + "...\n\n(الرسالة مختصرة / Message truncated)"
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        try:
            response = requests.post(
                url,
                json={
                    'chat_id': TELEGRAM_CHAT_ID,
                    'text': message,
                    'parse_mode': 'Markdown',
                    'disable_web_page_preview': False
                },
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"Telegram alert sent successfully for {len(products)} products")
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {str(e)}")
    
    def save_results(self, products: List[Product]):
        """Save results to JSON file for history"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"tamimi_deals_{timestamp}.json"
            
            data = {
                "timestamp": timestamp,
                "threshold": DISCOUNT_THRESHOLD,
                "total_products": len(self.products),
                "big_discounts": len(products),
                "products": [p.to_dict() for p in products]
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Results saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save results: {str(e)}")
    
    async def run(self):
        """Main execution method"""
        logger.info("=" * 50)
        logger.info("Starting Tamimimarkets Hot Deals Monitor")
        logger.info(f"Discount threshold: {DISCOUNT_THRESHOLD}%")
        logger.info(f"Chat ID: {TELEGRAM_CHAT_ID}")
        logger.info("=" * 50)
        
        # Fetch page
        html = await self.fetch_page()
        if not html:
            logger.error("No HTML content fetched, exiting")
            return
        
        # Parse products
        self.products = self.parse_products(html)
        self.session_data["products_found"] = len(self.products)
        logger.info(f"Total products found: {len(self.products)}")
        
        # Filter for big discounts
        hot_deals = self.filter_big_discounts(self.products)
        self.session_data["big_discounts"] = len(hot_deals)
        
        if hot_deals:
            logger.info(f"Found {len(hot_deals)} products with ≥{DISCOUNT_THRESHOLD}% discount")
            
            # Log top deals
            for i, deal in enumerate(sorted(hot_deals, key=lambda x: x.discount_percent, reverse=True)[:5]):
                logger.info(f"Top Deal {i+1}: {deal.name[:50]} - {deal.discount_percent:.1f}% off")
            
            # Send alerts
            self.send_telegram_alert(hot_deals)
            
            # Save results
            self.save_results(hot_deals)
        else:
            logger.info(f"No products found with discount ≥{DISCOUNT_THRESHOLD}%")
        
        logger.info("=" * 50)
        logger.info("Run completed successfully")
        logger.info(f"Summary: {self.session_data}")
        logger.info("=" * 50)


async def main():
    """Entry point"""
    scraper = TamimiScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
