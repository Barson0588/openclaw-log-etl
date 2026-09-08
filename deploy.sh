#!/bin/bash
# 一键部署入口 — 实际脚本在 skills/deploy/scripts/deploy.sh
# 使用方式: ./deploy.sh root@<host>
exec bash "$(cd "$(dirname "$0")" && pwd)/skills/deploy/scripts/deploy.sh" "$@"
