#!/usr/bin/env python3
"""
Arena - 로컬 서버에서 봇 대 봇 테스트.

사용법:
  # 1. 먼저 로컬 서버 시작 (별도 터미널):
  cd ../copperhead-server && python3 main.py --settings ../tommy-bot/local_server_settings.json

  # 2. 두 봇을 대결시키기:
  python3 arena.py v3_trapper v5_hybrid              # 1판
  python3 arena.py v3_trapper v5_hybrid --rounds 10  # 10판 연속

  # 3. 전체 라운드 로빈 (모든 봇 조합 테스트):
  python3 arena.py --roundrobin --rounds 5

  # 4. 리모트 서버에서 테스트:
  python3 arena.py v5_hybrid v1_aggressive --server wss://...
"""

import asyncio
import argparse
import importlib
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

LOCAL_SERVER = "ws://localhost:8765/ws/"

ALL_STRATEGIES = [
    "v1_aggressive",
    "v2_defensive",
    "v3_trapper",
    "v4_cutoff",
    "v5_hybrid",
]


def load_bot(strategy_name, server_url, bot_name=None):
    mod = importlib.import_module("strategies.%s" % strategy_name)
    name = bot_name or strategy_name
    bot = mod.Bot(server_url, name=name)
    bot.quiet = True
    return bot


async def run_match(bot1, bot2):
    """Run both bots concurrently. Returns when both finish."""
    await asyncio.gather(bot1.play(), bot2.play())


async def run_rounds(strat1, strat2, server, rounds):
    """Run multiple rounds between two strategies."""
    wins = {strat1: 0, strat2: 0, "draw": 0}

    for i in range(rounds):
        b1 = load_bot(strat1, server, "%s-A" % strat1)
        b2 = load_bot(strat2, server, "%s-B" % strat2)
        await run_match(b1, b2)

        # Determine winner by win/loss record
        if b1.wins > b1.losses:
            wins[strat1] += 1
            result = strat1
        elif b2.wins > b2.losses:
            wins[strat2] += 1
            result = strat2
        else:
            wins["draw"] += 1
            result = "DRAW"

        print("  Round %d/%d: %s wins (%s: %dW-%dL | %s: %dW-%dL)" % (
            i + 1, rounds, result,
            strat1, b1.wins, b1.losses,
            strat2, b2.wins, b2.losses))

    print()
    print("=== RESULT: %s vs %s ===" % (strat1, strat2))
    print("  %s: %d wins" % (strat1, wins[strat1]))
    print("  %s: %d wins" % (strat2, wins[strat2]))
    print("  Draws: %d" % wins["draw"])
    print()
    return wins


async def round_robin(server, rounds):
    """모든 봇 조합 테스트."""
    results = {}
    total_wins = {s: 0 for s in ALL_STRATEGIES}

    for i, s1 in enumerate(ALL_STRATEGIES):
        for s2 in ALL_STRATEGIES[i + 1:]:
            print("=" * 50)
            print("MATCH: %s vs %s (%d rounds)" % (s1, s2, rounds))
            print("=" * 50)
            w = await run_rounds(s1, s2, server, rounds)
            results[(s1, s2)] = w
            total_wins[s1] += w[s1]
            total_wins[s2] += w[s2]

    print()
    print("=" * 50)
    print("FINAL STANDINGS")
    print("=" * 50)
    ranking = sorted(total_wins.items(), key=lambda x: -x[1])
    for rank, (name, wins) in enumerate(ranking, 1):
        print("  #%d  %s: %d total wins" % (rank, name, wins))


def main():
    parser = argparse.ArgumentParser(description="CopperHead Bot Arena")
    parser.add_argument("bot1", nargs="?", help="First bot strategy name")
    parser.add_argument("bot2", nargs="?", help="Second bot strategy name")
    parser.add_argument("--server", default=LOCAL_SERVER,
                        help="Server URL (default: %s)" % LOCAL_SERVER)
    parser.add_argument("--rounds", type=int, default=1,
                        help="Number of rounds (default: 1)")
    parser.add_argument("--roundrobin", action="store_true",
                        help="Run all-vs-all round robin")
    parser.add_argument("--list", action="store_true",
                        help="List available strategies")
    args = parser.parse_args()

    if args.list:
        print("Available strategies:")
        for s in ALL_STRATEGIES:
            print("  - %s" % s)
        return

    if args.roundrobin:
        print("Round Robin Tournament (%d rounds each)" % args.rounds)
        print("Server: %s" % args.server)
        print()
        asyncio.run(round_robin(args.server, args.rounds))
        return

    if not args.bot1 or not args.bot2:
        parser.error("Specify two bot names, or use --roundrobin")

    print("%s vs %s (%d rounds)" % (args.bot1, args.bot2, args.rounds))
    print("Server: %s" % args.server)
    print()
    asyncio.run(run_rounds(args.bot1, args.bot2, args.server, args.rounds))


if __name__ == "__main__":
    main()
