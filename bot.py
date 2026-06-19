import asyncio, json, os, sys, traceback
import aiohttp
from twscrape import API

TWITTER_USER = "IranIntlBrk"
TELEGRAM_CHAT = "@AutoNewsOnTG"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
STATE_FILE = "state.json"
HEADER = "📰 <b>Iran International Breaking</b>"

api = API()

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

async def send_telegram(text, tweet_url):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    msg = f"{HEADER}\n\n{safe}\n\n<a href='{tweet_url}'>🔗 View on X</a>"
    payload = {"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": False}
    async with aiohttp.ClientSession() as sess:
        async with sess.post(url, json=payload) as resp:
            data = await resp.json()
            if data.get("ok"):
                print(f"✅ Sent: {tweet_url}")
                return True
            print(f"❌ Telegram error: {data}")
            return False

async def main():
    print(f"🚀 Run started")
    try:
        await api.pool.add_account("", os.environ["X_AUTH_TOKEN"], os.environ["X_CT0"], "")
        tweets = []
        async for t in api.user_tweets(TWITTER_USER, limit=10):
            tweets.append(t)
        print(f"📥 Got {len(tweets)} tweets")
    except Exception as e:
        print(f"❌ Fetch failed: {e}")
        traceback.print_exc()
        return

    if not tweets:
        print("⚠️ No tweets")
        return

    state = load_state()
    last_id = state.get("last_tweet_id")
    print(f"📌 Last forwarded tweet ID: {last_id or 'none'}")

    new_tweets = []
    for t in tweets:
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
    for t in new_tweets:
        url = f"https://x.com/{TWITTER_USER}/status/{t.id}"
        print(f"📤 Sending {t.id}...")
        if await send_telegram(t.rawContent, url):
            state["last_tweet_id"] = t.id
            save_state(state)
            success += 1
            await asyncio.sleep(1.5)
        else:
            print(f"❌ Send failed, stopping batch")
            break

    state["total_sent"] = state.get("total_sent", 0) + success
    save_state(state)
    print(f"✅ Forwarded {success}/{len(new_tweets)} tweets")

if __name__ == "__main__":
    asyncio.run(main())
