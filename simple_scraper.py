import os
import asyncio
import requests
from playwright.async_api import async_playwright

TELEGRAM_BOT_TOKEN = "8791585716:AAE-SEV2iACbYXMmymWeA1JJVyGFk5_Y1Jg"
TELEGRAM_CHAT_ID = "7420001477"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://shop.tamimimarkets.com/ar/hot-deals")
        await page.wait_for_timeout(5000)
        await page.screenshot(path="test.png")
        
        # Send success message
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            'chat_id': TELEGRAM_CHAT_ID, 
            'text': '✅ Page loaded successfully!'
        })
        await browser.close()

asyncio.run(run())
