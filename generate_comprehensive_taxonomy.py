#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the supplemental computer-science research taxonomy.

The taxonomy is grounded in:
  * ACM/IEEE-CS/AAAI Computer Science Curricula 2023 knowledge areas
  * CCF technical-committee research areas
  * active research topics represented in the local advisor index

This file is a curated, editable source of truth.  ``kb_widget.py`` merges
the generated JSON with the older taxonomy files so existing local data is
never discarded.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "research_taxonomy_comprehensive.json"


def _items(text: str) -> list[str]:
    return [item.strip() for item in text.split("|") if item.strip()]


def f(name: str, aliases: str = "", keywords: str = "") -> dict:
    alias_out, keyword_out = [], []
    for token in _items(aliases) + _items(keywords):
        target = keyword_out if re.search(r"[A-Za-z]", token) else alias_out
        if token not in target:
            target.append(token)
    return {
        "name": name,
        "aliases": alias_out,
        "keywords": keyword_out,
    }


CATEGORIES = {
    # Extend established categories rather than renaming them.  This keeps
    # existing advisor mappings, memories, and exports valid.
    "人工智能": {
        "venues": ["NeurIPS", "ICML", "ICLR", "AAAI", "IJCAI", "TPAMI"],
        "subs": [
            f("知识表示与推理", "知识表示|knowledge representation|推理|reasoning"),
            f("规划与搜索", "自动规划|路径规划|planning|search"),
            f("概率图模型与贝叶斯推断", "概率图模型|贝叶斯网络|probabilistic graphical model|Bayesian inference"),
            f("多智能体系统", "多智能体|multi-agent system|multiagent"),
            f("神经符号人工智能", "神经符号|neuro-symbolic|symbolic AI"),
            f("AutoML与神经架构搜索", "AutoML|神经架构搜索|NAS|neural architecture search"),
            f("智能体与世界模型", "AI智能体|agent|world model|world models"),
            f("AI评测与基准", "AI评测|模型评测|benchmark|evaluation"),
            f("类脑与神经形态智能", "类脑计算|neuromorphic|spiking intelligence"),
        ],
    },
    "计算机视觉": {
        "venues": ["CVPR", "ICCV", "ECCV", "TPAMI", "IJCV"],
        "subs": [
            f("视觉语言与开放词汇视觉", "视觉语言模型|开放词汇|VLM|vision-language|open-vocabulary"),
            f("指代分割与视觉定位", "指代分割|视觉定位|referring segmentation|visual grounding"),
            f("人体与动作理解", "人体姿态|动作识别|human pose|action recognition"),
            f("人脸与生物特征识别", "人脸识别|生物特征|face recognition|biometrics"),
            f("视频生成与世界模型", "视频生成|video generation|video world model"),
            f("生成式视觉与扩散模型", "图像生成|扩散模型|diffusion model|generative vision"),
            f("医学图像分析", "医学图像|医学影像|medical image analysis"),
            f("遥感与航空视觉", "遥感影像|航空视觉|remote sensing|aerial vision"),
            f("工业视觉与缺陷检测", "工业视觉|缺陷检测|industrial vision|defect detection"),
            f("多相机与全景视觉", "多相机|全景视觉|multi-camera|omnidirectional vision"),
        ],
    },
    "自然语言处理": {
        "venues": ["ACL", "EMNLP", "NAACL", "TACL", "COLING"],
        "subs": [
            f("语法分析与语言结构", "句法分析|语言结构|syntax|parsing"),
            f("语义理解与知识增强", "语义理解|知识增强|semantic understanding|knowledge-enhanced NLP"),
            f("问答与推理", "问答系统|question answering|reasoning"),
            f("可控文本生成", "可控生成|text generation|controllable generation"),
            f("对话系统与工具智能体", "对话系统|tool agent|dialogue system"),
            f("大模型安全与对齐", "大模型安全|LLM safety|LLM alignment"),
            f("语音增强与声学事件", "语音增强|声学事件|speech enhancement|acoustic event"),
            f("情感分析与立场识别", "情感分析|立场识别|sentiment analysis|stance detection"),
        ],
    },
    "数据挖掘与信息检索": {
        "venues": ["KDD", "SIGIR", "WWW", "WSDM", "CIKM", "TKDE"],
        "subs": [
            f("图神经网络与图学习", "图神经网络|GNN|graph learning"),
            f("序列与因果推荐", "序列推荐|因果推荐|sequential recommendation|causal recommendation"),
            f("神经信息检索", "神经检索|neural IR|dense retrieval"),
            f("知识图谱推理", "知识图谱|knowledge graph reasoning"),
            f("社会网络分析", "社会网络|social network analysis"),
            f("数据流挖掘", "流数据挖掘|data stream mining"),
            f("表格数据学习", "表格学习|tabular learning|tabular data"),
            f("隐私保护数据挖掘", "隐私保护挖掘|privacy-preserving data mining"),
        ],
    },
    "系统与网络": {
        "venues": ["SOSP", "OSDI", "EuroSys", "USENIX ATC", "ASPLOS"],
        "subs": [
            f("操作系统内核与调度", "操作系统|内核|内核调度|OS kernel|scheduler"),
            f("内存管理与文件系统", "内存管理|文件系统|memory management|file system"),
            f("实时与嵌入式系统", "实时系统|real-time system|embedded OS"),
            f("容错与崩溃一致性", "容错|崩溃一致性|fault tolerance|crash consistency"),
            f("系统性能建模", "系统性能|性能建模|system performance|performance modeling"),
            f("eBPF与内核可观测性", "eBPF|内核可观测性|kernel observability"),
            f("系统形式化验证", "系统验证|system verification|formal systems"),
            f("机器学习系统", "MLSys|机器学习系统|ML systems"),
            f("系统软件与运行时", "系统软件|system software|runtime system"),
        ],
    },
    "安全与隐私": {
        "venues": ["IEEE S&P", "CCS", "USENIX Security", "NDSS", "TDSC"],
        "subs": [
            f("机密计算与可信执行环境", "机密计算|TEE|confidential computing|trusted execution"),
            f("差分隐私与数据匿名化", "差分隐私|数据匿名化|differential privacy|anonymization"),
            f("密码协议分析", "密码协议分析|protocol analysis|cryptographic protocol"),
            f("漏洞生态与安全度量", "漏洞生态|安全度量|vulnerability ecosystem|security metrics"),
            f("安全治理与风险管理", "安全治理|风险管理|security governance|risk management"),
            f("安全评测与基准", "安全评测|安全基准|security benchmark|security evaluation"),
        ],
    },
    "软件工程": {
        "venues": ["ICSE", "FSE", "ASE", "ISSTA", "TSE", "EMSE"],
        "subs": [
            f("软件架构与设计", "软件架构|software architecture|software design"),
            f("模型驱动工程", "模型驱动|MDE|model-driven engineering"),
            f("软件仓库挖掘", "仓库挖掘|repository mining|mining software repositories"),
            f("软件演化与维护", "软件演化|软件维护|software evolution|software maintenance"),
            f("DevOps与持续交付", "DevOps|持续交付|continuous delivery|CI CD"),
            f("可信软件与形式化验证", "可信软件|软件验证|trustworthy software|software verification"),
            f("自动化测试与模糊测试", "自动化测试|模糊测试|automated testing|fuzzing"),
            f("人本软件工程", "人本软件工程|human aspects|human-centered software engineering"),
            f("实证软件工程", "实证研究|empirical software engineering"),
            f("移动与Web应用工程", "Web工程|移动应用工程|mobile software engineering|web engineering"),
            f("软件开发基础与程序设计", "软件开发基础|程序设计|software development fundamentals|program design"),
        ],
    },
    "数据库与数据管理": {
        "venues": ["SIGMOD", "VLDB", "ICDE", "TODS", "VLDBJ"],
        "subs": [
            f("关系数据库与查询处理", "关系数据库|查询处理|relational database|query processing"),
            f("分布式与云数据库", "分布式数据库|云数据库|distributed database|cloud database"),
            f("事务处理与并发控制", "事务处理|并发控制|transaction processing|concurrency control"),
            f("数据仓库与OLAP", "数据仓库|OLAP|data warehouse|analytical processing"),
            f("数据集成与ETL", "数据集成|ETL|data integration"),
            f("数据血缘与版本管理", "数据血缘|版本管理|data lineage|data versioning"),
            f("隐私保护数据库", "隐私数据库|privacy-preserving database"),
            f("嵌入式与边缘数据管理", "嵌入式数据库|边缘数据管理|edge data management"),
            f("高性能数据管理与存储", "高性能数据管理|存储引擎|high-performance data management|storage engine"),
        ],
    },
    "人机交互与图形学": {
        "venues": ["CHI", "UIST", "CSCW", "IEEE TVCG", "TOCHI"],
        "subs": [
            f("交互设计与用户研究", "交互设计|用户研究|interaction design|user study"),
            f("可用性与可访问性", "可用性|可访问性|usability|accessibility"),
            f("社会计算与协同", "社会计算|协同计算|social computing|collaborative computing"),
            f("智能用户界面", "智能界面|intelligent user interface|adaptive UI"),
            f("多模态与具身交互", "多模态交互|具身交互|multimodal interaction|embodied interaction"),
            f("用户建模与个性化", "用户建模|个性化|user modeling|personalization"),
            f("计算行为科学", "计算行为科学|behavioural computing|behavioral science"),
            f("移动与普适HCI", "移动交互|普适计算|mobile HCI|ubiquitous HCI"),
        ],
    },
    "理论与算法": {
        "venues": ["STOC", "FOCS", "SODA", "ICALP", "ACM TALG"],
        "subs": [
            f("近似算法与在线算法", "近似算法|在线算法|approximation algorithms|online algorithms"),
            f("图论与离散优化", "图论|离散优化|graph theory|discrete optimization"),
            f("自动机与形式语言", "自动机|形式语言|automata|formal languages"),
            f("程序逻辑与类型论", "程序逻辑|类型论|program logic|type theory"),
            f("模型检查与程序验证", "模型检查|程序验证|model checking|program verification"),
            f("自动定理证明", "定理证明|automated theorem proving|theorem prover"),
            f("信息论与编码理论", "信息论|编码理论|information theory|coding theory"),
            f("计算几何", "计算几何|computational geometry"),
            f("数据结构与算法基础", "数据结构|算法基础|data structures|algorithm foundations"),
        ],
    },
    "机器人与具身智能": {
        "venues": ["ICRA", "IROS", "RSS", "CoRL", "T-RO"],
        "subs": [
            f("机器人感知与定位", "机器人感知|定位|robot perception|localization"),
            f("机器人学习", "robot learning|机器人强化学习"),
            f("柔性与仿生机器人", "柔性机器人|仿生机器人|soft robotics|biomimetic robotics"),
            f("人机协作与交互", "人机协作|human-robot interaction|HRI"),
            f("机器人安全与可信", "机器人安全|robot safety|trustworthy robotics"),
            f("无人机与自主导航", "无人机|UAV|aerial robotics|autonomous navigation"),
            f("工业与农业机器人", "工业机器人|农业机器人|industrial robot|agricultural robotics"),
        ],
    },
    "交叉与AI4Science": {
        "venues": ["NeurIPS", "ICML", "Nature Machine Intelligence", "Bioinformatics", "JAMIA"],
        "subs": [
            f("AI for Physics", "AI物理|physics-informed machine learning|AI for science physics"),
            f("AI for Chemistry", "AI化学|computational chemistry|AI for chemistry"),
            f("基因组学与单细胞分析", "基因组学|单细胞|genomics|single-cell analysis"),
            f("临床与转化医学", "临床AI|转化医学|clinical AI|translational medicine"),
            f("自动化实验室", "自驱动实验室|self-driving lab|automated laboratory"),
            f("科学软件与可复现计算", "科学软件|可复现计算|scientific software|reproducible computing"),
            f("数学发现与推理", "AI数学|automated mathematical discovery|math reasoning"),
            f("生态与农业智能", "生态智能|农业智能|ecological intelligence|agricultural AI"),
        ],
    },
    "网络与通信": {
        "venues": ["SIGCOMM", "NSDI", "MobiCom", "INFOCOM", "CoNEXT"],
        "subs": [
            f("SDN与可编程网络", "SDN|可编程网络|programmable network"),
            f("5G与6G移动网络", "5G|6G|mobile network"),
            f("车联网与V2X", "车联网|V2X|vehicular network"),
            f("自组网与无线传感网", "自组网|无线传感网|ad hoc network|wireless sensor network"),
            f("P2P与内容分发网络", "P2P|CDN|内容分发|content delivery network"),
            f("网络经济与路由博弈", "网络经济|路由博弈|network economics|routing game"),
            f("网络智能运维与AIOps", "AIOps|网络智能运维|network intelligence"),
            f("确定性网络与TSN", "确定性网络|TSN|deterministic networking|time-sensitive networking"),
            f("互联网体系结构与协议", "互联网体系结构|Internet architecture|Internet protocols"),
        ],
    },
    "体系结构与高性能计算": {
        "venues": ["ISCA", "MICRO", "HPCA", "ASPLOS", "SC"],
        "subs": [
            f("CPU微架构", "微架构|CPU architecture|microarchitecture"),
            f("GPU与AI加速器", "GPU架构|AI加速器|GPU architecture|AI accelerator"),
            f("Chiplet与3D封装", "Chiplet|3D封装|3D packaging"),
            f("内存与缓存架构", "缓存架构|memory architecture|cache architecture"),
            f("存储架构与持久内存", "存储架构|持久内存|storage architecture|persistent memory"),
            f("FPGA与可重构计算", "FPGA|可重构计算|reconfigurable computing"),
            f("硬件验证与形式化", "硬件验证|hardware verification|formal hardware"),
            f("RISC-V与开放指令集", "RISC-V|开放指令集|open ISA"),
            f("计算机系统仿真", "系统仿真|architecture simulation|computer architecture simulator"),
        ],
    },
    "量子计算与信息": {
        "venues": ["QIP", "STOC", "FOCS", "Quantum", "PRX Quantum"],
        "subs": [
            f("量子硬件与量子比特", "量子硬件|量子比特|quantum hardware|qubit"),
            f("量子控制与校准", "量子控制|量子校准|quantum control|quantum calibration"),
            f("量子模拟", "quantum simulation|量子仿真"),
            f("量子软件与编译", "量子软件|量子编译|quantum software|quantum compiler"),
            f("量子密码", "quantum cryptography|量子密钥分发|QKD"),
            f("容错量子计算", "容错量子计算|fault-tolerant quantum computing"),
            f("量子体系结构", "quantum architecture|量子架构"),
        ],
    },
    "计算与社会": {
        "venues": ["FAccT", "CSCW", "CHI", "WWW", "AIES"],
        "subs": [
            f("AI伦理与公平", "AI伦理|算法公平|AI ethics|algorithmic fairness"),
            f("算法治理与问责", "算法治理|算法问责|algorithm governance|accountability"),
            f("数据治理与隐私政策", "数据治理|隐私政策|data governance|privacy policy"),
            f("平台治理与内容审核", "平台治理|内容审核|platform governance|content moderation"),
            f("虚假信息与信息生态", "虚假信息|错误信息|misinformation|information ecosystem"),
            f("开源软件与数字劳动", "开源软件|数字劳动|open source|digital labor"),
            f("数字公平与数字鸿沟", "数字公平|数字鸿沟|digital equity|digital divide"),
            f("科技政策与法律", "科技政策|计算法学|technology policy|computational law"),
            f("人本技术评估", "技术评估|human-centered evaluation|responsible innovation"),
            f("计算经济学与机制设计", "计算经济学|机制设计|computational economics|mechanism design"),
        ],
    },
    # CS2023 Foundations of Programming Languages and compiler research.
    "编程语言与编译": {
        "venues": ["PLDI", "POPL", "OOPSLA", "ICFP", "CAV", "TOPLAS"],
        "profile": "pl",
        "subs": [
            f("程序语言理论", "语言理论|程序语言理论|programming language theory"),
            f("类型系统与程序逻辑", "类型系统|type system|program logic"),
            f("形式语义与程序验证", "形式语义|程序验证|formal semantics|program verification"),
            f("编译器优化与代码生成", "编译器|编译优化|code generation|compiler optimization"),
            f("JIT与运行时系统", "JIT|即时编译|runtime system"),
            f("程序分析与抽象解释", "程序分析|抽象解释|abstract interpretation"),
            f("并发与内存模型", "内存模型|并发语义|memory model|concurrency semantics"),
            f("程序合成与程序修复", "程序合成|自动修复|program synthesis|program repair"),
            f("语言设计与领域语言", "语言设计|DSL|language design|domain-specific language"),
            f("模型检查与软件验证", "模型检查|model checking|software verification"),
            f("安全编译与内存安全", "安全编译|内存安全|safe compilation|memory safety"),
            f("概率、可逆与量子编程", "概率编程|可逆计算|quantum programming|probabilistic programming"),
        ],
    },
    # CS2023 Graphics and Interactive Techniques plus multimedia research.
    "计算机图形学与多媒体": {
        "venues": ["SIGGRAPH", "SIGGRAPH Asia", "ACM MM", "IEEE TVCG", "TOG"],
        "profile": "graphics",
        "subs": [
            f("真实感渲染", "渲染|physically based rendering|realistic rendering"),
            f("实时渲染与游戏引擎", "实时渲染|游戏引擎|real-time rendering|game engine"),
            f("几何建模与处理", "几何建模|geometry processing|computational geometry graphics"),
            f("动画与物理仿真", "动画|物理仿真|computer animation|physics simulation"),
            f("计算摄影", "computational photography|计算成像"),
            f("图像与视频编码", "视频编码|image coding|video compression"),
            f("多媒体内容理解", "多媒体理解|multimedia understanding"),
            f("虚拟现实与增强现实", "VR|AR|virtual reality|augmented reality"),
            f("可视化与可视分析", "可视化|visual analytics|information visualization"),
            f("生成式图形与神经渲染", "生成式图形|neural rendering|3D generation"),
            f("数字人与人体建模", "数字人|digital human|human modeling"),
            f("触觉与多感官媒体", "触觉媒体|多感官|haptic media|multisensory media"),
            f("媒体取证与生成检测", "媒体取证|deepfake detection|multimedia forensics"),
            f("三维重建与场景捕获", "场景捕获|3D capture|scene reconstruction"),
        ],
    },
    # CS2023 Parallel and Distributed Computing plus cloud systems.
    "分布式与云计算": {
        "venues": ["SOSP", "OSDI", "NSDI", "EuroSys", "ASPLOS", "SC"],
        "profile": "distributed",
        "subs": [
            f("分布式一致性与共识", "共识算法|分布式一致性|consensus|distributed consistency"),
            f("容错与高可用系统", "容错系统|高可用|fault-tolerant system|high availability"),
            f("云原生与容器编排", "云原生|容器编排|cloud native|Kubernetes"),
            f("无服务器计算", "Serverless|无服务器|function as a service"),
            f("边缘与雾计算", "边缘计算|雾计算|edge computing|fog computing"),
            f("分布式存储与文件系统", "分布式存储|distributed storage|distributed file system"),
            f("并行算法与编程模型", "并行算法|parallel algorithm|parallel programming model"),
            f("GPU与异构并行计算", "GPU计算|异构并行|heterogeneous parallelism"),
            f("数据中心资源调度", "数据中心|资源调度|datacenter scheduling"),
            f("联邦与去中心化系统", "联邦系统|去中心化|federated system|decentralized system"),
            f("区块链系统与共识", "区块链系统|blockchain system|consensus protocol"),
            f("分布式机器学习系统", "分布式训练|distributed training|ML systems"),
            f("服务计算与微服务", "服务计算|微服务|service computing|microservices"),
        ],
    },
    # CS2023 Specialized Platform Development plus embedded/CPS research.
    "嵌入式、物联网与CPS": {
        "venues": ["SenSys", "IPSN", "RTSS", "EMSOFT", "MobiSys", "IoTDI"],
        "profile": "embedded",
        "subs": [
            f("嵌入式系统与实时调度", "嵌入式系统|实时调度|embedded system|real-time scheduling"),
            f("嵌入式操作系统与固件", "RTOS|嵌入式操作系统|firmware|real-time operating system"),
            f("物联网系统与边缘感知", "物联网|IoT|edge sensing"),
            f("无线传感网络", "无线传感网|wireless sensor network|WSN"),
            f("信息物理系统", "CPS|cyber-physical system|信息物理系统"),
            f("工业控制系统", "工控|industrial control system|ICS"),
            f("智能硬件与可穿戴设备", "智能硬件|可穿戴|wearable device|smart hardware"),
            f("车联网与智能汽车", "车联网|智能汽车|connected vehicle|V2X"),
            f("无人机与低空系统", "无人机系统|UAV system|low-altitude system"),
            f("机器人操作系统", "ROS|robot operating system"),
            f("低功耗与能量采集", "低功耗|能量采集|low-power computing|energy harvesting"),
            f("嵌入式安全与可信启动", "可信启动|secure boot|embedded security"),
            f("恶劣环境与高可靠计算", "抗恶劣环境|高可靠计算|harsh-environment computing|high-assurance computing"),
        ],
    },
    "计算教育与专业实践": {
        "venues": ["SIGCSE", "ITiCSE", "ICER", "TOCE", "FIE"],
        "profile": "education",
        "subs": [
            f("计算教育研究", "计算机教育|computing education|CS education"),
            f("编程学习分析", "编程学习|programming learning|learning analytics"),
            f("自动评测与反馈", "自动评测|automatic assessment|automated feedback"),
            f("计算机课程与知识模型", "课程体系|CS2023|computing curriculum"),
            f("软件工程职业实践", "职业实践|professional practice|software professionalism"),
            f("科研可复现性", "可复现研究|reproducibility|replicability"),
            f("科研软件与开放科学", "科研软件|research software|open science"),
            f("AI辅助教育与学习", "AI教育|LLM教育|AI for education|AI-assisted learning"),
            f("计算思维与K12教育", "计算思维|computational thinking|K-12 computing"),
            f("工程伦理与团队协作", "工程伦理|团队协作|engineering ethics|teamwork"),
        ],
    },
    "电子设计自动化与计算机工程": {
        "venues": ["DAC", "ICCAD", "DATE", "ISCA", "MICRO", "IEEE TCAD"],
        "profile": "eda",
        "subs": [
            f("电子设计自动化", "EDA|electronic design automation"),
            f("超大规模集成电路设计", "VLSI|集成电路设计|chip design"),
            f("处理器与芯片设计", "处理器设计|processor design|SoC"),
            f("芯片验证与测试", "芯片验证|hardware verification|chip testing"),
            f("FPGA与可重构硬件", "FPGA|reconfigurable hardware"),
            f("嵌入式处理器与SoC", "SoC|system on chip|embedded processor"),
            f("模拟与混合信号电路", "模拟电路|mixed-signal circuit"),
            f("硬件软件协同设计", "软硬件协同|hardware-software co-design"),
            f("芯片可靠性与安全", "硬件可靠性|chip reliability|hardware security"),
            f("光电子与量子硬件", "光计算|photonic computing|quantum hardware"),
            f("芯片互连与Chiplet", "Chiplet|die-to-die interconnect|advanced packaging"),
            f("低功耗芯片设计", "低功耗设计|low-power VLSI"),
            f("数字逻辑与计算机组成", "数字逻辑|计算机组成|digital logic|computer organization"),
        ],
    },
    "数据科学与数据工程": {
        "venues": ["KDD", "VLDB", "SIGMOD", "ICDE", "JMLR", "TKDE"],
        "profile": "data",
        "subs": [
            f("大数据系统与分析", "大数据|big data|large-scale analytics"),
            f("数据清洗与数据准备", "数据清洗|data preparation|data wrangling"),
            f("数据集成与数据湖", "数据集成|data lake|data integration"),
            f("数据版本、血缘与可复现性", "数据版本|data lineage|data versioning"),
            f("数据治理与质量管理", "数据治理|data quality|data governance"),
            f("数据密集型机器学习", "data-centric ML|数据驱动机器学习"),
            f("流式数据分析", "流式计算|stream analytics|streaming data"),
            f("时空与轨迹数据分析", "轨迹数据|spatio-temporal analytics"),
            f("科学数据管理", "scientific data management|research data"),
            f("数据市场与数据定价", "data market|data pricing"),
            f("信息系统与业务流程", "信息系统|业务流程管理|information systems|business process management"),
        ],
    },
    "数学与统计基础": {
        "venues": ["STOC", "FOCS", "SODA", "JMLR", "Annals of Statistics"],
        "profile": "math",
        "subs": [
            f("离散数学与组合学", "离散数学|combinatorics|discrete mathematics"),
            f("概率论与随机过程", "概率论|随机过程|probability theory|stochastic process"),
            f("统计推断与高维统计", "统计推断|高维统计|statistical inference|high-dimensional statistics"),
            f("最优化理论与算法", "最优化|optimization theory|convex optimization"),
            f("数值分析与科学计算", "数值分析|numerical analysis|scientific computing"),
            f("线性代数与矩阵计算", "矩阵计算|linear algebra|matrix computation"),
            f("信息论与统计学习", "信息论|information theory|statistical learning"),
            f("博弈论与机制设计", "博弈论|game theory|mechanism design"),
        ],
    },
}


PROFILE_DEFINITIONS = {
    "pl": {
        "label": "编程语言/编译",
        "importance": {"scenario": 0.25, "method": 0.85, "task": 0.9, "modality": 0.2},
        "scenarios": ["软件研发", "云计算与数据中心"],
        "methods": ["形式化方法与验证", "静态与动态程序分析", "编译与代码生成"],
        "tasks": ["程序分析与验证", "测试与修复", "编译与调度"],
        "modalities": ["代码与程序", "文本"],
    },
    "distributed": {
        "label": "分布式/云系统",
        "importance": {"scenario": 0.45, "method": 0.8, "task": 0.9, "modality": 0.2},
        "scenarios": ["云计算与数据中心", "边缘与嵌入式", "工业检测与智能制造"],
        "methods": ["系统优化与资源调度", "分布式训练", "形式化方法与验证"],
        "tasks": ["性能优化与资源管理", "存储与查询", "评测与Benchmark"],
        "modalities": ["网络与系统日志", "图与时序", "代码与程序"],
    },
    "embedded": {
        "label": "嵌入式/物联网/CPS",
        "importance": {"scenario": 0.85, "method": 0.7, "task": 0.9, "modality": 0.6},
        "scenarios": ["边缘与嵌入式", "工业检测与智能制造", "智能座舱与车载", "低空经济"],
        "methods": ["软硬件协同设计", "低功耗与能量管理", "仿真与数字孪生"],
        "tasks": ["规划与控制", "性能优化与资源管理", "硬件设计与验证"],
        "modalities": ["多模态传感器", "事件相机与脉冲", "网络与系统日志"],
    },
    "education": {
        "label": "计算教育/专业实践",
        "importance": {"scenario": 0.75, "method": 0.5, "task": 0.9, "modality": 0.55},
        "scenarios": ["教育与学习分析", "软件研发"],
        "methods": ["人机交互与用户研究", "深度学习与Transformer", "实证研究与用户研究"],
        "tasks": ["交互与可视化", "评测与Benchmark", "程序分析与验证"],
        "modalities": ["文本", "代码与程序", "多模态传感器"],
    },
    "eda": {
        "label": "EDA/计算机工程",
        "importance": {"scenario": 0.2, "method": 0.85, "task": 0.9, "modality": 0.15},
        "scenarios": ["芯片与硬件", "边缘与嵌入式"],
        "methods": ["软硬件协同设计", "形式化方法与验证", "优化与运筹"],
        "tasks": ["硬件设计与验证", "编译与调度", "性能优化与资源管理"],
        "modalities": ["图与时序", "代码与程序"],
    },
    "math": {
        "label": "数学/统计基础",
        "importance": {"scenario": 0.05, "method": 0.9, "task": 0.7, "modality": 0.05},
        "scenarios": [],
        "methods": ["概率论与随机过程", "最优化理论与算法", "信息论与统计学习"],
        "tasks": ["推理与问答", "评测与Benchmark", "预测与回归"],
        "modalities": [],
    },
}


SCENARIOS = [
    f("软件研发", "软件研发|软件开发|software development"),
    f("芯片与硬件", "芯片设计|硬件工程|chip design|hardware engineering"),
    f("边缘与嵌入式", "边缘设备|嵌入式部署|edge deployment|embedded deployment"),
    f("教育与学习分析", "教育科技|学习分析|education technology|learning analytics"),
    f("智能终端与移动应用", "移动应用|智能终端|mobile application|smart device"),
    f("云原生与数据中心", "云原生|cloud native|data center"),
]

METHODS = [
    f("形式化方法与验证", "形式化验证|formal verification|formal methods"),
    f("静态与动态程序分析", "程序分析|program analysis|static analysis|dynamic analysis"),
    f("编译与代码生成", "编译优化|compiler|code generation"),
    f("系统优化与资源调度", "资源调度|resource scheduling|system optimization"),
    f("分布式训练", "distributed training|federated training"),
    f("软硬件协同设计", "hardware-software co-design|软硬件协同"),
    f("低功耗与能量管理", "low power|energy management|power management"),
    f("概率论与随机过程", "probability|stochastic process"),
    f("最优化理论与算法", "optimization|convex optimization"),
    f("信息论与统计学习", "information theory|statistical learning"),
    f("实证研究与用户研究", "empirical study|user study"),
]

TASKS = [
    f("程序分析与验证", "program analysis|program verification"),
    f("编译与调度", "compiler|scheduling"),
    f("硬件设计与验证", "hardware design|hardware verification"),
    f("性能优化与资源管理", "performance optimization|resource management"),
    f("评测与Benchmark", "evaluation|benchmark"),
    f("交互与可视化", "interaction|visualization"),
]

MODALITIES = [
    f("代码与程序", "source code|binary|program"),
    f("网络与系统日志", "system log|network log|trace"),
    f("工业传感器", "industrial sensor|SCADA"),
]


DEFAULT_PROFILES = {
    "人工智能": "ml_method",
    "计算机视觉": "vision",
    "自然语言处理": "nlp",
    "数据挖掘与信息检索": "data",
    "系统与网络": "systems",
    "安全与隐私": "security",
    "软件工程": "se",
    "数据库与数据管理": "db",
    "人机交互与图形学": "hci",
    "理论与算法": "theory",
    "机器人与具身智能": "robotics",
    "交叉与AI4Science": "science",
    "网络与通信": "networks",
    "体系结构与高性能计算": "architecture",
    "量子计算与信息": "quantum",
    "计算与社会": "social",
    "编程语言与编译": "pl",
    "计算机图形学与多媒体": "graphics",
    "分布式与云计算": "distributed",
    "嵌入式、物联网与CPS": "embedded",
    "计算教育与专业实践": "education",
    "电子设计自动化与计算机工程": "eda",
    "数据科学与数据工程": "data",
    "数学与统计基础": "math",
}

CATEGORY_PROFILES = {
    cat: {
        sub["name"]: entry.get("profile") or DEFAULT_PROFILES.get(cat, "ml_method")
        for sub in entry["subs"]
    }
    for cat, entry in CATEGORIES.items()
}

CATEGORY_RELATED = {
    "人工智能": ["计算机视觉", "自然语言处理", "数据挖掘与信息检索", "机器人与具身智能", "安全与隐私"],
    "计算机视觉": ["人工智能", "计算机图形学与多媒体", "机器人与具身智能", "交叉与AI4Science"],
    "自然语言处理": ["人工智能", "数据挖掘与信息检索", "人机交互与图形学", "计算与社会"],
    "数据挖掘与信息检索": ["人工智能", "数据库与数据管理", "数据科学与数据工程", "计算与社会"],
    "系统与网络": ["分布式与云计算", "网络与通信", "体系结构与高性能计算", "安全与隐私"],
    "安全与隐私": ["系统与网络", "软件工程", "网络与通信", "人工智能"],
    "软件工程": ["编程语言与编译", "系统与网络", "人机交互与图形学", "安全与隐私"],
    "数据库与数据管理": ["数据挖掘与信息检索", "数据科学与数据工程", "系统与网络", "分布式与云计算"],
    "人机交互与图形学": ["计算机图形学与多媒体", "人工智能", "计算与社会", "嵌入式、物联网与CPS"],
    "理论与算法": ["数学与统计基础", "编程语言与编译", "量子计算与信息", "人工智能"],
    "机器人与具身智能": ["计算机视觉", "人工智能", "嵌入式、物联网与CPS", "人机交互与图形学"],
    "交叉与AI4Science": ["人工智能", "数据科学与数据工程", "数学与统计基础", "机器人与具身智能"],
    "网络与通信": ["分布式与云计算", "系统与网络", "安全与隐私", "嵌入式、物联网与CPS"],
    "体系结构与高性能计算": ["分布式与云计算", "电子设计自动化与计算机工程", "嵌入式、物联网与CPS", "系统与网络"],
    "量子计算与信息": ["理论与算法", "体系结构与高性能计算", "安全与隐私", "数学与统计基础"],
    "计算与社会": ["人机交互与图形学", "数据挖掘与信息检索", "计算教育与专业实践", "人工智能"],
    "编程语言与编译": ["软件工程", "理论与算法", "系统与网络"],
    "计算机图形学与多媒体": ["计算机视觉", "人机交互与图形学", "人工智能"],
    "分布式与云计算": ["系统与网络", "网络与通信", "体系结构与高性能计算"],
    "嵌入式、物联网与CPS": ["系统与网络", "网络与通信", "机器人与具身智能", "安全与隐私"],
    "计算教育与专业实践": ["计算与社会", "人机交互与图形学", "软件工程"],
    "电子设计自动化与计算机工程": ["体系结构与高性能计算", "嵌入式、物联网与CPS", "安全与隐私"],
    "数据科学与数据工程": ["数据挖掘与信息检索", "数据库与数据管理", "人工智能"],
    "数学与统计基础": ["理论与算法", "人工智能", "数据挖掘与信息检索"],
}

THIN_CATEGORIES = [
    "编程语言与编译",
    "计算机图形学与多媒体",
    "分布式与云计算",
    "嵌入式、物联网与CPS",
    "计算教育与专业实践",
    "电子设计自动化与计算机工程",
    "数据科学与数据工程",
    "数学与统计基础",
]


def build() -> dict:
    return {
        "version": "1.0",
        "basis": [
            "ACM/IEEE-CS/AAAI Computer Science Curricula 2023 knowledge areas",
            "CCF technical committees and active research directions",
            "OpenAlex publication-topic mappings in the local advisor index",
        ],
        "references": [
            "https://csed.acm.org/knowledge-areas",
            "https://www.ccf.org.cn/Chapters/TC/TC_Listing/TCHPC",
            "https://api.openalex.org",
        ],
        "categories": CATEGORIES,
        "category_profiles": CATEGORY_PROFILES,
        "category_default_profiles": DEFAULT_PROFILES,
        "category_related": CATEGORY_RELATED,
        "thin_categories": THIN_CATEGORIES,
        "profiles": PROFILE_DEFINITIONS,
        "scenarios": SCENARIOS,
        "methods": METHODS,
        "tasks": TASKS,
        "modalities": MODALITIES,
    }


def main() -> None:
    payload = build()
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    fields = sum(len(entry["subs"]) for entry in payload["categories"].values())
    print(f"saved: {OUTPUT}")
    print(f"categories: {len(payload['categories'])}, supplemental fields: {fields}")


if __name__ == "__main__":
    main()
