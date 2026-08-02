#!/usr/bin/env python3
"""AGREEMENT 1 – Rule 10: Quick health check for both channels."""
import json, os

MAIN_STATE   = os.path.expanduser("~/tweet-to-telegram/state.json")
CLONE_STATE  = os.path.expanduser("~/tweet-to-telegram-clone/state.json")

def read_state(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)

def main():
    print("=" * 50)
    print("🏥  BOT HEALTH CHECK")
    print("=" * 50)

    for label, path in [("Main", MAIN_STATE), ("Clone", CLONE_STATE)]:
        print(f"\n── {label} channel ──")
        state = read_state(path)
        lid = state.get("last_tweet_id", "?")
        total = state.get("total_sent", "?")
        print(f"  last_tweet_id : {lid}")
        print(f"  total_sent    : {total}")

    print("\n── Latest GitHub Actions runs ──")
    for repo, name in [("nrmnnkkhh-svg/tweet-to-telegram", "Main"),
                       ("nrmnnkkhh-svg/tweet-to-telegram-clone", "Clone")]:
        print(f"\n{name}:")
        os.system(f"gh run list --repo {repo} --workflow=forward.yml --limit 1")

if __name__ == "__main__":
    main()
