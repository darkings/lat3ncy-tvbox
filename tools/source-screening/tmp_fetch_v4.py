#!/usr/bin/env python3
"""批量下载用户提供的新 TVBox 配置（v4）。"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
OUT = "/tmp/tvbox_configs2"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 用户提供的配置（去重后）
CONFIGS = [
    ("宝盒", "http://宝盒接口.top"),
    ("快乐接口", "http://影视仓接口.top"),
    ("天微七星", "http://7337.kstore.space/qxys/禁止传播.json"),
    ("麒麟", "http://cdn.qiaoji8.com/tvbox.json"),
    ("玩偶gitee", "https://gitee.com/blssss/jk/raw/api/bls.json"),
    ("戏曲", "http://mzrjk.top/戏曲"),
    ("学习", "http://mzrjk.top/学习"),
    ("音乐", "http://mzrjk.top/音乐"),
    ("肥猫hello", "http://hello.肥猫.com"),
    ("蓝天gitee", "https://gitee.com/lukei7/lib/raw/Luck/%E8%87%AA%E5%BB%BA.json"),
    ("牛二凯速", "https://9280.kstore.space/wex.json"),
    ("科技长青", "https://upld.zone.id/uploads/q9iq9e5iq/tvboxlvse.json"),
    ("神秘哥哥", "https://play.iptv365.org/tvbox.txt"),
    ("环宇轩", "https://6492.kstore.space/xnf/xnf.json"),
    ("拾光趣乐屋ck", "http://xmbjm.fh4u.org/ck.txt"),
    ("拾光ck_github", "https://xmbjm.github.io/ck.json"),
    ("拾光ck_kstore", "https://4708.kstore.space/ck.json"),
    ("奇奇单仓", "http://z.qiqiv.cn/123"),
    ("潇洒单仓", "https://9877.kstore.space/FourDS/api.json"),
    ("开心单仓", "http://kxrj.site:55"),
    ("天微单仓", "https://qixing.myhkw.com/DC.txt"),
    ("拾光hollo", "https://4708.kstore.space/omg/hollo.json"),
    ("星辰fmbox", "https://fmbox.cc/"),
    (
        "分享moeyy",
        "https://github.moeyy.xyz/https://raw.githubusercontent.com/maoystv/6/main/000.json",
    ),
    ("小屋acwing", "https://git.acwing.com/shhentu/lzxw/-/raw/main/Monster.json"),
    (
        "影探",
        "https://ghp.ci/https://raw.githubusercontent.com/vbskycn/tvbox/a244f6f5c08565a9a0e319d6a3cc2e919d05d893/MY%E6%8E%A2%E6%8E%A2.txt",
    ),
    ("小米mpanso", "https://www.mpanso.com/%E5%B0%8F%E7%B1%B3/DEMO.json"),
    ("摸鱼com", "http://我不是.摸鱼儿.com"),
    ("开心2", "http://kxrj.site:55/天天开心"),
    ("喵影视meowtv", "http://meowtv.cn/tv"),
    ("挺好thdjk", "https://ztha.top/TVBox/thdjk.json"),
    ("龙一", "https://xn--qoqw77q.top/"),
    ("宝盒ghp", "https://ghp.ci/raw.githubusercontent.com/guot55/YGBH/main/vip2.json"),
    ("西夏", "https://2912.kstore.space/0506.json"),
    (
        "非凡1024",
        "https://g.3344550.xyz/https://raw.githubusercontent.com/jigedos/1024/master/jsm.json",
    ),
    (
        "海冰",
        "https://git.acwing.com/cisenyuan/kdsb/-/raw/main/%E6%B5%B7%E5%85%B5%E5%BD%B1%E8%A7%86.json",
    ),
    ("花生", "https://git.acwing.com/abai/tv/-/raw/main/huas.json"),
    ("刘伟", "https://git.acwing.com/lw0704/66/-/raw/master/jjzx.json"),
    ("超级", "https://git.acwing.com/203BDXC/tvboxt/-/raw/main/CJ.json"),
    ("剪影", "https://git.acwing.com/lkq0379/zjys/-/raw/main/zjys.json"),
    ("金鹰", "http://550.3vcn.work/wdjyys.json"),
    (
        "heroaku",
        "https://cdn.githubraw.com/xuexuguang/tvbox_spider/main/tv/kk/heroaku_dtes.json",
    ),
    ("短剧74", "http://74.120.175.78/JK/XYQTVBox/dj.json"),
    ("白龙", "http://124.71.189.194/a.json"),
    ("浪里小白龙", "http://39.101.135.137:8080"),
    ("影视仓Box", "https://jihulab.com/mengzhu2/ysc/-/raw/main/YSC.json"),
    ("优质100km", "https://100km.top/0"),
    ("天命人", "http://t.lkkk.love/02.json"),
    ("多仓陌尘", "http://天命.陌尘.icu"),
    ("潇洒la", "https://la.kstore.dev/download/2863/01.txt"),
    ("小虎斑弹幕", "https://hb.xyyh.online/tvbox/"),
    ("老虎laohu", "http://tv.laohu.cool/tvbox.json"),
    ("秦始皇", "https://秦始皇.xyz"),
    ("蓝色影视", "https://d.kstore.dev/download/4684/Xboxb.json"),
    ("教育bhjk", "https://jihulab.com/bhjk1/vip/-/raw/main/vip.json"),
    ("短剧ufuzi", "http://box.ufuzi.com/tv/qq/短剧频道/api.json"),
    ("少儿ymz", "https://jihulab.com/ymz1231/xymz/-/raw/main/ymshaoer"),
    ("饭太硬com", "http://www.饭太硬.com/tv"),
    ("牛二中文", "http://tvbox.王二小放牛娃.top"),
]


def to_ascii(url: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    try:
        host = parts.hostname.encode("idna").decode("ascii")
    except Exception:
        return url
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit(
        (parts.scheme, host + port, parts.path, parts.query, parts.fragment)
    )


def strip_json_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("//") or s.startswith("/*"):
            continue
        lines.append(line)
    return "\n".join(lines)


def extract_maccms(sites: list) -> list:
    out = []
    for s in sites:
        api = s.get("api") or ""
        if not api:
            continue
        if any(
            m in api
            for m in (
                "/api.php/provide/vod",
                "/provide/vod",
                "/inc/api.php",
                "seacmsapi",
                "api_mac10",
            )
        ):
            out.append({"name": s.get("name", "?"), "api": api, "type": s.get("type")})
    return out


def analyze(name: str, url: str, body: bytes):
    text = body.decode("utf-8-sig", errors="replace")
    j = None
    try:
        j = json.loads(strip_json_comments(text))
    except Exception:
        pass
    if j is not None:
        sites = j.get("sites") or []
        maccms = extract_maccms(sites)
        flag = ""
        if maccms:
            fn = f"{OUT}/{re.sub(r'[^a-zA-Z0-9]', '_', name)}_maccms.json"
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(maccms, f, ensure_ascii=False, indent=1)
            flag = f" maccms={len(maccms)} -> {fn}"
        urls_field = j.get("urls") or []
        multi = f" urls={len(urls_field)}" if urls_field else ""
        print(f"[{name}] JSON sites={len(sites)}{flag}{multi}")
        return j
    lines = [
        l.strip()
        for l in text.splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    if lines and all(l.startswith("http") for l in lines[:5]):
        print(f"[{name}] 多仓文本 {len(lines)} 行")
        for l in lines[:10]:
            print(f"    {l[:90]}")
        return {"_txt": lines}
    head = text[:100].replace("\n", " ")
    print(f"[{name}] 非JSON size={len(body)} head={head}")
    return None


results = {}
for name, url in CONFIGS:
    try:
        req = urllib.request.Request(to_ascii(url), headers=UA)
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read(800 * 1024)
        j = analyze(name, url, body)
        if j:
            results[name] = {"url": url, "j": j}
    except urllib.error.HTTPError as e:
        print(f"[{name}] HTTP {e.code}")
    except Exception as e:
        print(f"[{name}] {type(e).__name__}: {str(e)[:70]}")

with open("/tmp/tvbox_configs2/summary.json", "w", encoding="utf-8") as f:
    json.dump(
        {k: v["url"] for k, v in results.items()}, f, ensure_ascii=False, indent=1
    )
