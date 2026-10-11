#!/bin/sh
# GIT_ASKPASS helper template — never hardcode tokens anywhere else.
# Usage:  chmod +x gh-askpass.sh
#         export GIT_ASKPASS=$PWD/tools/gh-askpass.sh
#         export GH_TOKEN_PATH=/home/z/.gh-token-pltown   # sin's token location
# git will call this with "Username for ..." / "Password for ..." prompts.
case "$1" in
  *[Uu]sername*) echo "wsxiaolin" ;;
  *) cat "${GH_TOKEN_PATH:-/home/z/.gh-token-pltown}" ;;
esac
