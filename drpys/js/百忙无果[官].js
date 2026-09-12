/*
@header({
  searchable: 2,
  filterable: 1,
  quickSearch: 0,
  title: '百忙无果[官]',
  lang: 'ds'
})
*/
function getMangoFilter(cid) {
    let configs = {
        "1": [
            ["kind", "类型", [["全部", "a1"], ["音乐", "8"], ["推理", "3075"], ["生活", "9"], ["情感", "7"], ["旅游", "170"], ["文化", "3143"], ["美食", "3011"], ["语言", "3152"], ["亲子", "179"], ["游戏", "3144"], ["演唱会", "4"], ["竞技", "174"], ["表演", "180"]]],
            ["chargeInfo", "资费", [["全部", "a1"], ["免费", "b1"], ["VIP", "b2"]]],
            ["sort", "排序", [["最热", "c2"], ["最新", "c1"]]]
        ],
        "2": [
            ["kind", "类型", [["全部", "a1"], ["爱情", "3094"], ["都市", "3093"], ["青春", "3003"], ["奇幻", "3092"], ["军旅", "3091"], ["武侠", "3090"], ["古装", "148"], ["科幻", "3088"], ["竞技", "3087"], ["传奇", "3086"], ["家庭", "3007"], ["历史", "3085"], ["仙侠", "3084"], ["喜剧", "3005"], ["革命", "3083"], ["悬疑", "3002"], ["民国", "3153"], ["现实", "3082"], ["乡村", "3010"], ["权谋", "3080"], ["商战", "3078"], ["逆袭", "3077"], ["年代剧", "3116"], ["神话", "3076"]]],
            ["area", "地区", [["全部", "a1"], ["内地", "10"], ["港台", "12"], ["泰国", "193"]]],
            ["year", "年份", [["全部", "all"], ["2026", "2026"], ["2025", "2025"], ["2024", "2024"], ["2023", "2023"], ["2022", "2022"], ["2021", "2021"], ["2020", "2020"], ["2019", "2019"], ["2018", "2018"], ["2017", "2017"], ["2016", "2016"], ["2015", "2015"], ["2010-2014", "2014t2010"], ["2000-2009", "2009t2000"], ["90年代", "1990s"], ["更早", "1989e"]]],
            ["feature", "状态", [["全部", "all"], ["已完结", "0"]]],
            ["chargeInfo", "资费", [["全部", "a1"], ["免费", "b1"], ["VIP", "b2"]]],
            ["sort", "排序", [["最热", "c2"], ["最新", "c1"]]]
        ],
        "3": [
            ["kind", "类型", [["全部", "a1"], ["爱情", "175"], ["喜剧", "176"], ["青春", "39"], ["奇幻", "3027"], ["剧情", "3028"], ["国漫", "3096"], ["科幻", "178"], ["动作", "177"], ["励志", "34"], ["历史", "46"], ["古装", "35"], ["家庭", "36"], ["战争", "44"], ["犯罪", "3097"], ["悬疑", "3029"], ["经典", "3098"], ["冒险", "3099"], ["灾难", "3100"]]],
            ["edition", "片种", [["全部", "a1"], ["院线大片", "182"], ["独播影院", "183"]]],
            ["area", "地区", [["全部", "a1"], ["内地", "27"], ["中国香港", "3036"], ["欧美", "3073"], ["其他", "other"]]],
            ["year", "年份", [["全部", "all"], ["2026", "2026"], ["2025", "2025"], ["2024", "2024"], ["2023", "2023"], ["2022", "2022"], ["2021", "2021"], ["2020", "2020"], ["2019", "2019"], ["2018", "2018"], ["2017", "2017"], ["2016", "2016"], ["2015", "2015"], ["2010-2014", "2014t2010"], ["2000-2009", "2009t2000"], ["90年代", "1990s"], ["更早", "1989e"]]],
            ["chargeInfo", "资费", [["全部", "a1"], ["免费", "b1"], ["VIP", "b2"], ["VIP用券", "b3"], ["付费点播", "b4"]]],
            ["sort", "排序", [["最热", "c2"], ["最新", "c1"]]]
        ],
        "50": [
            ["kind", "类型", [["全部", "a1"], ["恋爱", "84"], ["冒险", "87"], ["魔法", "64"], ["青春", "63"], ["搞笑", "62"], ["玄幻", "3150"], ["武侠", "195"], ["科幻", "90"], ["经典", "71"], ["特摄", "66"], ["悬疑", "3112"]]],
            ["area", "地区", [["全部", "a1"], ["内地", "52"], ["欧美", "53"], ["其他", "55"]]],
            ["edition", "版本", [["全部", "a1"], ["TV版", "57"], ["剧场版", "165"], ["真人版", "167"], ["其他", "58"]]],
            ["sort", "排序", [["最新", "c1"], ["最热", "c2"]]]
        ],
        "51": [
            ["kind", "类型", [["全部", "a1"], ["文化", "98"], ["励志", "99"], ["历史", "100"], ["生活", "97"], ["乡村", "3147"], ["职业", "3148"], ["青春", "3149"], ["旅游", "103"], ["科普", "3146"], ["军事", "101"], ["运动", "104"], ["动物", "3026"]]],
            ["sort", "排序", [["最新", "c1"], ["最热", "c2"]]]
        ],
        "115": [
            ["kind", "类型", [["全部", "a1"], ["幼儿", "134"], ["小学", "135"], ["初中", "136"], ["高中", "137"], ["科普", "138"], ["兴趣", "139"], ["育儿", "140"], ["实用", "141"], ["外语", "143"], ["公开课", "144"], ["其他", "145"]]],
            ["sort", "排序", [["最热", "c2"], ["最新", "c1"]]],
            ["chargeInfo", "资费", [["全部", "a1"], ["免费", "b1"], ["VIP", "b2"], ["付费", "b4"]]]
        ],
        "10": [
            ["kind", "类型", [["全部", "a1"], ["儿歌", "184"], ["冒险", "87"], ["益智", "83"], ["魔法", "3103"], ["机甲", "3104"], ["经典", "95"], ["竞技", "88"], ["搞笑", "62"], ["励志", "194"], ["科幻", "90"], ["早教", "3101"]]],
            ["fitAge", "年龄", [["全部", "a1"], ["0-3岁", "74"], ["4-6岁", "75"], ["7-10岁", "76"], ["11-14岁", "77"]]],
            ["sort", "排序", [["最新", "c1"], ["最热", "c2"]]]
        ]
    };
    if (configs[cid]) {
        return configs[cid].map(function(group) {
            return {
                key: group[0],
                name: group[1],
                value: group[2].map(function(item) { return {n: item[0], v: item[1]}; })
            };
        });
    }
    return [{
        "key": "chargeInfo",
        "name": "付费类型",
        "value": [{
                "n": "全部",
                "v": "all"
            },
            {
                "n": "免费",
                "v": "b1"
            },
            {
                "n": "vip",
                "v": "b2"
            },
            {
                "n": "VIP用券",
                "v": "b3"
            },
            {
                "n": "付费点播",
                "v": "b4"
            }
        ]
    }, {
        "key": "sort",
        "name": "排序",
        "value": [{
                "n": "最新",
                "v": "c1"
            },
            {
                "n": "最热",
                "v": "c2"
            },
            {
                "n": "知乎高分",
                "v": "c4"
            }
        ]
    }, {
        "key": "year",
        "name": "年代",
        "value": [{
                "n": "全部",
                "v": "all"
            },
            {
                "n": "2026",
                "v": "2026"
            },
            {
                "n": "2025",
                "v": "2025"
            },
            {
                "n": "2024",
                "v": "2024"
            },
            {
                "n": "2023",
                "v": "2023"
            },
            {
                "n": "2022",
                "v": "2022"
            },
            {
                "n": "2021",
                "v": "2021"
            },
            {
                "n": "2020",
                "v": "2020"
            },
            {
                "n": "2019",
                "v": "2019"
            },
            {
                "n": "2018",
                "v": "2018"
            },
            {
                "n": "2017",
                "v": "2017"
            },
            {
                "n": "2016",
                "v": "2016"
            },
            {
                "n": "2015",
                "v": "2015"
            },
            {
                "n": "2014",
                "v": "2014"
            },
            {
                "n": "2013",
                "v": "2013"
            },
            {
                "n": "2012",
                "v": "2012"
            },
            {
                "n": "2011",
                "v": "2011"
            },
            {
                "n": "2010",
                "v": "2010"
            },
            {
                "n": "2009",
                "v": "2009"
            },
            {
                "n": "2008",
                "v": "2008"
            },
            {
                "n": "2007",
                "v": "2007"
            },
            {
                "n": "2006",
                "v": "2006"
            },
            {
                "n": "2005",
                "v": "2005"
            },
            {
                "n": "2004",
                "v": "2004"
            }
        ]
    }];
}

var rule = {
    title: '百忙无果[官]',
    host: 'https://pianku.api.mgtv.com',
    homeUrl: '',
    searchUrl: 'https://mobileso.bz.mgtv.com/applet/search/v1?channelCode=mobile-wxapp&q=**&pn=fypage&pc=10&_support=10000000',
    detailUrl: 'https://pcweb.api.mgtv.com/episode/list?version=5.5.35&video_id=fyid&page=1&size=30&platform=4&src=mgtv&allowedRC=1&_support=10000000',
    searchable: 2,
    quickSearch: 0,
    filterable: 1,
    multi: 1,
    url: '/rider/list/pcweb/v3?allowedRC=1&platform=pcweb&channelId=fyclass&pn=fypage&pc=80&hudong=1&_support=10000000',
    filter_url: 'kind={{fl.kind or "a1"}}&edition={{fl.edition or "a1"}}&area={{fl.area or "a1"}}&year={{fl.year or "all"}}&feature={{fl.feature or "all"}}&fitAge={{fl.fitAge or "a1"}}&chargeInfo={{fl.chargeInfo or "a1"}}&sort={{fl.sort or "c2"}}',
    filter: {
        "short": [{key: "theater", name: "剧场", value: [
            {n: "全部", v: "all"}, {n: "精选", v: "featured"}, {n: "精品", v: "quality"},
            {n: "文旅", v: "travel"}, {n: "热点", v: "hot"}
        ]}],
        "1": getMangoFilter("1"),
        "2": getMangoFilter("2"),
        "3": getMangoFilter("3"),
        "50": getMangoFilter("50"),
        "51": getMangoFilter("51"),
        "115": getMangoFilter("115"),
        "10": getMangoFilter("10")
    },
    headers: {
        'User-Agent': 'PC_UA'
    },
    timeout: 5000,
    class_name: '电视剧&电影&短剧&综艺&动漫&纪录片&教育&少儿&音乐&游戏',
    class_url: '2&3&short&1&50&51&115&10&music&game',
    class_parse: async function () {
        let d = {class: [], filters: rule.filter || {}};
        let names = (rule.class_name || "").split("&");
        let urls = (rule.class_url || "").split("&");
        for (let i = 0; i < Math.min(names.length, urls.length); i++) {
            d.class.push({type_id: urls[i], type_name: names[i]});
        }
        return d;
    },
    limit: 80,
    play_parse: true,
    lazy: async function () {
        let {input} = this;
        return {jx: 1, url: input}
    },

    推荐: async function () {        let {fetch_params} = this;
        fetch_params.headers.Referer = "https://www.mgtv.com/";
        let d = [];
        let seen = {};
        function addItem(item) {
            let vid = item && item.videoId;
            if (!vid || seen[vid]) return;
            seen[vid] = true;
            d.push({
                url: String(vid),
                title: item.videoName || "",
                pic_url: item.img || "",
                desc: item.time || item.desc || item.cornerTitle || ""
            });
        }
        try {
            let api = "https://dc.bz.mgtv.com/dynamic/v1/channel/index/0/0/0/1000000/0/0/17/1354?type=17&version=5.0&t=" + Date.now() + "&_support=10000000";
            let json = JSON.parse(await request(api));
            let modules = json && Array.isArray(json.data) ? json.data : [];
            modules.forEach(function(module) {
                let blocks = module && Array.isArray(module.DSLList) ? module.DSLList : [];
                blocks.forEach(function(block) {
                    let items = block && block.data && Array.isArray(block.data.items) ? block.data.items : [];
                    items.forEach(addItem);
                });
            });
        } catch (e) {
            log("芒果首页推荐加载失败:" + e.message);
        }
        if (!d.length) {
            for (let cid of ["2", "3", "1", "50"]) {
                try {
                    let api = "https://pianku.api.mgtv.com/rider/list/pcweb/v3?allowedRC=1&platform=pcweb&channelId=" + cid + "&pn=1&pc=6&hudong=1&_support=10000000";
                    let json = JSON.parse(await request(api));
                    let list = json && json.data && Array.isArray(json.data.hitDocs) ? json.data.hitDocs : [];
                    list.forEach(function(item) {
                        let vid = item.playPartId;
                        if (!vid || seen[vid]) return;
                        seen[vid] = true;
                        d.push({
                            url: String(vid),
                            title: item.title || "",
                            pic_url: item.img || "",
                            desc: item.updateInfo || (item.rightCorner && item.rightCorner.text) || ""
                        });
                    });
                } catch (e) {
                    log("芒果推荐回退频道" + cid + "加载失败:" + e.message);
                }
            }
        }
        return setResult(d.slice(0, 24));
    },
    一级: async function () {
        let {input, MY_CATE, MY_PAGE, MY_FL} = this;
        let d = [];
        if (MY_CATE === "short") {
            let page = Math.max(1, parseInt(MY_PAGE) || 1);
            let cacheKey = "mango_short_catalog_v1";
            let snapshot = null;
            try {
                let saved = JSON.parse(getItem(cacheKey, ""));
                if (saved && saved.lists && ["all", "featured", "quality", "travel", "hot"].every(function(key) {
                    return Array.isArray(saved.lists[key]);
                })) snapshot = saved;
            } catch (e) {}
            async function readJson(url, mobile) {
                let json = JSON.parse(await request(url, {headers: {
                    "User-Agent": mobile ? MOBILE_UA : PC_UA,
                    "Referer": "https://www.mgtv.com/"
                }}));
                if (!json || Number(json.code) !== 200 || !Array.isArray(json.data)) throw new Error("短剧接口未返回完整数据");
                return json;
            }
            function positiveId(values) {
                for (let i = 0; i < values.length; i++) {
                    let value = String(values[i] || "");
                    if (/^\d+$/.test(value) && Number(value) > 0) return value;
                }
                return "";
            }
            async function loadChannel(cid, mobile) {
                let seqId = String(Date.now());
                let base = "https://dc.bz.mgtv.com/dynamic/v1/";
                let suffix = mobile ? "/0/0/0/1000000/0/0/7/" + cid : "/" + seqId + "/9.0.7-5/10.0/10000000/space/0/4/" + cid;
                let query = mobile ? "?type=7&version=5.0&_support=1000000" : "?osType=window&seqId=" + seqId + "&device=pc&playList=";
                let root = await readJson(base + "channel/index" + suffix + query, mobile);
                if (!Array.isArray(root.moduleIDS)) throw new Error("短剧模块目录缺失");
                let ids = root.moduleIDS.map(function(item) { return String(item.moduleEntityId); });
                let modules = {};
                function receive(list) {
                    list.forEach(function(module) {
                        if (module && module.moduleEntityId) modules[String(module.moduleEntityId)] = module;
                    });
                }
                receive(root.data);
                let missing = ids.filter(function(id) { return !modules[id]; });
                for (let offset = 0; offset < missing.length; offset += 10) {
                    let moduleQuery = mobile ? "?type=7&version=5.0&_support=10000000" : query;
                    receive((await readJson(base + "module/infos" + suffix + "/" + missing.slice(offset, offset + 10).join(",") + moduleQuery, mobile)).data);
                }
                if (ids.some(function(id) { return !modules[id]; })) throw new Error("短剧模块回包不完整");
                let cards = [];
                function walk(item) {
                    if (!item || typeof item !== "object") return;
                    if (Array.isArray(item)) { item.forEach(walk); return; }
                    let url = String(item.videoUrl || item.cms_videoUrl || item.jumpUrl || "");
                    let match = url.match(/\/b\/(\d+)/) || url.match(/[?&]clipId=(\d+)/);
                    let clip = positiveId([match && match[1], item.albumId, item.ctid, item.jumpId]);
                    let vid = positiveId([item.childId, item.videoId, item.vid, (item.albumId || item.ctid) && item.id]);
                    let title = item.name || item.title || item.videoName || "";
                    let subtitle = item.subName || item.subTitle || "";
                    if (title.charCodeAt(0) === 55357 && title.charCodeAt(1) === 56525 && subtitle) title = subtitle;
                    if (clip && title && (vid || match || Number(item.jumpKind) === 1)) {
                        cards.push({clip: clip, url: vid, title: title,
                            pic_url: item.imageV || item.imageH || item.imageNew || item.thumbImg || item.cover || item.phoneImgUrl || item.img || item.image || item.imgUrl || item.imgHUrl || "",
                            desc: item.updateInfo || subtitle || item.desc || item.rbCornerText || item.IbCornerText || ""});
                    }
                    Object.keys(item).forEach(function(key) { if (item[key] && typeof item[key] === "object") walk(item[key]); });
                }
                ids.forEach(function(id) {
                    (modules[id].DSLList || []).forEach(function(block) { if (block) walk(block.data); });
                });
                return cards;
            }
            async function resolveVideos(groups) {
                let ids = {}, pending = {}, complete = true;
                groups.forEach(function(cards) {
                    cards.forEach(function(card) {
                        if (card.url && !ids[card.clip]) ids[card.clip] = card.url;
                        else if (!card.url) pending[card.clip] = true;
                    });
                });
                for (let clip of Object.keys(pending)) {
                    if (ids[clip]) return;
                    try {
                        let html = await request("https://www.mgtv.com/b/" + clip + ".html", {headers: {
                            "User-Agent": PC_UA, "Referer": "https://www.mgtv.com/"
                        }});
                        let tags = String(html).match(/<[^>]+\bdata-cid\s*=\s*["'][^"']+["'][^>]*>/gi) || [];
                        tags.some(function(tag) {
                            let cid = tag.match(/\bdata-cid\s*=\s*["'](\d+)["']/i);
                            let vid = tag.match(/\bdata-vid\s*=\s*["'](\d+)["']/i);
                            if (cid && cid[1] === clip && vid && Number(vid[1]) > 0) {
                                ids[clip] = vid[1]; return true;
                            }
                            return false;
                        });
                    } catch (e) { log("芒果短剧视频地址加载失败:" + clip + ":" + e.message); }
                    if (!ids[clip]) { complete = false; log("芒果短剧未取得真实视频地址:" + clip); }
                }
                groups.forEach(function(cards) {
                    cards.forEach(function(card) { if (!card.url && ids[card.clip]) card.url = ids[card.clip]; });
                });
                return complete;
            }
            function merge(groups) {
                let seen = {}, list = [];
                groups.forEach(function(cards) {
                    cards.forEach(function(card) {
                        if (card.url && !seen[card.clip]) { seen[card.clip] = true; list.push(card); }
                    });
                });
                return list;
            }
            if (!snapshot || (page === 1 && Date.now() - snapshot.time > (snapshot.complete === false ? 60000 : 600000))) {
                try {
                    let complete = true;
                    async function load(cid, mobile) {
                        try { return await loadChannel(cid, mobile); }
                        catch (e) { complete = false; log("芒果短剧频道" + cid + "加载失败:" + e.message); return []; }
                    }
                    let pc = await load("100970", false);
                    let mobile = await load("744", true);
                    let quality = await load("100869", true);
                    let travel = await load("100867", true);
                    let hot = await load("100865", true);
                    complete = await resolveVideos([pc, mobile, quality, travel, hot]) && complete;
                    quality = merge([quality]); travel = merge([travel]); hot = merge([hot]);
                    let featured = merge([pc, mobile]);
                    let fresh = {time: Date.now(), complete: complete, lists: {all: merge([featured, quality, travel, hot]), featured: featured, quality: quality, travel: travel, hot: hot}};
                    if (!fresh.lists.all.length) throw new Error("短剧合集为空");
                    if (complete || !snapshot || snapshot.complete === false) {
                        snapshot = fresh;
                        setItem(cacheKey, JSON.stringify(fresh));
                    }
                    if (!complete) log("芒果短剧合集部分来源未完成，保留完整快照或短期重试");
                } catch (e) {
                    log("芒果短剧合集更新失败，保留已有完整快照:" + e.message);
                }
            }
            if (snapshot) {
                let theater = MY_FL && MY_FL.theater || "all";
                let list = snapshot.lists[theater] || snapshot.lists.all;
                rule.pagecount = rule.pagecount || {};
                rule.pagecount.short = Math.max(1, Math.ceil(list.length / 40));
                d = list.slice((page - 1) * 40, page * 40);
            }
        } else if (MY_CATE === "music" || MY_CATE === "game" || MY_CATE === "short") {
            let cid = { music: "12", game: "112", short: "100970" }[MY_CATE];
            let page = Number(MY_PAGE) || 1;
            let seqId = String(Date.now());
            let base = "https://dc.bz.mgtv.com/dynamic/v1/";
            let suffix = "/" + seqId + "/9.0.7-5/10.0/10000000/space/0/4/" + cid;
            let query = "?osType=window&seqId=" + seqId + "&device=pc&playList=";
            let root = JSON.parse(await request(base + "channel/index" + suffix + query));
            let moduleIds = root && Array.isArray(root.moduleIDS) ? root.moduleIDS : [];
            try {
                rule.pagecount = rule.pagecount || {};
                rule.pagecount[MY_CATE] = Math.max(1, Math.ceil(moduleIds.length / 6));
            } catch (e) {}
            let start = (page - 1) * 6;
            async function loadModules(offset) {
                if (offset >= moduleIds.length) return [];
                if (offset === 0) return root && Array.isArray(root.data) ? root.data : [];
                let ids = moduleIds.slice(offset, offset + 6).map(function(it) { return it.moduleEntityId; }).filter(Boolean);
                if (!ids.length) return [];
                let json = JSON.parse(await request(base + "module/infos" + suffix + "/" + ids.join(",") + query));
                return json && Array.isArray(json.data) ? json.data : [];
            }
            function moduleItems(modules) {
                let items = [];
                modules.forEach(function(module) {
                    let blocks = module && Array.isArray(module.DSLList) ? module.DSLList : [];
                    blocks.forEach(function(block) {
                        let list = block && block.data && Array.isArray(block.data.items) ? block.data.items : [];
                        items = items.concat(list);
                    });
                });
                return items;
            }
            function cardKey(item) {
                let id = item && (item.childId || item.videoId);
                let clip = MY_CATE === "short" && String(item && item.videoUrl || "").match(/\/b\/(\d+)/);
                return clip ? "clip_" + clip[1] : "video_" + id;
            }
            let previous = {};
            if (page > 1) {
                moduleItems(await loadModules(start - 6)).forEach(function(item) {
                    let id = item && (item.childId || item.videoId);
                    if (id) previous[cardKey(item)] = true;
                });
            }
            let seen = {};
            moduleItems(await loadModules(start)).forEach(function(item) {
                let id = item && (item.childId || item.videoId);
                id = id ? String(id) : "";
                let key = cardKey(item);
                if (!id || previous[key] || seen[key]) return;
                seen[key] = true;
                let name = item.name || item.title || "";
                if (MY_CATE === "short" && name.charCodeAt(0) === 55357 && name.charCodeAt(1) === 56525 && item.subName) name = item.subName;
                d.push({
                    title: name,
                    pic_url: item.imageV || item.imageH || item.imageNew || item.thumbImg || "",
                    desc: item.updateInfo || item.subName || item.IbCornerText || "",
                    url: id
                });
            });
        } else {
            let json = JSON.parse(await request(input));
            let list = json && json.data && Array.isArray(json.data.hitDocs) ? json.data.hitDocs : [];
            list.forEach(function(item) {
                if (!item || !item.playPartId) return;
                d.push({
                    title: item.title || "",
                    pic_url: item.img || "",
                    desc: item.updateInfo || (item.rightCorner && item.rightCorner.text) || "",
                    url: String(item.playPartId)
                });
            });
        }
        return setResult(d);
    },
    二级: async function () {
        let {input, fetch_params} = this;
        fetch_params.headers.Referer = "https://www.mgtv.com";
        fetch_params.headers["User-Agent"] = MOBILE_UA;

        let videoId = input.split('video_id=')[1].split('&')[0];
        let infoUrl = `https://pcweb.api.mgtv.com/video/info?allowedRC=1&vid=${videoId}&type=b&_support=10000000`;
        let infoData = JSON.parse(await request(infoUrl));
        let VOD = {
            vod_name: "",
            type_name: "",
            vod_year: "",
            vod_area: "",
            vod_lang: "",
            vod_actor: "",
            vod_director: "",
            vod_content: "",
            vod_remarks: "",
            vod_pic: ""
        };

        if (infoData && infoData.data && infoData.data.info) {
            let info = infoData.data.info;
            let detail = info.detail || {};
            VOD = {
                vod_name: info.title || "",
                type_name: detail.kind || "",
                vod_year: detail.releaseTime || "",
                vod_area: detail.area || "",
                vod_lang: detail.language || "",
                vod_actor: detail.leader || "",
                vod_director: detail.director || "",
                vod_content: detail.story || "",
                vod_remarks: detail.updateInfo || "",
                vod_pic: detail.img || info.videoImage || info.clipImage2 || info.clipImage || info.plImage || ""
            };
        }

        let d = [];
        let html = await request(input);
        let json = JSON.parse(html);
        let host = "https://www.mgtv.com";
        let firstList = json && json.data && Array.isArray(json.data.list) ? json.data.list : [];
        let firstSeries = json && json.data && Array.isArray(json.data.series) ? json.data.series : [];
        let ourl = firstList.length ? firstList[0].url : (firstSeries.length ? firstSeries[0].url : "");
        if (ourl && !/^https?:/.test(ourl)) ourl = host + ourl;

        fetch_params.headers["User-Agent"] = MOBILE_UA;
        if (ourl) {
            html = await request(ourl);
            if (html.includes("window.location =")) {
                ourl = pdfh(html, "meta[http-equiv=refresh]&&content").split("url=")[1];
                if (ourl) html = await request(ourl);
            }
        }

        try {
            let details = pdfh(html, ".m-details&&Html").replace(/h1>/, "h6>").replace(/div/g, "br");
            let actor = "",
                director = "",
                time = "";
            if (/播出时间/.test(details)) {
                actor = pdfh(html, "p:eq(5)&&Text").substr(0, 25);
                director = pdfh(html, "p:eq(4)&&Text");
                time = pdfh(html, "p:eq(3)&&Text");
            } else {
                actor = pdfh(html, "p:eq(4)&&Text").substr(0, 25);
                director = pdfh(html, "p:eq(3)&&Text");
                time = "已完结";
            }
            let _img = pd(html, ".video-img&&img&&src");
            let JJ = pdfh(html, ".desc&&Text").split("牛马简介：")[1];
            VOD.vod_name = VOD.vod_name || pdfh(html, ".vt-txt&&Text");
            VOD.type_name = VOD.type_name || pdfh(html, "p:eq(0)&&Text").substr(0, 6);
            VOD.vod_area = VOD.vod_area || pdfh(html, "p:eq(1)&&Text");
            VOD.vod_actor = VOD.vod_actor || actor;
            VOD.vod_director = VOD.vod_director || director;
            VOD.vod_remarks = VOD.vod_remarks || time;
            VOD.vod_pic = VOD.vod_pic || _img;
            VOD.vod_content = VOD.vod_content || JJ;
            if (!VOD.vod_name) VOD.vod_name = VOD.type_name;
        } catch (e) {
            log("获取影片信息发生错误:" + e.message);
        }

        function getRjpg(imgUrl, xs) {
            if (!imgUrl) return "";
            xs = xs || 3;
            let picSize = /jpg_/.test(imgUrl) ? imgUrl.split("jpg_")[1].split(".")[0] : false;
            let rjpg = false;
            if (picSize) {
                let a = parseInt(picSize.split("x")[0]) * xs;
                let b = parseInt(picSize.split("x")[1]) * xs;
                rjpg = a + "x" + b + ".jpg";
            }
            return /jpg_/.test(imgUrl) && rjpg ? imgUrl.replace(imgUrl.split("jpg_")[1], rjpg) : imgUrl;
        }

        let seen = {};
        function addPage(pageRoot) {
            let list = pageRoot && pageRoot.data && Array.isArray(pageRoot.data.list) ? pageRoot.data.list : [];
            list.forEach(function(data) {
                if (String(data.isIntact) !== "1" || !data.url) return;
                let playUrl = /^https?:/.test(data.url) ? data.url : host + data.url;
                if (seen[playUrl]) return;
                seen[playUrl] = true;
                d.push({
                    title: data.t4 || data.t3 || data.t1 || "播放",
                    desc: data.t2 || "",
                    pic_url: getRjpg(data.img),
                    url: playUrl
                });
            });
        }
        let totalPage = json && json.data ? (parseInt(json.data.total_page) || 1) : 1;
        addPage(json);
        for (let i = 2; i <= totalPage; i++) {
            let pageRoot = JSON.parse(await request(input.replace("page=1", "page=" + i)));
            addPage(pageRoot);
        }
        if (!d.length) print(input + "暂无片源");
        VOD.vod_play_from = "芒果TV";
        VOD.vod_play_url = d.map(function(it) {
            return it.title + "$" + it.url;
        }).join("#");
        return VOD;
    },
    搜索: async function () {
        let {input, MY_PAGE, fetch_params} = this;
        fetch_params.headers.Referer = "https://www.mgtv.com";
        fetch_params.headers["User-Agent"] = MOBILE_UA;
        let d = [];
        let html = await request(input);
        let json = JSON.parse(html);
        let contents = json && json.data && Array.isArray(json.data.contents) ? json.data.contents : [];
        contents.forEach(function(data) {
            if (!data || data.type !== "media" || !Array.isArray(data.data) || !data.data.length) return;
            let item = data.data[0];
            if (item.source !== "imgo" || !item.vid) return;
            d.push({
                title: (item.title || "").replace(/<\/?(?:B|em)>/gi, ""),
                pic_url: item.img || "",
                content: "",
                desc: Array.isArray(item.desc) ? item.desc.join(",") : (item.desc || ""),
                url: String(item.vid)
            });
        });
        return setResult(d);
    }
}
