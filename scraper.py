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
    
    # If no hot deals, send a simple message
    if not hot_deals:
        message = self._create_no_deals_message(products)
        self._send_telegram_message(message)
        return
    
    # Split hot deals into chunks of 10 products per message
    chunk_size = 10
    message_chunks = []
    
    # Create summary message first
    summary = self._create_summary_message(products, hot_deals)
    message_chunks.append(summary)
    
    # Create product detail messages in chunks
    for i in range(0, len(hot_deals), chunk_size):
        chunk = hot_deals[i:i+chunk_size]
        chunk_message = self._create_product_chunk_message(chunk, i+1, i+len(chunk))
        message_chunks.append(chunk_message)
    
    # Send all messages
    logger.info(f"📤 Sending {len(message_chunks)} messages to Telegram...")
    for idx, msg in enumerate(message_chunks):
        logger.info(f"📤 Sending message {idx+1}/{len(message_chunks)}...")
        self._send_telegram_message(msg)
        
        # Small delay between messages to avoid rate limiting
        if idx < len(message_chunks) - 1:
            time.sleep(2)
    
    logger.info(f"✅ All {len(message_chunks)} messages sent successfully!")

def _create_summary_message(self, products, hot_deals):
    """Create summary message with overview"""
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
            # Show first 2 from each range
            for product in range_deals[:2]:
                arabic_name = product.get_arabic_name()
                message += f"  • {product.name[:20]}... ({product.discount_percent}%)\n"
                message += f"    {arabic_name[:20]}...\n"
            if len(range_deals) > 2:
                message += f"  ... and {len(range_deals)-2} more\n"
                message += f"  ... و {len(range_deals)-2} منتج آخر\n"
            message += "\n"
    
    message += f"📋 <b>Detailed list in following messages ({len(hot_deals)} products)</b>\n"
    message += f"📋 <b>القائمة التفصيلية في الرسائل التالية ({len(hot_deals)} منتج)</b>\n"
    
    return message

def _create_product_chunk_message(self, products_chunk, start_num, end_num):
    """Create a message chunk with product details"""
    message = f"<b>Products {start_num}-{end_num} of {len(self.products_filtered)} | المنتجات {start_num}-{end_num}</b>\n\n"
    
    for i, product in enumerate(products_chunk, start_num):
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
    
    return message

def _send_telegram_message(self, message):
    """Send a single message to Telegram"""
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
