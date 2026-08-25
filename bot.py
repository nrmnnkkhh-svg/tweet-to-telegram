import asyncio, json, os, random, traceback
from difflib import SequenceMatcher
import aiohttp
from twikit import Client

from logger import (
    setup_logging, get_logger, set_log_context, log_exception, flush_and_stop
)

TWITTER_USER   = "IranIntlBrk"
TELEGRAM_CHAT  = "@Intlbrk"
TOKEN          = os.environ["TELEGRAM_BOT_TOKEN"]
COOKIES_STR    = os.environ["X_COOKIES"]
STATE_FILE     = "state.json"
TEMPLATE_FILE  = "template.txt"

SEPARATOR = "\n\n"

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_tweet_id": None, "thread_messages": {}, "total_sent": 0}
    with open(STATE_FILE) as f:
        state = json.load(f)
    state.setdefault("last_tweet_id", None)
    state.setdefault("thread_messages", {})
    state.setdefault("total_sent", 0)
    return state

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def load_template():
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

def get_footer():
    return load_template().replace("{text}", "").strip()

def parse_cookies(cookie_string: str) -> dict:
    cookies = {}
    for part in cookie_string.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            cookies[k] = v
    return cookies

def is_similar(a: str, b: str, threshold=0.7) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= threshold

async def send_message(text: str, tweet_id: str) -> int | None:
    log = get_logger("send_message")
    set_log_context(tweet_id=tweet_id)
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    msg = load_template().replace("{text}", safe)
    payload = {"chat_id": TELEGRAM_CHAT, "text": msg, "disable_web_page_preview": True}
    for attempt in range(5):
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.post(url, json=payload) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        log.info(f"Sent tweet → msg {data['result']['message_id']}")
                        return data["result"]["message_id"]
                    if data.get("error_code") == 429:
                        wait = data.get("parameters", {}).get("retry_after", 10)
                        log.warning(f"Rate limited. Waiting {wait}s")
                        await asyncio.sleep(wait + 2)
                        continue
                    log.error(f"Telegram API error: {data}")
                    return None
        except Exception as exc:
            log_exception(log, exc, f"Telegram send error (attempt {attempt+1})")
            await asyncio.sleep(2 ** attempt)
    return None

async def edit_message(msg_id: int, new_text: str) -> bool:
    log = get_logger("edit_message")
    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    payload = {"chat_id": TELEGRAM_CHAT, "message_id": msg_id, "text": new_text, "disable_web_page_preview": True}
    for attempt in range(5):
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.post(url, json=payload) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        log.info(f"Edited msg {msg_id}")
                        return True
                    if data.get("error_code") == 429:
                        wait = data.get("parameters", {}).get("retry_after", 10)
                        log.warning(f"Edit rate limited. Waiting {wait}s")
                        await asyncio.sleep(wait + 2)
                        continue
                    log.error(f"Edit error: {data}")
                    return False
        except Exception as exc:
            log_exception(log, exc, f"Edit error (attempt {attempt+1})")
            await asyncio.sleep(2 ** attempt)
    return False

async def delete_message(msg_id: int) -> bool:
    log = get_logger("delete_message")
    url = f"https://api.telegram.org/bot{TOKEN}/deleteMessage"
    payload = {"chat_id": TELEGRAM_CHAT, "message_id": msg_id}
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.post(url, json=payload) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        log.info(f"Deleted msg {msg_id}")
                        return True
                    if data.get("error_code") == 429:
                        wait = data.get("parameters", {}).get("retry_after", 10)
                        log.warning(f"Delete rate limited. Waiting {wait}s")
                        await asyncio.sleep(wait + 2)
                        continue
                    log.error(f"Delete error: {data}")
                    return False
        except Exception as exc:
            log_exception(log, exc, f"Delete error (attempt {attempt+1})")
            await asyncio.sleep(2 ** attempt)
    return False

def build_thread_text(texts: list[str], footer: str) -> str:
    safe_texts = [t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") for t in texts]
    combined = SEPARATOR.join(safe_texts)
    if footer:
        combined += "\n\n" + footer
    return combined

async def main():
    log = setup_logging()
    set_log_context("main")
    log.info("Run started")

    try:
        cookies = parse_cookies(COOKIES_STR)
        client = Client()
        await client.login(cookies=cookies)
        log.info("Twikit client logged in")

        user = await client.get_user_by_screen_name(TWITTER_USER)
        user_id = user.id
        log.info(f"User ID: {user_id}")

        tweets = []
        async for tweet in client.get_user_tweets(user_id, count=30, tweet_type='Tweets'):
            tweets.append(tweet)
        log.info(f"Fetched {len(tweets)} tweets")
    except Exception as e:
        log_exception(log, e, "Fetch failed")
        return

    if not tweets:
        log.info("No tweets"); return

    state = load_state()
    last_id = int(state.get("last_tweet_id", 0))
    thread_map = state.get("thread_messages", {})
    footer = get_footer()

    new_tweets = []
    for t in tweets:
        tid = int(t.id)
        if tid <= last_id:
            log.debug(f"Skipping duplicate tweet {tid}")
            continue
        text = getattr(t, "text", "") or ""
        if not text:
            continue
        conv_id = str(getattr(t, "conversation_id", tid))
        new_tweets.append({"id": tid, "text": text, "conv_id": conv_id})

    if not new_tweets:
        log.info("No new tweets")
    else:
        new_tweets.sort(key=lambda x: x["id"])
        for tw in new_tweets:
            conv_id = tw["conv_id"]
            existing = thread_map.get(conv_id)
            set_log_context(section="process_tweet", tweet_id=str(tw["id"]))

            if existing and existing.get("msg_id"):
                last_text = existing["texts"][-1] if existing["texts"] else ""
                if last_text and is_similar(tw["text"], last_text):
                    log.info("Similarity dedup triggered – deleting old msg")
                    if await delete_message(existing["msg_id"]):
                        del thread_map[conv_id]
                        existing = None

            if existing and existing.get("msg_id"):
                all_texts = existing["texts"] + [tw["text"]]
                combined = build_thread_text(all_texts, footer)
                if await edit_message(existing["msg_id"], combined):
                    existing["texts"] = all_texts
                    existing["combined"] = combined
                    existing["last_tweet_id"] = str(tw["id"])
                    thread_map[conv_id] = existing
                    state["total_sent"] = state.get("total_sent", 0) + 1
                else:
                    msg_id = await send_message(tw["text"], str(tw["id"]))
                    if msg_id:
                        thread_map[conv_id] = {
                            "msg_id": msg_id,
                            "last_tweet_id": str(tw["id"]),
                            "texts": [tw["text"]],
                            "combined": tw["text"],
                        }
                        state["total_sent"] = state.get("total_sent", 0) + 1
            else:
                msg_id = await send_message(tw["text"], str(tw["id"]))
                if msg_id:
                    thread_map[conv_id] = {
                        "msg_id": msg_id,
                        "last_tweet_id": str(tw["id"]),
                        "texts": [tw["text"]],
                        "combined": tw["text"],
                    }
                    state["total_sent"] = state.get("total_sent", 0) + 1

            state["last_tweet_id"] = str(tw["id"])
            save_state(state)
            await asyncio.sleep(1.5)

    state["thread_messages"] = thread_map
    save_state(state)
    log.info("Run complete")
    flush_and_stop()

if __name__ == "__main__":
    asyncio.run(main())
