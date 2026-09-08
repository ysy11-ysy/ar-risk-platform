# -*- coding: utf-8 -*-
"""面向大模型的中文提示词模板(角色设定 + 任务 + 输出约束)。"""
from core import fields as F

AUDITOR_SYS = (
    "你是一位具备注册会计师(审计)专业能力、熟悉中国证监会行政处罚案例的资深审计专家,"
    "正在使用一套『年报舞弊风险规则库』对上市公司年报做风险筛查。"
    "你严谨、克制,区分『定量指标的统计异常』与『构成舞弊风险的结论』,"
    "所有结论必须给出年报文本或数值依据,不允许编造年报中不存在的内容。"
    "始终使用简体中文。"
)


def _field_list() -> str:
    return "\n".join(f"- {cn}(键名 {k})" for k, cn, _ in F.FIELDS)


def schema_block() -> str:
    """给模型的财务科目 JSON 输出模板(年度结构 Y0/Y1/Y2 + 季度 + 附注)。"""
    annual_keys = F.ALL_ANNUAL_KEYS
    return f"""{{
  "year": "审计年度,如 2023",
  "company": "公司全称",
  "unit": "万元",
  "Y0": {{ {', '.join(f'"{k}": <数值或null>' for k in annual_keys)} }},
  "Y1": {{ ...同上一年度... }},
  "Y2": {{ ...再上一年度... }},
  "quarter": {{
     "q1_rev": <数值>, "q2_rev": <数值>, "q3_rev": <数值>, "q4_rev": <数值>,
     "q1_cost": <数值>, "q2_cost": <数值>, "q3_cost": <数值>, "q4_cost": <数值>,
     "next_q1_rev": <次年一季度营业收入,无则 null>
  }},
  "extra": {{
     "top5_customer_ratio": <前五大客户销售占比%,无则 null>,
     "top1_customer_ratio": <第一大客户销售占比%,无则 null>,
     "related_sales_ratio": <关联方销售占比%,无则 null>,
     "pledge_ratio": <实控人质押比例%,无则 null>,
     "special_events": "<年报提及的本年度重大特殊事件,如并购/新产能/行业波动/政策/诉讼等,无则空串>"
  }}
}}"""


def extract_finance_prompt(annual_text: str, page_hint: str = "") -> tuple:
    """返回 (system, user)。annual_text 为年报文本(可截断到关键章节)。"""
    user = f"""请阅读下面的年报文本({page_hint}),提取审计年度三大报表的财务科目数值。

要求:
1. 金额一律换算为「万元」:如 12.34 亿元 → 123400 万元;保留两位小数。
2. Y0/Y1/Y2 三列:Y0 为本期(审计年度)合并报表口径,Y1/Y2 依次为上年、前年(取自年报"上年同期数"列)。找不到该年度数据时填 null,不得猜测。
3. 优先用「合并资产负债表 / 合并利润表 / 合并现金流量表」;若正文只给了母公司口径,extra 中注明口径差异。
4. quarter 从年报「分季度主要财务数据」节取;找不到对应季度的填 null;若 Q4 未直接披露,可用全年-前三季推算并在备注说明。
5. 员工人数取「在职员工的数量合计(人)」,staff_end 为期末、staff_begin 为上年同期/期初。
6. 只输出一个 JSON 对象,不要输出任何解释文字。字段模板:

{schema_block()}

可用科目键名说明:
{_field_list()}

===== 年报文本开始 =====
{annual_text}
===== 年报文本结束 =====
"""
    return AUDITOR_SYS, user


# ---------------- 第二步:指标计算 ----------------

def calc_metrics_prompt(rule_text: str, finance_json: str, risk_ids: list) -> tuple:
    user = f"""第一步已完成:从年报中抽取了财务科目(单位:万元,结构 Y0/Y1/Y2 与 quarter、extra)。

财务科目 JSON:
{finance_json}

现在执行第二步:依据风险规则库,对风险 {','.join(risk_ids)} 的全部信号指标逐项计算数值,并依据阈值判定风险等级。

规则库(截取):
{rule_text}

要求:
1. 能计算的指标必须代入科目数值计算并给出结果值(value);缺数据无法计算的,level 填 "无法计算" 并说明缺哪个科目。
2. 判定级别只能取:高风险 / 关注 / 正常 / 无法计算。当阈值要求"连续两年"时需用 Y0、Y1 两个年度判断;要求"行业对标"而没有行业数据时,按公司自身历史趋势判断并在 basis 中说明局限。
3. 只做客观计算与阈值比对,不要下"舞弊"结论;basis 一律极简,≤12 个汉字,只写判定口径或依据(如"Q4占比骤升""连续两年为负"),不得展开论述。
4. 返回 JSON 数组(单行紧凑,不要缩进、空行、编号或任何注释),每个元素:
{{"risk_id":"R00X","signal_id":"R00X-SYY","indicator":"指标名称","value":<数值,无量纲百分比/比率直接用数值,无法计算为null>,"unit":"%或倍或天或空","level":"高风险|关注|正常|无法计算","basis":"判定依据一句话"}}
对规则库列出的每一个信号及其每一个指标都必须输出一行,不得遗漏、不得合并;只输出 JSON 数组,不要任何额外文字。"""
    return AUDITOR_SYS, user


# ---------------- 第三步:疑点核验 ----------------

def verify_prompt(rule_text: str, signal: dict, metric_brief: str,
                  report_excerpts: str, finance_json: str, industry: str) -> tuple:
    kw = (signal.get("keywords") or "").strip()
    user = f"""第二步筛查到以下异常指标(疑点),请执行第三步:回到年报原文核查——该异常是否由特殊/偶发事件合理解释。

【目标公司行业】{industry or "未指定"}

【疑点信号】
{signal['id']} {signal['name']}
指标计算情况:{metric_brief or "见下"}
规则关键词(用于定位年报相关段落):{kw}

【命中规则与判定标准】
{rule_text}

【从年报原文召回的相关段落】(关键词定位结果)
{report_excerpts or "(未召回段落)"}

【财务科目】(单位:万元)
{finance_json[:6000]}

请判断:
1. explanation:年报中对上述异常给出的原因解释(逐条引用或概括原文表述,未提及则写"年报未直接解释")。
2. reason_type:该原因属于哪类——经营扩张 / 行业周期 / 会计政策变更 / 并购重组 / 季节性或项目性 / 偶发事件 / 披露缺陷 / 无合理解释 / 其他。
3. acceptable:该原因能否被接受(是/否)。判断口径:有实质业务证据支撑(产能投产、新客户订单、回款、行业数据、期后事项等)且与异常幅度匹配 → 是;解释空泛、与数值幅度不匹配、自相矛盾或只有口号性表述 → 否。
4. verdict: 最终意见,只能取:可接受-视为无问题 / 存疑-建议关注 / 确定为风险点(acceptable=否且无其他合理解释时)。
5. manual_review:需要人工进一步核验的事项清单(数组,≤4 项,每一项写明"核什么、看年报哪个部分/外部资料")。
6. evidence:年报原文中最能支持结论的一句话(原文照抄,限 200 字)。

只输出 JSON:
{{"signal_id":"{signal['id']}","suspicious":true,"explanation":"...","reason_type":"...","acceptable":true或false,"verdict":"可接受-视为无问题|存疑-建议关注|确定为风险点","manual_review":["..."],"evidence":"..."}}
只输出 JSON,不要任何额外文字。"""
    return AUDITOR_SYS, user


def keyword_extract_prompt(signal: dict, excerpts: str) -> tuple:
    """把命中的段落整理为证据片段(保留上下文)由前端直接展示,无需 LLM;保留接口。"""
    return "", ""
