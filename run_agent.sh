#!/usr/bin/env bash
# run_agent.sh "your question here"
# Runs the read-only campaign analyst agent in its own container. With no
# question given, analyst.py falls back to its own default ("what's
# trending right now"). Needs GEMINI_API_KEY in .env — see .env.example.
cd "$(dirname "$0")" || exit
docker compose --profile agent run --rm --build \
  agent python analyst.py "$@"
