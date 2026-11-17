# -*- coding: utf-8 -*-
"""生成 venue_meta.json：给 venue_links.json 里那 130 个 venue 补上
CCF 分级、国别、主办方、领域、一句话简介。

数据来源与口径（写进页面说明，别当成权威审定）：
  * CCF 分级按《中国计算机学会推荐国际学术会议和期刊目录》2022 版录入。
    只录 A/B/C 三档；不在目录里的留空（例如 PRX Quantum、QIP、FIE）。
  * 国别按主办学会/出版社所在国：ACM→美国(US)、IEEE→美国(US)、USENIX→美国(US)、
    IACR→国际(INT)、ELSEVIER→荷兰(NL)/英国(UK)、Springer→德国(DE)、
    aclanthology→US、IEEE-RA→US。
  * 分区（中科院分区）**不录**：那套目录每年调整且没有公开机器可读版，
    手工填一份必然过期，宁可不写也不写错的。
  * 简介是我们自己写的、面向「这个会/刊收什么稿」的一句话，不是官方描述。

用法：
    python make_venue_meta.py            # 写出 venue_meta.json
    python make_venue_meta.py --check    # 只报缺哪些 venue
"""

import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINKS = HERE / "venue_links.json"
OUT = HERE / "venue_meta.json"

# (CCF 等级, 类型, 国别, 领域, 一句话简介)
# CCF: A / B / C / ""（未收录）
# 国别: CN / US / EU / INT / JP …
META = {
    # ---------------- 计算机视觉 / 图形学 ----------------
    "CVPR": ("A", "会议", "US", "CV", "IEEE 计算机视觉与模式识别大会，视觉领域规模最大的主会；深度估计、检测、分割、生成都在这"),
    "ICCV": ("A", "会议", "US", "CV", "两年一届的国际计算机视觉大会，与 CVPR/ECCV 并称视觉三大主会"),
    "ECCV": ("A", "会议", "EU", "CV", "欧洲计算机视觉大会，两年一届，与 CVPR/ICCV 并列"),
    "3DV": ("B", "会议", "INT", "CV", "三维视觉专门会议，深度估计、三维重建、点云与小体量的三维工作很适合投这里"),
    "TPAMI": ("A", "期刊", "US", "CV", "IEEE 模式分析与机器智能汇刊，视觉与模式识别领域的旗舰期刊"),
    "IJCV": ("B", "期刊", "EU", "CV", "International Journal of Computer Vision，视觉领域老牌期刊"),
    "TIP": ("A", "期刊", "US", "CV", "IEEE 图像处理汇刊，偏图像处理的算法与底层视觉任务"),
    "TMI": ("B", "期刊", "US", "医学影像", "IEEE 医学成像汇刊，医学影像分析的核心期刊"),
    # 注意："TMI"/"TVCG" 这两个短名在 venue_links.json 里只以 "IEEE TMI"/"IEEE TVCG"
    # 的形式出现，但 venue_rules.json 用的是短名，两个键都留着查表用，
    # 所以 --check 的「多出来」名单里出现它们是正常的（不是错误）。
    "IEEE TMI": ("B", "期刊", "US", "医学影像", "同 IEEE TMI（另一种写法）"),
    "MedIA": ("B", "期刊", "EU", "医学影像", "Medical Image Analysis，医学影像分割/配准/诊断的权威刊物"),
    "MICCAI": ("B", "会议", "INT", "医学影像", "医学影像计算与计算机辅助干预大会，医学影像方向最主要的会议"),
    "ISBI": ("C", "会议", "US", "医学影像", "IEEE 生物医学成像国际研讨会，医学影像入门与短文的常用去处"),
    "SIGGRAPH": ("A", "会议", "US", "图形学", "ACM 计算机图形学与交互技术年会，渲染、几何、动画的主会场"),
    "SIGGRAPH Asia": ("B", "会议", "INT", "图形学", "SIGGRAPH 的亚洲区年会，图形学与可视化的同档次平台"),
    "TOG": ("A", "期刊", "US", "图形学", "ACM Transactions on Graphics，图形学顶级期刊，SIGGRAPH 论文常同时刊于此"),
    "TVCG": ("A", "期刊", "US", "可视化", "IEEE 可视化与计算机图形学汇刊，可视化与图形学并重"),
    "IEEE TVCG": ("A", "期刊", "US", "可视化", "同 IEEE TVCG（另一种写法）"),
    "UIST": ("B", "会议", "US", "人机交互", "ACM 用户界面软件与技术年会，交互技术与界面原型的顶会"),
    "CHI": ("A", "会议", "US", "人机交互", "ACM CHI 人机交互大会，HCI 领域规模与影响力最大"),
    "CSCW": ("B", "会议", "US", "人机交互", "ACM 计算机支持的协同工作与社会计算会议"),
    "TOCHI": ("A", "期刊", "US", "人机交互", "ACM Transactions on Computer-Human Interaction，HCI 权威期刊"),
    "IEEE TGRS": ("B", "期刊", "US", "遥感", "IEEE 地球科学与遥感汇刊，遥感影像分析主力刊物"),
    "ISPRS Journal": ("B", "期刊", "EU", "遥感", "ISPRS 摄影测量与遥感杂志，遥感与对地观测的权威期刊"),
    "IGARSS": ("", "会议", "US", "遥感", "IEEE 地球科学与遥感国际研讨会，规模化但受众广的遥感会议"),

    # ---------------- 机器学习 / AI 基础 ----------------
    "NeurIPS": ("A", "会议", "US", "ML", "神经信息处理系统大会，机器学习三大主会之一"),
    "ICML": ("A", "会议", "INT", "ML", "国际机器学习大会，偏理论与方法创新"),
    "ICLR": ("A", "会议", "INT", "ML", "国际学习表征会议，深度学习表征学习的主场，审稿公开"),
    "AAAI": ("A", "会议", "US", "AI", "AAAI 人工智能大会，AI 综合类顶会，规模大、接收面广"),
    "IJCAI": ("A", "会议", "INT", "AI", "国际人工智能联合会议，AI 综合类老牌顶会"),
    "JMLR": ("A", "期刊", "US", "ML", "Journal of Machine Learning Research，机器学习最重要的期刊之一，开放获取"),
    "Nature Machine Intelligence": ("", "期刊", "UK", "ML", "Nature 旗下机器智能期刊，偏交叉与有影响力的综合工作，不是常规投稿目标"),
    "PETS": ("B", "会议", "INT", "隐私", "Privacy Enhancing Technologies 会议，差分隐私/联邦学习等隐私技术的专门会"),

    # ---------------- NLP ----------------
    "ACL": ("A", "会议", "INT", "NLP", "国际计算语言学协会年会，NLP 三大主会之首"),
    "EMNLP": ("A", "会议", "INT", "NLP", "自然语言处理经验方法会议，NLP 主力会议"),
    "NAACL": ("B", "会议", "US", "NLP", "北美计算语言学协会年会，ACL 系列的北美分支"),
    "COLING": ("B", "会议", "INT", "NLP", "国际计算语言学大会，两年一届"),
    "TACL": ("A", "期刊", "INT", "NLP", "Transactions of the ACL，NLP 顶级期刊，文章可在 ACL 系列会上报告"),
    "Computational Linguistics": ("A", "期刊", "US", "NLP", "MIT Press 的计算语言学季刊，NLP 理论性工作的重要出口"),

    # ---------------- 数据挖掘 / 信息检索 ----------------
    "KDD": ("A", "会议", "US", "DM", "ACM SIGKDD 知识发现与数据挖掘大会，数据挖掘主会"),
    "SIGIR": ("A", "会议", "US", "IR", "ACM SIGIR 信息检索大会，检索方向的最高会议"),
    "WWW": ("A", "会议", "INT", "Web", "The Web Conference，万维网大会，Web 挖掘与检索并重"),
    "WSDM": ("B", "会议", "US", "IR", "ACM 网络搜索与数据挖掘会议，偏检索与推荐"),
    "CIKM": ("B", "会议", "US", "DM", "ACM 信息与知识管理会议，数据挖掘与检索的中坚会议"),
    "TKDE": ("A", "期刊", "US", "DM", "IEEE 知识与数据工程汇刊，数据挖掘与知识工程权威期刊"),

    # ---------------- 数据库 / 系统 / 网络 ----------------
    "SIGMOD": ("A", "会议", "US", "DB", "ACM SIGMOD 数据管理国际会议，数据库两大主会之一"),
    "VLDB": ("A", "会议", "INT", "DB", "Very Large Data Bases 会议，数据库系统与查询处理主会"),
    "ICDE": ("A", "会议", "US", "DB", "IEEE 数据工程国际会议，数据库三大主会之一"),
    "TODS": ("A", "期刊", "US", "DB", "ACM Transactions on Database Systems，数据库理论权威期刊"),
    "VLDBJ": ("A", "期刊", "EU", "DB", "The VLDB Journal，数据库系统领域最好的期刊之一"),
    "SOSP": ("A", "会议", "US", "系统", "ACM 操作系统原理大会，系统方向两大会之一"),
    "OSDI": ("A", "会议", "US", "系统", "USENIX 操作系统设计与实现会议，系统方向最高平台"),
    "EuroSys": ("A", "会议", "EU", "系统", "欧洲计算机系统大会，系统方向的欧洲主场"),
    "USENIX ATC": ("A", "会议", "US", "系统", "USENIX 年度技术会议，系统与运维方向主力会议"),
    "ATC": ("A", "会议", "US", "系统", "同 USENIX ATC，实际是同一会议的两个称呼"),
    "ISCA": ("A", "会议", "US", "体系结构", "国际计算机体系结构大会，体系结构三大主会之一"),
    "MICRO": ("A", "会议", "US", "体系结构", "IEEE/ACM 微架构国际研讨会，体系结构三大主会之一"),
    "HPCA": ("A", "会议", "US", "体系结构", "高性能计算机体系结构国际研讨会，体系结构三大主会之一"),
    "ASPLOS": ("A", "会议", "US", "体系结构", "体系结构、编程语言与操作系统的交叉会议，系统栈整体设计常投这里"),
    "SC": ("A", "会议", "US", "高性能计算", "高性能计算、网络、存储与分析国际会议"),
    "TPDS": ("A", "期刊", "US", "并行计算", "IEEE 并行与分布式系统汇刊"),
    "SIGCOMM": ("A", "会议", "US", "网络", "ACM SIGCOMM，计算机网络方向最高会议"),
    "INFOCOM": ("A", "会议", "US", "网络", "IEEE INFOCOM，网络方向规模最大的顶会"),
    "NSDI": ("A", "会议", "US", "网络", "USENIX 网络系统设计与实现研讨会"),
    "MobiCom": ("A", "会议", "US", "移动网络", "ACM 移动计算与网络国际会议"),
    "MobiSys": ("B", "会议", "US", "移动系统", "ACM 移动系统、应用与服务国际会议"),
    "CoNEXT": ("B", "会议", "EU", "网络", "ACM 新兴网络实验与技术会议"),
    "SenSys": ("B", "会议", "US", "传感网络", "ACM 嵌入式网络化传感系统会议"),
    "IPSN": ("B", "会议", "US", "传感网络", "国际信息处理与传感网络研讨会"),
    "IoTDI": ("B", "会议", "US", "物联网", "ACM/IEEE 物联网设计与实现国际会议"),
    "RTSS": ("A", "会议", "US", "实时系统", "IEEE 实时系统研讨会，实时调度与时限分析的主会"),
    "EMSOFT": ("B", "会议", "US", "嵌入式", "嵌入式软件国际会议，与 ESWeek 同期举办"),
    "IEEE TCAD": ("A", "期刊", "US", "EDA", "IEEE 计算机辅助设计汇刊，EDA 与芯片设计自动化权威期刊"),
    "DAC": ("A", "会议", "US", "EDA", "设计自动化大会，EDA 领域最大的会议"),
    "ICCAD": ("A", "会议", "US", "EDA", "国际计算机辅助设计大会，EDA 主力会议"),
    "DATE": ("B", "会议", "EU", "EDA", "欧洲设计与测试会议，EDA 与嵌入式系统的欧洲主场"),

    # ---------------- 安全 / 密码学 ----------------
    "IEEE S&P": ("A", "会议", "US", "安全", "IEEE 安全与隐私研讨会（Oakland），安全四大顶会之一"),
    "CCS": ("A", "会议", "US", "安全", "ACM 计算机与通信安全会议，安全四大顶会之一"),
    "USENIX Security": ("A", "会议", "US", "安全", "USENIX 安全研讨会，安全四大顶会之一"),
    "NDSS": ("A", "会议", "US", "安全", "网络与分布式系统安全研讨会，安全四大顶会之一"),
    "TDSC": ("A", "期刊", "US", "安全", "IEEE 可靠与安全计算汇刊"),
    "TCC": ("A", "期刊", "US", "安全", "IEEE 计算机汇刊，IEEE 最早的学术期刊之一，综合类"),
    "IEEE CSF": ("A", "会议", "EU", "安全", "IEEE 计算机安全基础研讨会，偏安全形式化与协议证明"),
    "SOUPS": ("B", "会议", "US", "安全", "可用安全研讨会，偏人因与用户行为的安全研究"),
    "CRYPTO": ("A", "会议", "US", "密码学", "IACR 国际密码学会议，密码学两大顶会之一"),
    "EUROCRYPT": ("A", "会议", "EU", "密码学", "IACR 欧洲密码学会议，密码学两大顶会之一"),
    "Journal of Cryptology": ("A", "期刊", "INT", "密码学", "IACR 主办的国际密码学杂志"),
    "Designs, Codes and Cryptography": ("B", "期刊", "NL", "密码学", "设计、编码与密码学杂志，偏组合设计与编码理论"),
    "Financial Cryptography": ("B", "会议", "INT", "区块链", "金融密码学与数据安全国际会议，区块链与加密货币研究常投这里"),
    "PoPETs": ("B", "期刊", "INT", "隐私", "Privacy Enhancing Technologies 的期刊形式，与 PETS 会议同源"),

    # ---------------- 软件工程 / 程序语言 ----------------
    "ICSE": ("A", "会议", "US", "软件工程", "国际软件工程大会，软工方向最高会议"),
    "FSE": ("A", "会议", "US", "软件工程", "ACM 软件工程基础会议（原 ESEC/FSE）"),
    "ASE": ("A", "会议", "US", "软件工程", "IEEE/ACM 自动化软件工程国际会议"),
    "ISSTA": ("A", "会议", "US", "软件测试", "软件测试与分析国际研讨会，测试方向主会"),
    "TSE": ("A", "期刊", "US", "软件工程", "IEEE 软件工程汇刊，软工领域最权威期刊"),
    "EMSE": ("B", "期刊", "DE", "软件工程", "经验软件工程杂志，偏实证研究与工业实践"),
    "PLDI": ("A", "会议", "US", "程序语言", "ACM 编程语言设计与实现会议"),
    "POPL": ("A", "会议", "US", "程序语言", "ACM 程序语言原理研讨会，偏形式化与类型系统"),
    "OOPSLA": ("A", "会议", "US", "程序语言", "面向对象程序设计、系统、语言与应用会议"),
    "ICFP": ("A", "会议", "US", "程序语言", "ACM 国际函数式编程会议"),
    "TOPLAS": ("A", "期刊", "US", "程序语言", "ACM 程序设计语言与系统汇刊"),
    "CAV": ("A", "会议", "INT", "形式化", "计算机辅助验证国际会议，形式化方法与模型检验主会"),
    "TACAS": ("B", "会议", "EU", "形式化", "软件工具与算法构造分析会议，与 ETAPS 同期"),

    # ---------------- 理论 ----------------
    "STOC": ("A", "会议", "US", "理论", "ACM 计算理论研讨会，理论计算机科学最高会议之一"),
    "FOCS": ("A", "会议", "US", "理论", "IEEE 计算机科学基础研讨会，与 STOC 并列的理论顶会"),
    "SODA": ("A", "会议", "US", "算法", "ACM-SIAM 离散算法研讨会"),
    "ICALP": ("A", "会议", "EU", "理论", "国际自动机、语言与程序设计研讨会，欧洲理论主场"),
    "SICOMP": ("A", "期刊", "US", "理论", "SIAM 计算杂志，理论计算机科学权威期刊"),
    "JACM": ("A", "期刊", "US", "理论", "Journal of the ACM，计算机科学最老牌的综合性顶刊"),
    "Algorithmica": ("B", "期刊", "DE", "算法", "算法设计与分析的经典期刊"),
    "ACM TALG": ("B", "期刊", "US", "算法", "ACM 算法汇刊"),
    "Annals of Statistics": ("A", "期刊", "US", "统计", "数理统计最高刊物，统计学习方法常投这里"),
    "PRX Quantum": ("", "期刊", "US", "量子", "APS 量子领域期刊，量子计算与量子信息的重要出口"),
    "Quantum": ("", "期刊", "INT", "量子", "开放获取的量子科学期刊，量子算法与信息理论"),
    "QIP": ("", "会议", "INT", "量子", "量子信息处理国际会议，量子算法/纠错/复杂度方向"),

    # ---------------- 机器人 / 交叉 ----------------
    "ICRA": ("A", "会议", "US", "机器人", "IEEE 国际机器人与自动化会议，机器人方向规模最大"),
    "IROS": ("", "会议", "US", "机器人", "IEEE/RSJ 智能机器人与系统国际会议，机器人主力会议"),
    "RSS": ("A", "会议", "US", "机器人", "机器人科学与系统会议，偏算法与系统集成的精品会"),
    "CoRL": ("B", "会议", "US", "机器人学习", "机器人学习会议，机器人 + 强化学习/模仿学习的专门会"),
    "T-RO": ("A", "期刊", "US", "机器人", "IEEE 机器人汇刊，机器人领域最权威期刊"),
    "TRO": ("A", "期刊", "US", "机器人", "同 IEEE T-RO（T-RO 的另一种写法）"),
    "RA-L": ("B", "期刊", "US", "机器人", "IEEE 机器人与自动化快报，篇幅短、周期快，常与 ICRA/IROS 联动"),
    "ACM MM": ("A", "会议", "US", "多媒体", "ACM 国际多媒体会议，多模态与视频理解主会"),
    "AIES": ("B", "会议", "US", "AI 伦理", "AAAI/ACM 人工智能伦理与社会会议"),
    "FAccT": ("B", "会议", "US", "AI 伦理", "公平、问责与透明会议，AI 治理与社会影响"),
    "Bioinformatics": ("B", "期刊", "UK", "生物信息", "牛津大学出版社的生物信息学期刊"),
    "JAMIA": ("A", "期刊", "US", "医学信息", "美国医学信息学会会刊，临床信息学权威期刊"),

    # ---------------- 教育 / 其他 ----------------
    "SIGCSE": ("A", "会议", "US", "计算机教育", "ACM 计算机科学教育技术研讨会，CS 教育研究主会"),
    "ITiCSE": ("", "会议", "EU", "计算机教育", "创新与技术计算机科学教育会议"),
    "ICER": ("", "会议", "US", "计算机教育", "国际计算教育研究会议，偏教育实证研究"),
    "TOCE": ("B", "期刊", "US", "计算机教育", "ACM 计算教育汇刊"),
    "FIE": ("", "会议", "US", "工程教育", " frontiers in Education 工程教育前沿会议"),
}


# ---- 方向 → 领域标签的中文名，供筛选下拉框用 ----
FIELD_CN = {
    "CV": "计算机视觉", "医学影像": "医学影像", "图形学": "图形与渲染",
    "可视化": "可视化", "人机交互": "人机交互", "遥感": "遥感与对地观测",
    "ML": "机器学习", "AI": "人工智能综合", "NLP": "自然语言处理",
    "DM": "数据挖掘", "IR": "信息检索", "Web": "Web 与网络数据",
    "DB": "数据库", "系统": "操作系统与系统", "体系结构": "体系结构",
    "高性能计算": "高性能计算", "并行计算": "并行计算", "网络": "计算机网络",
    "移动网络": "移动网络", "移动系统": "移动系统", "传感网络": "传感网络",
    "物联网": "物联网", "实时系统": "实时系统", "嵌入式": "嵌入式系统",
    "EDA": "EDA 与芯片设计", "安全": "网络与系统安全", "密码学": "密码学",
    "隐私": "隐私保护", "区块链": "区块链与金融密码",
    "软件工程": "软件工程", "软件测试": "软件测试", "程序语言": "程序语言",
    "形式化": "形式化方法", "理论": "理论计算机", "算法": "算法",
    "统计": "统计与概率", "量子": "量子计算",
    "机器人": "机器人", "机器人学习": "机器人学习", "多媒体": "多媒体",
    "AI 伦理": "AI 伦理与治理", "生物信息": "生物信息", "医学信息": "医学信息学",
    "计算机教育": "计算机教育", "工程教育": "工程教育",
}

COUNTRY_CN = {
    "CN": "中国", "US": "美国", "EU": "欧洲", "INT": "国际", "UK": "英国",
    "DE": "德国", "NL": "荷兰", "JP": "日本", "CA": "加拿大", "SG": "新加坡",
}

# ---------------------------------------------------------------- 别名归一
# venue_links.json 与 venue_rules.json 对同一个 venue 用了不同写法，
# 直接按名字列出来就会出现两条（用户实测看到 IEEE TVCG 和 TVCG 并列）。
# 这里给出「别名 → 规范名」，build() 会把别名条目丢掉、只留规范名，
# 并把 alias 表一起写进 venue_meta.json，供 recommend 结果反查用。
CANON = {
    "TMI": "IEEE TMI",          # venue_rules 用短名
    "TVCG": "IEEE TVCG",        # venue_rules 用短名
    "ATC": "USENIX ATC",        # 同一个会，官网同一个 USENIX 页面
    "TRO": "T-RO",              # IEEE T-RO 的两种写法
    "PoPETs": "PETS",           # PoPETs 是 PETS 的期刊形式，同一主办方
}


def build():
    links = json.loads(io.open(LINKS, encoding="utf-8").read())["links"]
    out, missing, dropped = {}, [], []
    for name, lk in links.items():
        canon = CANON.get(name, name)
        if canon != name:
            # 别名条目直接跳过，由规范名那条统一承担
            dropped.append(name)
            continue
        m = META.get(name) or META.get(canon)
        if not m:
            missing.append(name)
            continue
        ccf, vtype, country, field, intro = m
        out[name] = {
            "name": name,
            "type": vtype,
            "ccf": ccf,
            "country": country,
            "country_cn": COUNTRY_CN.get(country, country),
            "field": field,
            "field_cn": FIELD_CN.get(field, field),
            "intro": intro,
            "url": lk.get("url", ""),
            "label": lk.get("label", name),
        }
    doc = {
        "version": "2026-11-15",
        "note": (
            "CCF 分级按《中国计算机学会推荐国际学术会议和期刊目录》2022 版录入，"
            "只覆盖 A/B/C 三档；不在目录里的留空。"
            "国别按主办学会/出版社所在国。**不含中科院分区与影响因子**（每年调整、"
            "无公开机器可读版，宁可留空也不写错）。简介是自写的一句话，不是官方描述。"
        ),
        "fields": FIELD_CN,
        "countries": COUNTRY_CN,
        "alias": CANON,
        "venues": out,
    }
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(doc, ensure_ascii=False, indent=1))
    print("写出 %s：%d 个 venue" % (OUT.name, len(out)))
    if dropped:
        print("按别名合并掉的：%s" % "、".join(dropped))
    if missing:
        print("缺元数据的 %d 个：" % len(missing))
        for n in missing:
            print("  ", n)
    # 统计
    from collections import Counter
    print("CCF 分布：", dict(Counter(v["ccf"] or "未收录" for v in out.values())))
    print("类型分布：", dict(Counter(v["type"] for v in out.values())))
    print("国别分布：", dict(Counter(v["country_cn"] for v in out.values())))
    return 0


def check():
    links = json.loads(io.open(LINKS, encoding="utf-8").read())["links"]
    missing = [n for n in links if n not in META]
    # 别名键（TMI/TVCG/ATC/TRO 这些）是给 venue_rules 短名查表用的，不算多余
    _ALIAS = {"TMI", "TVCG"}
    extra = [n for n in META if n not in links and n not in _ALIAS]
    print("links 里共 %d 个，META 里共 %d 个" % (len(links), len(META)))
    if missing:
        print("缺元数据：", missing)
    if extra:
        print("多出来的（links 里没有）：", extra)
    return 0 if not missing and not extra else 1


if __name__ == "__main__":
    sys.exit(check() if "--check" in sys.argv else build())