/*
@header({
  searchable: 2,
  filterable: 1,
  quickSearch: 0,
  title: '奇艺[官]',
  lang: 'ds'
})
*/

var rule = {
    title: '奇艺[官]',
    host: 'https://www.iqiyi.com',
    homeUrl: '',
    detailUrl: 'https://pcw-api.iqiyi.com/video/video/videoinfowithuser/fyid?agent_type=1&authcookie=&subkey=fyid&subscribe=1',
    searchUrl: 'https://search.video.iqiyi.com/o?if=html5&key=**&pageNum=fypage&pos=1&pageSize=24&site=iqiyi',
    searchable: 2,
    multi: 1,
    filterable: 1,
    url: 'https://pcw-api.iqiyi.com/search/recommend/list?channel_id=fyclass&data_type=1&page_id=fypage&ret_num=24',
    filter_url: 'is_purchase={{fl.is_purchase}}&mode={{fl.mode}}&three_category_id={{fl.three_category_id}}&market_release_date_level={{fl.year}}&region={{fl.region}}',
    filter: {
        '1': [{
            'key': 'mode',
            'name': '综合排序',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '热播榜',
                'v': 11
            }, {
                'n': '好评榜',
                'v': 8
            }, {
                'n': '新上线',
                'v': 4
            }]
        }, {
            'key': 'three_category_id',
            'name': '类型',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '喜剧',
                'v': 8
            }, {
                'n': '爱情',
                'v': 6
            }, {
                'n': '动作',
                'v': 11
            }, {
                'n': '悬疑',
                'v': 289
            }, {
                'n': '科幻',
                'v': 9
            }, {
                'n': '恐怖',
                'v': 10
            }, {
                'n': '犯罪',
                'v': 291
            }, {
                'n': '战争',
                'v': 7
            }, {
                'n': '动画',
                'v': 12
            }, {
                'n': '奇幻',
                'v': 1284
            }, {
                'n': '枪战',
                'v': 131
            }, {
                'n': '惊悚',
                'v': 128
            }, {
                'n': '青春',
                'v': 130
            }, {
                'n': '家庭',
                'v': 27356
            }]
        }, {
            'key': 'region',
            'name': '地区',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '华语',
                'v': 1
            }, {
                'n': '香港地区',
                'v': 28997
            }, {
                'n': '美国',
                'v': 2
            }, {
                'n': '欧洲',
                'v': 3
            }, {
                'n': '韩国',
                'v': 4
            }, {
                'n': '日本',
                'v': 308
            }, {
                'n': '泰国',
                'v': 1115
            }, {
                'n': '印度',
                'v': 28999
            }, {
                'n': '其它',
                'v': 5
            }]
        }, {
            'key': 'year',
            'name': '全部年份',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                "n": "2026",
                "v": 2026
            }, {
                "n": "2025",
                "v": 2025
            }, {
                "n": "2024",
                "v": 2024
            }, {
                'n': '2023',
                'v': 2023
            }, {
                'n': '2022',
                'v': 2022
            }, {
                'n': '2021',
                'v': 2021
            }, {
                'n': '2020',
                'v': 2020
            }, {
                'n': '2019',
                'v': 2019
            }, {
                'n': '2018',
                'v': 2018
            }, {
                'n': '2017',
                'v': 2017
            }, {
                'n': '2016-2011',
                'v': '2011_2016'
            }, {
                'n': '2010-2000',
                'v': '2000_2010'
            }, {
                'n': '90年代',
                'v': '1990_1999'
            }, {
                'n': '80年代',
                'v': '1980_1989'
            }, {
                'n': '更早',
                'v': '1964_1979'
            }]
        }, {
            'key': 'is_purchase',
            'name': '全部资费',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '免费',
                'v': 0
            }, {
                'n': '会员',
                'v': 1
            }, {
                'n': '付费',
                'v': 2
            }]
        }],
        '2': [{
            'key': 'mode',
            'name': '综合排序',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '热播榜',
                'v': 11
            }, {
                'n': '好评榜',
                'v': 8
            }, {
                'n': '新上线',
                'v': 4
            }]
        }, {
            'key': 'three_category_id',
            'name': '类型',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '古装',
                'v': 24
            }, {
                'n': '言情',
                'v': 20
            }, {
                'n': '都市',
                'v': 24064
            }, {
                'n': '悬疑',
                'v': 32
            }, {
                'n': '武侠',
                'v': 23
            }, {
                'n': '家庭',
                'v': 1654
            }, {
                'n': '喜剧',
                'v': 135
            }, {
                'n': '战争',
                'v': 27916
            }, {
                'n': '军旅',
                'v': 1655
            }, {
                'n': '谍战',
                'v': 290
            }, {
                'n': '偶像',
                'v': 30
            }, {
                'n': '青春',
                'v': 1653
            }, {
                'n': '罪案',
                'v': 149
            }, {
                'n': '历史',
                'v': 21
            }, {
                'n': '年代',
                'v': 27
            }, {
                'n': '科幻',
                'v': 34
            }, {
                'n': '奇幻',
                'v': 27881
            }, {
                'n': '剧情',
                'v': 24063
            }, {
                'n': '农村',
                'v': 29
            }, {
                'n': '宫廷',
                'v': 139
            }, {
                'n': '商战',
                'v': 140
            }]
        }, {
            'key': 'region',
            'name': '地区',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '内地',
                'v': 15
            }, {
                'n': '中国台湾',
                'v': 1117
            }, {
                'n': '美国',
                'v': 18
            }]
        }, {
            'key': 'year',
            'name': '全部年份',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                "n": "2026",
                "v": 2026
            }, {
                "n": "2025",
                "v": 2025
            }, {
                "n": "2024",
                "v": 2024
            }, {
                'n': '2023',
                'v': 2023
            }, {
                'n': '2022',
                'v': 2022
            }, {
                'n': '2021',
                'v': 2021
            }, {
                'n': '2020',
                'v': 2020
            }, {
                'n': '2019',
                'v': 2019
            }, {
                'n': '2018',
                'v': 2018
            }, {
                'n': '2017',
                'v': 2017
            }, {
                'n': '2016-2011',
                'v': '2011_2016'
            }, {
                'n': '2010-2000',
                'v': '2000_2010'
            }, {
                'n': '90年代',
                'v': '1990_1999'
            }, {
                'n': '80年代',
                'v': '1980_1989'
            }, {
                'n': '更早',
                'v': '1964_1979'
            }]
        }, {
            'key': 'is_purchase',
            'name': '全部资费',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '免费',
                'v': 0
            }, {
                'n': '会员',
                'v': 1
            }, {
                'n': '付费',
                'v': 2
            }]
        }],
        '3': [{
            'key': 'mode',
            'name': '综合排序',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '热播榜',
                'v': 11
            }, {
                'n': '好评榜',
                'v': 8
            }, {
                'n': '新上线',
                'v': 4
            }]
        }, {
            'key': 'three_category_id',
            'name': '类型',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '人文',
                'v': 70
            }, {
                'n': '历史',
                'v': 74
            }, {
                'n': '军事',
                'v': 72
            }, {
                'n': '自然',
                'v': 33933
            }, {
                'n': '探险',
                'v': 73
            }, {
                'n': '社会',
                'v': 71
            }, {
                'n': '美食',
                'v': 33908
            }, {
                'n': '科技',
                'v': 28119
            }]
        }, {
            'key': 'region',
            'name': '地区',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '国内',
                'v': 20323
            }, {
                'n': '国外',
                'v': 20324
            }]
        }, {
            'key': 'year',
            'name': '全部年份',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                "n": "2026",
                "v": 2026
            }, {
                "n": "2025",
                "v": 2025
            }, {
                "n": "2024",
                "v": 2024
            }, {
                'n': '2023',
                'v': 2023
            }, {
                'n': '2022',
                'v': 2022
            }, {
                'n': '2021',
                'v': 2021
            }, {
                'n': '2020',
                'v': 2020
            }, {
                'n': '2019',
                'v': 2019
            }, {
                'n': '2018',
                'v': 2018
            }, {
                'n': '2017',
                'v': 2017
            }, {
                'n': '2016-2011',
                'v': '2011_2016'
            }, {
                'n': '2010-2000',
                'v': '2000_2010'
            }, {
                'n': '90年代',
                'v': '1990_1999'
            }, {
                'n': '80年代',
                'v': '1980_1989'
            }, {
                'n': '更早',
                'v': '1964_1979'
            }]
        }, {
            'key': 'is_purchase',
            'name': '全部资费',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '免费',
                'v': 0
            }, {
                'n': '会员',
                'v': 1
            }, {
                'n': '付费',
                'v': 2
            }]
        }],
        '4': [{
            'key': 'mode',
            'name': '综合排序',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '热播榜',
                'v': 11
            }, {
                'n': '好评榜',
                'v': 8
            }, {
                'n': '新上线',
                'v': 4
            }]
        }, {
            'key': 'three_category_id',
            'name': '类型',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '热血',
                'v': 30232
            }, {
                'n': '搞笑',
                'v': 30230
            }, {
                'n': '恋爱',
                'v': 30243
            }, {
                'n': '冒险',
                'v': 30267
            }, {
                'n': '校园',
                'v': 30249
            }, {
                'n': '科幻',
                'v': 30245
            }]
        }, {
            'key': 'region',
            'name': '地区',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '中国大陆',
                'v': 37
            }, {
                'n': '日本',
                'v': 38
            }, {
                'n': '欧美',
                'v': 39
            }, {
                'n': '其它',
                'v': 40
            }]
        }, {
            'key': 'year',
            'name': '全部年份',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                "n": "2026",
                "v": 2026
            }, {
                "n": "2025",
                "v": 2025
            }, {
                "n": "2024",
                "v": 2024
            }, {
                'n': '2023',
                'v': 2023
            }, {
                'n': '2022',
                'v': 2022
            }, {
                'n': '2021',
                'v': 2021
            }, {
                'n': '2020',
                'v': 2020
            }, {
                'n': '2019',
                'v': 2019
            }, {
                'n': '2018',
                'v': 2018
            }, {
                'n': '2017',
                'v': 2017
            }, {
                'n': '2016-2011',
                'v': '2011_2016'
            }, {
                'n': '2010-2000',
                'v': '2000_2010'
            }, {
                'n': '90年代',
                'v': '1990_1999'
            }, {
                'n': '80年代',
                'v': '1980_1989'
            }]
        }, {
            'key': 'is_purchase',
            'name': '全部资费',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '免费',
                'v': 0
            }, {
                'n': '会员',
                'v': 1
            }, {
                'n': '付费',
                'v': 2
            }]
        }],
        '6': [{
            'key': 'mode',
            'name': '综合排序',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '热播榜',
                'v': 11
            }, {
                'n': '好评榜',
                'v': 8
            }, {
                'n': '新上线',
                'v': 4
            }]
        }, {
            'key': 'three_category_id',
            'name': '类型',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '真人秀',
                'v': 2224
            }, {
                'n': '脱口秀',
                'v': 2118
            }, {
                'n': '晚会',
                'v': 292
            }, {
                'n': '音乐',
                'v': 33163
            }, {
                'n': '舞蹈',
                'v': 33172
            }, {
                'n': '竞技',
                'v': 30278
            }]
        }, {
            'key': 'region',
            'name': '地区',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '内地',
                'v': 151
            }]
        }, {
            'key': 'year',
            'name': '全部年份',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                "n": "2026",
                "v": 2026
            }, {
                "n": "2025",
                "v": 2025
            }, {
                "n": "2024",
                "v": 2024
            }, {
                'n': '2023',
                'v': 2023
            }, {
                'n': '2022',
                'v': 2022
            }, {
                'n': '2021',
                'v': 2021
            }, {
                'n': '2020',
                'v': 2020
            }, {
                'n': '2019',
                'v': 2019
            }, {
                'n': '2018',
                'v': 2018
            }, {
                'n': '2017',
                'v': 2017
            }, {
                'n': '2016-2011',
                'v': '2011_2016'
            }, {
                'n': '2010-2000',
                'v': '2000_2010'
            }, {
                'n': '90年代',
                'v': '1990_1999'
            }, {
                'n': '80年代',
                'v': '1980_1989'
            }]
        }, {
            'key': 'is_purchase',
            'name': '全部资费',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '免费',
                'v': 0
            }, {
                'n': '会员',
                'v': 1
            }, {
                'n': '付费',
                'v': 2
            }]
        }],
        '35': [{
            'key': 'mode',
            'name': '综合排序',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '热播榜',
                'v': 11
            }, {
                'n': '好评榜',
                'v': 8
            }, {
                'n': '新上线',
                'v': 4
            }]
        }, {
            'key': 'year',
            'name': '全部年份',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                "n": "2026",
                "v": 2026
            }, {
                "n": "2025",
                "v": 2025
            }, {
                "n": "2024",
                "v": 2024
            }, {
                'n': '2023',
                'v': 2023
            }, {
                'n': '2022',
                'v': 2022
            }]
        }, {
            'key': 'is_purchase',
            'name': '全部资费',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '免费',
                'v': 0
            }, {
                'n': '会员',
                'v': 1
            }, {
                'n': '付费',
                'v': 2
            }]
        }],
        '15': [{
            'key': 'mode',
            'name': '综合排序',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '热播榜',
                'v': 11
            }, {
                'n': '好评榜',
                'v': 8
            }, {
                'n': '新上线',
                'v': 4
            }]
        }, {
            'key': 'is_purchase',
            'name': '全部资费',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '免费',
                'v': 0
            }, {
                'n': '会员',
                'v': 1
            }, {
                'n': '付费',
                'v': 2
            }]
        }],
        '37': [{
            'key': 'mode',
            'name': '综合排序',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '热播榜',
                'v': 11
            }, {
                'n': '好评榜',
                'v': 8
            }, {
                'n': '新上线',
                'v': 4
            }]
        }, {
            'key': 'year',
            'name': '全部年份',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                "n": "2026",
                "v": 2026
            }, {
                "n": "2025",
                "v": 2025
            }, {
                "n": "2024",
                "v": 2024
            }, {
                'n': '2023',
                'v': 2023
            }, {
                'n': '2022',
                'v': 2022
            }]
        }, {
            'key': 'is_purchase',
            'name': '全部资费',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '免费',
                'v': 0
            }, {
                'n': '会员',
                'v': 1
            }, {
                'n': '付费',
                'v': 2
            }]
        }],
        '31': [{
            'key': 'mode',
            'name': '综合排序',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '热播榜',
                'v': 11
            }, {
                'n': '好评榜',
                'v': 8
            }, {
                'n': '新上线',
                'v': 4
            }]
        }, {
            'key': 'is_purchase',
            'name': '全部资费',
            'value': [{
                'n': '全部',
                'v': ''
            }, {
                'n': '免费',
                'v': 0
            }, {
                'n': '会员',
                'v': 1
            }, {
                'n': '付费',
                'v': 2
            }]
        }]
    },
    headers: {
        'User-Agent': 'MOBILE_UA'
    },
    timeout: 5000,
    class_name: '电视剧&短剧&电影&综艺&少儿&动漫&漫剧&纪录片&知识&音乐&游戏&体育',
    class_url: '2&35&1&6&15&4&37&3&31&5&8&17',
    class_parse: async function () {
        let d = {class: [], filters: rule.filter || {}};
        let names = (rule.class_name || "").split("&");
        let urls = (rule.class_url || "").split("&");
        for (let i = 0; i < Math.min(names.length, urls.length); i++) {
            d.class.push({type_id: urls[i], type_name: names[i]});
        }
        return d;
    },
    limit: 24,
    play_parse: true,
    lazy: async function () {
        let {input} = this;
        return {jx: 1, url: input}
    },

    推荐: async function () {        let {input} = this;
        let d = [];
        let seen = {};
        for (let cid of ["2", "1", "6", "4"]) {
            try {
                let api = "https://pcw-api.iqiyi.com/search/recommend/list?channel_id=" + cid + "&data_type=1&mode=11&page_id=1&ret_num=6";
                let json = JSON.parse(await request(api));
                let list = json && json.data && Array.isArray(json.data.list) ? json.data.list : [];
                list.slice(0, 6).forEach(function(data) {
                    let vid = data.albumId || data.tvId;
                    if (!vid || seen[vid]) return;
                    seen[vid] = true;
                    let pic = data.imageUrl || "";
                    if (pic) pic = pic.replace(".jpg", "_390_520.jpg?caplist=jpg,webp");
                    d.push({
                        url: cid + "$" + vid,
                        title: data.name || data.title || "",
                        desc: data.focus || (data.latestOrder ? "更新至 " + data.latestOrder + "集" : ""),
                        pic_url: pic
                    });
                });
            } catch (e) {
                log("爱奇艺推荐频道" + cid + "加载失败:" + e.message);
            }
        }
        return setResult(d);    },
    一级: async function () {        let {input, MY_CATE, MY_PAGE, MY_FL} = this;
        let d = [];
        if (MY_CATE === "4") {
            input = input.replace("search/recommend/list", "search/video/videolists")
                .replace("page_id=", "pageNum=")
                .replace("ret_num=24", "pageSize=24");
        }
        let json = JSON.parse(await request(input));
        if (json.code === "A00003") {
            let fetch_params = {headers: {"user-agent": PC_UA}};
            json = JSON.parse(await fetch(input, fetch_params));
        }
        let list = json && json.data && Array.isArray(json.data.list) ? json.data.list : [];
        list.forEach(function(data) {
            let vid = data.albumId || data.tvId;
            if (!vid) return;
            let desc = "";
            if (data.channelId === 1) {
                desc = data.score ? data.score + "分\t" : "";
                if (data.duration) desc += data.duration;
            } else if (data.channelId === 2 || data.channelId === 4 || data.channelId === 35 || data.channelId === 15 || data.channelId === 37) {
                if (data.latestOrder === data.videoCount && data.latestOrder) {
                    desc = (data.score ? data.score + "分\t" : "") + data.latestOrder + "集全";
                } else if (data.videoCount) {
                    desc = (data.score ? data.score + "分\t" : "") + (data.latestOrder || 0) + "/" + data.videoCount + "集";
                } else if (data.latestOrder) {
                    desc = "更新至 " + data.latestOrder + "集";
                } else {
                    desc = data.focus || "";
                }
            } else if (data.channelId === 6) {
                desc = data.period ? data.period + "期" : (data.focus || "");
            } else {
                desc = data.latestOrder ? "更新至 第" + data.latestOrder + "期" : (data.period || data.focus || "");
            }
            let pic = data.imageUrl || "";
            if (pic) pic = pic.replace(".jpg", "_390_520.jpg?caplist=jpg,webp");
            d.push({url: MY_CATE + "$" + vid, title: data.name || data.title || "", desc: desc, pic_url: pic});
        });
        return setResult(d);    },
    二级: async function () {        let {input} = this;
        let d = [];
        let VOD = {};
        let root = JSON.parse(await request(input));
        let json = root && root.data ? root.data : {};
        let categories = Array.isArray(json.categories) ? json.categories : [];
        let people = json.people || {};
        let categoryNames = categories.map(function(it) { return it && it.name ? it.name : ""; }).filter(Boolean);
        let areas = Array.isArray(json.areas) ? json.areas.join(",") : (json.areas || "");
        let pic = json.imageUrl || json.albumImageUrl || "";
        let vsize = json.imageSize && json.imageSize[12] ? json.imageSize[12] : "579_772";
        if (pic) pic = pic.replace(".jpg", "_" + vsize + ".jpg?caplist=jpg,webp");
        VOD = {
            vod_id: json.albumId || json.tvId || "",
            vod_url: input,
            vod_name: json.name || json.albumName || "",
            type_name: categoryNames.join(","),
            vod_actor: "",
            vod_year: json.period ? String(json.period).split("-")[0] : "",
            vod_director: "",
            vod_area: (json.focus || "") + "\n资费：" + (json.payMark === 1 ? "VIP" : "免费") + "\n地区：" + areas,
            vod_content: json.description || "",
            vod_remarks: "",
            vod_pic: pic
        };
        if (json.latestOrder) {
            VOD.vod_remarks = "类型: " + categoryNames.slice(0, 3).join("\t") + "\t评分：" + (json.score || "") + "\n更新至：第" + json.latestOrder + "集(期)/共" + (json.videoCount || json.latestOrder) + "集(期)";
        } else {
            VOD.vod_remarks = json.subtitle || ("类型: " + categoryNames.slice(0, 3).join("\t") + "\t评分：" + (json.score || "") + (json.period || ""));
        }
        if (Array.isArray(people.main_charactor)) {
            VOD.vod_actor = people.main_charactor.map(function(it) { return it.name || ""; }).filter(Boolean).join(",");
        }
        if (Array.isArray(people.director)) {
            VOD.vod_director = people.director.map(function(it) { return it.name || ""; }).filter(Boolean).join(",");
        }
        let playlists = [];
        if (json.channelId === 1) {
            if (json.playUrl) playlists.push(json);
        } else if (json.channelId === 6) {
            let qs = json.period ? String(json.period).split("-")[0] : "";
            if (qs && json.albumId) {
                let listUrl = "https://pcw-api.iqiyi.com/album/source/svlistinfo?cid=6&sourceid=" + json.albumId + "&timelist=" + qs;
                let playRoot = JSON.parse(await request(listUrl));
                playlists = playRoot && playRoot.data && Array.isArray(playRoot.data[qs]) ? playRoot.data[qs] : [];
            }
        } else if (json.albumId) {
            let listUrl = "https://pcw-api.iqiyi.com/albums/album/avlistinfo?aid=" + json.albumId + "&size=200&page=1";
            let listRoot = JSON.parse(await request(listUrl));
            let listData = listRoot && listRoot.data ? listRoot.data : {};
            playlists = Array.isArray(listData.epsodelist) ? listData.epsodelist : [];
            let pages = Math.ceil((Number(listData.total) || playlists.length) / 200);
            for (let i = 2; i <= pages; i++) {
                let pageRoot = JSON.parse(await request("https://pcw-api.iqiyi.com/albums/album/avlistinfo?aid=" + json.albumId + "&size=200&page=" + i));
                let pageList = pageRoot && pageRoot.data && Array.isArray(pageRoot.data.epsodelist) ? pageRoot.data.epsodelist : [];
                playlists = playlists.concat(pageList);
            }
            if (!playlists.length) {
                let fallbackUrl = json.latestVideoUrl || json.firstVideoUrl || "";
                if (fallbackUrl) playlists.push({shortTitle: "播放", playUrl: fallbackUrl});
            }
        }
        let seen = {};
        playlists.forEach(function(it) {
            let playUrl = it && it.playUrl ? it.playUrl : "";
            if (!playUrl || seen[playUrl]) return;
            seen[playUrl] = true;
            let epPic = it.imageUrl || "";
            if (epPic) epPic = epPic.replace(".jpg", "_480_270.jpg?caplist=jpg,webp");
            d.push({
                title: it.shortTitle || it.name || (it.order ? "第" + it.order + "集" : "播放"),
                desc: it.subtitle || it.focus || it.period || "",
                pic_url: epPic,
                url: playUrl
            });
        });
        VOD.vod_play_from = "qiyi";
        VOD.vod_play_url = d.map(function(it) { return it.title + "$" + it.url; }).join("#");
        return VOD;    },
    搜索: async function () {        let {input, MY_PAGE} = this;
        let d = [];
        let json = JSON.parse(await request(input));
        let list = json && json.data && Array.isArray(json.data.docinfos) ? json.data.docinfos : [];
        list.forEach(function(data) {
            let item = data && data.albumDocInfo ? data.albumDocInfo : {};
            if (!item.albumId || !item.albumTitle) return;
            d.push({
                title: item.albumTitle,
                pic_url: item.albumVImage || item.albumImg || "",
                desc: item.tvFocus || item.channel || "",
                url: String(item.albumId)
            });
        });
        return setResult(d);    }
}