#!/usr/bin/env python3
import asyncio, aiohttp, os, sys
from datetime import datetime

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNELS_TO_WIPE = ["@Intlbrk", "@CloneIntlbrk"]
BATCH_SIZE = 100
CALLS_PER_SEC = 10
DELAY = 1.0 / CALLS_PER_SEC

async def send_probe(session, chat_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": "🔄 Wipe in progress — deleting automatically…"}
    async with session.post(url, json=payload) as resp:
        data = await resp.json()
    if not data.get("ok"):
        code = data.get("error_code", "?")
        desc = data.get("description", "unknown error")
        if code == 403:
            print(f"  ❌ Bot is not a member/admin of {chat_id}")
        elif code == 400:
            print(f"  ❌ Bad request for {chat_id}: {desc}")
        else:
            print(f"  ❌ Cannot reach {chat_id} (error {code}): {desc}")
        return 0
    ceiling_id = data["result"]["message_id"]
    del_url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
    async with session.post(del_url, json={"chat_id": chat_id, "message_id": ceiling_id}):
        pass
    return ceiling_id

async def delete_batch(session, chat_id, ids, retry=0):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessages"
    payload = {"chat_id": chat_id, "message_ids": ids}
    async with session.post(url, json=payload) as resp:
        data = await resp.json()
    if not data.get("ok") and data.get("error_code") == 429:
        if retry >= 3:
            print(f"  ⛔ Flood wait retries exhausted for batch {ids[0]}-{ids[-1]}")
            return False
        wait = data.get("parameters", {}).get("retry_after", 15)
        print(f"  ⏳ Flood wait: pausing {wait}s before retry {retry + 1}/3…")
        await asyncio.sleep(wait + 1)
        return await delete_batch(session, chat_id, ids, retry + 1)
    return True

async def wipe_channel(session, chat_id):
    start_time = datetime.now()
    print(f"\n{'━' * 52}")
    print(f"🗑️   Wiping: {chat_id}")
    print(f"{'━' * 52}")
    ceiling = await send_probe(session, chat_id)
    if ceiling == 0:
        print(f"  ⏭️  Skipping {chat_id} (could not probe channel)\n")
        return
    total_ids = ceiling
    total_batches = (total_ids + BATCH_SIZE - 1) // BATCH_SIZE
    est_seconds = total_batches * DELAY
    print(f"  📊 Ceiling ID:     {ceiling}")
    print(f"  📦 Total batches:  {total_batches} × {BATCH_SIZE} IDs each")
    print(f"  ⏱️  Est. time:      ~{est_seconds:.0f} seconds\n")
    batches_done = 0
    for chunk_start in range(1, ceiling + 1, BATCH_SIZE):
        chunk_end = min(chunk_start + BATCH_SIZE - 1, ceiling)
        batch_ids = list(range(chunk_start, chunk_end + 1))
        await delete_batch(session, chat_id, batch_ids)
        batches_done += 1
        if batches_done % max(1, total_batches // 10) == 0 or batches_done == total_batches:
            pct = (batches_done / total_batches) * 100
            ids_done = min(batches_done * BATCH_SIZE, ceiling)
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"  🔄 {pct:5.1f}%  |  {ids_done:,}/{ceiling:,} IDs  |  {elapsed:.0f}s elapsed")
        await asyncio.sleep(DELAY)
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n  ✅ Finished {chat_id}")
    print(f"     Processed {ceiling:,} IDs in {total_batches:,} batches ({elapsed:.1f}s)")
    print(f"     (IDs with no matching message were silently skipped by Telegram)")

async def main():
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN is not set")
        sys.exit(1)
    print("🧹 Telegram Channel Mass Deleter")
    print(f"📋 Channels: {', '.join(CHANNELS_TO_WIPE)}")
    print(f"⚙️  Batch size: {BATCH_SIZE} IDs/call  |  Rate: {CALLS_PER_SEC} calls/sec\n")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        for channel in CHANNELS_TO_WIPE:
            await wipe_channel(session, channel)
    print(f"\n{'━' * 52}")
    print("🎉 All channels processed!")
    print(f"{'━' * 52}")

if __name__ == "__main__":
    asyncio.run(main())
