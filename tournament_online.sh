#!/bin/bash
# ============================================================
# 온라인 토너먼트: 5개 봇을 각각 별도 프로세스로 실행
# 각 봇이 독립적으로 토너먼트 서버에 접속하여 대전
#
# 사용법:
#   chmod +x tournament_online.sh
#   ./tournament_online.sh
#
# 결과 확인:
#   cat results/v1_aggressive.log
#   cat results/v5_hybrid.log
# ============================================================

SERVER="wss://copperhead-server.politesmoke-80c82ad7.eastasia.azurecontainerapps.io/ws/"
DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS="$DIR/results"
mkdir -p "$RESULTS"

STRATEGIES=(
    "v1_aggressive"
    "v2_defensive"
    "v3_trapper"
    "v4_cutoff"
    "v5_hybrid"
)

echo "=========================================="
echo "  ONLINE TOURNAMENT - 5 Bots Deployed"
echo "=========================================="
echo "  Server: $SERVER"
echo "  Results: $RESULTS/"
echo ""

PIDS=()

for strat in "${STRATEGIES[@]}"; do
    echo "  Starting $strat..."
    python3 "$DIR/run_bot.py" "$strat" \
        --server "$SERVER" \
        --name "tommy_${strat}" \
        > "$RESULTS/${strat}.log" 2>&1 &
    PIDS+=($!)
    sleep 1  # stagger joins slightly
done

echo ""
echo "  All 5 bots launched! PIDs: ${PIDS[*]}"
echo ""
echo "  Watch live:"
echo "    tail -f $RESULTS/v5_hybrid.log"
echo ""
echo "  Watch all:"
echo "    tail -f $RESULTS/*.log"
echo ""
echo "  Stop all:"
echo "    kill ${PIDS[*]}"
echo ""
echo "  Press Ctrl+C to stop all bots"
echo ""

# Wait for all to finish
trap "echo 'Stopping all bots...'; kill ${PIDS[*]} 2>/dev/null; exit" INT TERM
wait
echo "All bots finished."
