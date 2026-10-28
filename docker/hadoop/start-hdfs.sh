#!/usr/bin/env bash
set -euo pipefail
if [ "$1" = "namenode" ]; then
  if [ ! -f /hadoop/dfs/name/current/VERSION ]; then
    hdfs namenode -format -nonInteractive
  fi
  exec hdfs namenode
fi
exec hdfs datanode
