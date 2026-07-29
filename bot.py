import asyncio, json, os, random, traceback, time
from curl_cffi import requests as curl_requests
import aiohttp

TWITTER_USER  = "IranIntlBrk"
TELEGRAM_CHAT = "@Intlbrk"
TOKEN         = os.environ["TELEGRAM_BOT_TOKEN"]
AUTH_TOKEN    = os.environ["X_AUTH_TOKEN"]
CT0           = os.environ["X_CT0"]
STATE_FILE    = "state.json"

# SearchTimeline query ID (confirmed working as of mid‑2025)
SEARCH_QID    = "GKwKte_sT4PzFubvq9x3Vg"

FEATURES = {
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": False,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_jetfuel_header": True,
    "articles_preview_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_show_grok_translated_post": False,
}

BASE_HEADERS = {
    "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
    "cookie": f"auth_token={AUTH_TOKEN}; ct0={CT0}",
    "x-csrf-token": CT0,
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

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

def search_tweets(query: str, since_id: int = 0):
    """
    Fetch tweets via SearchTimeline GraphQL.
    Returns list of {id, text} newest first.
    """
    url = f"https://x.com/i/api/graphql/{SEARCH_QID}/SearchTimeline"
    variables = {
        "rawQuery": query,
        "count": 20,
        "product": "Latest",
        "querySource": "typed_query",
    }
    params = {
        "variables": json.dumps(variables),
        "features": json.dumps(FEATURES),
    }
    resp = curl_requests.get(url, headers=BASE_HEADERS, params=params, impersonate="chrome131")
    if resp.status_code != 200:
        print(f"❌ Search error {resp.status_code}: {resp.text[:200]}")
        return []

    try:
        data = resp.json()
    except Exception as e:
        print(f"❌ JSON decode error: {e}")
        return []

    instructions = (
        data.get("data", {})
        .get("search_by_raw_query", {})
        .get("search_timeline", {})
        .get("timeline", {})
        .get("instructions", [])
    )

    tweets = []
    for instr in instructions:
        if instr.get("type") != "TimelineAddEntries":
            continue
        for entry in instr.get("entries", []):
            tweet_result = (
                entry.get("content", {})
                .get("itemContent", {})
                .get("tweet_results", {})
                .get("result", {})
            )
            if not tweet_result:
                continue
            rest_id = tweet_result.get("rest_id")
            legacy = tweet_result.get("legacy", {})
            text = legacy.get("full_text", "")
            if rest_id and text:
                tweets.append({
                    "id": int(rest_id),
                    "text": text,
                })

    tweets.sort(key=lambda t: t["id"], reverse=True)
    return tweets

async def send_telegram(tweet_id: int, text: str) -> bool:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    link = f"https://x.com/{TWITTER_USER}/status/{tweet_id}"
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    msg = f"📡 <b>Iran Intl Breaking</b>\n\n{safe}\n\n<a href='{link}'>🔗 View on X</a>"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "text": msg,
        "parse_mode": "HTML",
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
                        print(f"⏳ Rate limited, waiting {wait}s…")
                        await asyncio.sleep(wait + 2)
                        continue
                    print(f"❌ Telegram error: {data}")
                    return False
        except Exception as exc:
            print(f"❌ Telegram error (attempt {attempt+1}): {exc}")
            await asyncio.sleep(2 ** attempt + random.uniform(0, 2))
    return False

async def main():
    print("🚀 Run started")
    state = load_state()
    last_id = int(state.get("last_tweet_id", 0))
    print(f"Last stored tweet ID: {last_id or '(none — first run)'}")

    query = f"from:{TWITTER_USER} -filter:replies -filter:retweets"
    tweets = search_tweets(query)
    print(f"📥 Fetched {len(tweets)} tweets")

    new = [t for t in tweets if t["id"] > last_id]
    new.sort(key=lambda t: t["id"])   # oldest → newest

    if not new:
        print("✓ No new tweets found.")
        return

    print(f"📬 {len(new)} new tweet(s) to forward")
    newest_id = last_id
    for t in new:
        ok = await send_telegram(t["id"], t["text"])
        if ok:
            newest_id = max(newest_id, t["id"])
        await asyncio.sleep(1.5)

    if newest_id > last_id:
        save_state({"last_tweet_id": str(newest_id)})
        print(f"✅ Saved new last_tweet_id: {newest_id}")
    else:
        print("⚠️ No tweets successfully sent; state not updated")

if __name__ == "__main__":
    asyncio.run(main())
