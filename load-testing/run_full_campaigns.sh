#!/bin/bash
# Orchestrates the full Lab 2 Python-script test matrix (Alta carga / Muy alta
# carga / Estres / Estres fuerte, GET campaign then POST campaign), with a
# clean docker compose down -v + reseed between campaigns as required by the
# lab statement (POST runs contaminate the GET tienda's history otherwise).
set -uo pipefail

REPO_ROOT="/Users/santi/Documents/Universidad/9. Noveno/Arquisoft/Laboratorios/cheapest-api"
LT_DIR="$REPO_ROOT/load-testing"
VENV_PY="$LT_DIR/.venv/bin/python"
LOG="$LT_DIR/orchestrator.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

wait_postgres_healthy() {
  for i in $(seq 1 60); do
    st=$(docker inspect --format='{{.State.Health.Status}}' cheapest-postgres 2>/dev/null)
    if [ "$st" = "healthy" ]; then return 0; fi
    sleep 1
  done
  return 1
}

start_backend() {
  local seed_file="$1"
  local backend_log="$2"
  cd "$REPO_ROOT"
  LOAD_SEED_FILE="$seed_file" nohup npm run start:dev > "$backend_log" 2>&1 &
  disown
  BACKEND_PID=$!
  log "Backend starting (PID $BACKEND_PID) with LOAD_SEED_FILE=$seed_file, log=$backend_log"
  for i in $(seq 1 90); do
    if grep -q "Nest application successfully started" "$backend_log" 2>/dev/null; then
      log "Backend ready after ${i}s"
      sleep 1
      return 0
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      log "ERROR: backend process died during startup, see $backend_log"
      return 1
    fi
    sleep 1
  done
  log "ERROR: backend did not report ready within 90s"
  return 1
}

stop_backend() {
  if [ -n "${BACKEND_PID:-}" ]; then
    log "Stopping backend PID $BACKEND_PID"
    kill "$BACKEND_PID" 2>/dev/null || true
    sleep 2
  fi
  # Best-effort cleanup of any stray dev-server processes regardless of BACKEND_PID.
  pkill -f "nest start --watch" 2>/dev/null || true
  pkill -f "dist/main" 2>/dev/null || true
  sleep 1
}

reset_and_seed() {
  local seed_file="$1"
  local backend_log="$2"
  log "=== Reset + reseed with $seed_file ==="
  stop_backend
  cd "$REPO_ROOT"
  docker compose down -v >> "$LOG" 2>&1
  docker compose up postgres -d >> "$LOG" 2>&1
  if ! wait_postgres_healthy; then
    log "ERROR: postgres did not become healthy"
    return 1
  fi
  if ! start_backend "$seed_file" "$backend_log"; then
    return 1
  fi
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/health)
  log "Health check: $code"
  pedidos=$(docker exec cheapest-postgres psql -U postgres -d cheapest -t -c "SELECT count(*) FROM pedidos;" 2>/dev/null | tr -d ' ')
  log "Baseline pedidos count after reseed: $pedidos"
}

run_scenario() {
  local campaign_dir="$1"   # get_campaign | post_campaign
  local endpoint="$2"       # get | post
  local scenario="$3"
  local users="$4"
  local ramp_up="$5"
  local duration="$6"
  local reps="$7"
  local body_path="$8"      # empty string if no --body needed

  for run in $(seq 1 "$reps"); do
    local out_dir="$LT_DIR/results/$campaign_dir/$scenario/run$run"
    mkdir -p "$out_dir"
    log "--- $campaign_dir / $scenario / run $run (endpoint=$endpoint users=$users ramp_up=${ramp_up}s duration=${duration}s) ---"

    local cmd=("$VENV_PY" "$LT_DIR/load_test.py" \
      --endpoint "$endpoint" --users "$users" --ramp-up "$ramp_up" --duration "$duration" \
      --output-dir "$out_dir")
    if [ -n "$body_path" ]; then
      cmd+=(--body "$body_path")
    fi

    "${cmd[@]}" > "$out_dir/console.log" 2>&1
    rc=$?
    if [ $rc -ne 0 ]; then
      log "WARNING: run exited with code $rc, see $out_dir/console.log"
    fi
    tail -n 12 "$out_dir/console.log" | tee -a "$LOG" > /dev/null
    # brief pause between repetitions to let the server settle
    sleep 5
  done
}

run_campaign() {
  local campaign_dir="$1"
  local endpoint="$2"
  local body_path="$3"

  run_scenario "$campaign_dir" "$endpoint" "alta_carga"      1500  75  60 3 "$body_path"
  run_scenario "$campaign_dir" "$endpoint" "muy_alta_carga"  3000 100  60 3 "$body_path"
  run_scenario "$campaign_dir" "$endpoint" "estres"          7500 150  60 3 "$body_path"
  run_scenario "$campaign_dir" "$endpoint" "estres_fuerte"  18000 200  60 5 "$body_path"
}

main() {
  : > "$LOG"
  log "=========================================="
  log "FULL CAMPAIGN RUN STARTING"
  log "=========================================="

  # ---------------- GET campaign ----------------
  if ! reset_and_seed "load-seed-get.yaml" "$LT_DIR/backend_get_campaign.log"; then
    log "ABORT: could not prepare environment for GET campaign"
    exit 1
  fi
  log ">>> Starting GET campaign (14 runs) <<<"
  run_campaign "get_campaign" "get" ""
  log ">>> GET campaign done <<<"

  # ---------------- POST campaign ----------------
  if ! reset_and_seed "load-seed-post.yaml" "$LT_DIR/backend_post_campaign.log"; then
    log "ABORT: could not prepare environment for POST campaign"
    exit 1
  fi
  log "Regenerating sample_body.json against fresh POST-campaign seed"
  "$VENV_PY" "$LT_DIR/load_test.py" --make-sample-body "$LT_DIR/sample_body.json" >> "$LOG" 2>&1

  log ">>> Starting POST campaign (14 runs) <<<"
  run_campaign "post_campaign" "post" "$LT_DIR/sample_body.json"
  log ">>> POST campaign done <<<"

  log "Aggregating results table..."
  "$VENV_PY" "$LT_DIR/aggregate_results.py" | tee -a "$LOG"

  log "=========================================="
  log "FULL CAMPAIGN RUN COMPLETE"
  log "=========================================="
  touch "$LT_DIR/DONE"
}

main
