#!/usr/bin/env python3
"""GitHub 特征搜索：README 含 api.php/provide/vod 的最新仓库 → 提取 maccms。"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "ponyo-discovery", "Accept": "application/vnd.github+json"}


def gh_get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read())


def fetch(url, timeout=20):
    """经 jsdelivr 下载（服务器直连 raw.githubusercontent.com 会 SYN-SENT 挂起）。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_repo_file(fn, branch, path):
    """优先 jsdelivr，失败退 gh-proxy。"""
    for base in (
        f"https://cdn.jsdelivr.net/gh/{fn}@{branch}/{path}",
        f"https://gh-proxy.com/https://raw.githubusercontent.com/{fn}/{branch}/{path}",
    ):
        try:
            return fetch(base, timeout=15)
        except Exception:
            continue
    raise RuntimeError(f"{fn} {branch} {path} 下载失败")


def extract_maccms_from_text(text):
    """从文本提取 maccms API 地址（含 URL 编码的）。"""
    found = []
    # 常见形式
    pats = [
        r'https?://[a-zA-Z0-9._-]+(?::\d+)?/[^\s"\'\'<>]*?(?:api\.php/provide/vod|provide/vod|inc/api\.php|api_mac10)[^\s"\'\'<>]*',
        r'(?<![\w.])[a-zA-Z0-9-]+\.[a-zA-Z]{2,}[^\s"\'\'<>]*?(?:api\.php/provide/vod|provide/vod|inc/api\.php|api_mac10)[^\s"\'\'<>]*',
    ]
    for p in pats:
        for m in re.finditer(p, text):
            u = m.group(0).rstrip(".,;)'\"")
            # 解码常见转义
            u = u.replace("\\/", "/")
            if not u.startswith("http"):
                u = "http://" + u
            found.append(u)
    return found


# 1. 搜索最新仓库
queries = [
    '"api.php/provide/vod" in:readme archived:false sort:updated',
    '"provide/vod" in:readme maccms archived:false sort:updated',
]
repos = []
for q in queries:
    params = urllib.parse.urlencode({"q": q, "per_page": 20})
    try:
        d = gh_get(f"https://api.github.com/search/repositories?{params}")
        repos.extend(d.get("items", []))
        print(f"查询 [{q[:50]}] → {d.get('total_count')} 个仓库")
    except Exception as e:
        print(f"查询失败: {e}")
    time.sleep(7)  # 限流 10/min

# 去重
seen = set()
uniq_repos = []
for it in repos:
    fn = it["full_name"]
    if fn not in seen:
        seen.add(fn)
        uniq_repos.append(it)
print(f"去重后仓库: {len(uniq_repos)}")

# 2. 每个仓库：下载 README + 常见配置文件，提取 maccms
all_maccms = {}
for it in uniq_repos[:15]:
    fn = it["full_name"]
    default_branch = it.get("default_branch", "master")
    desc = (it.get("description") or "")[:40]
    print(f"\n== {fn} ({desc}) ==")
    texts = []
    # README
    for br in (default_branch, "main", "master"):
        try:
            body = fetch_repo_file(fn, br, "README.md")
            texts.append(body.decode("utf-8", errors="replace"))
            print(f"  README {len(body)}B", flush=True)
            break
        except Exception:
            continue
    # 常见配置路径
    for path in (
        "tv.json",
        "config.json",
        "jsm.json",
        "json/config.json",
        "box.json",
        "api.json",
    ):
        for path in (
            "tv.json",
            "config.json",
            "jsm.json",
            "json/config.json",
            "box.json",
            "api.json",
        ):
            for br in (default_branch, "main", "master"):
                try:
                    body = fetch_repo_file(fn, br, path)
                    texts.append(body.decode("utf-8", errors="replace"))
                    print(f"  {path} {len(body)}B", flush=True)
                    break
                except Exception:
                    continue
    for t in texts:
        for u in extract_maccms_from_text(t):
            host = re.sub(r"^https?://", "", u).split("/")[0].lower()
            if host.startswith("www."):
                host = host[4:]
            host = host.split(":")[0]
            if host not in all_maccms:
                all_maccms[host] = {"api": u, "repo": fn}
    time.sleep(2)

print(f"\n== 提取 maccms host: {len(all_maccms)} ==")
for h, v in sorted(all_maccms.items()):
    print(f"  {h:<32} {v['api'][:70]}  [{v['repo']}]")

with open("/tmp/gh_feature_maccms.json", "w", encoding="utf-8") as f:
    json.dump(all_maccms, f, ensure_ascii=False, indent=1)
