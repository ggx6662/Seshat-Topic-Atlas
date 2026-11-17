#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文姓名 → 英文姓名匹配。

问题
----
导师库里的学者名大多是英文（OpenAlex 的 display_name），例如 "Maosong Sun"。
但中国学生习惯输入中文名「孙茂松」，直接按字面匹配查不到。

不做的事：不引入 pypinyin 之类的外部依赖（要保证零依赖可运行）。

做法：中文姓氏表 + 首字母/全拼模糊匹配。
    1. 常见汉语姓氏 → 拼音（覆盖绝大多数中国人姓）
    2. 姓名按「姓 + 名」拆开，各自转拼音
    3. 与英文名做「姓在中、名在前」和「名在中、姓在前」两种比对
    4. 支持首字母匹配（孙茂松 → Sun Maosong / M Sun / Mao-Song Sun）

局限：多音字、生僻姓可能转不准。查不到时会退化到机构中文名匹配。
"""

# 常见汉语姓氏拼音（覆盖人口 top 200）
SURNAMES = {
    "赵": "zhao", "钱": "qian", "孙": "sun", "李": "li", "周": "zhou",
    "吴": "wu", "郑": "zheng", "王": "wang", "冯": "feng", "陈": "chen",
    "褚": "chu", "卫": "wei", "蒋": "jiang", "沈": "shen", "韩": "han",
    "杨": "yang", "朱": "zhu", "秦": "qin", "尤": "you", "许": "xu",
    "何": "he", "吕": "lv", "施": "shi", "张": "zhang", "孔": "kong",
    "曹": "cao", "严": "yan", "华": "hua", "金": "jin", "魏": "wei",
    "陶": "tao", "姜": "jiang", "戚": "qi", "谢": "xie", "邹": "zou",
    "喻": "yu", "柏": "bai", "水": "shui", "窦": "dou", "章": "zhang",
    "云": "yun", "苏": "su", "潘": "pan", "葛": "ge", "奚": "xi",
    "范": "fan", "彭": "peng", "郎": "lang", "鲁": "lu", "韦": "wei",
    "昌": "chang", "马": "ma", "苗": "miao", "凤": "feng", "花": "hua",
    "方": "fang", "俞": "yu", "任": "ren", "袁": "yuan", "柳": "liu",
    "酆": "feng", "鲍": "bao", "史": "shi", "唐": "tang", "费": "fei",
    "廉": "lian", "岑": "cen", "薛": "xue", "雷": "lei", "贺": "he",
    "倪": "ni", "汤": "tang", "滕": "teng", "殷": "yin", "罗": "luo",
    "毕": "bi", "郝": "hao", "邬": "wu", "安": "an", "常": "chang",
    "乐": "yue", "于": "yu", "时": "shi", "傅": "fu", "皮": "pi",
    "卞": "bian", "齐": "qi", "康": "kang", "伍": "wu", "余": "yu",
    "元": "yuan", "卜": "bu", "顾": "gu", "孟": "meng", "平": "ping",
    "黄": "huang", "和": "he", "穆": "mu", "萧": "xiao", "尹": "yin",
    "姚": "yao", "邵": "shao", "湛": "zhan", "汪": "wang", "祁": "qi",
    "毛": "mao", "禹": "yu", "狄": "di", "米": "mi", "贝": "bei",
    "明": "ming", "臧": "zang", "计": "ji", "伏": "fu", "成": "cheng",
    "戴": "dai", "谈": "tan", "宋": "song", "茅": "mao", "庞": "pang",
    "熊": "xiong", "纪": "ji", "舒": "shu", "屈": "qu", "项": "xiang",
    "祝": "zhu", "董": "dong", "梁": "liang", "杜": "du", "阮": "ruan",
    "蓝": "lan", "闵": "min", "席": "xi", "季": "ji", "麻": "ma",
    "强": "qiang", "贾": "jia", "路": "lu", "娄": "lou", "危": "wei",
    "江": "jiang", "童": "tong", "颜": "yan", "郭": "guo", "梅": "mei",
    "盛": "sheng", "林": "lin", "刁": "diao", "钟": "zhong", "徐": "xu",
    "邱": "qiu", "骆": "luo", "高": "gao", "夏": "xia", "蔡": "cai",
    "田": "tian", "樊": "fan", "胡": "hu", "凌": "ling", "霍": "huo",
    "虞": "yu", "万": "wan", "支": "zhi", "柯": "ke", "昝": "zan",
    "管": "guan", "卢": "lu", "莫": "mo", "经": "jing", "房": "fang",
    "裘": "qiu", "缪": "miao", "干": "gan", "解": "xie", "应": "ying",
    "宗": "zong", "丁": "ding", "宣": "xuan", "贲": "ben", "邓": "deng",
    "郁": "yu", "单": "shan", "杭": "hang", "洪": "hong", "包": "bao",
    "诸": "zhu", "左": "zuo", "石": "shi", "崔": "cui", "吉": "ji",
    "钮": "niu", "龚": "gong", "程": "cheng", "嵇": "ji", "邢": "xing",
    "滑": "hua", "裴": "pei", "陆": "lu", "荣": "rong", "翁": "weng",
    "荀": "xun", "羊": "yang", "於": "yu", "惠": "hui", "甄": "zhen",
    "曲": "qu", "家": "jia", "封": "feng", "芮": "rui", "羿": "yi",
    "储": "chu", "靳": "jin", "汲": "ji", "邴": "bing", "糜": "mi",
    "松": "song", "井": "jing", "段": "duan", "富": "fu", "巫": "wu",
    "乌": "wu", "焦": "jiao", "巴": "ba", "弓": "gong", "牧": "mu",
    "隗": "wei", "山": "shan", "谷": "gu", "车": "che", "侯": "hou",
    "宓": "mi", "蓬": "peng", "全": "quan", "郗": "xi", "班": "ban",
    "仰": "yang", "秋": "qiu", "仲": "zhong", "伊": "yi", "宫": "gong",
    "宁": "ning", "仇": "qiu", "栾": "luan", "暴": "bao", "甘": "gan",
    "钭": "tou", "厉": "li", "戎": "rong", "祖": "zu", "武": "wu",
    "符": "fu", "刘": "liu", "景": "jing", "詹": "zhan", "束": "shu",
    "龙": "long", "叶": "ye", "幸": "xing", "司": "si", "韶": "shao",
    "郜": "gao", "黎": "li", "蓟": "ji", "薄": "bo", "印": "yin",
    "宿": "su", "白": "bai", "怀": "huai", "蒲": "pu", "邰": "tai",
    "从": "cong", "鄂": "e", "索": "suo", "咸": "xian", "籍": "ji",
    "赖": "lai", "卓": "zhuo", "蔺": "lin", "屠": "tu", "蒙": "meng",
    "池": "chi", "乔": "qiao", "阴": "yin", "郁 ": "yu", "胥": "xu",
    "能": "neng", "苍": "cang", "双": "shuang", "闻": "wen", "莘": "shen",
    "党": "dang", "翟": "zhai", "谭": "tan", "贡": "gong", "劳": "lao",
    "逄": "pang", "姬": "ji", "申": "shen", "扶": "fu", "堵": "du",
    "冉": "ran", "宰": "zai", "郦": "li", "雍": "yong", "却": "que",
    "璩": "qu", "桑": "sang", "桂": "gui", "濮": "pu", "牛": "niu",
    "寿": "shou", "通": "tong", "边": "bian", "扈": "hu", "燕": "yan",
    "冀": "ji", "郏": "jia", "浦": "pu", "尚": "shang", "农": "nong",
    "温": "wen", "别": "bie", "庄": "zhuang", "晏": "yan", "柴": "chai",
    "瞿": "qu", "阎": "yan", "充": "chong", "慕": "mu", "连": "lian",
    "茹": "ru", "习": "xi", "宦": "huan", "艾": "ai", "鱼": "yu",
    "容": "rong", "向": "xiang", "古": "gu", "易": "yi", "慎": "shen",
    "戈": "ge", "廖": "liao", "庾": "yu", "终": "zhong", "暨": "ji",
    "居": "ju", "衡": "heng", "步": "bu", "都": "du", "耿": "geng",
    "满": "man", "弘": "hong", "匡": "kuang", "国": "guo", "文": "wen",
    "寇": "kou", "广": "guang", "禄": "lu", "阙": "que", "东": "dong",
    "欧": "ou", "殳": "shu", "沃": "wo", "利": "li", "蔚": "wei",
    "越": "yue", "夔": "kui", "隆": "long", "师": "shi", "巩": "gong",
    "厍": "she", "聂": "nie", "晁": "chao", "勾": "gou", "敖": "ao",
    "融": "rong", "冷": "leng", "訾": "zi", "辛": "xin", "阚": "kan",
    "那": "na", "简": "jian", "饶": "rao", "空": "kong", "曾": "zeng",
    "毋": "wu", "沙": "sha", "乜": "nie", "养": "yang", "鞠": "ju",
    "须": "xu", "丰": "feng", "巢": "chao", "关": "guan", "蒯": "kuai",
    "相": "xiang", "查": "zha", "后": "hou", "荆": "jing", "红": "hong",
    "游": "you", "竺": "zhu", "权": "quan", "逯": "lu", "盖": "gai",
    "益": "yi", "桓": "huan", "公": "gong", "欧阳": "ouyang",
    "司马": "sima", "上官": "shangguan", "诸葛": "zhuge", "东方": "dongfang",
    "皇甫": "huangfu", "尉迟": "yuchi", "公孙": "gongsun", "慕容": "murong",
}

# 常见名字用字拼音（用于名部分的模糊匹配，覆盖高频字）
GIVEN = {
    "茂": "mao", "松": "song", "明": "ming", "华": "hua", "伟": "wei",
    "芳": "fang", "秀": "xiu", "英": "ying", "军": "jun", "强": "qiang",
    "磊": "lei", "洋": "yang", "勇": "yong", "艳": "yan", "杰": "jie",
    "娟": "juan", "涛": "tao", "超": "chao", "敏": "min", "静": "jing",
    "丽": "li", "鹏": "peng", "飞": "fei", "宇": "yu", "浩": "hao",
    "凯": "kai", "健": "jian", "俊": "jun", "文": "wen", "武": "wu",
    "建": "jian", "国": "guo", "志": "zhi", "海": "hai", "峰": "feng",
    "波": "bo", "斌": "bin", "峰": "feng", "涛": "tao", "亮": "liang",
    "刚": "gang", "辉": "hui", "东": "dong", "红": "hong", "梅": "mei",
    "兰": "lan", "云": "yun", "霞": "xia", "平": "ping", "新": "xin",
    "春": "chun", "晓": "xiao", "泽": "ze", "鑫": "xin", "鑫": "xin",
    "琳": "lin", "婷": "ting", "悦": "yue", "欣": "xin", "怡": "yi",
    "睿": "rui", "轩": "xuan", "宸": "chen", "珩": "heng", "璟": "jing",
    "博": "bo", "哲": "zhe", "涵": "han", "清": "qing", "源": "yuan",
    "毅": "yi", "恒": "heng", "凯": "kai", "锐": "rui", "钧": "jun",
    "楷": "kai", "振": "zhen", "赫": "he", "琦": "qi", "瑶": "yao",
    "紫": "zi", "萱": "xuan", "薇": "wei", "蕾": "lei", "茜": "qian",
    "珊": "shan", "琪": "qi", "羽": "yu", "辰": "chen", "昊": "hao",
    "旭": "xu", "晗": "han", "曦": "xi", "楠": "nan", "梓": "zi",
}


def _is_cn(text):
    return bool(text) and all("\u4e00" <= ch <= "\u9fff" for ch in text)


def split_cn_name(name):
    """把中文姓名拆成 (姓拼音, 名拼音)。

    支持复姓（欧阳、司马…）。返回 (surname_pinyin, given_pinyin) 或 (None, None)。
    """
    if not _is_cn(name):
        return None, None
    # 复姓优先
    if len(name) >= 3 and name[:2] in SURNAMES:
        sur = SURNAMES[name[:2]]
        given_chars = name[2:]
    elif name[0] in SURNAMES:
        sur = SURNAMES[name[0]]
        given_chars = name[1:]
    else:
        return None, None
    given = "".join(GIVEN.get(c, "") for c in given_chars)
    return sur, given


def match_cn_query(cn_query, english_name):
    """判断中文姓名查询是否匹配某个英文姓名。

    支持的形式（以「孙茂松 / Maosong Sun」为例）：
        Maosong Sun     姓在后
        Sun Maosong     姓在前
        M. Sun / Sun M  首字母
        Mao-Song Sun    带连字符
        Maosong         只写了名（姓缺省时也能命中）
    """
    sur, given = split_cn_name(cn_query)
    if not sur:
        return False
    low = (english_name or "").lower().replace("-", " ").replace(".", " ")
    tokens = [t for t in low.split() if t]
    if not tokens:
        return False

    joined = "".join(tokens)
    # 只写了一个英文名（没有姓氏段）时，按整名匹配
    if len(tokens) == 1:
        if given and (tokens[0] == given or joined.startswith(given)):
            return True
        return tokens[0] == sur

    # 姓必须在某一段里出现
    if not any(t == sur or t.startswith(sur) for t in tokens):
        return False
    if not given:
        return True      # 只给了姓，算匹配
    # 名的拼音连续出现，或首字母序列匹配
    if given in joined:
        return True
    initials = "".join(t[0] for t in tokens if t)
    if len(given) >= 1 and given[0] in initials:
        return True
    return False