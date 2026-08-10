#!/usr/bin/env bash
# Manual end-to-end smoke test for Phase D (transcript/evaluation delivery).
# Prereqs (each in its own terminal, or backgrounded):
#   1. docker compose -f infra/docker-compose.yml up -d
#   2. cd platform && npm run start:dev
#   3. cd ai-service && set -a && source .env && set +a && \
#        .venv/bin/uvicorn app.main:app --port 8000
#   4. cd ai-service && set -a && source .env && set +a && \
#        .venv/bin/python -m app.voice_agent.worker start
#
# This script only creates the session and prints the candidate join info —
# actually joining needs real audio (a browser mic, or livekit-cli's
# `lk room join --publish-demo`, see bottom of this file). Ending the call
# (either the candidate hanging up or POST /interviews/:id/end) is what
# triggers the shutdown callback that delivers the transcript to platform.

set -euo pipefail

API="http://localhost:4000/api/v1"

echo "== Logging in as seeded admin =="
TOKEN=$(curl -sf -X POST "$API/auth/login" \
  -H "content-type: application/json" \
  -d '{"email":"admin@hireos.local","password":"Password123!"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")

echo "== Creating interview session =="
SESSION=$(curl -sf -X POST "$API/interviews" \
  -H "content-type: application/json" -H "authorization: Bearer $TOKEN" \
  -d '{"candidateRef":"e2e-test-candidate"}')
echo "$SESSION" | python3 -m json.tool
SESSION_ID=$(echo "$SESSION" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
INVITE_URL=$(echo "$SESSION" | python3 -c "import sys,json;print(json.load(sys.stdin)['inviteUrl'])")

echo
echo "== Session created: $SESSION_ID =="
echo "Join with a real client (browser at hireOsFe, or livekit-cli — see below):"
echo "  $INVITE_URL"
echo
echo "Once you've joined and spoken a few turns, end the call by hanging up,"
echo "or force-end it now with:"
echo "  curl -X POST $API/interviews/$SESSION_ID/end -H \"authorization: Bearer $TOKEN\""
echo
echo "Then check platform's DB for the delivered transcript:"
echo "  cd platform && npx dotenv -e .env -- node -e \""
echo "    const {PrismaClient}=require('@prisma/client');"
echo "    const {PrismaPg}=require('@prisma/adapter-pg');"
echo "    const p=new PrismaClient({adapter:new PrismaPg({connectionString:process.env.DATABASE_URL})});"
echo "    p.interviewSummary.findUnique({where:{interviewSessionId:'$SESSION_ID'}})"
echo "      .then(r=>{console.log(r); return p.\\\$disconnect();});\""
echo
echo "== Headless join without a browser (optional) =="
echo "Install livekit-cli (curl -sSL https://get.livekit.io/cli | bash), then:"
echo "  lk room join --url <livekit-url-from-join-response> --api-key devkey \\"
echo "    --api-secret hireosdevsecret_do_not_use_in_prod --identity test-candidate \\"
echo "    --publish-demo <room-name>"
echo "(check 'lk room join --help' for current audio-publish flags on your installed version)"
