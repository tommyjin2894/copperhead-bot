#!/usr/bin/env python3
"""
단일 전략 봇을 실행하는 래퍼.
arena.py 없이 직접 전략 봇을 서버에 연결.

사용법:
  python3 run_bot.py v5_hybrid --server wss://... --name "MyTeam"
"""
import asyncio
import argparse
import importlib
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

REMOTE = "wss://copperhead-server.politesmoke-80c82ad7.eastasia.azurecontainerapps.io/ws/"


def main():
    parser = argparse.ArgumentParser(description="Run a strategy bot")
    parser.add_argument("strategy", help="Strategy name (e.g. v5_hybrid)")
    parser.add_argument("--server", "-s", default=REMOTE)
    parser.add_argument("--name", "-n", default=None)
    args = parser.parse_args()

    mod = importlib.import_module("strategies.%s" % args.strategy)
    name = args.name or ("tommy_%s" % args.strategy)
    bot = mod.Bot(args.server, name=name)
    bot.quiet = False

    print("%s" % bot.name)
    print("  Strategy: %s" % args.strategy)
    print("  Server: %s" % args.server)
    print()

    asyncio.run(bot.play())


if __name__ == "__main__":
    main()
