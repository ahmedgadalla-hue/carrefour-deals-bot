"""
Tamimi Markets Hot Deals Monitor - 50-99% DISCOUNTS
Prioritized: Cheese → Food → Meat → Others
With Arabic translations and multi-message support
"""

import os
import re
import json
import logging
import asyncio
import random
import time
from datetime import datetime
from typing import List, Optional, Dict
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
    category: str = "Others"  # Will be set by categorizer
    
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
        self.categorized_products = {
            "CHEESE": [],      # Priority 1: Any cheese products
            "FOOD": [],        # Priority 2: General food items
            "MEAT": [],        # Priority 3: Meat, chicken, fish
            "OTHERS": []       # Priority 4: Everything else
        }
    
    def categorize_product(self, product):
        """Categorize product based on name"""
        name_lower = product.name.lower()
        
        # Priority 1: CHEESE (any cheese product)
        cheese_keywords = ['cheese', 'جبن', 'cream cheese', 'mozzarella', 'cheddar', 'parmesan']
        if any(keyword in name_lower for keyword in cheese_keywords):
            return "CHEESE"
        
        # Priority 2: FOOD (general food items)
        food_keywords = [
            'flour', 'طحين', 'sugar', 'سكر', 'rice', 'أرز', 'pasta', 'معكرونة',
            'bread', 'خبز', 'oil', 'زيت', 'water', 'ماء', 'juice', 'عصير',
            'coffee', 'قهوة', 'tea', 'شاي', 'chocolate', 'شوكولاتة', 'cookies', 'بسكويت',
            'honey', 'عسل', 'dates', 'تمر', 'yogurt', 'زبادي', 'labneh', 'لبنة',
            'cream', 'قشطة', 'butter', 'زبدة', 'milk', 'حليب', 'eggs', 'بيض'
        ]
        if any(keyword in name_lower for keyword in food_keywords):
            return "FOOD"
        
        # Priority 3: MEAT (including chicken and fish)
        meat_keywords = [
            'meat', 'لحم', 'chicken', 'دجاج', 'fish', 'سمك', 'beef', 'لحم بقري',
            'lamb', 'خروف', 'veal', 'عجل', 'turkey', 'ديك رومي', 'sausage', 'سجق',
            'burger', 'برجر', 'steak', 'ستيك', 'ground', 'مفروم', 'fillet', 'فيليه'
        ]
        if any(keyword in name_lower for keyword in meat_keywords):
            return "MEAT"
        
        # Priority 4: OTHERS
        return "OTHERS"
    
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
        """Convert data to Product objects, categorize, and sort"""
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
                
                # Categorize the product
                product.category = self.categorize_product(product)
                products.append(product)
                
            except Exception as e:
                logger.debug(f"Error creating product: {e}")
                continue
        
        return products
    
    def _send_telegram_message(self, message):
        """Send a single message to Telegram"""
        global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.error("❌ Missing Telegram credentials")
            return False
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                logger.info(f"✅ Message sent successfully")
                return True
            else:
                logger.error(f"❌ Telegram error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to send: {e}")
            return False
    
    def _create_category_summary(self, category_name, products):
        """Create a summary for a specific category"""
        if not products:
            return ""
        
        # Sort products in this category by discount (highest first)
        sorted_products = sorted(products, key=lambda x: x.discount_percent, reverse=True)
        
        message = f"<b>{category_name} ({len(products)} items)</b>\n"
        
        # Arabic translation of category
        arabic_category = {
            "CHEESE": "الأجبان",
            "FOOD": "المواد الغذائية",
            "MEAT": "اللحوم",
            "OTHERS": "منتجات أخرى"
        }.get(category_name, category_name)
        
        message += f"<b>{arabic_category} ({len(products)} منتج)</b>\n\n"
        
        # Show top 5 from this category
        for i, product in enumerate(sorted_products[:5], 1):
            arabic_name = product.get_arabic_name()
            message += f"<b>{i}.</b> {product.name[:30]}...\n"
            message += f"   {arabic_name[:30]}...\n"
            message += f"   <b>{product.discount_percent}%</b> off | خصم <b>{product.discount_percent}%</b>\n"
            message += f"   {product.current_price:.2f} SAR | {product.current_price:.2f} ريال\n"
            
            if product.url:
                message += f"   <a href='{product.url}'>🔗 View</a>\n"
            message += "\n"
        
        if len(sorted_products) > 5:
            message += f"   ... and {len(sorted_products)-5} more in this category\n"
            message += f"   ... و {len(sorted_products)-5} منتج آخر في هذه الفئة\n\n"
        
        return message
    
    def _create_detailed_category_message(self, category_name, products, start_num):
        """Create a detailed message for a category's products"""
        if not products:
            return "", start_num
        
        # Sort products in this category by discount (highest first)
        sorted_products = sorted(products, key=lambda x: x.discount_percent, reverse=True)
        
        message = f"<b>{category_name} - All Items ({len(products)})</b>\n"
        
        # Arabic translation
        arabic_category = {
            "CHEESE": "الأجبان",
            "FOOD": "المواد الغذائية",
            "MEAT": "اللحوم",
            "OTHERS": "منتجات أخرى"
        }.get(category_name, category_name)
        
        message += f"<b>{arabic_category} - جميع المنتجات ({len(products)})</b>\n\n"
        
        current_num = start_num
        for product in sorted_products:
            arabic_name = product.get_arabic_name()
            message += f"<b>{current_num}.</b> {product.name}\n"
            message += f"<b>{current_num}.</b> {arabic_name}\n"
            message += f"   <b>{product.discount_percent}%</b> off | خصم <b>{product.discount_percent}%</b>\n"
            if product.original_price:
                message += f"   <s>{product.original_price:.2f}</s> → {product.current_price:.2f} SAR\n"
            else:
                message += f"   Now {product.current_price:.2f} SAR | الآن {product.current_price:.2f} ريال\n"
            
            if product.url:
                message += f"   <a href='{product.url}'>🔗 View Product | عرض المنتج</a>\n"
            message += "\n"
            
            current_num += 1
        
        return message, current_num
    
    def send_telegram_alert(self, products):
        """Send alert for products with 50-99% discounts, categorized and prioritized"""
        global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.error("❌ Missing Telegram credentials - Check your secrets!")
            return
        
        logger.info(f"📤 Preparing to send Telegram message...")
        logger.info(f"📊 Total products received: {len(products)}")
        
        # Filter for 50-99% discounts
        hot_deals = [p for p in products if MIN_DISCOUNT <= p.discount_percent <= MAX_DISCOUNT]
        logger.info(f"🔥 Hot deals found: {len(hot_deals)}")
        
        # If no hot deals, send a simple message
        if not hot_deals:
            message = f"🔍 <b>Tamimi Monitor - No {MIN_DISCOUNT}-{MAX_DISCOUNT}% Deals</b>\n"
            message += f"🔍 <b>مراقب التميمي - لا توجد عروض {MIN_DISCOUNT}-{MAX_DISCOUNT}%</b>\n\n"
            message += f"📊 Total products scanned: <b>{len(products)}</b>\n"
            message += f"📊 إجمالي المنتجات الممسوحة: <b>{len(products)}</b>"
            self._send_telegram_message(message)
            return
        
        # Categorize the hot deals
        categorized = {
            "CHEESE": [],
            "FOOD": [],
            "MEAT": [],
            "OTHERS": []
        }
        
        for product in hot_deals:
            category = self.categorize_product(product)
            categorized[category].append(product)
        
        # Sort each category by discount (highest first)
        for category in categorized:
            categorized[category].sort(key=lambda x: x.discount_percent, reverse=True)
        
        # Log category counts
        logger.info("📊 Category breakdown:")
        for category, items in categorized.items():
            logger.info(f"   {category}: {len(items)} items")
        
        # ===== SEND SUMMARY MESSAGE =====
        summary = f"🔥🔥🔥 <b>MASSIVE {MIN_DISCOUNT}-{MAX_DISCOUNT}% DISCOUNTS!</b> 🔥🔥🔥\n"
        summary += f"🔥🔥🔥 <b>خصومات ضخمة {MIN_DISCOUNT}-{MAX_DISCOUNT}%!</b> 🔥🔥🔥\n\n"
        
        summary += f"📊 Scanned <b>{len(products)}</b> total products\n"
        summary += f"📊 تم مسح <b>{len(products)}</b> منتج إجمالاً\n"
        summary += f"🎯 Found <b>{len(hot_deals)}</b> items with {MIN_DISCOUNT}-{MAX_DISCOUNT}% off!\n"
        summary += f"🎯 تم العثور على <b>{len(hot_deals)}</b> منتج بخصم {MIN_DISCOUNT}-{MAX_DISCOUNT}%!\n\n"
        
        # Add category summaries in priority order
        category_order = ["CHEESE", "FOOD", "MEAT", "OTHERS"]
        category_names = {
            "CHEESE": "🧀 CHEESE / الأجبان",
            "FOOD": "🍞 FOOD / المواد الغذائية",
            "MEAT": "🥩 MEAT / اللحوم",
            "OTHERS": "📦 OTHER PRODUCTS / منتجات أخرى"
        }
        
        for cat in category_order:
            if categorized[cat]:
                summary += f"<b>{category_names[cat]}: {len(categorized[cat])} items</b>\n"
                # Show top 2 from each category
                for i, product in enumerate(categorized[cat][:2], 1):
                    arabic_name = product.get_arabic_name()
                    summary += f"  {i}. {product.name[:20]}... ({product.discount_percent}%)\n"
                    summary += f"     {arabic_name[:20]}...\n"
                if len(categorized[cat]) > 2:
                    summary += f"     ... and {len(categorized[cat])-2} more\n"
                    summary += f"     ... و {len(categorized[cat])-2} منتج آخر\n"
                summary += "\n"
        
        summary += f"📋 <b>Detailed lists by category in following messages</b>\n"
        summary += f"📋 <b>القوائم التفصيلية حسب الفئة في الرسائل التالية</b>\n"
        
        self._send_telegram_message(summary)
        time.sleep(2)
        
        # ===== SEND DETAILED CATEGORY MESSAGES =====
        product_counter = 1
        
        for cat in category_order:
            if not categorized[cat]:
                continue
            
            # Split category products into chunks of 8
            chunk_size = 8
            for i in range(0, len(categorized[cat]), chunk_size):
                chunk = categorized[cat][i:i+chunk_size]
                
                cat_name = category_names[cat].split(" / ")[0]
                start_num = product_counter
                end_num = product_counter + len(chunk) - 1
                
                message = f"<b>{cat_name} - Items {start_num}-{end_num} of {len(hot_deals)}</b>\n\n"
                
                for j, product in enumerate(chunk, start_num):
                    arabic_name = product.get_arabic_name()
                    message += f"<b>{j}.</b> {product.name}\n"
                    message += f"<b>{j}.</b> {arabic_name}\n"
                    message += f"   <b>{product.discount_percent}%</b> off | خصم <b>{product.discount_percent}%</b>\n"
                    if product.original_price:
                        message += f"   <s>{product.original_price:.2f}</s> → {product.current_price:.2f} SAR\n"
                    else:
                        message += f"   Now {product.current_price:.2f} SAR | الآن {product.current_price:.2f} ريال\n"
                    
                    if product.url:
                        message += f"   <a href='{product.url}'>🔗 View Product | عرض المنتج</a>\n"
                    message += "\n"
                
                self._send_telegram_message(message)
                product_counter += len(chunk)
                time.sleep(2)
        
        logger.info(f"✅ All categorized messages sent successfully!")
    
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
                self._send_telegram_message(error_msg)
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
