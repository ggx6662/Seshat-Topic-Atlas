// 幂等扩展：为基础方向补充应用标签与公开基准，并新增应用与交叉方向。
// 运行：node competition/scripts/expand_applications.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DATA = path.resolve(HERE, "../site/data");
const read = (p) => JSON.parse(fs.readFileSync(path.join(DATA, p), "utf8"));
const write = (p, v) => fs.writeFileSync(path.join(DATA, p), JSON.stringify(v), "utf8");

const index = read("index.json");
const appsFile = read("applications.json");
const bench = read("benchmarks.json");
const advisors = read("advisors.json");

const NEW = [
  ["医学影像组学", ["影像组学", "放射组学", "radiomics", "病灶分割", "预后预测"], ["医学图像分析", "医学影像", "生物信息"], ["交叉与AI4Science", "计算机视觉"], ["med-imaging"]],
  ["医学自然语言处理", ["临床文本", "电子病历", "医学问答", "医学信息抽取"], ["信息抽取", "问答与推理", "临床与转化医学"], ["自然语言处理", "交叉与AI4Science"], ["clinical"]],
  ["临床决策支持系统", ["临床决策", "电子病历", "风险预测", "治疗推荐"], ["临床与转化医学", "因果推断与决策", "数据质量"], ["交叉与AI4Science", "计算与社会"], ["clinical"]],
  ["数字健康与可穿戴计算", ["可穿戴", "生理信号", "健康监测", "睡眠分期", "活动识别"], ["健康HCI", "可穿戴与普适计算", "数字健康"], ["人机交互与图形学", "交叉与AI4Science"], ["digital-health"]],
  ["心理健康计算", ["抑郁识别", "情绪计算", "心理评估", "多模态行为分析"], ["情感分析与立场识别", "健康HCI", "数字健康"], ["人机交互与图形学", "自然语言处理"], ["mental-health"]],
  ["公共卫生信息学", ["流行病建模", "疫情监测", "公共卫生", "时空传播"], ["计算社会科学", "时空数据挖掘", "数字健康"], ["计算与社会", "数据挖掘与信息检索"], ["public-health"]],
  ["手术与介入智能", ["手术视频", "器械分割", "阶段识别", "术中导航"], ["医学图像分析", "医疗机器人", "视频理解"], ["交叉与AI4Science", "计算机视觉", "机器人与具身智能"], ["surgery"]],
  ["智慧城市与城市计算", ["城市计算", "时空预测", "城市感知", "轨迹数据"], ["时空数据挖掘", "社会网络分析", "可持续计算"], ["数据挖掘与信息检索", "计算与社会"], ["mobility"]],
  ["交通流与出行预测", ["交通流预测", "出行需求", "轨迹预测", "时空图网络"], ["时空数据挖掘", "自动驾驶", "时序挖掘"], ["数据挖掘与信息检索", "机器人与具身智能"], ["mobility"]],
  ["智能座舱与车载交互", ["智能座舱", "驾驶员监测", "车载交互", "多模态感知"], ["人机协作与交互", "自动驾驶", "车联网与V2X"], ["人机交互与图形学", "计算机视觉"], ["autonomous-driving"]],
  ["智能制造与预测性维护", ["预测性维护", "剩余寿命", "工业时序", "故障诊断"], ["时序挖掘", "工业控制系统", "数据质量"], ["数据科学与数据工程", "嵌入式、物联网与CPS"], ["smart-manufacturing", "industrial-inspection"]],
  ["工业互联网与数字孪生", ["数字孪生", "工业互联网", "边缘协同", "工业数据空间"], ["信息物理系统", "工业控制系统", "边缘与雾计算"], ["嵌入式、物联网与CPS", "分布式与云计算"], ["smart-manufacturing"]],
  ["物流与供应链优化", ["车辆路径", "供应链", "库存优化", "组合优化"], ["组合优化", "强化学习", "时空数据挖掘"], ["理论与算法", "数据挖掘与信息检索"], ["logistics"]],
  ["能源与智能电网", ["智能电网", "负荷预测", "调度优化", "综合能源"], ["可持续计算", "科学计算", "强化学习"], ["交叉与AI4Science", "数据挖掘与信息检索"], ["climate-energy"]],
  ["碳中和与气候适应", ["碳中和", "气候风险", "碳排放", "气候适应"], ["气候与地球系统", "可持续计算", "遥感与地球观测"], ["交叉与AI4Science", "计算与社会"], ["climate-energy"]],
  ["智慧农业与精准作业", ["精准农业", "作物监测", "农机导航", "产量预测"], ["生态与农业智能", "工业与农业机器人", "遥感与航空视觉"], ["交叉与AI4Science", "机器人与具身智能"], ["agriculture"]],
  ["灾害感知与应急", ["灾害评估", "应急响应", "变化检测", "多源遥感"], ["遥感与地球观测", "多机器人系统", "时空数据挖掘"], ["交叉与AI4Science", "计算机视觉"], ["disaster"]],
  ["海洋与水下感知", ["水下图像", "声呐", "海洋遥感", "水下机器人"], ["遥感与地球观测", "机器人感知与定位", "图像恢复与增强"], ["交叉与AI4Science", "机器人与具身智能"], ["ocean-space"]],
  ["空间科学与天文信息学", ["天文数据", "星系分类", "红移估计", "空间科学"], ["AI for Physics", "科学计算", "遥感与地球观测"], ["交叉与AI4Science"], ["ocean-space"]],
  ["数字人文与文化遗产", ["古籍数字化", "文化遗产", "文本对齐", "多语言检索"], ["计算社会科学", "知识图谱", "三维重建与场景捕获"], ["计算与社会", "自然语言处理"], ["digital-humanities"]],
  ["金融风控与反欺诈", ["信用风险", "欺诈检测", "异常交易", "可解释风控"], ["计算金融", "时序挖掘", "图挖掘"], ["数据挖掘与信息检索", "计算与社会"], ["fintech"]],
  ["招聘与人岗匹配", ["人岗匹配", "简历解析", "人才画像", "推荐"], ["推荐系统", "信息抽取", "社会网络分析"], ["数据挖掘与信息检索", "自然语言处理"], ["recruiting"]],
  ["广告与营销计算", ["点击率预估", "广告竞价", "用户增长", "因果推断"], ["推荐系统", "因果推断与决策", "序列与因果推荐"], ["数据挖掘与信息检索"], ["advertising"]],
  ["法律文书与合同智能", ["法律文本", "合同审查", "判决预测", "法条检索"], ["法律与政务计算", "信息抽取", "检索与排序"], ["自然语言处理", "计算与社会"], ["law-gov"]],
  ["内容生产与新闻智能", ["新闻摘要", "事实核查", "内容生成", "媒体分析"], ["可控文本生成", "虚假信息与信息生态", "多媒体内容理解"], ["自然语言处理", "计算机图形学与多媒体"], ["content-social"]],
  ["游戏AI与内容生成", ["游戏智能体", "程序化内容生成", "玩家建模", "强化学习"], ["智能体与世界模型", "实时渲染与游戏引擎", "强化学习"], ["人工智能", "计算机图形学与多媒体"], ["games"]],
  ["空间计算与交互", ["空间交互", "混合现实", "手势交互", "场景理解"], ["VR与AR", "多模态与具身交互", "三维重建与神经渲染"], ["人机交互与图形学", "计算机视觉"], ["spatial-computing"]],
  ["无障碍与辅助技术", ["无障碍", "辅助技术", "手语识别", "老龄计算"], ["可用性与可访问性", "数字健康", "语音识别与合成"], ["人机交互与图形学", "计算与社会"], ["accessibility"]],
  ["体育计算与运动分析", ["运动分析", "姿态估计", "比赛事件", "战术分析"], ["人体与动作理解", "视频理解", "可穿戴与普适计算"], ["计算机视觉", "数据挖掘与信息检索"], ["sports"]],
  ["教育测量与学习分析", ["学习分析", "知识追踪", "自动评分", "教育测量"], ["编程学习分析", "自动评测与反馈", "AI辅助教育与学习"], ["计算教育与专业实践", "数据挖掘与信息检索"], ["edtech"]],
  ["科学发现智能体", ["科学智能体", "自动化实验", "假设生成", "工具调用"], ["自动化实验室", "科学基础模型", "智能体与世界模型"], ["人工智能", "交叉与AI4Science"], ["science"]],
  ["具身导航与交互", ["视觉语言导航", "具身交互", "路径规划", "场景理解"], ["具身智能", "SLAM与定位", "人机协作与交互"], ["机器人与具身智能", "计算机视觉"], ["robotics"]],
  ["端侧智能与TinyML", ["TinyML", "模型量化", "端侧推理", "低功耗"], ["嵌入式系统与实时调度", "轻量化与实时部署", "边缘与雾计算"], ["嵌入式、物联网与CPS", "体系结构与高性能计算"], ["edge-ai"]],
  ["大模型系统与推理服务", ["推理服务", "KV缓存", "批处理调度", "模型并行"], ["机器学习系统", "分布式机器学习系统", "GPU与异构并行计算"], ["系统与网络", "分布式与云计算"], ["llm-systems"]],
  ["芯片设计与验证自动化", ["芯片设计", "逻辑综合", "形式验证", "布局布线"], ["电子设计自动化", "芯片验证与测试", "硬件验证与形式化"], ["电子设计自动化与计算机工程", "体系结构与高性能计算"], ["chips"]],
  ["企业对话与流程自动化", ["智能客服", "流程自动化", "RPA", "工具调用"], ["对话系统与工具智能体", "信息系统与业务流程", "检索增强生成"], ["自然语言处理", "软件工程"], ["enterprise"]],

  // 医疗、生命科学与健康
  ["计算病理学与全切片图像", ["全切片图像", "病理", "WSI", "肿瘤分级", "免疫组化"], ["医学图像分析", "计算病理", "生物信息"], ["计算机视觉", "交叉与AI4Science"], ["med-imaging"], "计算机视觉"],
  ["内窥镜与术中视觉", ["内窥镜", "术中", "腔镜", "息肉", "手术视频"], ["医学图像分析", "手术视觉", "视频理解"], ["计算机视觉", "交叉与AI4Science"], ["surgery", "med-imaging"], "计算机视觉"],
  ["神经影像与脑连接组", ["神经影像", "fMRI", "脑连接", "脑网络", "结构MRI"], ["医学图像分析", "计算神经科学", "生物信息"], ["交叉与AI4Science", "计算机视觉"], ["med-imaging"], "交叉与AI4Science"],
  ["分子生成与药物设计", ["分子生成", "药物设计", "分子性质", "虚拟筛选", "化学信息学"], ["药物与蛋白质", "AI for Chemistry", "生物信息"], ["交叉与AI4Science"], ["drug-protein"], "交叉与AI4Science"],
  ["蛋白质结构与功能预测", ["蛋白质结构", "折叠", "功能注释", "蛋白语言模型", "结构预测"], ["药物与蛋白质", "生物信息", "科学基础模型"], ["交叉与AI4Science"], ["drug-protein", "science"], "交叉与AI4Science"],
  ["真实世界证据与临床研究", ["真实世界数据", "观察性研究", "因果推断", "倾向评分", "临床研究"], ["临床与转化医学", "因果推断与决策", "数据质量"], ["交叉与AI4Science", "数据科学与数据工程"], ["clinical", "public-health"], "交叉与AI4Science"],
  ["睡眠与生理信号分析", ["睡眠分期", "多导睡眠", "脑电", "心电", "生理信号"], ["睡眠分析", "数字健康", "生物医学信号"], ["交叉与AI4Science"], ["digital-health"], "交叉与AI4Science"],
  ["康复评估与运动功能", ["康复", "运动功能", "步态", "肌电", "可穿戴"], ["数字健康", "运动分析", "生物医学信号"], ["交叉与AI4Science", "人机交互与图形学"], ["digital-health"], "交叉与AI4Science"],
  ["疫苗与免疫信息学", ["疫苗设计", "免疫原性", "抗原", "免疫信息学", "抗体"], ["生物信息", "药物与蛋白质"], ["交叉与AI4Science"], ["public-health", "drug-protein"], "交叉与AI4Science"],
  ["生物医学文献挖掘", ["生物医学文献", "文献检索", "实体识别", "知识图谱", "证据综合"], ["信息检索", "信息抽取", "知识图谱"], ["自然语言处理", "交叉与AI4Science"], ["clinical", "science"], "自然语言处理"],

  // 交通、制造、物流与供应链
  ["端到端自动驾驶", ["端到端", "自动驾驶", "感知决策", "轨迹规划", "世界模型"], ["自动驾驶", "机器人学习", "计算机视觉"], ["机器人与具身智能", "计算机视觉"], ["autonomous-driving"], "机器人与具身智能"],
  ["车路协同与智能交通", ["车路协同", "V2X", "智能交通", "交通信号", "协同感知"], ["车联网", "智能交通", "网络与通信"], ["网络与通信", "机器人与具身智能"], ["mobility", "autonomous-driving"], "网络与通信"],
  ["轨道交通与调度优化", ["轨道交通", "列车调度", "时刻表", "客流预测", "运筹优化"], ["组合优化", "时序挖掘", "智能交通"], ["数据挖掘与信息检索", "理论与算法"], ["mobility", "logistics"], "数据挖掘与信息检索"],
  ["港口与航运智能化", ["港口", "航运", "船舶调度", "集装箱", "供应链"], ["组合优化", "时空数据挖掘", "智能交通"], ["数据挖掘与信息检索", "数据科学与数据工程"], ["logistics", "mobility"], "数据挖掘与信息检索"],
  ["仓储机器人与拣选", ["仓储", "拣选", "AGV", "多机器人", "路径规划"], ["机器人学习", "运动规划", "组合优化"], ["机器人与具身智能"], ["logistics", "robotics"], "机器人与具身智能"],
  ["工业缺陷检测与质检", ["缺陷检测", "工业质检", "表面缺陷", "异常检测", "小样本"], ["工业视觉", "计算机视觉", "异常检测"], ["计算机视觉", "数据科学与数据工程"], ["industrial-inspection"], "计算机视觉"],
  ["设备故障诊断与健康管理", ["故障诊断", "剩余寿命", "健康管理", "振动信号", "预测性维护"], ["时序挖掘", "工业控制系统", "可靠性工程"], ["数据科学与数据工程", "嵌入式、物联网与CPS"], ["smart-manufacturing"], "数据科学与数据工程"],
  ["工艺优化与过程控制", ["工艺优化", "过程控制", "质量预测", "参数寻优", "工业数据"], ["工业控制系统", "组合优化", "数据质量"], ["数据科学与数据工程", "嵌入式、物联网与CPS"], ["smart-manufacturing"], "数据科学与数据工程"],
  ["供应链韧性与风险", ["供应链", "韧性", "风险传播", "库存", "网络优化"], ["组合优化", "图挖掘", "因果推断与决策"], ["数据科学与数据工程", "数据挖掘与信息检索"], ["logistics"], "数据科学与数据工程"],
  ["无人配送与末端物流", ["无人配送", "末端物流", "配送机器人", "路径规划", "调度"], ["运动规划", "组合优化", "机器人学习"], ["机器人与具身智能", "数据挖掘与信息检索"], ["logistics", "robotics"], "机器人与具身智能"],

  // 地球、环境、农业与灾害
  ["森林与植被遥感", ["森林", "植被", "遥感", "生物量", "变化检测"], ["遥感与地球观测", "生态与农业智能", "计算机视觉"], ["交叉与AI4Science", "计算机视觉"], ["remote-sensing", "agriculture"], "交叉与AI4Science"],
  ["水资源与水环境监测", ["水资源", "水质", "水文", "遥感", "水环境"], ["遥感与地球观测", "气候与地球系统", "科学计算"], ["交叉与AI4Science"], ["climate-energy", "remote-sensing"], "交叉与AI4Science"],
  ["空气质量与污染监测", ["空气质量", "PM2.5", "污染", "排放", "时空预测"], ["气候与地球系统", "时空数据挖掘", "遥感与地球观测"], ["交叉与AI4Science", "数据挖掘与信息检索"], ["climate-energy", "remote-sensing"], "交叉与AI4Science"],
  ["极端天气与气候预测", ["极端天气", "气候预测", "台风", "热浪", "集合预报"], ["气候与地球系统", "科学计算", "科学基础模型"], ["交叉与AI4Science"], ["climate-energy"], "交叉与AI4Science"],
  ["地震与地质灾害", ["地震", "地质灾害", "滑坡", "地震波", "风险评估"], ["遥感与地球观测", "科学计算", "时空数据挖掘"], ["交叉与AI4Science"], ["disaster"], "交叉与AI4Science"],
  ["洪水与城市内涝", ["洪水", "内涝", "淹没", "水文模型", "应急"], ["遥感与地球观测", "气候与地球系统", "时空数据挖掘"], ["交叉与AI4Science", "计算与社会"], ["disaster"], "交叉与AI4Science"],
  ["野火监测与预警", ["野火", "火点", "烟雾", "遥感", "预警"], ["遥感与地球观测", "计算机视觉", "时空数据挖掘"], ["交叉与AI4Science", "计算机视觉"], ["disaster"], "交叉与AI4Science"],
  ["海洋生态与渔业", ["海洋生态", "渔业", "海洋遥感", "生物量", "海洋模型"], ["遥感与地球观测", "生态与农业智能", "科学计算"], ["交叉与AI4Science"], ["ocean-space"], "交叉与AI4Science"],
  ["行星探测与行星地质", ["行星", "行星地质", "陨石坑", "火星", "遥感"], ["遥感与地球观测", "计算机视觉", "AI for Physics"], ["交叉与AI4Science"], ["ocean-space"], "交叉与AI4Science"],
  ["农业病虫害识别", ["病虫害", "作物", "叶片", "细粒度识别", "农业遥感"], ["生态与农业智能", "计算机视觉", "小样本学习"], ["计算机视觉", "交叉与AI4Science"], ["agriculture"], "计算机视觉"],
  ["气候变化与地表监测", ["气候变化", "地表", "温度", "遥感", "长期趋势"], ["气候与地球系统", "遥感与地球观测", "时序挖掘"], ["交叉与AI4Science"], ["climate-energy", "remote-sensing"], "交叉与AI4Science"],
  ["夜间灯光与城市计算", ["夜间灯光", "城市", "遥感", "经济指标", "时空分析"], ["遥感与地球观测", "时空数据挖掘", "计算社会科学"], ["交叉与AI4Science", "数据挖掘与信息检索"], ["remote-sensing", "mobility"], "交叉与AI4Science"],
  ["城市计算与空间分析", ["城市计算", "空间分析", "地理数据", "轨迹", "城市感知"], ["时空数据挖掘", "地理信息科学", "计算社会科学"], ["数据挖掘与信息检索", "计算与社会"], ["mobility"], "数据挖掘与信息检索"],

  // 商业、金融、社会与教育
  ["信用评分与风险管理", ["信用评分", "违约风险", "风控", "可解释", "公平性"], ["计算金融", "因果推断与决策", "表格数据学习"], ["数据挖掘与信息检索", "计算与社会"], ["fintech"], "数据挖掘与信息检索"],
  ["保险科技与精算", ["保险", "精算", "风险定价", "理赔", "生存分析"], ["计算金融", "统计推断", "因果推断与决策"], ["数据挖掘与信息检索", "计算与社会"], ["fintech"], "数据挖掘与信息检索"],
  ["量化交易与市场微观结构", ["量化交易", "订单簿", "市场微观结构", "高频", "时序预测"], ["计算金融", "时序挖掘", "强化学习"], ["数据挖掘与信息检索", "理论与算法"], ["fintech"], "数据挖掘与信息检索"],
  ["支付与反洗钱", ["反洗钱", "支付", "异常交易", "图挖掘", "风险网络"], ["计算金融", "图挖掘", "安全与隐私"], ["安全与隐私", "数据挖掘与信息检索"], ["fintech", "security"], "安全与隐私"],
  ["电商搜索与推荐", ["电商搜索", "推荐", "商品理解", "查询改写", "多模态"], ["推荐系统", "信息检索", "多模态检索"], ["数据挖掘与信息检索"], ["ecommerce"], "数据挖掘与信息检索"],
  ["短视频与直播推荐", ["短视频", "直播", "推荐", "多模态", "实时"], ["推荐系统", "多媒体内容理解", "序列与因果推荐"], ["数据挖掘与信息检索", "计算机图形学与多媒体"], ["content-social", "ecommerce"], "数据挖掘与信息检索"],
  ["社交传播与影响力分析", ["社交网络", "传播", "影响力", "信息扩散", "社区发现"], ["社会网络分析", "图挖掘", "计算社会科学"], ["数据挖掘与信息检索", "计算与社会"], ["content-social"], "数据挖掘与信息检索"],
  ["虚假评论与刷单检测", ["虚假评论", "刷单", "异常检测", "图挖掘", "风控"], ["图挖掘", "异常检测", "安全与隐私"], ["安全与隐私", "数据挖掘与信息检索"], ["content-social", "security"], "安全与隐私"],
  ["智能客服与坐席辅助", ["智能客服", "坐席辅助", "对话", "意图识别", "知识库"], ["对话系统与工具智能体", "信息抽取", "检索增强生成"], ["自然语言处理"], ["enterprise"], "自然语言处理"],
  ["文档智能与流程自动化", ["文档理解", "OCR", "表单", "流程自动化", "信息抽取"], ["OCR与文档理解", "信息抽取", "信息系统与业务流程"], ["自然语言处理", "软件工程"], ["enterprise"], "自然语言处理"],
  ["智慧法院与司法辅助", ["司法", "法院", "判决预测", "法律检索", "文书"], ["法律与政务计算", "信息检索", "信息抽取"], ["自然语言处理", "计算与社会"], ["law-gov"], "自然语言处理"],
  ["政务问答与政策分析", ["政务问答", "政策", "政务服务", "知识库", "RAG"], ["法律与政务计算", "检索增强生成", "计算社会科学"], ["自然语言处理", "计算与社会"], ["law-gov"], "自然语言处理"],
  ["语言学习与口语评测", ["语言学习", "口语评测", "发音", "语法纠错", "对话练习"], ["AI辅助教育与学习", "语音识别与合成", "教育测量"], ["计算教育与专业实践", "自然语言处理"], ["edtech"], "计算教育与专业实践"],
  ["老龄照护与跌倒检测", ["老龄", "跌倒检测", "照护", "可穿戴", "辅助技术"], ["数字健康", "可穿戴与普适计算", "可用性与可访问性"], ["人机交互与图形学", "交叉与AI4Science"], ["accessibility", "digital-health"], "人机交互与图形学"],

  // 安全、网络、系统与芯片
  ["漏洞挖掘与自动利用", ["漏洞挖掘", "模糊测试", "程序分析", "利用生成", "漏洞复现"], ["系统安全", "程序分析", "软件测试"], ["安全与隐私", "软件工程"], ["security"], "安全与隐私"],
  ["软件成分分析与供应链安全", ["软件供应链", "SBOM", "依赖分析", "开源组件", "供应链攻击"], ["软件供应链", "软件仓库挖掘", "系统安全"], ["安全与隐私", "软件工程"], ["security"], "安全与隐私"],
  ["云原生安全", ["云安全", "容器", "Kubernetes", "运行时安全", "策略"], ["系统安全", "云计算", "虚拟化"], ["安全与隐私", "分布式与云计算"], ["security"], "安全与隐私"],
  ["工控与关键基础设施安全", ["工控", "SCADA", "关键基础设施", "入侵检测", "CPS安全"], ["工业控制与CPS安全", "系统安全", "网络攻防"], ["安全与隐私", "嵌入式、物联网与CPS"], ["security"], "安全与隐私"],
  ["深度伪造检测与内容溯源", ["深度伪造", "取证", "内容溯源", "生成检测", "水印"], ["媒体取证", "计算机视觉", "安全与隐私"], ["安全与隐私", "计算机图形学与多媒体"], ["security", "content-social"], "安全与隐私"],
  ["隐私增强计算与数据协作", ["隐私计算", "联邦学习", "安全多方计算", "可信执行环境", "差分隐私"], ["隐私计算", "联邦与分布式学习", "密码学应用"], ["安全与隐私", "分布式与云计算"], ["security"], "安全与隐私"],
  ["后量子迁移与密码敏捷", ["后量子", "密码迁移", "密码敏捷", "PQC", "协议升级"], ["后量子密码", "密码学与协议安全", "应用密码学"], ["安全与隐私", "理论与算法"], ["security"], "安全与隐私"],
  ["大模型红队与越狱防御", ["红队", "越狱", "提示注入", "安全对齐", "防御"], ["大模型安全与对齐", "对抗与鲁棒性", "安全评测"], ["安全与隐私", "自然语言处理"], ["security", "llm-systems"], "安全与隐私"],
  ["智能合约审计", ["智能合约", "形式验证", "漏洞检测", "区块链", "审计"], ["区块链与智能合约安全", "形式化安全验证", "程序分析"], ["安全与隐私", "软件工程"], ["security"], "安全与隐私"],
  ["卫星互联网与星地网络", ["卫星互联网", "低轨星座", "星地链路", "路由", "切换"], ["卫星与空间网络", "网络协议与架构", "无线与移动网络"], ["网络与通信"], ["networking", "ocean-space"], "网络与通信"],
  ["6G与通感一体化", ["6G", "通感一体", "太赫兹", "智能超表面", "无线感知"], ["5G与6G移动网络", "无线与移动网络", "网络智能"], ["网络与通信"], ["networking"], "网络与通信"],
  ["算力网络与异构调度", ["算力网络", "异构计算", "任务调度", "资源管理", "数据中心"], ["数据中心资源调度", "分布式系统", "网络协议与架构"], ["网络与通信", "分布式与云计算"], ["networking", "llm-systems"], "网络与通信"],
  ["边缘智能与分布式推理", ["边缘推理", "模型切分", "端边云", "分布式推理", "低时延"], ["边缘与雾计算", "机器学习系统", "轻量化与实时部署"], ["分布式与云计算", "嵌入式、物联网与CPS"], ["edge-ai", "llm-systems"], "分布式与云计算"],
  ["AI编译器与算子优化", ["AI编译器", "算子优化", "图编译", "自动调优", "张量程序"], ["编译器优化与代码生成", "GPU与AI加速器", "机器学习系统"], ["体系结构与高性能计算", "系统与网络"], ["chips", "llm-systems"], "体系结构与高性能计算"],
  ["芯片热管理与可靠性", ["热管理", "可靠性", "老化", "功耗", "封装"], ["硬件可靠性与安全", "低功耗芯片设计", "Chiplet与3D封装"], ["体系结构与高性能计算", "电子设计自动化与计算机工程"], ["chips"], "体系结构与高性能计算"],
  ["开源EDA与硬件敏捷开发", ["开源EDA", "硬件敏捷", "RTL", "形式验证", "开放指令集"], ["电子设计自动化", "硬件验证与形式化", "RISC-V与开放指令集"], ["电子设计自动化与计算机工程"], ["chips"], "电子设计自动化与计算机工程"],

  // 科学、机器人、空间与交叉
  ["科学工作流与自动化实验", ["科学工作流", "自动化实验", "实验编排", "可复现", "实验室"], ["自动化实验室", "科学软件与可复现计算", "科学基础模型"], ["交叉与AI4Science"], ["science"], "交叉与AI4Science"],
  ["材料基因组与高通量筛选", ["材料基因组", "高通量", "材料筛选", "性质预测", "数据库"], ["材料与化学", "AI for Chemistry", "科学基础模型"], ["交叉与AI4Science"], ["science"], "交叉与AI4Science"],
  ["电池与储能材料", ["电池", "储能", "电解质", "循环寿命", "材料设计"], ["材料与化学", "AI for Chemistry", "科学计算"], ["交叉与AI4Science"], ["science", "climate-energy"], "交叉与AI4Science"],
  ["核聚变与等离子体控制", ["核聚变", "等离子体", "托卡马克", "控制", "强化学习"], ["AI for Physics", "科学计算", "控制理论"], ["交叉与AI4Science"], ["science", "climate-energy"], "交叉与AI4Science"],
  ["天文巡天与瞬变源", ["天文", "巡天", "瞬变源", "光变曲线", "星系"], ["AI for Physics", "时空数据挖掘", "计算机视觉"], ["交叉与AI4Science"], ["science", "ocean-space"], "交叉与AI4Science"],
  ["脑机接口与神经工程", ["脑机接口", "神经工程", "解码", "脑电", "刺激"], ["脑机接口", "生物医学信号", "计算神经科学"], ["交叉与AI4Science", "人机交互与图形学"], ["science", "digital-health"], "交叉与AI4Science"],
  ["空间机器人与在轨服务", ["空间机器人", "在轨服务", "捕获", "空间操作", "自主导航"], ["机器人学习", "运动规划", "SLAM与定位"], ["机器人与具身智能"], ["robotics", "ocean-space"], "机器人与具身智能"],
  ["人形机器人与灵巧操作", ["人形机器人", "灵巧手", "全身控制", "操作", "运动"], ["机器人学习", "操作与抓取", "机器人控制"], ["机器人与具身智能"], ["robotics"], "机器人与具身智能"],
  ["集群机器人与蜂群", ["集群", "蜂群", "多机器人", "协同", "编队"], ["多机器人系统", "运动规划", "分布式系统"], ["机器人与具身智能", "分布式与云计算"], ["robotics"], "机器人与具身智能"],
  ["水下机器人与海洋工程", ["水下机器人", "AUV", "声呐", "水下感知", "海洋工程"], ["机器人感知与定位", "SLAM与定位", "遥感与地球观测"], ["机器人与具身智能", "交叉与AI4Science"], ["robotics", "ocean-space"], "机器人与具身智能"],
  ["农业机器人与采摘", ["农业机器人", "采摘", "导航", "作物检测", "田间作业"], ["机器人学习", "机器人感知与定位", "生态与农业智能"], ["机器人与具身智能", "交叉与AI4Science"], ["robotics", "agriculture"], "机器人与具身智能"],
  ["建筑机器人与施工自动化", ["建筑机器人", "施工", "砌筑", "测量", "现场感知"], ["机器人学习", "SLAM与定位", "工业控制系统"], ["机器人与具身智能"], ["robotics", "smart-manufacturing"], "机器人与具身智能"],
  ["危险环境与核工业机器人", ["核工业", "危险环境", "辐射", "遥操作", "巡检"], ["机器人学习", "机器人安全与可信", "硬件可靠性"], ["机器人与具身智能", "安全与隐私"], ["robotics", "security"], "机器人与具身智能"],
  ["生物多样性监测", ["生物多样性", "物种识别", "声景", "相机陷阱", "生态监测"], ["生态与农业智能", "遥感与地球观测", "计算机视觉"], ["交叉与AI4Science", "计算机视觉"], ["agriculture", "remote-sensing"], "交叉与AI4Science"],
  ["碳核算与碳交易", ["碳核算", "碳交易", "碳排放", "碳足迹", "遥感"], ["气候与地球系统", "可持续计算", "计算金融"], ["交叉与AI4Science", "计算与社会"], ["climate-energy", "fintech"], "交叉与AI4Science"],

  // 基础模型、智能体与系统（2026 扩展）
  ["视觉-语言-动作模型", ["VLA", "视觉语言动作", "机器人基础模型", "跨本体迁移", "操作策略"], ["机器人学习", "具身智能", "多模态学习", "强化学习", "操作与抓取"], ["机器人与具身智能"], ["robotics"], "机器人与具身智能"],
  ["GUI智能体与计算机使用", ["GUI智能体", "计算机使用", "界面操作", "屏幕理解", "工具调用"], ["对话与智能体", "多模态学习", "信息抽取", "人机协作与交互"], ["人工智能", "人机交互与图形学"], ["llm-systems", "enterprise"], "人工智能"],
  ["多智能体编排与协作", ["多智能体", "智能体编排", "角色分工", "协作规划", "通信协议"], ["多智能体系统", "对话与智能体", "规划与搜索"], ["人工智能", "分布式与云计算"], ["llm-systems"], "人工智能"],
  ["大模型推理与测试时计算", ["测试时计算", "思维链", "推理模型", "搜索增强推理", "过程奖励"], ["大语言模型", "规划与搜索", "机器学习理论"], ["人工智能"], ["llm-systems"], "人工智能"],
  ["大模型评测与数据污染", ["基准评测", "数据污染", "评测饱和", "动态评测", "可信评测"], ["AI评测与基准", "大语言模型", "数据治理"], ["人工智能", "数据科学与数据工程"], ["llm-systems", "science"], "人工智能"],
  ["长上下文与记忆", ["长上下文", "上下文压缩", "外部记忆", "检索增强", "位置编码"], ["大语言模型", "检索增强生成", "神经信息检索"], ["自然语言处理", "人工智能"], ["llm-systems"], "自然语言处理"],
  ["多模态检索与文档智能", ["多模态检索", "文档理解", "版面分析", "表格问答", "跨模态对齐"], ["多模态检索", "OCR与文档理解", "多模态学习"], ["数据挖掘与信息检索", "计算机视觉"], ["enterprise", "llm-systems"], "数据挖掘与信息检索"],
  ["机制可解释性与表征工程", ["机制可解释性", "稀疏自编码器", "表征工程", "激活干预", "电路分析"], ["可信与可解释AI", "大语言模型", "机器学习理论"], ["人工智能", "安全与隐私"], ["security", "llm-systems"], "人工智能"],
  ["机器遗忘与模型编辑", ["机器遗忘", "模型编辑", "知识更新", "隐私删除", "副作用评估"], ["大模型安全与对齐", "隐私计算", "可信与可解释AI"], ["安全与隐私", "人工智能"], ["security"], "安全与隐私"],
  ["合成数据与数据归因", ["合成数据", "数据归因", "影响力函数", "数据混合", "数据估值"], ["生成式视觉与扩散模型", "数据治理", "大语言模型"], ["数据科学与数据工程", "人工智能"], ["llm-systems", "science"], "数据科学与数据工程"],
  ["扩散语言模型", ["扩散语言模型", "离散扩散", "并行解码", "非自回归生成", "可控生成"], ["生成模型", "深度学习架构", "大语言模型"], ["人工智能", "自然语言处理"], ["llm-systems"], "人工智能"],
  ["时序基础模型", ["时序基础模型", "零样本预测", "时序Transformer", "协变量", "概率预测"], ["时序挖掘", "深度学习架构", "科学计算"], ["数据挖掘与信息检索", "数据科学与数据工程"], ["climate-energy", "fintech", "smart-manufacturing"], "数据挖掘与信息检索"],
  ["图基础模型", ["图基础模型", "图预训练", "迁移学习", "图神经网络", "少样本图学习"], ["图挖掘", "深度学习架构", "知识表示与推理"], ["数据挖掘与信息检索", "人工智能"], ["fintech", "science"], "数据挖掘与信息检索"],
  ["表格基础模型", ["表格基础模型", "表格预训练", "小样本分类", "特征交互", "缺失值"], ["表格数据学习", "AutoML与神经架构搜索", "深度学习架构"], ["数据科学与数据工程", "人工智能"], ["enterprise", "fintech"], "数据科学与数据工程"],
  ["神经算子与PDE基础模型", ["神经算子", "偏微分方程", "算子学习", "物理约束", "数值求解"], ["科学计算", "数值分析与科学计算", "AI for Physics"], ["交叉与AI4Science"], ["science", "climate-energy"], "交叉与AI4Science"],
  ["AI气象与地球系统预报", ["天气预报", "地球系统", "集合预报", "再分析", "极端事件"], ["气候与地球系统", "科学计算", "遥感与地球观测"], ["交叉与AI4Science", "数据科学与数据工程"], ["climate-energy", "disaster", "ocean-space"], "交叉与AI4Science"],
  ["遥感基础模型", ["遥感基础模型", "多光谱", "变化检测", "自监督预训练", "跨传感器"], ["遥感与地球观测", "多模态学习", "图像分割"], ["计算机视觉", "交叉与AI4Science"], ["remote-sensing", "disaster", "climate-energy"], "计算机视觉"],
  ["单细胞与空间组学基础模型", ["单细胞", "空间组学", "细胞类型注释", "扰动预测", "基因表达"], ["基因组学与单细胞分析", "生物信息", "多模态学习"], ["交叉与AI4Science"], ["drug-protein", "science"], "交叉与AI4Science"],
  ["语音大模型与全双工对话", ["语音大模型", "全双工", "语音对话", "流式识别", "副语言"], ["语音识别与合成", "对话与智能体", "大语言模型"], ["自然语言处理", "人机交互与图形学"], ["llm-systems", "accessibility", "enterprise"], "自然语言处理"],
  ["音频理解与生成", ["音频理解", "音频生成", "声音事件", "音乐生成", "音频语言模型"], ["语音增强与声学事件", "多模态学习", "深度学习架构"], ["计算机图形学与多媒体", "自然语言处理"], ["content-social", "games"], "计算机图形学与多媒体"],
  ["具身世界模型", ["世界模型", "具身智能", "视频预测", "模型预测控制", "仿真到现实"], ["视频生成与世界模型", "具身智能", "强化学习", "机器人学习"], ["机器人与具身智能"], ["robotics", "autonomous-driving"], "机器人与具身智能"],
  ["实时三维重建与高斯泼溅", ["3D高斯", "实时重建", "神经渲染", "新视角合成", "动态场景"], ["三维重建与神经渲染", "渲染与几何", "实时渲染与游戏引擎"], ["计算机图形学与多媒体", "计算机视觉"], ["spatial-computing", "games", "digital-humanities"], "计算机图形学与多媒体"],
  ["AI内容取证与来源追踪", ["深度伪造", "内容溯源", "生成检测", "数字取证", "内容凭证"], ["媒体取证与生成检测", "虚假信息与信息生态", "多模态学习"], ["安全与隐私", "计算机视觉"], ["security", "content-social"], "安全与隐私"],
  ["大模型水印与版权保护", ["文本水印", "模型指纹", "版权保护", "训练数据溯源", "水印鲁棒性"], ["数据安全与合规", "媒体取证与生成检测", "大模型安全与对齐"], ["安全与隐私", "计算与社会"], ["security", "law-gov"], "安全与隐私"],
  ["端侧大模型推理", ["端侧推理", "量化", "推测解码", "模型压缩", "异构加速"], ["机器学习系统", "边缘与雾计算", "嵌入式系统与实时调度", "加速器与异构计算"], ["体系结构与高性能计算", "分布式与云计算"], ["edge-ai", "chips"], "体系结构与高性能计算"],
  ["大模型训练系统与容错", ["训练系统", "容错", "检查点", "并行策略", "通信优化"], ["分布式机器学习系统", "容错与崩溃一致性", "并行与分布式计算"], ["分布式与云计算", "体系结构与高性能计算"], ["llm-systems"], "分布式与云计算"],
  ["AI形式数学与定理证明", ["定理证明", "形式化数学", "自动推理", "证明助手", "数学竞赛"], ["数学发现与推理", "自动定理证明", "神经符号人工智能"], ["交叉与AI4Science", "人工智能"], ["science", "llm-systems"], "交叉与AI4Science"],
  ["医学多模态大模型", ["医学多模态", "临床报告生成", "影像问答", "医学VQA", "多模态诊断"], ["医学图像分析", "多模态语言模型", "大语言模型"], ["交叉与AI4Science", "计算机视觉"], ["med-imaging", "clinical"], "交叉与AI4Science"],
  ["法律大模型与合同推理", ["法律大模型", "合同审查", "法条检索", "法律推理", "合规"], ["大语言模型", "信息抽取", "知识表示与推理"], ["计算与社会", "自然语言处理"], ["law-gov", "enterprise"], "计算与社会"],
  ["科学文献智能体", ["文献智能体", "科学发现", "论文检索", "实验规划", "证据综合"], ["科学数据管理", "对话与智能体", "信息抽取", "知识图谱"], ["交叉与AI4Science", "数据挖掘与信息检索"], ["science", "llm-systems"], "交叉与AI4Science"],
];

// 新增方向的公开基准映射：只引用目录中已存在的真实数据集，避免落到大类兜底。
const NEW_BENCHMARK = {
  "视觉-语言-动作模型": { datasets: ["BridgeData V2", "Open X-Embodiment", "CALVIN", "LIBERO", "ManiSkill2", "SimplerEnv"], metrics: ["任务成功率", "平均完成步数", "跨任务 / 跨本体泛化", "真机迁移成功率"], note: "仿真与真机环境差异大，需同时报告仿真成功率与真机抽查结果。" },
  "GUI智能体与计算机使用": { datasets: ["OSWorld", "WebArena", "Mind2Web", "AndroidWorld", "WebVoyager", "GAIA"], metrics: ["任务成功率", "步骤效率", "错误恢复率", "跨平台泛化"], note: "在线环境会变化，复现时记录页面快照、日期与工具版本。" },
  "多智能体编排与协作": { datasets: ["GAIA", "AgentBench", "tau-bench", "ToolBench", "WebArena", "HotpotQA"], metrics: ["任务成功率", "协作轮数", "通信开销", "失败归因可复现性"], note: "多智能体收益需与同等预算的单智能体基线对比。" },
  "大模型推理与测试时计算": { datasets: ["MATH", "GSM8K", "GPQA", "ARC-AGI", "Humanity's Last Exam", "MMLU-Pro"], metrics: ["pass@1 准确率", "采样预算 / token 成本", "推理延迟", "自一致性"], note: "必须同时报告计算预算，否则准确率不可比较。" },
  "大模型评测与数据污染": { datasets: ["MMLU-Pro", "GPQA", "Humanity's Last Exam", "SimpleQA", "HaluEval", "Chatbot Arena"], metrics: ["准确率", "污染检测率", "置信区间", "时间切片稳定性"], note: "公开题面可能进入训练语料，优先使用私有保留集与时间切分。" },
  "长上下文与记忆": { datasets: ["RULER", "LongBench", "MultiHop-RAG", "LongVideoBench", "CRAG", "HotpotQA"], metrics: ["有效上下文长度", "检索 / 定位准确率", "长文问答准确率", "显存与延迟"], note: "标称窗口不等于有效窗口，需在目标长度上单独报告。" },
  "多模态检索与文档智能": { datasets: ["DocVQA", "ChartQA", "CORD", "SciFact", "TabFact", "ScienceQA"], metrics: ["ANLS / 准确率", "字段级 F1", "表格结构准确率", "跨版式泛化"], note: "扫描件与版式变化是主要失败来源，需报告版式切分。" },
  "机制可解释性与表征工程": { datasets: ["MMLU", "TruthfulQA", "HaluEval", "GSM8K", "MATH", "SimpleQA"], metrics: ["因果干预效应", "探针准确率", "重构误差", "能力副作用"], note: "解释结论需通过干预实验验证，相关性证据不足。" },
  "机器遗忘与模型编辑": { datasets: ["WMDP", "TruthfulQA", "MMLU", "HaluEval", "SimpleQA", "GPQA"], metrics: ["遗忘集准确率", "保留集准确率", "对抗恢复率", "副作用评估"], note: "遗忘分数下降不必然等于知识不可恢复，需做对抗探测。" },
  "合成数据与数据归因": { datasets: ["OpenWebText", "C4", "The Pile", "WikiText-103", "MMLU", "GSM8K"], metrics: ["下游任务收益", "数据效率", "分布偏移鲁棒性", "归因 / 许可可追溯性"], note: "合成数据需记录生成模型、提示与过滤规则，避免许可证污染。" },
  "扩散语言模型": { datasets: ["OpenWebText", "C4", "WikiText-103", "The Pile", "MMLU", "GSM8K"], metrics: ["生成质量（PPL / 准确率）", "解码步数", "吞吐", "可控性"], note: "质量与速度需同时报告，单独比较困惑度会掩盖解码预算差异。" },
  "时序基础模型": { datasets: ["Monash Time Series Forecasting Archive", "GIFT-Eval", "TSB-AD", "UCR Time Series Archive", "UEA Time Series Classification Archive", "Weather"], metrics: ["MASE / sMAPE", "CRPS", "零样本迁移", "推理成本"], note: "频率与预测长度组合多，需报告完整任务矩阵。" },
  "图基础模型": { datasets: ["Open Graph Benchmark", "Temporal Graph Benchmark", "Cora", "Graph500"], metrics: ["ROC-AUC / AP", "MRR", "跨图迁移", "时间外推"], note: "直推与归纳设置不可混比，需说明划分方式。" },
  "表格基础模型": { datasets: ["Folktables", "Adult", "Home Credit", "IEEE-CIS Fraud", "German Credit", "TabFact"], metrics: ["AUC / 准确率", "校准误差 ECE", "小样本表现", "缺失值鲁棒性"], note: "表格任务需固定预处理与缺失值策略，否则结果不可复现。" },
  "神经算子与PDE基础模型": { datasets: ["PDEBench", "The Well", "ClimSim", "WeatherBench 2", "ERA5", "ClimateBench"], metrics: ["相对 L2 误差", "长期 rollout 稳定性", "跨分辨率泛化", "推理成本"], note: "长期 rollout 稳定性比单步误差更能暴露模型缺陷。" },
  "AI气象与地球系统预报": { datasets: ["WeatherBench 2", "ERA5", "ClimSim", "ClimateBench", "The Well", "Weather"], metrics: ["RMSE / ACC", "极端事件命中率", "集合离散度", "预报时效"], note: "再分析数据与观测存在偏差，需说明验证数据来源。" },
  "遥感基础模型": { datasets: ["BigEarthNet", "fMoW", "SpaceNet", "xView", "EuroSAT", "SEN12MS"], metrics: ["mIoU / mAP", "跨传感器泛化", "变化检测 F1", "推理吞吐"], note: "跨区域与跨传感器迁移是关键检验，单一区域高分不足。" },
  "单细胞与空间组学基础模型": { datasets: ["CZ CELLxGENE Census", "Human Cell Atlas", "GTEx", "KEGG", "STRING", "Allen Brain Atlas"], metrics: ["细胞类型注释准确率", "扰动预测相关性", "批次效应校正", "跨组织泛化"], note: "批次效应与数据泄漏会显著高估性能，需按供体划分。" },
  "语音大模型与全双工对话": { datasets: ["GigaSpeech", "LibriSpeech", "LibriTTS", "LJSpeech", "Speech Commands", "VoxCeleb"], metrics: ["WER / CER", "对话轮次延迟", "打断响应正确率", "副语言情感 F1"], note: "全双工需报告延迟分位数与打断场景，而非仅离线 WER。" },
  "音频理解与生成": { datasets: ["AudioCaps", "AudioSet", "FSD50K", "VoxCeleb", "Speech Commands", "GigaSpeech"], metrics: ["mAP / 准确率", "FAD / 主观评分", "文本相关性", "生成多样性"], note: "生成质量需结合客观指标与人工听测。" },
  "具身世界模型": { datasets: ["DM Control", "D4RL", "Atari 100k", "ManiSkill2", "nuScenes", "CALVIN"], metrics: ["长程预测误差", "任务成功率", "sim-to-real 差距", "规划成功率"], note: "世界模型的价值需通过下游规划或策略学习验证。" },
  "实时三维重建与高斯泼溅": { datasets: ["DL3DV-10K", "Replica", "Mip-NeRF 360", "Tanks and Temples", "ScanNet", "3D-FRONT"], metrics: ["PSNR / SSIM / LPIPS", "重建时间", "渲染帧率", "动态场景一致性"], note: "需同时报告画质与实时性，并说明训练视角与评测视角划分。" },
  "AI内容取证与来源追踪": { datasets: ["FaceForensics++", "FFHQ", "CelebA", "LFW", "COCO", "ImageNet"], metrics: ["AUC / 准确率", "跨生成器泛化", "压缩 / 裁剪鲁棒性", "溯源证据完整率"], note: "跨生成器与后处理鲁棒性是核心，单一数据集高分不可外推。" },
  "大模型水印与版权保护": { datasets: ["C4", "OpenWebText", "The Pile", "WikiText-103", "MMLU", "GSM8K"], metrics: ["检测 AUC", "误报率", "改写攻击下的保留率", "文本质量损失"], note: "水印需报告攻击条件下的检测率与误报率。" },
  "端侧大模型推理": { datasets: ["MLPerf", "GLUE", "SQuAD", "ImageNet", "COCO", "WikiText-103"], metrics: ["延迟 / 吞吐", "内存占用", "能耗", "精度损失"], note: "需固定设备、功耗模式与批大小，否则延迟不可比。" },
  "大模型训练系统与容错": { datasets: ["MLPerf", "Alibaba Cluster Trace", "C4", "The Pile", "ImageNet", "GLUE"], metrics: ["吞吐 / MFU", "故障恢复时间", "有效训练占比", "收敛稳定性"], note: "容错结论需包含故障注入实验与恢复后的收敛证据。" },
  "AI形式数学与定理证明": { datasets: ["MiniF2F", "MATH", "OlympiadBench", "GSM8K", "GPQA", "MMLU-Pro"], metrics: ["证明通过率", "形式化验证通过率", "步骤正确率", "搜索预算"], note: "自然语言答案与形式化证明通过是两种证据，需分开报告。" },
  "医学多模态大模型": { datasets: ["MedMCQA", "MedQA", "MIMIC-CXR", "CheXpert", "PubMedQA", "ScienceQA"], metrics: ["准确率 / F1", "临床报告生成指标", "幻觉率", "医生评审通过率"], note: "基准分数不能替代临床验证；需说明数据脱敏与伦理审批。" },
  "法律大模型与合同推理": { datasets: ["CAIL", "LexGLUE", "CUAD", "LegalBench", "ContractNLI", "CaseHOLD"], metrics: ["法条 / 罪名 F1", "判决预测准确率", "引用准确率", "拒答与合规率"], note: "法律结论需可追溯到法条与案例，预测分数不等于法律正确性。" },
  "科学文献智能体": { datasets: ["SciCode", "SciFact", "ScienceQA", "PubMedQA", "QASPER", "SciDocs"], metrics: ["证据引用准确率", "检索召回率", "实验步骤可执行率", "结论可核查率"], note: "必须逐条给出可核验的文献标识；无法核验时明确标注。" },
};

for (const [name, entry] of Object.entries(NEW_BENCHMARK)) bench.directions[name] = entry;
write("benchmarks.json", bench);

// 补充 4 个应用标签（招聘 / 广告 / 体育 / 企业流程），并补芯片映射。
const byId = Object.fromEntries(appsFile.groups.flatMap((g) => g.apps.map((a) => [a.id, a])));
const ensureApp = (groupName, app) => {
  let group = appsFile.groups.find((g) => g.name === groupName);
  if (!group) { group = { name: groupName, apps: [] }; appsFile.groups.push(group); }
  if (!group.apps.some((a) => a.id === app.id)) group.apps.push(app);
};
ensureApp("商业、社会与教育", { id: "recruiting", name: "招聘与人力资源", terms: ["招聘", "简历", "人岗匹配", "人才画像", "recruiting", "resume"], categories: ["数据挖掘与信息检索", "自然语言处理"], directions: ["招聘与人岗匹配", "推荐系统", "信息抽取", "社会网络分析"], note: "简历解析、人岗匹配与人才画像；公平性与隐私是主要风险。" });
ensureApp("商业、社会与教育", { id: "advertising", name: "广告与营销", terms: ["广告", "营销", "点击率", "竞价", "CTR", "advertising"], categories: ["数据挖掘与信息检索"], directions: ["广告与营销计算", "推荐系统", "因果推断与决策", "序列与因果推荐"], note: "点击率预估、竞价与增量测量；离线 AUC 不能证明业务收益。" });
ensureApp("商业、社会与教育", { id: "sports", name: "体育与运动", terms: ["体育", "运动分析", "比赛", "战术", "sports analytics"], categories: ["计算机视觉", "数据挖掘与信息检索"], directions: ["体育计算与运动分析", "人体与动作理解", "视频理解", "可穿戴与普适计算"], note: "动作分析、事件检测与战术建模；遮挡和快速运动是常见失败点。" });
ensureApp("商业、社会与教育", { id: "enterprise", name: "企业服务与流程自动化", terms: ["智能客服", "流程自动化", "RPA", "企业服务", "workflow automation"], categories: ["自然语言处理", "软件工程"], directions: ["企业对话与流程自动化", "对话系统与工具智能体", "信息系统与业务流程", "检索增强生成"], note: "客服对话、工单流转与流程自动化；权限和可审计性优先。" });
if (byId.chips) for (const n of ["芯片设计与验证自动化"]) if (!byId.chips.directions.includes(n)) byId.chips.directions.push(n);
write("applications.json", appsFile);

const directionByName = new Map(index.directions.filter((d) => !d.aliasOf).map((d) => [d.name, d]));
const existingFiles = new Set(index.directions.filter((d) => !d.aliasOf).map((d) => d.id));
let nextId = Math.max(...index.directions.filter((d) => /^d\d+$/.test(d.id)).map((d) => Number(d.id.slice(1)))) + 1;

const appOfDirection = new Map();
for (const g of appsFile.groups) for (const a of g.apps) for (const n of a.directions) {
  if (!appOfDirection.has(n)) appOfDirection.set(n, []);
  appOfDirection.get(n).push(a);
}

const datasetByName = new Map(bench.datasets.map((d) => [d.name, d]));
const norm = (s) => String(s || "").toLowerCase().replace(/\s+/g, " ").trim();

function pickDatasets(dir) {
  const explicit = bench.directions[dir.name];
  const out = [];
  const push = (name) => {
    if (!name || out.some((d) => d.name === name)) return;
    out.push(datasetByName.get(name) || { name, task: "", url: "", note: "目录中暂无该基准的官方链接，请检索名称确认。" });
  };
  if (explicit) for (const n of explicit.datasets || []) push(n);
  for (const app of appOfDirection.get(dir.name) || []) {
    for (const ds of bench.datasets) {
      if ((ds.applications || []).includes(app.name)) push(ds.name);
      if (out.length >= 6) break;
    }
  }
  for (const ds of bench.datasets) {
    if ((ds.categories || []).includes(dir.category)) push(ds.name);
    if (out.length >= 8) break;
  }
  if (!out.length) for (const n of ["COCO", "ImageNet", "GLUE", "MovieLens"]) push(n);
  return out.slice(0, 6);
}

function benchmarkFor(dir) {
  const explicit = bench.directions[dir.name] || {};
  const metrics = explicit.metrics || bench.metrics[dir.category] || bench.metrics["应用领域"];
  const baselines = explicit.baselines || bench.baselines[dir.category] || bench.baselines["应用领域"];
  return {
    datasets: pickDatasets(dir),
    metrics,
    baselines,
    note: explicit.note || "基准来自项目人工整理的公开目录；使用前请核对官方划分、许可与评测协议。",
  };
}

// 1) 补充应用型方向
for (const [name, kws, fields, cats, appIds, category] of NEW) {
  if (directionByName.has(name)) continue;
  const id = `d${nextId++}`;
  const entry = { id, name, category: category || "应用领域", keywords: kws.slice(0, 8), terms: [name, ...kws], papers: 0, apps: appIds };
  index.directions.push(entry);
  directionByName.set(name, entry);
  if (!appOfDirection.has(name)) appOfDirection.set(name, appIds.map((x) => byId[x]).filter(Boolean));
  for (const appId of appIds) {
    const app = byId[appId];
    if (app && !app.directions.includes(name)) app.directions.push(name);
  }
}
write("applications.json", appsFile);

// 2) 应用标签补到全部方向（含基础方向）
for (const dir of index.directions) {
  if (dir.aliasOf) continue;
  const apps = (appOfDirection.get(dir.name) || []).map((a) => a.id);
  if (apps.length) dir.apps = [...new Set([...(dir.apps || []), ...apps])];
}

// 3) 类别与统计重算
const counts = {};
for (const d of index.directions) if (!d.aliasOf) counts[d.category] = (counts[d.category] || 0) + 1;
for (const c of index.categories) c.count = counts[c.name] || 0;
if (!index.categories.some((c) => c.name === "应用领域")) index.categories.push({ name: "应用领域", count: counts["应用领域"] || 0 });
index.stats.directions = index.directions.filter((d) => !d.aliasOf).length;
index.stats.categories = index.categories.length;
index.stats.applicationTags = appsFile.groups.reduce((s, g) => s + g.apps.length, 0);
index.stats.curatedDatasets = bench.datasets.length;
index.version = "2026-11-17b";

// 4) 新方向详情文件
const gapBase = {
  scope: index.gap.scope || "全库",
  total: index.gap.total || 0,
  methods: index.gap.methods || [],
  tasks: index.gap.tasks || [],
  combos: (index.gap.combos || []).slice(0, 16),
  gaps: (index.gap.gaps || []).slice(0, 8),
  issueGaps: index.gap.issue_gaps || [],
  rising: index.gap.rising || [],
};
const emptyGap = { scope: "", total: 0, methods: [], tasks: [], combos: [], gaps: [], issueGaps: [], rising: [] };

function advisorsFor(dir, fields, cats) {
  const fieldSet = fields.map(norm);
  const catSet = cats.map(norm);
  const termSet = dir.terms.map(norm).filter((t) => t.length >= 2);
  const scored = [];
  for (const a of advisors) {
    const fieldsA = (a.fields || []).map(norm);
    const kwA = (a.keywords || []).map(norm);
    let score = 0;
    for (const f of fieldsA) if (fieldSet.some((x) => f.includes(x) || x.includes(f))) score += 34;
    if (catSet.includes(norm(a.category))) score += 10;
    for (const k of kwA) if (termSet.some((t) => k.includes(t))) score += 14;
    if (!score) continue;
    scored.push({ a, score: score + Math.min(12, Math.log10((a.cited || 0) + 10) * 2) });
  }
  scored.sort((x, y) => y.score - x.score || (y.a.cited || 0) - (x.a.cited || 0));
  const picked = [];
  const seen = new Set();
  for (const { a, score } of scored) {
    if (seen.has(a.name)) continue;
    seen.add(a.name);
    picked.push(toAdvisor(a, score));
    if (picked.length >= 12) break;
  }
  if (picked.length < 12) {
    const pool = advisors.filter((a) => catSet.includes(norm(a.category))).sort((x, y) => (y.cited || 0) - (x.cited || 0));
    for (const a of pool) {
      if (seen.has(a.name)) continue;
      seen.add(a.name);
      picked.push(toAdvisor(a, 6, ["大类兜底"]));
      if (picked.length >= 12) break;
    }
  }
  return picked;
}

function toAdvisor(a, score, extra = []) {
  return {
    name: a.name, institution: a.institution || "", institutionZh: a.institutionZh || a.institution || "",
    province: a.province || "", country: a.country === "CN" ? "中国" : a.country || "",
    cited: a.cited || 0, works: a.works || 0, fields: (a.fields || []).slice(0, 2),
    keywords: (a.keywords || []).slice(0, 2), orcid: a.orcid || "", score: Math.round(score),
    reasons: [...new Set([...(a.fields || []).slice(0, 1), ...extra, "引用量排序"])].slice(0, 3),
  };
}

const repVenueCache = new Map();
function venuesFor(cats) {
  for (const cat of cats) {
    if (repVenueCache.has(cat)) return repVenueCache.get(cat);
    const rep = index.directions.find((d) => d.category === cat && !d.aliasOf && existingFiles.has(d.id));
    if (!rep) continue;
    const p = path.join(DATA, "directions", `${rep.id}.json`);
    if (!fs.existsSync(p)) continue;
    const data = JSON.parse(fs.readFileSync(p, "utf8"));
    if (data.venues?.length) { repVenueCache.set(cat, data.venues); return data.venues; }
  }
  return [];
}

let created = 0;
const freshNames = new Set(Object.keys(NEW_BENCHMARK));
for (const [name, kws, fields, cats, appIds, category] of NEW) {
  const dir = directionByName.get(name);
  if (!dir) continue;
  const target = path.join(DATA, "directions", `${dir.id}.json`);
  if (fs.existsSync(target)) {
    if (!freshNames.has(name)) continue;
    const data = JSON.parse(fs.readFileSync(target, "utf8"));
    data.apps = appIds;
    data.benchmark = benchmarkFor(dir);
    write(path.join("directions", `${dir.id}.json`), data);
    continue;
  }
  const payload = {
    id: dir.id, name, category: category || "应用领域",
    scope: { localTotal: 0, scopeKeyword: "", gapSource: "全库", note: `应用型方向：本地 345 篇文献未单独覆盖「${name}」。下方候选来自全库共现结构，仅作结构参考，不代表该应用方向已有文献空白。` },
    advisors: advisorsFor(dir, fields, cats),
    venues: venuesFor(cats),
    gap: gapBase,
    localGap: emptyGap,
    papers: [],
    apps: appIds,
    benchmark: benchmarkFor(dir),
  };
  write(path.join("directions", `${dir.id}.json`), payload);
  created += 1;
}

// 5) 为每个已有方向补 benchmark 与 apps（不重写算法字段）
for (const [name, dir] of directionByName) {
  const p = path.join(DATA, "directions", `${dir.id}.json`);
  if (!fs.existsSync(p)) continue;
  const data = JSON.parse(fs.readFileSync(p, "utf8"));
  const apps = (appOfDirection.get(name) || []).map((a) => a.id);
  data.apps = [...new Set([...(data.apps || []), ...apps])];
  data.benchmark = data.benchmark?.datasets?.length ? data.benchmark : benchmarkFor(dir);
  write(path.join("directions", `${dir.id}.json`), data);
}

// 6) 应用的索引映射补齐（含新增应用）
const appCounts = {};
for (const a of appsFile.groups.flatMap((g) => g.apps)) for (const n of a.directions) appCounts[n] = (appCounts[n] || 0) + 1;
index.applicationIndex = appsFile.groups.flatMap((g) => g.apps.map((a) => ({ id: a.id, name: a.name, group: g.name, count: a.directions.filter((n) => directionByName.has(n)).length })));

write("index.json", index);
console.log(`directions=${index.stats.directions} categories=${index.stats.categories} apps=${index.stats.applicationTags} datasets=${index.stats.curatedDatasets} newDirectionFiles=${created}`);
