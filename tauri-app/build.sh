#!/bin/bash
set -e
cd /Users/evanli/WorkBuddy/2026-07-28-22-33-31/cira-prototype/tauri-app
export PATH="$HOME/.cargo/bin:$PATH"
# 强制走可用代理 7897（覆盖失效的 57213 git 全局代理）
export HTTP_PROXY=http://127.0.0.1:7897/
export HTTPS_PROXY=http://127.0.0.1:7897/
export http_proxy=http://127.0.0.1:7897/
export https_proxy=http://127.0.0.1:7897/
# 若 cargo 触发 git 拉取，也走 7897 而非失效的 57213
export GIT_CONFIG_COUNT=2
export GIT_CONFIG_KEY_0=http.proxy
export GIT_CONFIG_VALUE_0=http://127.0.0.1:7897/
export GIT_CONFIG_KEY_1=https.proxy
export GIT_CONFIG_VALUE_1=http://127.0.0.1:7897/
./node_modules/.bin/tauri build 2>&1 | tail -80
