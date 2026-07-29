import asyncio, json, os, random, traceback
import aiohttp
from twscrape import API

TWITTER_USER   = "IranIntlBrk"
TELEGRAM_CHAT  = "@Intlbrk"
TOKEN          = os.environ["TELEGRAM_BOT_TOKEN"]
AUTH_TOKEN     = os.environ["X_AUTH_TOKEN"]
CT0            = os.environ["X_CT0"]
ACCOUNT_NAME   = os.environ.get("X_USERNAME", "burner_account")
STATE_FILE     = "state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

async def send_telegram(tweet_id: str, text: str) -> bool:
    url    = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    link   = f"https://x.com/{TWITTER_USER}/status/{tweet_id}"
    safe   = (text
               .replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;"))
    msg    = f"📡 <b>Iran Intl Breaking</b>\n\n{safe}\n\n<a href='{link}'>🔗 View on X</a>"
    payload = {
        "chat_id":                  TELEGRAM_CHAT,
        "text":                     msg,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
    }
    for attempt in range(5):
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.post(url, json=payload) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        print(f"✅ Sent tweet {tweet_id}")
                        return True
                    if data.get("error_code") == 429:
                        wait = data.get("parameters", {}).get("retry_after", 10)
                        print(f"⏳ Telegram rate limit, waiting {wait}s…")
                        await asyncio.sleep(wait + 2)
                        continue
                    print(f"❌ Telegram error: {data}")
                    return False
        except Exception as exc:
            print(f"❌ Telegram network error (attempt {attempt+1}): {exc}")
            await asyncio.sleep(2 ** attempt + random.uniform(0, 2))
    return False

async def main():
    print("🚀 Run started")
    state      = load_state()
    last_id    = int(state.get("last_tweet_id", 0))
    print(f"Last stored tweet ID: {last_id or '(none — first run)'}")

    api          = API()
    cookie_str   = f"auth_token={AUTH_TOKEN}; ct0={CT0}"
    await api.pool.add_account_cookies(ACCOUNT_NAME, cookie_str)
    print(f"✅ Account '{ACCOUNT_NAME}' added via cookie auth")

    query = f"from:{TWITTER_USER} -filter:replies -filter:retweets"
    if last_id:
        query += f" since_id:{last_id}"

    print(f"🔍 Search query: {query}")

    new_tweets = []
    try:
        async with asyncio.timeout(60):
            async for tweet in api.search(query, limit=20):
                if tweet.id <= last_id:
                    continue
                new_tweets.append(tweet)
    except asyncio.TimeoutError:
        print("⚠️ Search timed out after 60s — using tweets collected so far")
    except Exception as exc:
        print(f"❌ Fetch error: {exc}")
        traceback.print_exc()

    if not new_tweets:
        print("✓ No new tweets found.")
        return

    new_tweets.sort(key=lambda t: t.id)
    print(f"📬 {len(new_tweets)} new tweet(s) to forward")

    newest_id = last_id
    for tweet in new_tweets:
        ok = await send_telegram(str(tweet.id), tweet.rawContent)
        if ok:
            newest_id = max(newest_id, tweet.id)
        await asyncio.sleep(1.5)

    if newest_id > last_id:
        save_state({"last_tweet_id": str(newest_id)})
        print(f"✅ Saved new last_tweet_id: {newest_id}")
    else:
        print("⚠️ No tweets successfully sent; state not updated")

if __name__ == "__main__":
    asyncio.run(main())
