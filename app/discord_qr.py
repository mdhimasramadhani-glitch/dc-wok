import asyncio
import base64
from playwright.async_api import async_playwright

class DiscordQRAuthSession:
    async def run_qr_flow(self, frontend_ws, on_token_captured):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            captured_token = None
            token_event = asyncio.Event()

            async def handle_request(route, request):
                nonlocal captured_token
                headers = request.headers
                if "authorization" in headers and "api/v9" in request.url:
                    token = headers["authorization"]
                    if not captured_token and len(token) > 50 and token != "undefined":
                        captured_token = token
                        token_event.set()
                await route.continue_()

            await page.route("**/*", handle_request)
            
            try:
                await page.goto("https://discord.com/login", wait_until="domcontentloaded")

                # Gunakan selector yang lebih tahan perubahan class Discord
                qr_locator = page.locator('div[class*="qrCode"], [aria-label*="QR"], svg + img').first
                await qr_locator.wait_for(state="visible", timeout=20000)
                
                # Beri waktu 1 detik agar kode QR selesai di-render sempurna
                await asyncio.sleep(1.0)
                
                qr_bytes = await qr_locator.screenshot()
                qr_b64 = base64.b64encode(qr_bytes).decode("utf-8")
                qr_data_url = f"data:image/png;base64,{qr_b64}"
                
                await frontend_ws.send_json({"event": "qr_image", "url": qr_data_url})

                await asyncio.wait_for(token_event.wait(), timeout=120.0)
                
                if captured_token:
                    user_info = await on_token_captured(captured_token)
                    await frontend_ws.send_json({
                        "event": "authenticated",
                        "username": user_info["username"],
                        "avatar": user_info["avatar_url"]
                    })
            except Exception as e:
                await frontend_ws.send_json({"event": "error", "detail": f"QR Timeout/Block: {str(e)}"})
            finally:
                await browser.close()