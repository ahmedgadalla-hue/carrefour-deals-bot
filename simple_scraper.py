"""
Tamimi Hot Deals Monitor - FIXED VERSION
Specifically designed for Tamimimarkets website
"""

import os
import re
import json
import asyncio
import logging
from datetime import datetime
from playwright.async_api import async_playwright
import requests

# ================= CONFIGURATION =================
TELEGRAM_BOT_TOKEN = "8791585716:AAE-SEV2iACbYXMymwMeA1JJVyGfK5_Y1Jg"
TELEGRAM_CHAT_ID = "7420001477"
DISCOUNT_THRESHOLD = 50  # Alert if discount >= 50%

# Tamimimarkets URL
TAMIMI_URL = "https://shop.tamimimarkets.com/ar/hot-deals"
# =================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def scrape_tamimi_deals():
    """Scrape Tamimi hot deals page for discounts"""
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            logger.info(f"🌐 Opening Tamimi website...")
            await page.goto(TAMIMI_URL, timeout=60000)
            
            # Wait for page to load
            await page.wait_for_timeout(5000)
            
            # Scroll to load all deals
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)
            
            # Take screenshot for debugging
            await page.screenshot(path="tamimi_deals.png")
            logger.info("📸 Screenshot saved")
            
            # Get all product information
            products = await page.evaluate("""
                () => {
                    const deals = [];
                    
                    // Look for discount badges - they usually show "% خصم"
                    const discountElements = document.querySelectorAll('[class*="discount"], [class*="badge"], [class*="offer"], .percentage, .sale-badge');
                    
                    discountElements.forEach(element => {
                        // Get the text content
                        const text = element.innerText || element.textContent;
                        
                        // Look for percentage pattern (e.g., "50%", "٪٥٠", "50% خصم")
                        const percentageMatch = text.match(/(\\d+)\\s*[٪%]/);
                        if (!percentageMatch) return;
                        
                        const discount = parseInt(percentageMatch[1]);
                        
                        // Find the product container (go up 3-5 levels)
                        let productContainer = element;
                        for (let i = 0; i < 5; i++) {
                            if (productContainer.parentElement) {
                                productContainer = productContainer.parentElement;
                            } else {
                                break;
                            }
                        }
                        
                        // Get product name
                        let name = '';
                        const nameElement = productContainer.querySelector('h2, h3, h4, [class*="title"], [class*="name"]');
                        if (nameElement) {
                            name = nameElement.innerText || nameElement.textContent;
                        }
                        
                        // Get price
                        let price = 0;
                        let originalPrice = 0;
                        
                        // Look for current price
                        const priceElement = productContainer.querySelector('[class*="price"], [class*="sale"], [class*="current"]');
                        if (priceElement) {
                            const priceText = priceElement.innerText || priceElement.textContent;
                            const priceMatch = priceText.match(/(\\d+\\.?\\d*)/);
                            if (priceMatch) {
                                price = parseFloat(priceMatch[1]);
                            }
                        }
                        
                        // Look for original price (strikethrough)
                        const oldPriceElement = productContainer.querySelector('del, s, [class*="old"], [class*="regular"]');
                        if (oldPriceElement) {
                            const oldText = oldPriceElement.innerText || oldPriceElement.textContent;
                            const oldMatch = oldText.match(/(\\d+\\.?\\d*)/);
                            if (oldMatch) {
                                originalPrice = parseFloat(oldMatch[1]);
                            }
                        }
                        
                        // Get product link
                        let link = '';
                        const linkElement = productContainer.querySelector('a[href*="/product"]');
                        if (linkElement) {
                            link = linkElement.href;
                        }
                        
                        if (name && price > 0 && discount > 0) {
                            deals.push({
                                name: name.trim(),
                                current_price: price,
                                original_price: originalPrice || (price * 100 / (100 - discount)),
                                discount: discount,
                                url: link
                            });
                        }
                    });
                    
                    return deals;
                }
            """)
            
            logger.info(f"✅ Found {len(products)} products with discounts")
            
            # Filter for hot deals (>=50% discount)
            hot_deals = [p for p in products if p['discount'] >= DISCOUNT_THRESHOLD]
            
            # Sort by discount percentage (highest first)
            hot_deals.sort(key=lambda x: x['discount'], reverse=True)
            
            # Send results to Telegram
            await send_telegram_message(products, hot_deals)
            
            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(f"deals_{timestamp}.json", "w", encoding='utf-8') as f:
                json.dump({
                    "total_products": len(products),
                    "hot_deals": len(hot_deals),
                    "deals": hot_deals
                }, f, ensure_ascii=False, indent=2)
            
            return hot_deals
            
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            await send_error_message(str(e))
            return []
        finally:
            await browser.close()

async def send_telegram_message(all_products, hot_deals):
    """Send formatted message to Telegram"""
    
    if hot_deals:
        # Create message for hot deals
        message = f"🔥 *تميمي ماركتس - عروض حصرية* 🔥\n"
        message += f"🔥 *TAMIMIMARKETS - HOT DEALS* 🔥\n\n"
        message += f"✅ وجدنا *{len(hot_deals)}* منتج بتخفيض ≥{DISCOUNT_THRESHOLD}%\n"
        message += f"✅ Found *{len(hot_deals)}* items with ≥{DISCOUNT_THRESHOLD}% off\n\n"
        
        for i, deal in enumerate(hot_deals[:5], 1):
            message += f"*{i}. {deal['name'][:50]}*\n"
            if deal['original_price']:
                message += f"   ~~{deal['original_price']:.2f}~~ → "
            message += f"*{deal['current_price']:.2f} SAR*"
            message += f"  (-{deal['discount']}% 🔥)\n\n"
        
        if len(hot_deals) > 5:
            message += f"...و {len(hot_deals)-5} عروض أخرى!\n"
            
    else:
        # Show what we found even if no hot deals
        message = f"🔍 *Tamimi Monitor - Scan Results*\n\n"
        message += f"📊 Total products found: {len(all_products)}\n"
        
        if all_products:
            message += f"\n📈 Discount range found: "
            discounts = [p['discount'] for p in all_products]
            message += f"{min(discounts)}% - {max(discounts)}%\n\n"
            
            message += f"*Sample products:*\n"
            for p in all_products[:3]:
                message += f"• {p['name'][:30]}... - {p['discount']}% off\n"
        else:
            message += f"\n⚠️ No products found. The website structure may have changed.\n"
            message += f"Check the screenshot in GitHub Actions artifacts."
    
    # Send to Telegram
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        response = requests.post(url, json={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        })
        logger.info(f"📱 Telegram message sent: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Failed to send Telegram: {e}")

async def send_error_message(error):
    """Send error message to Telegram"""
    message = f"⚠️ *Tamimi Monitor Error*\n\n`{error}`"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        })
    except:
        pass

async def main():
    logger.info("=" * 50)
    logger.info("🚀 Starting Tamimi Deals Monitor")
    logger.info("=" * 50)
    
    deals = await scrape_tamimi_deals()
    
    logger.info(f"✅ Scan complete! Found {len(deals)} hot deals")
    logger.info("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
