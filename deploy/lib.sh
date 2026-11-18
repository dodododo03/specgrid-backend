#!/bin/bash
# Shared helpers for deploy/*.sh (sourced, not run).

# env_get KEY [default] -> value of KEY from ./.env (last occurrence, surrounding quotes removed).
# Reads one key instead of sourcing the file, so values with spaces or [] can't break the shell.
env_get() {
  local value
  value=$(grep -E "^$1=" .env 2>/dev/null | tail -n 1 | cut -d= -f2-)
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "${value:-${2:-}}"
}
