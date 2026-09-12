#!/bin/bash
# ============================================================
# 服务器 <-> GitHub 同步工具
# ============================================================
# 服务器仓库根 == GitHub 的 source-manager/ 子树
# 服务器 main 跟踪 origin/server-source-manager-sync
#
# 用法:
#   sync.sh pull          # 从 GitHub 拉取（直连，可能超时）
#   sync.sh pull-bundle   # 从 /tmp/srv-sync.bundle 拉取（推荐）
#   sync.sh status        # 查看同步状态
#   sync.sh push          # 推送服务器改动到 GitHub（需网络）
# ============================================================
set -e
cd /opt/ponyo-source-manager
BRANCH=server-source-manager-sync
BUNDLE=/tmp/srv-sync.bundle

case "$1" in
  pull)
    echo "=== 从 GitHub 拉取 $BRANCH ==="
    git fetch origin
    git merge --ff-only origin/$BRANCH
    echo "完成: $(git log --oneline -1)"
    ;;

  pull-bundle)
    if [ ! -f "$BUNDLE" ]; then
      echo "错误: 找不到 $BUNDLE"
      echo "请先在本地执行:"
      echo "  git subtree split --prefix=source-manager -b $BRANCH"
      echo "  git push origin $BRANCH"
      echo "  git bundle create srv-sync.bundle $BRANCH"
      echo "  scp srv-sync.bundle jie:/tmp/"
      exit 1
    fi
    echo "=== 从 bundle 拉取 ==="
    git fetch "$BUNDLE" "$BRANCH:refs/remotes/origin/$BRANCH"
    git merge --ff-only origin/$BRANCH
    echo "完成: $(git log --oneline -1)"
    ;;

  status)
    echo "=== 同步状态 ==="
    git status -sb | head -3
    echo ""
    echo "本地 HEAD:  $(git log --oneline -1)"
    echo "远程引用:   $(git log --oneline -1 origin/$BRANCH 2>/dev/null || echo '未获取')"
    echo ""
    echo "跟踪文件数: $(git ls-files | wc -l)"
    ;;

  push)
    echo "=== 推送服务器改动到 GitHub ==="
    if [ -n "$(git status --porcelain)" ]; then
      echo "错误: 工作区不干净，请先提交"
      exit 1
    fi
    git push origin HEAD:$BRANCH
    echo "完成"
    ;;

  *)
    echo "用法: $0 {pull|pull-bundle|status|push}"
    exit 1
    ;;
esac
