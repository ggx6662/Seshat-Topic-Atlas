#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补齐院校的地区字段。

问题
----
institutions_cn.json 来自 OpenAlex，其中有 618 所教育机构没有 region 字段
（哈尔滨工业大学、同济、华南理工等名校都在内），
导致这些院校的导师在界面里地区显示为空，按省份筛选时被漏掉。

做法
----
这些机构 100% 都有 city 字段，因此用「城市 → 省级地区」映射补齐。
只补 region 为空的记录，已有 region 的一律不动。

用法
----
python fix_institution_regions.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSTITUTIONS = HERE / "institutions_cn.json"

# 城市 / 别名（小写） → OpenAlex 风格的省级地区英文名
CITY_REGION = {
    # —— 直辖市
    "beijing": "Beijing", "shanghai": "Shanghai", "tianjin": "Tianjin",
    "chongqing": "Chongqing", "pudong": "Shanghai",
    # —— 河北 / 山西 / 内蒙古
    "baoding": "Hebei", "tangshan": "Hebei", "qinhuangdao": "Hebei",
    "cangzhou": "Hebei", "chengde": "Hebei", "handan": "Hebei",
    "langfang": "Hebei", "shijiazhuang": "Hebei", "zhangjiakou": "Hebei",
    "taiyuan": "Shanxi", "changzhi": "Shanxi", "huozhou": "Shanxi",
    "jinzhong": "Shanxi", "linfen": "Shanxi", "lvliang": "Shanxi",
    "xinzhou": "Shanxi", "yuncheng": "Shanxi", "yulinshi": "Shaanxi",
    "baotou": "Inner Mongolia", "chifeng": "Inner Mongolia",
    "hailar": "Inner Mongolia", "hohhot": "Inner Mongolia",
    "bayannur shi": "Inner Mongolia",
    # —— 辽宁 / 吉林 / 黑龙江
    "dalian": "Liaoning", "dandong": "Liaoning", "fuxin": "Liaoning",
    "jinzhou": "Liaoning", "liaoyang": "Liaoning", "shenyang": "Liaoning",
    "yingkou": "Liaoning", "anshan": "Liaoning",
    "changchun": "Jilin", "baicheng": "Jilin", "jilin city": "Jilin",
    "siping": "Jilin", "tonghua": "Jilin", "yanji": "Jilin",
    "harbin": "Heilongjiang", "heihe": "Heilongjiang", "jixi": "Heilongjiang",
    "mudanjiang": "Heilongjiang", "qiqihar": "Heilongjiang",
    "suihua": "Heilongjiang", "daqing": "Heilongjiang",
    # —— 江苏 / 浙江 / 安徽
    "nanjing": "Jiangsu", "suzhou": "Jiangsu", "wuxi": "Jiangsu",
    "changzhou": "Jiangsu", "xuzhou": "Jiangsu", "yancheng": "Jiangsu",
    "yangzhou": "Jiangsu", "zhenjiang": "Jiangsu", "nantong": "Jiangsu",
    "jiangning": "Jiangsu", "zhangjiagang": "Jiangsu", "yixing": "Jiangsu",
    "huai'an": "Jiangsu", "yucheng": "Jiangsu",
    "hangzhou": "Zhejiang", "ningbo": "Zhejiang", "wenzhou": "Zhejiang",
    "jiaxing": "Zhejiang", "jinhua": "Zhejiang", "lishui": "Zhejiang",
    "shaoxing": "Zhejiang", "taizhou": "Zhejiang", "zhoushan": "Zhejiang",
    "haining": "Zhejiang", "tongxiang": "Zhejiang", "shangyu": "Zhejiang",
    "zhuji": "Zhejiang", "zhoushan city": "Zhejiang",
    "hefei": "Anhui", "anqing": "Anhui", "bengbu": "Anhui",
    "chaohu": "Anhui", "chizhou": "Anhui", "huainan": "Anhui",
    "huangshan city": "Anhui", "luan": "Anhui", "lu'an": "Anhui",
    "ma'anshan city": "Anhui", "tongling": "Anhui", "wuhu": "Anhui",
    "fuyang": "Anhui", "suzhou city": "Anhui",
    # —— 福建 / 江西 / 山东
    "fuzhou": "Fujian", "xiamen": "Fujian", "amoy": "Fujian",
    "quanzhou": "Fujian", "longyan": "Fujian", "ningde": "Fujian",
    "putian": "Fujian", "zhangzhou": "Fujian", "sanming": "Fujian",
    "nanchang": "Jiangxi", "ganzhou": "Jiangxi", "jingdezhen": "Jiangxi",
    "jiujiang": "Jiangxi", "pingxiang": "Jiangxi", "shangrao": "Jiangxi",
    "xinyu": "Jiangxi", "yichun": "Jiangxi", "jiangxi": "Jiangxi",
    "jinan": "Shandong", "qingdao": "Shandong", "yantai": "Shandong",
    "weifang": "Shandong", "zibo": "Shandong", "linyi": "Shandong",
    "jining": "Shandong", "taishan": "Shandong", "taian": "Shandong",
    "tai'an": "Shandong", "heze": "Shandong", "binzhou": "Shandong",
    "qufu": "Shandong", "weihai": "Shandong", "liaocheng": "Shandong",
    "dezhou": "Shandong", "rizhao": "Shandong",
    # —— 河南 / 湖北 / 湖南
    "zhengzhou": "Henan", "kaifeng": "Henan", "anyang": "Henan",
    "jiaozuo": "Henan", "luohe": "Henan", "luoyang": "Henan",
    "nanyang": "Henan", "pingdingshan": "Henan", "shangqiu": "Henan",
    "xinxiang": "Henan", "xuchang": "Henan", "zhoukou": "Henan",
    "zhumadian": "Henan", "xinyang": "Henan",
    "wuhan": "Hubei", "huangzhou": "Hubei", "xiangyang": "Hubei",
    "xianning": "Hubei", "xiaogan": "Hubei", "yichang": "Hubei",
    "shiyan": "Hubei", "jingzhou": "Hubei",
    "changsha": "Hunan", "chenzhou": "Hunan", "hengyang": "Hunan",
    "loudi": "Hunan", "xiangtan": "Hunan", "yueyang": "Hunan",
    "zhuzhou": "Hunan", "hunan": "Hunan", "jishou": "Hunan",
    # —— 广东 / 广西 / 海南
    "guangzhou": "Guangdong", "shenzhen": "Guangdong", "zhuhai": "Guangdong",
    "foshan": "Guangdong", "dongguan": "Guangdong", "jiangmen": "Guangdong",
    "shantou": "Guangdong", "zhanjiang": "Guangdong", "zhaoqing": "Guangdong",
    "chaozhou": "Guangdong", "guangdongdi": "Guangdong", "shaoguan": "Guangdong",
    "jieyang": "Guangdong", "maoming": "Guangdong", "heyuan": "Guangdong",
    "nanning": "Guangxi", "guilin": "Guangxi", "qinzhou": "Guangxi",
    "beihai": "Guangxi", "liuzhou": "Guangxi", "yulin": "Guangxi",
    "haikou": "Hainan", "sanya": "Hainan",
    # —— 四川 / 贵州 / 云南 / 西藏
    "chengdu": "Sichuan", "mianyang": "Sichuan", "yibin": "Sichuan",
    "neijiang": "Sichuan", "dazhou": "Sichuan", "lasa": "Tibet",
    "luzhou": "Sichuan", "nanchong": "Sichuan",
    "guiyang": "Guizhou", "guizhou": "Guizhou", "anshun": "Guizhou",
    "duyun": "Guizhou", "liupanshui": "Guizhou", "zunyi": "Guizhou",
    "kunming": "Yunnan", "chuxiong": "Yunnan", "qujing": "Yunnan",
    "yuxi": "Yunnan", "pu'er": "Yunnan", "pu’er": "Yunnan",
    "wenshan city": "Yunnan", "dali": "Yunnan",
    "lhasa": "Tibet", "xigaze": "Tibet",
    # —— 陕西 / 甘肃 / 青海 / 宁夏 / 新疆
    "xi'an": "Shaanxi", "xian": "Shaanxi", "xianyang": "Shaanxi",
    "ankang": "Shaanxi", "hanzhong": "Shaanxi", "weinan": "Shaanxi",
    "shangxian": "Shaanxi", "yan'an": "Shaanxi", "baoji": "Shaanxi",
    "lanzhou": "Gansu", "zhangye": "Gansu", "guyuan": "Ningxia",
    "tianshui": "Gansu", "jiuquan": "Gansu",
    "xining": "Qinghai", "hezuo": "Gansu",
    "yinchuang": "Ningxia", "yinchuan": "Ningxia",
    "ürümqi": "Xinjiang", "urumqi": "Xinjiang", "kashgar": "Xinjiang",
    "changji": "Xinjiang", "xinjiang": "Xinjiang", "shihezi": "Xinjiang",
    # —— 港澳台
    "hong kong": "Hong Kong",
    # —— 区镇级城市名 / 特殊写法（按机构所在地人工确认）
    "ji'an": "Jiangxi", "ji’an": "Jiangxi",
    "chenzhouzhai": "Hunan", "tangdukou": "Hunan", "jinxi": "Hunan",
    "chuzhou": "Anhui", "yishan": "Guangxi", "baise city": "Guangxi",
    "lishi": "Shanxi", "chaoyang": "Beijing", "jiangxiangzhen": "Hubei",
    "gongyi": "Henan", "jinggangshan": "Jiangxi",
}

# 城市名无法唯一确定省份时，用机构名做二次判断
NAME_HINTS = [
    ("hunan", "Hunan"), ("jiangxi", "Jiangxi"), ("guizhou", "Guizhou"),
    ("xinjiang", "Xinjiang"), ("hubei", "Hubei"), ("hebei", "Hebei"),
    ("shandong", "Shandong"), ("henan", "Henan"), ("anhui", "Anhui"),
    ("fujian", "Fujian"), ("guangxi", "Guangxi"), ("yunnan", "Yunnan"),
    ("sichuan", "Sichuan"), ("jiangsu", "Jiangsu"), ("zhejiang", "Zhejiang"),
    ("guangdong", "Guangdong"), ("shaanxi", "Shaanxi"), ("shanxi", "Shanxi"),
    ("gansu", "Gansu"), ("liaoning", "Liaoning"), ("jilin", "Jilin"),
    ("heilongjiang", "Heilongjiang"), ("qinghai", "Qinghai"),
    ("ningxia", "Ningxia"), ("hainan", "Hainan"), ("tibet", "Tibet"),
]


def resolve(institution):
    city = (institution.get("city") or "").strip().lower()
    if city in CITY_REGION:
        return CITY_REGION[city]
    name = (institution.get("name") or "").lower()
    for hint, region in NAME_HINTS:
        if hint in name:
            return region
    return ""


def main():
    data = json.loads(INSTITUTIONS.read_text(encoding="utf-8"))
    institutions = data.get("institutions", [])
    fixed, unresolved = 0, []
    for inst in institutions:
        if inst.get("region"):
            continue
        region = resolve(inst)
        if region:
            inst["region"] = region
            fixed += 1
        else:
            unresolved.append((inst.get("name", ""), inst.get("city", "")))

    data["region_fixed"] = fixed
    INSTITUTIONS.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print("补齐地区:", fixed, " 仍未知:", len(unresolved))
    for name, city in unresolved[:25]:
        print("   ?", name, "|", city)


if __name__ == "__main__":
    main()