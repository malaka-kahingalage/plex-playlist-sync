#!/bin/bash
# Auto-sync local repo with remote GitHub (main branch)
# Usage: ./git_auto_sync.sh

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo "[AutoSync] Pulling latest changes from remote..."
git pull origin main --allow-unrelated-histories

if [ $? -ne 0 ]; then
  echo "[AutoSync] Pull failed. Resolve conflicts and try again."
  exit 1
fi

echo "[AutoSync] Adding all changes..."
git add .

CHANGES=$(git status --porcelain)
if [ -z "$CHANGES" ]; then
  echo "[AutoSync] No changes to commit."
else
  COMMIT_MSG="Auto-sync: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "[AutoSync] Committing changes: $COMMIT_MSG"
  git commit -m "$COMMIT_MSG"
fi

echo "[AutoSync] Pushing to remote..."
git push origin main

if [ $? -eq 0 ]; then
  echo "[AutoSync] Sync complete!"
else
  echo "[AutoSync] Push failed. Check your credentials or resolve conflicts."
fi
