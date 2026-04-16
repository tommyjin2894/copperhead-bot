#!/bin/bash
# ============================================================
# 로컬 토너먼트: 서버 시작 + 2개 봇 자동 대결
#
# 사용법:
#   chmod +x tournament_local.sh
#   ./tournament_local.sh v3_trapper v5_hybrid
#   ./tournament_local.sh v1_aggressive v2_defensive
#
# 전체 라운드 로빈:
#   ./tournament_local.sh --roundrobin
# ============================================================

DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$DIR/../copperhead-server"
SETTINGS="$DIR/local_server_settings.json"
RESULTS="$DIR/results"
mkdir -p "$RESULTS"

# Check if server code exists
if [ ! -f "$SERVER_DIR/main.py" ]; then
    echo "ERROR: copperhead-server not found at $SERVER_DIR"
    echo "Run: cd .. && git clone https://github.com/revodavid/copperhead-server.git"
    exit 1
fi

echo "=========================================="
echo "  LOCAL TOURNAMENT"
echo "=========================================="

# Start local server
echo "  Starting local server..."
cp "$SETTINGS" "$SERVER_DIR/server-settings.json"
python3 "$SERVER_DIR/main.py" > "$RESULTS/server.log" 2>&1 &
SERVER_PID=$!
echo "  Server PID: $SERVER_PID"
sleep 3

trap "echo 'Cleaning up...'; kill $SERVER_PID 2>/dev/null; exit" INT TERM

if [ "$1" == "--roundrobin" ]; then
    ROUNDS="${2:-3}"
    echo "  Mode: Round Robin ($ROUNDS rounds each)"
    echo ""
    python3 "$DIR/arena.py" --roundrobin --rounds "$ROUNDS" \
        --server "ws://localhost:8765/ws/" 2>&1 | tee "$RESULTS/roundrobin.log"
else
    BOT1="${1:-v5_hybrid}"
    BOT2="${2:-v1_aggressive}"
    ROUNDS="${3:-5}"
    echo "  Match: $BOT1 vs $BOT2 ($ROUNDS rounds)"
    echo ""
    python3 "$DIR/arena.py" "$BOT1" "$BOT2" \
        --rounds "$ROUNDS" \
        --server "ws://localhost:8765/ws/" 2>&1 | tee "$RESULTS/match_${BOT1}_vs_${BOT2}.log"
fi

echo ""
echo "Stopping server..."
kill $SERVER_PID 2>/dev/null
echo "Done."
