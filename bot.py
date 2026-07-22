import asyncio, json, os, sys, traceback, random
import aiohttp
from twscrape import API

TWITTER_USER = "IranIntlBrk"
TELEGRAM_CHAT = "@Intlbrk"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
STATE_FILE = "state.json"
TEMPLATE_FILE = "template.txt"

BURNER_USERNAME = "NormanKosmaqz"

api = API()

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def load_template():
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

async def send_telegram(text, tweet_url):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    template = load_template()
    msg = template.replace("{text}", safe)
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "text": msg,
        "disable_web_page_preview": True,
    }
    for attempt in range(5):
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.post(url, json=payload) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        print(f"✅ Sent: {tweet_url}")
                        return True
                    if data.get("error_code") == 429:
                        wait = data.get("parameters", {}).get("retry_after", 5)
                        print(f"⏳ Rate limited (attempt {attempt+1}), waiting {wait}s...")
                        await asyncio.sleep(wait + random.uniform(1, 3))
                        continue
                    print(f"❌ Telegram error: {data}")
                    return False
        except Exception as e:
            print(f"❌ Telegram network error (attempt {attempt+1}): {e}")
            await asyncio.sleep(2 ** attempt + random.uniform(1, 3))
    print(f"❌ Telegram send failed after 5 attempts")
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
    if last_id:
        last_id = int(last_id)
    print(f"📌 Last forwarded tweet ID: {last_id or 'none'}")

    new_tweets = []
    for t in raw_tweets:
        if last_id and int(t.id) <= last_id:
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
    for t in new_tweets:
        url = f"https://x.com/{TWITTER_USER}/status/{t.id}"
        print(f"📤 Sending {t.id}...")
        if not await send_telegram(t.rawContent, url):
            print(f"❌ Send failed, stopping batch")
            break

        state["last_tweet_id"] = t.id
        save_state(state)
        success += 1
        await asyncio.sleep(3 + random.uniform(0, 2))

    state["total_sent"] = state.get("total_sent", 0) + success
    save_state(state)
    print(f"✅ Forwarded {success}/{len(new_tweets)} tweets")

if __name__ == "__main__":
    asyncio.run(main())
