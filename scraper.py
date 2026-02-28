"""
Tamimi Markets Hot Deals Monitor - 50-99% DISCOUNTS
With Arabic translations for each product
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

# Arabic translations for common product terms
TRANSLATIONS = {
    # Food items
    "Flour": "طحين",
    "Sugar": "سكر",
    "Rice": "أرز",
    "Pasta": "معكرونة",
    "Bread": "خبز",
    "Milk": "حليب",
    "Cheese": "جبن",
    "Butter": "زبدة",
    "Yogurt": "زبادي",
    "Labneh": "لبنة",
    "Cream": "قشطة",
    "Eggs": "بيض",
    "Chicken": "دجاج",
    "Meat": "لحم",
    "Fish": "سمك",
    "Vegetables": "خضروات",
    "Fruits": "فواكه",
    "Oil": "زيت",
    "Water": "ماء",
    "Juice": "عصير",
    "Coffee": "قهوة",
    "Tea": "شاي",
    "Chocolate": "شوكولاتة",
    "Cookies": "بسكويت",
    "Chips": "رقائق",
    "Honey": "عسل",
    "Dates": "تمر",
    
    # Brands
    "Almarai": "المراعي",
    "Nadec": "نادك",
    "Aloula": "الأولى",
    "Tamimi": "التميمي",
    "Saudia": "سعودية",
    "Goody": "جودي",
    "Sunbulah": "سنبلة",
    "Kuwait Bakeries": "مخابز الكويت",
    "Puck": "بك",
    "Philadelphia": "فيلادلفيا",
    "Lurpak": "لورباك",
    "President": "بريزيدنت",
    "Nova": "نوفا",
    "Driscoll's": "دريسكول",
    "Alosra": "الأوسرة",
    "Qoot & Root": "قوت وروت",
    "Riyadh Food": "رياض فود",
    "Foom": "فوم",
    "Greens": "جرينز",
    
    # Common words
    "Fresh": "طازج",
    "Organic": "عضوي",
    "Full Fat": "كامل الدسم",
    "Low Fat": "قليل الدسم",
    "Skimmed": "منزوع الدسم",
    "With": "مع",
    "Without": "بدون",
    "And": "و",
    "Pack": "عبوة",
    "Box": "علبة",
    "Bottle": "قارورة",
    "Bag": "كيس",
    "Can": "معلبة",
    "Jar": "برطمان",
    "Piece": "قطعة",
    "Each": "للحبة",
    "Promo": "عرض",
    "Offer": "عرض خاص",
    "Save": "وفر",
    "Discount": "خصم",
    "Price": "السعر",
    "Now": "الآن",
    "Was": "كان",
    
    # Measurements
    "G": "جرام",
    "Kg": "كيلو",
    "ML": "مل",
    "L": "لتر",
    "Cm": "سم",
    "Inch": "بوصة",
    
    # Product types
    "Premium": "ممتاز",
    "Superior": "فاخر",
    "Original": "أصلي",
    "Classic": "كلاسيك",
    "Regular": "عادي",
    "Extra": "إضافي",
    "Large": "كبير",
    "Small": "صغير",
    "Medium": "وسط",
    "Family": "عائلي",
    "Party": "حفلات",
    
    # Colors
    "White": "أبيض",
    "Brown": "بني",
    "Red": "أحمر",
    "Green": "أخضر",
    "Yellow": "أصفر",
    "Blue": "أزرق",
    "Black": "أسود",
    
    # Other
    "Free": "مجاني",
    "Limited": "محدود",
    "New": "جديد",
    "Special": "خاص",
    "Best": "أفضل",
    "Value": "قيمة",
    "Quality": "جودة"
}
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
    
    def get_arabic_name(self):
        """Translate product name to Arabic"""
        arabic_name = self.name
        
        # Replace common terms with Arabic translations
        for english, arabic in TRANSLATIONS.items():
            # Case-insensitive replacement
            pattern = re.compile(re.escape(english), re.IGNORECASE)
            arabic_name = pattern.sub(arabic, arabic_name)
        
        # Remove extra spaces
        arabic_name = re.sub(r'\s+', ' ', arabic_name).strip()
        
        return arabic_name


class TamimiScraper:
    def __init__(self):
        self.products = []
    
    async def fetch_page(self):
        """Fetch the hot deals page and SCROLL TO THE VERY END to load ALL products"""
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
                
                # ============ AGGRESSIVE SCROLLING TO LOAD ALL PRODUCTS ============
                logger.info("🚀 Starting AGGRESSIVE scrolling to load ALL products...")
                
                previous_height = 0
                same_height_count = 0
                scroll_attempt = 0
                max_scroll_attempts = 50
                
                while scroll_attempt < max_scroll_attempts:
                    scroll_attempt += 1
                    
                    # Scroll to bottom
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    
                    # Wait for new content to load
                    await page.wait_for_timeout(3000)
                    
                    # Get current scroll height and product count
                    current_height = await page.evaluate("document.body.scrollHeight")
                    current_count = await page.evaluate("document.querySelectorAll('[data-testid=\"product\"]').length")
                    
                    logger.info(f"Scroll #{scroll_attempt}: Height={current_height}px, Products={current_count}")
                    
                    # Check if we've reached the end
                    if current_height == previous_height:
                        same_height_count += 1
                        if same_height_count >= 3:
                            logger.info(f"✅ Reached end after {scroll_attempt} scrolls. Total products: {current_count}")
                            break
                    else:
                        same_height_count = 0
                    
                    previous_height = current_height
                    await asyncio.sleep(random.uniform(1, 2))
                
                # Get final product count
                final_count = await page.evaluate("document.querySelectorAll('[data-testid=\"product\"]').length")
                logger.info(f"🎯 FINAL PRODUCT COUNT: {final_count}")
                
                # ============ EXTRACT ALL PRODUCTS USING IMPROVED JAVASCRIPT ============
                logger.info("Extracting all product data with improved discount detection...")
                
                products_data = await page.evaluate("""
                    () => {
                        const products = [];
                        const productElements = document.querySelectorAll('[data-testid="product"]');
                        
                        console.log(`Found ${productElements.length} products to extract`);
                        
                        productElements.forEach((element) => {
                            try {
                                // ===== MULTIPLE METHODS TO FIND DISCOUNT =====
                                let discount = 0;
                                const allText = element.innerText;
                                
                                // Method 1: Look for discount badge with specific class
                                const discountElem = element.querySelector('[class*="Product__StyledDiscount"]');
                                if (discountElem) {
                                    const discountText = discountElem.innerText;
                                    const match = discountText.match(/(\\d+)%/);
                                    if (match) discount = parseInt(match[1]);
                                }
                                
                                // Method 2: Look for any element with percentage
                                if (discount === 0) {
                                    const percentElements = element.querySelectorAll('[class*="percent"], [class*="discount"], [class*="offer"]');
                                    for (const el of percentElements) {
                                        const text = el.innerText;
                                        const match = text.match(/(\\d+)%/);
                                        if (match) {
                                            discount = parseInt(match[1]);
                                            break;
                                        }
                                    }
                                }
                                
                                // Method 3: Look for percentage in text with "OFF"
                                if (discount === 0) {
                                    const offMatch = allText.match(/(\\d+)%\\s*OFF/i);
                                    if (offMatch) discount = parseInt(offMatch[1]);
                                }
                                
                                // Method 4: Look for any percentage in the entire text
                                if (discount === 0) {
                                    const anyMatch = allText.match(/(\\d+)%/);
                                    if (anyMatch) discount = parseInt(anyMatch[1]);
                                }
                                
                                // Get current price
                                let currentPrice = 0;
                                const priceElem = element.querySelector('[class*="Price__SellingPrice"]');
                                if (priceElem) {
                                    const priceText = priceElem.innerText;
                                    const priceMatch = priceText.match(/(\\d+\\.?\\d*)/);
                                    if (priceMatch) currentPrice = parseFloat(priceMatch[1]);
                                }
                                
                                // Get original price (if discounted)
                                let originalPrice = null;
                                const originalElem = element.querySelector('[class*="Price__SellingPriceOutDated"]');
                                if (originalElem) {
                                    const originalText = originalElem.innerText;
                                    const originalMatch = originalText.match(/(\\d+\\.?\\d*)/);
                                    if (originalMatch) originalPrice = parseFloat(originalMatch[1]);
                                }
                                
                                // Method 5: Calculate discount from prices
                                if (discount === 0 && originalPrice && currentPrice && originalPrice > currentPrice) {
                                    discount = Math.round(((originalPrice - currentPrice) / originalPrice) * 100);
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
                                
                                // If still no name, get the first long text
                                if (!name || name.length < 3) {
                                    const textLines = allText.split('\\n').filter(line => line.trim().length > 5);
                                    if (textLines.length > 0) name = textLines[0].trim();
                                }
                                
                                // Clean up name
                                name = name.replace(/\\s+/g, ' ').trim();
                                
                                // Get product URL
                                let url = '';
                                const link = element.closest('a');
                                if (link && link.href) url = link.href;
                                
                                // Only include if we have valid data
                                if (name && currentPrice > 0) {
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
                
                # Count how many have discounts
                with_discounts = len([p for p in products_data if p.get('discount_percent', 0) > 0])
                logger.info(f"📊 Products WITH discounts: {with_discounts}")
                logger.info(f"📊 Products WITHOUT discounts: {len(products_data) - with_discounts}")
                
                # Save debug files
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                await page.screenshot(path=f"tamimi_deals_{timestamp}.png", full_page=True)
                
                # Save products to JSON
                with open(f"tamimi_products_{timestamp}.json", "w", encoding="utf-8") as f:
                    json.dump({
                        'total_products_found': final_count,
                        'products_extracted': len(products_data),
                        'products_with_discounts': with_discounts,
                        'products': products_data
                    }, f, indent=2)
                
                logger.info(f"📊 Total products in DOM: {final_count}")
                logger.info(f"📊 Products extracted: {len(products_data)}")
                logger.info(f"📊 Products with discounts: {with_discounts}")
                
                return products_data
                
            except Exception as e:
                logger.error(f"Error: {e}")
                return []
            finally:
                await browser.close()
    
    def process_products(self, products_data):
        """Convert data to Product objects and sort by discount"""
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
        """Send alert for products with 50-99% discounts with Arabic translations"""
        global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.error("❌ Missing Telegram credentials - Check your secrets!")
            return
        
        logger.info(f"📤 Preparing to send Telegram message...")
        logger.info(f"📊 Total products received: {len(products)}")
        
        # Filter for 50-99% discounts
        hot_deals = [p for p in products if MIN_DISCOUNT <= p.discount_percent <= MAX_DISCOUNT]
        logger.info(f"🔥 Hot deals found: {len(hot_deals)}")
        
        # Prepare message with bilingual format (English + Arabic)
        if not hot_deals:
            message = f"🔍 <b>Tamimi Monitor - No {MIN_DISCOUNT}-{MAX_DISCOUNT}% Deals</b>\n"
            message += f"🔍 <b>مراقب التميمي - لا توجد عروض {MIN_DISCOUNT}-{MAX_DISCOUNT}%</b>\n\n"
            
            message += f"📊 Total products scanned: <b>{len(products)}</b>\n"
            message += f"📊 إجمالي المنتجات الممسوحة: <b>{len(products)}</b>\n\n"
            
            if products:
                # Count by discount range
                ranges = [
                    (90, 99), (80, 89), (70, 79), (60, 69), 
                    (50, 59), (40, 49), (30, 39), (20, 29), 
                    (10, 19), (1, 9), (0, 0)
                ]
                
                message += "📈 <b>All Discounts Found / جميع الخصومات الموجودة:</b>\n"
                for high, low in ranges:
                    if low == high:
                        count = len([p for p in products if p.discount_percent == low])
                        if count > 0:
                            message += f"  • {low}%: {count} items\n"
                    else:
                        count = len([p for p in products if low <= p.discount_percent <= high])
                        if count > 0:
                            message += f"  • {low}-{high}%: {count} items\n"
                
                # Show top 20 deals
                message += f"\n🏆 <b>Top 20 Deals Today / أفضل 20 عرض اليوم:</b>\n"
                for i, product in enumerate(products[:20], 1):
                    arabic_name = product.get_arabic_name()
                    message += f"  {i}. {product.name[:30]}... - <b>{product.discount_percent}%</b>\n"
                    message += f"     {arabic_name[:30]}...\n"
            
        else:
            # We have 50-99% deals
            message = f"🔥🔥🔥 <b>MASSIVE {MIN_DISCOUNT}-{MAX_DISCOUNT}% DISCOUNTS!</b> 🔥🔥🔥\n"
            message += f"🔥🔥🔥 <b>خصومات ضخمة {MIN_DISCOUNT}-{MAX_DISCOUNT}%!</b> 🔥🔥🔥\n\n"
            
            message += f"📊 Scanned <b>{len(products)}</b> total products\n"
            message += f"📊 تم مسح <b>{len(products)}</b> منتج إجمالاً\n"
            message += f"🎯 Found <b>{len(hot_deals)}</b> items with {MIN_DISCOUNT}-{MAX_DISCOUNT}% off!\n"
            message += f"🎯 تم العثور على <b>{len(hot_deals)}</b> منتج بخصم {MIN_DISCOUNT}-{MAX_DISCOUNT}%!\n\n"
            
            # Group by discount range
            ranges = [(90,99), (80,89), (70,79), (60,69), (50,59)]
            for high, low in ranges:
                range_deals = [p for p in hot_deals if low <= p.discount_percent <= high]
                if range_deals:
                    message += f"<b>{low}-{high}% OFF ({len(range_deals)} items):</b>\n"
                    message += f"<b>{low}-{high}% خصم ({len(range_deals)} منتج):</b>\n"
                    # Show first 3 from each range
                    for product in range_deals[:3]:
                        arabic_name = product.get_arabic_name()
                        message += f"  • {product.name[:25]}... ({product.discount_percent}%)\n"
                        message += f"    {arabic_name[:25]}...\n"
                    if len(range_deals) > 3:
                        message += f"  ... and {len(range_deals)-3} more\n"
                        message += f"  ... و {len(range_deals)-3} منتج آخر\n"
                    message += "\n"
            
            # Show all hot deals (limit to 20 to avoid message too long)
            message += f"<b>Complete List of {MIN_DISCOUNT}-{MAX_DISCOUNT}% Deals / قائمة الخصومات:</b>\n\n"
            
            for i, product in enumerate(hot_deals[:20], 1):
                arabic_name = product.get_arabic_name()
                message += f"<b>{i}.</b> {product.name}\n"
                message += f"<b>{i}.</b> {arabic_name}\n"
                message += f"   <b>{product.discount_percent}%</b> off | خصم <b>{product.discount_percent}%</b>\n"
                if product.original_price:
                    message += f"   <s>{product.original_price:.2f}</s> → {product.current_price:.2f} SAR\n"
                else:
                    message += f"   Now {product.current_price:.2f} SAR | الآن {product.current_price:.2f} ريال\n"
                
                if product.url:
                    message += f"   <a href='{product.url}'>🔗 View Product | عرض المنتج</a>\n"
                message += "\n"
            
            if len(hot_deals) > 20:
                message += f"...and {len(hot_deals)-20} more deals! | و {len(hot_deals)-20} عروض أخرى!\n"
        
        # Send to Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }
        
        logger.info(f"📤 Sending message to Telegram...")
        logger.info(f"📤 Chat ID: {TELEGRAM_CHAT_ID}")
        logger.info(f"📤 Bot Token: {TELEGRAM_BOT_TOKEN[:10]}...{TELEGRAM_BOT_TOKEN[-5:]}")
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            logger.info(f"📥 Telegram response status: {response.status_code}")
            
            if response.status_code == 200:
                logger.info(f"✅ Telegram alert sent successfully!")
            else:
                logger.error(f"❌ Telegram error: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Failed to send: {e}")
    
    async def run(self):
        """Main execution"""
        logger.info("=" * 70)
        logger.info(f"🚀 Starting Tamimi Markets Hot Deals Monitor")
        logger.info(f"🎯 Looking for discounts between {MIN_DISCOUNT}% and {MAX_DISCOUNT}%")
        logger.info("=" * 70)
        
        # Verify Telegram credentials
        if not TELEGRAM_BOT_TOKEN:
            logger.error("❌ TELEGRAM_BOT_TOKEN is not set!")
        if not TELEGRAM_CHAT_ID:
            logger.error("❌ TELEGRAM_CHAT_ID is not set!")
        
        products_data = await self.fetch_page()
        if not products_data:
            logger.error("❌ No products found")
            # Send error message
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                error_msg = "⚠️ <b>Tamimi Monitor Error</b>\n⚠️ <b>خطأ في مراقب التميمي</b>\n\nNo products were found on the page. Check the debug files.\nلم يتم العثور على منتجات في الصفحة. تحقق من ملفات التصحيح."
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                try:
                    requests.post(url, json={
                        'chat_id': TELEGRAM_CHAT_ID,
                        'text': error_msg,
                        'parse_mode': 'HTML'
                    })
                except:
                    pass
            return
        
        self.products = self.process_products(products_data)
        
        # Log comprehensive summary
        logger.info("=" * 50)
        logger.info(f"📊 FINAL SUMMARY")
        logger.info(f"📦 Total products with discounts: {len(self.products)}")
        
        # Count by discount range
        ranges = [(90,99), (80,89), (70,79), (60,69), (50,59), (40,49), (30,39), (20,29), (10,19), (1,9)]
        for high, low in ranges:
            count = len([p for p in self.products if low <= p.discount_percent <= high])
            if count > 0:
                percentage = (count / len(self.products)) * 100 if len(self.products) > 0 else 0
                logger.info(f"📊 {low}-{high}%: {count} items ({percentage:.1f}%)")
        
        # Show top discounts
        if self.products:
            logger.info("🏆 Top 5 discounts:")
            for i, p in enumerate(self.products[:5], 1):
                logger.info(f"   {i}. {p.name[:40]}... - {p.discount_percent}%")
        
        logger.info("=" * 50)
        
        # Send alert
        logger.info("📤 Calling send_telegram_alert...")
        self.send_telegram_alert(self.products)
        logger.info("=" * 70)


async def main():
    scraper = TamimiScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
