/**
 * 影视TV 弹幕支持
 * https://t.me/fongmi_offical/
 * https://github.com/FongMi/Release/tree/main/apk
 * Cookie设置
 * Cookie获取方法 https://ghproxy.net/https://raw.githubusercontent.com/UndCover/PyramidStore/main/list.md
 * Cookie设置方法1: DR-PY 后台管理界面
 * CMS后台管理 > 设置中心 > 环境变量 > {"bili_cookie":"XXXXXXX","vmid":"XXXXXX"} > 保存
 * Cookie设置方法2: 手动替换Cookie
 * 底下代码 headers的
 * "Cookie":"$bili_cookie"
 * 手动替换为
 * "Cookie":"将获取的Cookie黏贴在这"
 * 客户端长期Cookie设置教程:
 * 抓包哔哩手机端搜索access_key,取任意链接里的access_key和appkey在drpy环境变量中增加同名的环境变量即可
 * 此时哔哩.js这个解析可用于此源的解析线路用
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 0,
  title: '哔哩影视[官]',
  lang: 'ds'
  })
 */
// === ENV compatibility shim (injected by ponyo-source-manager) ===
// App QuickJS sandbox only defines globalThis.env = {} without ENV object.
// Standard drpyS rules call ENV.get('xxx') which throws ReferenceError.
// This shim provides the standard drpyS ENV interface backed by globalThis.env.
if (typeof ENV === 'undefined') {
    globalThis.ENV = {
        get: function (k, d) {
            var v = globalThis.env && globalThis.env[k];
            return (v === undefined || v === null) ? (d === undefined ? '' : d) : v;
        },
        put: function (k, v) {
            if (!globalThis.env) globalThis.env = {};
            globalThis.env[k] = v;
        },
        keys: function () {
            return globalThis.env ? Object.keys(globalThis.env) : [];
        }
    };
}
// === end ENV shim ===
var rule = {
    title: '哔哩影视[官]',
    host: 'https://api.bilibili.com',
    url: '/fyclass-fypage&vmid=$vmid',
    detailUrl: '/pgc/view/web/season?season_id=fyid',
    filter_url: 'fl={{fl}}',
    vmid获取教程: '登录后访问https://api.bilibili.com/x/web-interface/nav,搜索mid就是,cookie需要 bili_jct,DedeUserID,SESSDATA参数',
    searchUrl: '/x/web-interface/search/type?keyword=**&page=fypage&search_type=',
    searchable: 1,
    filterable: 1,
    quickSearch: 0,
    headers: {
        'User-Agent': 'PC_UA',
        "Referer": "https://www.bilibili.com",
        // "Cookie": "$bili_cookie"
    },
    tab_order: ['bilibili', 'B站'],//线路顺序,按里面的顺序优先，没写的依次排后面
    timeout: 5000,
    class_name: '番剧&国创&电影&电视剧&纪录片&综艺&全部&追番&追剧&时间表',
    class_url: '1&4&2&5&3&7&全部&追番&追剧&时间表',
    filter: 'H4sIAAAAAAAAA7VSy0rDQBT9lwF3FbRqhW79DAkSaBaiptC0gpRAQfuIosXS2GC6UBBaLGoKUcxLfyZ3MvkLJ2bsJGTt8p5z751zzp02gu48Pp+j6n4bHUlnqIqahzVUQrJ4ItECBr1o6dH6VDxuSb9dMoUj/Rm0WQLTYhOppRQGM4CByeDtFRyN3yFYMrichcmsx/fsrBjyakGgR1qfMVt8xvOJ5jJ4F6lCQqS6642a1ODK8c0I3GFBOR694PEX1q24PywowqaN7yw8+YgnNiM3ODntxAuDvF3QTAoWwXfA0XNreSzkO4imV6HrUr7gCPxOoin7Jg8i/LzExkOOrORMK5Ko1OUDpSk2Wwo3H3oGsZ2CeXbrdNF65m7da9ae0823JCmtlfcqfOJpFvr3cGv8JZGygiqUUCqXPP7Tp6JvqD/Bcj8itwIAAA==',
    play_parse: true,
    pagecount: {"1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "7": 1, "时间表": 1},
    limit: 5,
    推荐: async function () {
        return await home_video();
    },
    预处理: async function () {
        rule.headers.Cookie = ENV.get('bili_cookie');
        try {
            let json = await request('https://api.bilibili.com/x/web-interface/nav');
            json = JSON.parse(json);
            let mid = json.data.mid;
            log('mid:', mid);
            if (mid) {
                rule.url = rule.url.replace('$vmid', mid);
            }
        } catch (e) {
            log('预处理获取vmid错误:', e.message);
        }
    },
    一级: async function () {
        let {input, MY_CATE, MY_PAGE, MY_FL} = this;
        rule.headers.Cookie = ENV.get('bili_cookie');
        let d = [];
        let vmid = input.split("vmid=")[1].split("&")[0];

        async function get_zhui(pg, mode) {
            let url = "https://api.bilibili.com/x/space/bangumi/follow/list?type=" + mode + "&follow_status=0&pn=" + pg + "&ps=10&vmid=" + vmid;
            return get_result(url)
        }

        async function get_all(tid, pg, order, season_status) {
            let url = "https://api.bilibili.com/pgc/season/index/result?order=" + order + "&pagesize=20&type=1&season_type=" + tid + "&page=" + pg + "&season_status=" + season_status;
            return get_result(url)
        }

        async function get_timeline(tid, pg) {
            let videos = [];
            let url = "https://api.bilibili.com/pgc/web/timeline/v2?season_type=" + tid + "&day_before=2&day_after=4";
            let html = await request(url);
            let jo = JSON.parse(html);
            if (jo["code"] === 0) {
                let videos1 = [];
                let vodList = jo.result.latest;
                vodList.forEach(function (vod) {
                    let aid = (vod["season_id"] + "").trim();
                    let title = vod["title"].trim();
                    let img = vod["cover"].trim();
                    let remark = vod["pub_index"] + "　" + vod["follows"].replace("系列", "");
                    videos1.push({vod_id: aid, vod_name: title, vod_pic: img, vod_remarks: remark})
                });
                let videos2 = [];
                for (let i = 0; i < 7; i++) {
                    let vodList = jo["result"]["timeline"][i]["episodes"];
                    vodList.forEach(function (vod) {
                        if (vod["published"] + "" === "0") {
                            let aid = (vod["season_id"] + "").trim();
                            let title = vod["title"].trim();
                            let img = vod["cover"].trim();
                            let date = vod["pub_ts"];
                            let remark = date + "   " + vod["pub_index"];
                            videos2.push({vod_id: aid, vod_name: title, vod_pic: img, vod_remarks: remark})
                        }
                    })
                }
                videos = videos2.concat(videos1)
            }
            return videos
        }

        async function cate_filter(d, cookie) {
            if (MY_CATE === "1") {
                return get_rank(MY_CATE, MY_PAGE)
            } else if (["2", "3", "4", "5", "7"].includes(MY_CATE)) {
                return get_rank2(MY_CATE, MY_PAGE)
            } else if (MY_CATE === "全部") {
                let tid = MY_FL.tid || "1";
                let order = MY_FL.order || "2";
                let season_status = MY_FL.season_status || "-1";
                return get_all(tid, MY_PAGE, order, season_status)
            } else if (MY_CATE === "追番") {
                return get_zhui(MY_PAGE, 1)
            } else if (MY_CATE === "追剧") {
                return get_zhui(MY_PAGE, 2)
            } else if (MY_CATE === "时间表") {
                let tid = MY_FL.tid || "1";
                return get_timeline(tid, MY_PAGE)
            } else {
                return []
            }
        }

        return await cate_filter()

    },
    二级: async function () {
        let {input} = this;

        function zh(num) {
            let p = "";
            if (Number(num) > 1e8) {
                p = (num / 1e8).toFixed(2) + "亿"
            } else if (Number(num) > 1e4) {
                p = (num / 1e4).toFixed(2) + "万"
            } else {
                p = num
            }
            return p
        }

        let html = await request(input);
        let jo = JSON.parse(html).result;
        let id = jo["season_id"];
        let title = jo["title"];
        let pic = jo["cover"];
        let areas = jo["areas"][0]["name"];
        let typeName = jo["share_sub_title"];
        let date = jo["publish"]["pub_time"].substr(0, 4);
        let dec = jo["evaluate"];
        let remark = jo["new_ep"]["desc"];
        let stat = jo["stat"];
        let status = "弹幕: " + zh(stat["danmakus"]) + "　点赞: " + zh(stat["likes"]) + "　投币: " + zh(stat["coins"]) + "　追番追剧: " + zh(stat["favorites"]);
        let score = jo.hasOwnProperty("rating") ? "评分: " + jo["rating"]["score"] + "　" + jo["subtitle"] : "暂无评分" + "　" + jo["subtitle"];
        let vod = {
            vod_id: id,
            vod_name: title,
            vod_pic: pic,
            type_name: typeName,
            vod_year: date,
            vod_area: areas,
            vod_remarks: remark,
            vod_actor: status,
            vod_director: score,
            vod_content: dec
        };
        let ja = jo["episodes"];
        let playurls1 = [];
        let playurls2 = [];
        ja.forEach(function (tmpJo) {
            let eid = tmpJo["id"];
            let cid = tmpJo["cid"];
            let link = tmpJo["link"];
            let part = tmpJo["title"].replace("#", "-") + " " + tmpJo["long_title"];
            playurls1.push(part + "$" + eid + "_" + cid);
            playurls2.push(part + "$" + link)
        });
        // 播放地址顺序与 vod_play_from 对应：bilibili 线路（link）在前，B站线路（eid_cid）在后
        let playUrl = playurls2.join("#") + "$$$" + playurls1.join("#");
        // 线路顺序：bilibili（jx:1 服务器采集站直连，全类型可用）在前为默认线路；
        // B站（官方 playurl API，大会员内容需 bili_cookie）退居第二。
        // 注意：App 端按 vod_play_from 的 $$$ 顺序取默认线路，不解析 tab_order。
        vod["vod_play_from"] = "bilibili$$$B站";
        vod["vod_play_url"] = playUrl;
        return vod
    },

    搜索: async function () {
        let {input, KEY, publicUrl} = this;
        let url1 = input + "media_bangumi";
        let url2 = input + "media_ft";
        rule.headers.Cookie = ENV.get('bili_cookie');
        // === ponyo patch: buvid 预热（B站 412 风控需要 buvid3/buvid4 cookie） ===
        try {
            if (typeof _fetch === 'function' && !(rule.headers.Cookie && rule.headers.Cookie.indexOf('buvid3') >= 0)) {
                let warm = _fetch('https://www.bilibili.com/', {headers: {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', 'Referer': 'https://www.bilibili.com/'}});
                let sc = '';
                try { sc = warm.headers['set-cookie'] || ''; } catch (e) { sc = ''; }
                if (Array.isArray(sc)) sc = sc.join('; ');  // 多值 set-cookie 是数组
                if (sc && sc.indexOf) {
                    let buvid3 = (sc.match(/buvid3=([^;]+)/) || [])[1] || '';
                    let buvid4 = (sc.match(/buvid4=([^;]+)/) || [])[1] || '';
                    let bnut = (sc.match(/b_nut=([^;]+)/) || [])[1] || '';
                    let parts = [];
                    if (buvid3) parts.push('buvid3=' + buvid3);
                    if (buvid4) parts.push('buvid4=' + buvid4);
                    if (bnut) parts.push('b_nut=' + bnut);
                    if (parts.length) {
                        rule.headers.Cookie = (rule.headers.Cookie ? rule.headers.Cookie + '; ' : '') + parts.join('; ');
                        log('bili buvid warm ok: ' + parts.join(',').substring(0, 40));
                    }
                }
            }
        } catch (e) { log('bili buvid warm fail: ' + (e && e.message || e)); }
        // === end ponyo patch ===
        // === ponyo patch: bangumi 请求防护 + 412 重试（最多 3 次，每次重新预热 buvid） ===
        let jRoot1 = null;
        let msg = null;
        for (let attempt1 = 0; attempt1 < 3; attempt1++) {
            let html = await request(url1);
            try {
                jRoot1 = JSON.parse(html);
                break;
            } catch (e) {
                log('bili bangumi parse fail attempt=' + attempt1 + ': ' + (e && e.message || e));
                jRoot1 = null;
                if (attempt1 < 2) {
                    try {
                        let warmR = _fetch('https://www.bilibili.com/', {headers: {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', 'Referer': 'https://www.bilibili.com/'}});
                        let scR = '';
                        try { scR = warmR.headers['set-cookie'] || ''; } catch (eR) { scR = ''; }
                        if (Array.isArray(scR)) scR = scR.join('; ');
                        if (scR) {
                            let b3R = (scR.match(/buvid3=([^;]+)/) || [])[1] || '';
                            let bnR = (scR.match(/b_nut=([^;]+)/) || [])[1] || '';
                            let pR = [];
                            if (b3R) pR.push('buvid3=' + b3R);
                            if (bnR) pR.push('b_nut=' + bnR);
                            if (pR.length) rule.headers.Cookie = (ENV.get('bili_cookie') ? ENV.get('bili_cookie') + '; ' : '') + pR.join('; ');
                        }
                    } catch (eR) { log('bili re-warm fail: ' + (eR && eR.message || eR)); }
                }
            }
        }
        if (jRoot1 === null) {
            return [{vod_name: KEY, vod_id: 'no_data', vod_remarks: 'B站风控拦截,稍后再试', vod_pic: urljoin(publicUrl, './images/404.jpg')}];
        }
        // === ponyo patch: B站 API 成功时 message="OK"（旧规则误判为失败），改用 code 判断 ===
        msg = jRoot1.code !== 0 ? (jRoot1.message || 'error') : null;
        let VODS = [];
        if (msg !== null) {
        // === end ponyo patch ===
            VODS = [{
                vod_name: KEY + "➢" + msg,
                vod_id: "no_data",
                vod_remarks: "别点,缺少bili_cookie",
                vod_pic: urljoin(publicUrl, './images/404.jpg'),
            }];
            return VODS;
        } else {
            let jo1 = jRoot1.data;
            // === ponyo patch: media_ft 响应解析防护 + 412 重试（B站风控瞬时波动） ===
            let jo2 = {numResults: 0, result: []};
            for (let attempt = 0; attempt < 2; attempt++) {
                html = await request(url2);
                try {
                    let jRoot2 = JSON.parse(html);
                    if (jRoot2.code === 0 && jRoot2.data) { jo2 = jRoot2.data; break; }
                    log('bili media_ft code=' + jRoot2.code + ' attempt=' + attempt);
                } catch (e) {
                    log('bili media_ft parse fail attempt=' + attempt + ': ' + (e && e.message || e));
                }
                if (attempt === 0) {
                    // 重试前重新预热 buvid（换新 cookie 提高成功率）
                    try {
                        let warm2 = _fetch('https://www.bilibili.com/', {headers: {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', 'Referer': 'https://www.bilibili.com/'}});
                        let sc2 = '';
                        try { sc2 = warm2.headers['set-cookie'] || ''; } catch (e2) { sc2 = ''; }
                        if (Array.isArray(sc2)) sc2 = sc2.join('; ');
                        if (sc2) {
                            let b3 = (sc2.match(/buvid3=([^;]+)/) || [])[1] || '';
                            let bn = (sc2.match(/b_nut=([^;]+)/) || [])[1] || '';
                            let p2 = [];
                            if (b3) p2.push('buvid3=' + b3);
                            if (bn) p2.push('b_nut=' + bn);
                            if (p2.length) rule.headers.Cookie = (ENV.get('bili_cookie') ? ENV.get('bili_cookie') + '; ' : '') + p2.join('; ');
                        }
                    } catch (e2) { log('bili re-warm fail: ' + (e2 && e2.message || e2)); }
                }
            }
            // === end ponyo patch ===
            let videos = [];
            let vodList = [];
            if (jo1["numResults"] === 0) {
                vodList = jo2["result"]
            } else if (jo2["numResults"] === 0) {
                vodList = jo1["result"]
            } else {
                vodList = jo1["result"].concat(jo2["result"])
            }
            vodList.forEach(function (vod) {
                let aid = (vod["season_id"] + "").trim();
                let title = KEY + "➢" + vod["title"].trim().replace('<em class="keyword">', "").replace("</em>", "");
                let img = vod["cover"].trim();
                let remark = vod["index_show"];
                videos.push({vod_id: aid, vod_name: title, vod_pic: img, vod_remarks: remark})
            });
            VODS = videos;
        }
        return VODS
    },
    lazy: async function () {
        let {input} = this;
        if (/^http/.test(input)) {
            input = {
                jx: 1,
                url: input,
                parse: 0,
                header: JSON.stringify({
                    "user-agent": "Mozilla/5.0"
                })
            }
        } else {
            let ids = input.split("_");
            let dan = 'https://api.bilibili.com/x/v1/dm/list.so?oid=' + ids[1];
            let result = {};
            let url = "https://api.bilibili.com/pgc/player/web/playurl?qn=116&ep_id=" + ids[0] + "&cid=" + ids[1];
            rule.headers.Cookie = ENV.get('bili_cookie');
            let html = await request(url);
            let jRoot = JSON.parse(html);
            if (jRoot["message"] !== "success") {
                log("需要大会员权限才能观看");
                input = ""
            } else {
                let jo = jRoot["result"];
                let ja = jo["durl"];
                let maxSize = -1;
                let position = -1;
                ja.forEach(function (tmpJo, i) {
                    if (maxSize < Number(tmpJo["size"])) {
                        maxSize = Number(tmpJo["size"]);
                        position = i
                    }
                });
                let url = "";
                if (ja.length > 0) {
                    if (position === -1) {
                        position = 0
                    }
                    url = ja[position]["url"]
                }
                result["parse"] = 0;
                result["playUrl"] = "";
                result["url"] = url;
                result["header"] = {
                    Referer: "https://www.bilibili.com",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
                };
                if (rule.headers.Cookie) {
                    result["header"]["Cookie"] = rule.headers.Cookie
                }
                result["contentType"] = "video/x-flv";
                result["danmaku"] = dan;
                input = result
            }
        }
        return input
    }
}

async function get_result(url) {
    let videos = [];
    let html = await request(url);
    let jo = JSON.parse(html);
    if (jo["code"] === 0) {
        let vodList = jo.result ? jo.result.list : jo.data.list;
        vodList.forEach(function (vod) {
            let aid = (vod["season_id"] + "").trim();
            let title = vod["title"].trim();
            let img = vod["cover"].trim();
            let remark = vod.new_ep ? vod["new_ep"]["index_show"] : vod["index_show"];
            videos.push({vod_id: aid, vod_name: title, vod_pic: img, vod_remarks: remark})
        })
    }
    return videos
}

async function get_rank(tid, pg) {
    return get_result("https://api.bilibili.com/pgc/web/rank/list?season_type=" + tid + "&pagesize=20&page=" + pg + "&day=3")
}

async function get_rank2(tid, pg) {
    return get_result("https://api.bilibili.com/pgc/season/rank/web/list?season_type=" + tid + "&pagesize=20&page=" + pg + "&day=3")
}

async function home_video() {
    let videos = (await get_rank(1)).slice(0, 5);
    for (const i of [4, 2, 5, 3, 7]) {
        videos = videos.concat((await get_rank2(i)).slice(0, 5))
    }
    return videos
}

