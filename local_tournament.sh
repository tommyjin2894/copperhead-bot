#!/bin/bash
# ============================================================
# 로컬 토너먼트: 서버 + 봇 4개 자동 실행 (2라운드 브라켓)
#
# 사용법:
#   ./local_tournament.sh              # 기본 4봇 토너먼트
#   ./local_tournament.sh 1 3 4 5      # 특정 전략 선택
#   ./local_tournament.sh all          # 8봇 (5개 + CopperBot 3개 자동추가)
# ============================================================

DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$DIR/../copperhead-server"
RESULTS="$DIR/results"
mkdir -p "$RESULTS"

if [ ! -f "$SERVER_DIR/main.py" ]; then
    echo "ERROR: copperhead-server not found!"
    echo "Run: cd $DIR/.. && git clone https://github.com/revodavid/copperhead-server.git"
    exit 1
fi

# Parse arguments
if [ "$1" == "all" ]; then
    BOTS=(1 2 3 4 5)
    # 5봇 = arenas 4 (8슬롯), bots=3 으로 CopperBot 자동 채움
    ARENAS=4
    AUTO_BOTS=3
else
    if [ $# -ge 4 ]; then
        BOTS=("$@")
    else
        # 기본: V1, V3, V4, V5
        BOTS=(1 3 4 5)
    fi
    NUM=${#BOTS[@]}
    ARENAS=$((NUM / 2))
    AUTO_BOTS=0
fi

echo "=========================================="
echo "  LOCAL TOURNAMENT"
echo "=========================================="
echo "  Bots: ${BOTS[*]}"
echo "  Arenas: $ARENAS (${#BOTS[@]} players)"
echo "=========================================="

# 서버 설정 생성
cat > "$DIR/_tournament_settings.json" << SETTINGS
{
    "log_file": "",
    "auto_start": "always",
    "tournament_countdown": 3,
    "arenas": $ARENAS,
    "points_to_win": 3,
    "reset_delay": 2,
    "game-timeout": 10,
    "grid_size": "15x15",
    "speed": 0.01,
    "bots": $AUTO_BOTS,
    "fruit_warning": 10,
    "max_fruits": 5,
    "fruit_interval": 8,
    "fruits": {
        "apple": { "propensity": 9, "lifetime": 0 },
        "orange": { "propensity": 0, "lifetime": 0 },
        "lemon": { "propensity": 0, "lifetime": 0 },
        "grapes": { "propensity": 1, "lifetime": 40 },
        "strawberry": { "propensity": 0, "lifetime": 0 },
        "banana": { "propensity": 0, "lifetime": 0 },
        "peach": { "propensity": 0, "lifetime": 0 },
        "cherry": { "propensity": 0, "lifetime": 0 },
        "watermelon": { "propensity": 0, "lifetime": 0 },
        "kiwi": { "propensity": 0, "lifetime": 0 }
    }
}
SETTINGS

# 기존 서버 종료
pkill -f "main.py" 2>/dev/null
sleep 1

# 서버 시작
echo ""
echo "  Starting server (speed=0.05, arenas=$ARENAS)..."
cp "$DIR/_tournament_settings.json" "$SERVER_DIR/server-settings.json"
cd "$SERVER_DIR"
python3 main.py > "$RESULTS/server.log" 2>&1 &
SERVER_PID=$!
echo "  Server PID: $SERVER_PID"
sleep 3

# 서버 확인
if ! curl -s http://localhost:8765/status > /dev/null 2>&1; then
    echo "  ERROR: Server failed to start!"
    cat "$RESULTS/server.log"
    exit 1
fi
echo "  Server OK!"

NAMES=("" "V1-Aggressive" "V2-Defensive" "V3-Trapper" "V4-Cutoff" "V5-Hybrid")
BOT_PIDS=()

echo ""
echo "  Launching bots..."
for strat in "${BOTS[@]}"; do
    name="${NAMES[$strat]}"
    echo "    -> $name (strategy $strat)"
    cd "$DIR"
    python3 mybot.py "$strat" \
        --server ws://localhost:8765/ws/ \
        --name "$name" \
        > "$RESULTS/bot_${strat}.log" 2>&1 &
    BOT_PIDS+=($!)
    sleep 0.5
done

echo ""
echo "=========================================="
echo "  Tournament running!"
echo "=========================================="
echo ""
echo "  Watch: http://localhost:8765"
echo ""
echo "  Logs:"
for strat in "${BOTS[@]}"; do
    echo "    cat results/bot_${strat}.log"
done
echo ""
echo "  Live:"
echo "    tail -f results/bot_*.log"
echo ""
echo "  Press Ctrl+C to stop"
echo ""

cleanup() {
    echo ""
    echo "  Stopping..."
    for p in "${BOT_PIDS[@]}"; do kill "$p" 2>/dev/null; done
    kill "$SERVER_PID" 2>/dev/null
    echo ""

    # 결과 요약
    echo "=========================================="
    echo "  RESULTS"
    echo "=========================================="
    for strat in "${BOTS[@]}"; do
        name="${NAMES[$strat]}"
        log="$RESULTS/bot_${strat}.log"
        if [ -f "$log" ]; then
            champ=$(grep -o "Champion: .*" "$log" 2>/dev/null | tail -1)
            won=$(grep -c "WON!" "$log" 2>/dev/null)
            lost=$(grep -c "LOST!" "$log" 2>/dev/null)
            draw=$(grep -c "DRAW!" "$log" 2>/dev/null)
            match_w=$(grep -c "MATCH WON" "$log" 2>/dev/null)
            printf "  %-16s  Games: %dW-%dL-%dD  Matches: %d won" "$name" "$won" "$lost" "$draw" "$match_w"
            if echo "$champ" | grep -q "$name" 2>/dev/null; then
                echo "  *** CHAMPION ***"
            else
                echo ""
            fi
        fi
    done
    echo "=========================================="
    exit 0
}

trap cleanup INT TERM

# 봇들이 끝날때까지 대기
wait "${BOT_PIDS[@]}" 2>/dev/null
sleep 2
cleanup
