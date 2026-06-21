import asyncio, json, os, sys, traceback
import aiohttp
from twscrape import API

TWITTER_USER = "IranIntlBrk"
TELEGRAM_CHAT = "@Intlbrk"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
STATE_FILE = "state.json"
HEADER = "—————————————————————\n📢 ایران اینترنشنال - خبر فوری\n@Intlbrk"

BURNER_USERNAME = "NormanKosmaqz"

STICKER_FILE_ID = "CAACAgQAAxkBAAMCajdhWmizvusQB4anhde3bFYP4TQAAkoeAAK9UsFR2diMWgEMWjU8BA"

api = API()

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

async def send_sticker():
    url = f"https://api.telegram.org/bot{TOKEN}/sendSticker"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "sticker": STICKER_FILE_ID,
    }
    async with aiohttp.ClientSession() as sess:
        async with sess.post(url, json=payload) as resp:
            data = await resp.json()
            if data.get("ok"):
                print(f"✅ Sticker sent")
                return True
            print(f"❌ Sticker error: {data}")
            return False

async def send_telegram(text, tweet_url):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    msg = f"{safe}\n\n{HEADER}"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "text": msg,
        "disable_web_page_preview": True,
    }
    async with aiohttp.ClientSession() as sess:
        async with sess.post(url, json=payload) as resp:
            data = await resp.json()
            if data.get("ok"):
                print(f"✅ Sent: {tweet_url}")
                return True
            if data.get("error_code") == 429:
                wait = data.get("parameters", {}).get("retry_after", 5)
                print(f"⏳ Rate limited, waiting {wait}s...")
                await asyncio.sleep(wait + 1)
                async with sess.post(url, json=payload) as resp2:
                    data2 = await resp2.json()
                    if data2.get("ok"):
                        print(f"✅ Sent: {tweet_url}")
                        return True
                    print(f"❌ Telegram error after retry: {data2}")
                    return False
            print(f"❌ Telegram error: {data}")
            return False

async def main():
    print(f"🚀 Run started")
    try:
        auth_token = os.environ["X_AUTH_TOKEN"]
        ct0 = os.environ["X_CT0"]
        cookies_str = f"auth_token={auth_token}; ct0={ct0}"
        await api.pool.add_account(BURNER_USERNAME, "dummy_pass", "", "", cookies=cookies_str)

        acc = await api.pool.get_account(BURNER_USERNAME)
        print(f"Account active: {acc.active}")
        if not acc.active:
            print("Account not active")
            return

        user = await api.user_by_login(TWITTER_USER)
        user_id = user.id
        print(f"📌 User ID for {TWITTER_USER}: {user_id}")

        raw_tweets = []
        seen = set()
        async for t in api.user_tweets(user_id, limit=20):
            if t.id not in seen:
                seen.add(t.id)
                raw_tweets.append(t)
                if len(raw_tweets) >= 20:
                    break
        raw_tweets.sort(key=lambda t: t.id, reverse=True)
        print(f"📥 Got {len(raw_tweets)} unique tweets")
    except Exception as e:
        print(f"❌ Fetch failed: {e}")
        traceback.print_exc()
        return

    if not raw_tweets:
        print("⚠️ No tweets")
        return

    state = load_state()
    last_id = state.get("last_tweet_id")
    print(f"📌 Last forwarded tweet ID: {last_id or 'none'}")

    new_tweets = []
    for t in raw_tweets:
        if last_id and t.id <= last_id:
            continue
        text = t.rawContent or ""
        if not text:
            continue
        new_tweets.append(t)

    new_tweets.reverse()

    if not new_tweets:
        print("✅ Nothing new")
        return

    print(f"📬 {len(new_tweets)} new tweet(s)")

    success = 0
    total = len(new_tweets)
    for idx, t in enumerate(new_tweets):
        url = f"https://x.com/{TWITTER_USER}/status/{t.id}"
        print(f"📤 Sending {t.id} ({idx+1}/{total})...")
        if not await send_telegram(t.rawContent, url):
            print(f"❌ Send failed, stopping batch")
            break

        state["last_tweet_id"] = t.id
        save_state(state)
        success += 1

        if idx < total - 1:
            await asyncio.sleep(1)
            await send_sticker()
            await asyncio.sleep(2)
        else:
            await asyncio.sleep(2)

    state["total_sent"] = state.get("total_sent", 0) + success
    save_state(state)
    print(f"✅ Forwarded {success}/{total} tweets")

if __name__ == "__main__":
    asyncio.run(main())
