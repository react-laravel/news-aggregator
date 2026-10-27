#!/usr/bin/env bash
set -euo pipefail
: "${NEWS_B_SSH_KEY:?Missing News-scoped deployment key}"
: "${NEWS_B_KNOWN_HOSTS:?Missing pinned B host key}"
: "${GITHUB_SHA:?Missing revision}"
[[ "$GITHUB_SHA" =~ ^[0-9a-f]{40}$ ]]
task_dir=$(mktemp -d "${RUNNER_TEMP:-/tmp}/news-deploy.XXXXXXXX")
trap 'rm -rf -- "$task_dir"' EXIT
umask 077
printf '%s\n' "$NEWS_B_SSH_KEY" > "$task_dir/key"
printf '%s\n' "$NEWS_B_KNOWN_HOSTS" > "$task_dir/known_hosts"
unset NEWS_B_SSH_KEY NEWS_B_KNOWN_HOSTS
args=(-i "$task_dir/key" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$task_dir/known_hosts" -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -T news-deploy@154.21.197.138)
ssh "${args[@]}" "receive $GITHUB_SHA" < news-runtime.tar.gz
ssh "${args[@]}" "publish $GITHUB_SHA"
ssh "${args[@]}" "validate $GITHUB_SHA"
