import asyncio, json, os, random, traceback
import aiohttp

TWITTER_USER   = "IranIntlBrk"
TELEGRAM_CHAT  = "@Intlbrk"
TOKEN          = os.environ["TELEGRAM_BOT_TOKEN"]
AUTH_TOKEN     = os.environ["X_AUTH_TOKEN"]
CT0            = os.environ["X_CT0"]
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

async def fetch_tweets_direct():
    """Fetch tweets using direct GraphQL request with correct headers."""
    url = "https://x.com/i/api/graphql/xxxx/UserTweets"   # we'll get the exact feature id
    # X's actual endpoint for user tweets uses this feature hash (may change, but this is current)
    features = {
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
    variables = {
        "userId": None,  # will be filled after we resolve username
        "count": 20,
        "includePromotedContent": False,
        "withQuickPromoteEligibilityTweetFields": False,
        "withVoice": False,
        "withV2Timeline": False,
    }

    headers = {
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "cookie": f"auth_token={AUTH_TOKEN}; ct0={CT0}",
        "x-csrf-token": CT0,
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    # Step 1: get user ID from username
    async with aiohttp.ClientSession() as sess:
        # Use a quick GraphQL call to get user by screen name
        user_query_url = "https://x.com/i/api/graphql/.../UserByScreenName"   # placeholder, we'll use a simpler approach
        # Instead, we can use the legacy endpoint: /i/api/1.1/users/show.json
        lookup_url = f"https://api.x.com/1.1/users/show.json?screen_name={TWITTER_USER}"
        headers_lookup = {
            "authorization": headers["authorization"],
            "cookie": headers["cookie"],
            "x-csrf-token": headers["x-csrf-token"],
        }
        try:
            async with sess.get(lookup_url, headers=headers_lookup) as resp:
                data = await resp.json()
                user_id = data.get("id_str")
                if not user_id:
                    print(f"❌ Could not find user ID for {TWITTER_USER}")
                    return []
                print(f"📌 User ID: {user_id}")
        except Exception as e:
            print(f"❌ Failed to get user ID: {e}")
            return []

        # Step 2: fetch tweets
        # The real endpoint for user tweets is:
        # /i/api/graphql/xxxx/UserTweets
        # We need a valid feature hash. We'll use a known one (may change, but this works now)
        graphql_id = "WZT7sCTrLvSOaMkGE5DIVw"   # UserTweets
        tweets_url = f"https://x.com/i/api/graphql/{graphql_id}/UserTweets"
        variables["userId"] = user_id

        payload = {
            "variables": variables,
            "features": features,
            "fieldToggles": {"withArticlePlainText": False},
        }
        try:
            async with sess.get(tweets_url, headers=headers, params={"variables": json.dumps(variables), "features": json.dumps(features), "fieldToggles": '{"withArticlePlainText":false}'}) as resp:
                data = await resp.json()
                # Extract tweet entries
                entries = []
                instructions = data.get("data", {}).get("user", {}).get("result", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions", [])
                for instr in instructions:
                    if instr.get("type") == "TimelineAddEntries":
                        for entry in instr.get("entries", []):
                            tweet_result = entry.get("content", {}).get("itemContent", {}).get("tweet_results", {}).get("result", {})
                            if not tweet_result:
                                continue
                            # Restructure to twscrape-compatible format
                            legacy = tweet_result.get("legacy", {})
                            tweet_obj = type('obj', (object,), {
                                'id': int(tweet_result.get("rest_id") or 0),
                                'rawContent': legacy.get("full_text", ""),
                                'date': legacy.get("created_at", "")
                            })()
                            entries.append(tweet_obj)
                return entries
        except Exception as e:
            print(f"❌ Error fetching tweets: {e}")
            traceback.print_exc()
            return []

async def main():
    print("🚀 Run started")
    state   = load_state()
    last_id = int(state.get("last_tweet_id", 0))
    print(f"Last stored tweet ID: {last_id or '(none — first run)'}")

    tweets = await fetch_tweets_direct()
    print(f"📥 Fetched {len(tweets)} tweets")

    new_tweets = [t for t in tweets if t.id > last_id]
    new_tweets.sort(key=lambda t: t.id)

    if not new_tweets:
        print("✓ No new tweets found.")
        return

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
