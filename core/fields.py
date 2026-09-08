# -*- coding: utf-8 -*-
"""财务科目表(schema):定义年报中需要抽取/录入的科目集合。

金额单位统一为「万元」。历史期 Y0=审计年度,Y1=上一年度,Y2=再上一年度。
"""
# (键, 中文名, 来源表)
FIELDS = [
    # ---- 利润表 ----
    ("revenue",             "营业收入",                     "利润表"),
    ("cost",                "营业成本",                     "利润表"),
    ("net_profit",          "净利润",                       "利润表"),
    ("net_profit_parent",   "归属于母公司所有者的净利润",     "利润表"),
    ("deduct_profit",       "扣除非经常性损益后的净利润",     "利润表"),
    ("sales_expense",       "销售费用",                     "利润表"),
    ("admin_expense",       "管理费用",                     "利润表"),
    ("rd_expense",          "研发费用",                     "利润表"),
    ("finance_expense",     "财务费用",                     "利润表"),
    # ---- 现金流量表 ----
    ("cfo_net",             "经营活动产生的现金流量净额",     "现金流量表"),
    ("cfo_inflow",          "经营活动现金流入小计",           "现金流量表"),
    ("sales_cash_in",       "销售商品、提供劳务收到的现金",   "现金流量表"),
    ("staff_cash_out",      "支付给职工以及为职工支付的现金", "现金流量表"),
    ("other_op_cash_out",   "支付的其他与经营活动有关的现金", "现金流量表"),
    ("buy_goods_cash_out",  "购买商品、接受劳务支付的现金",   "现金流量表"),
    ("asset_cash_out",      "购建固定资产、无形资产和其他长期资产支付的现金", "现金流量表"),
    # ---- 资产负债表 ----
    ("cash",                "货币资金",                     "资产负债表"),
    ("ar",                  "应收账款",                     "资产负债表"),
    ("ar_notes",            "应收票据及应收账款(如合并列示)", "资产负债表"),
    ("adv_receipt",         "预付款项",                     "资产负债表"),
    ("other_receivable",    "其他应收款",                   "资产负债表"),
    ("inventory",           "存货",                         "资产负债表"),
    ("contract_liab",       "合同负债",                     "资产负债表"),
    ("adv_from_customer",   "预收款项",                     "资产负债表"),
    ("current_assets",      "流动资产合计",                 "资产负债表"),
    ("current_liab",        "流动负债合计",                 "资产负债表"),
    ("total_assets",        "资产总计",                     "资产负债表"),
    ("total_liab",          "负债合计",                     "资产负债表"),
    ("fixed_assets",        "固定资产",                     "资产负债表"),
    ("cip",                 "在建工程",                     "资产负债表"),
    ("intangible_assets",   "无形资产",                     "资产负债表"),
    ("dev_expenditure",     "开发支出",                     "资产负债表"),
    ("goodwill",            "商誉",                         "资产负债表"),
    ("st_loan",             "短期借款",                     "资产负债表"),
    ("lt_loan",             "长期借款",                     "资产负债表"),
    ("bond_payable",        "应付债券",                     "资产负债表"),
    ("noncurrent_liab_due", "一年内到期的非流动负债",         "资产负债表"),
    ("equity_total",        "所有者权益合计",               "资产负债表"),
    ("equity_parent",       "归属于母公司所有者权益",        "资产负债表"),
    ("restricted_cash",     "受限货币资金(如披露)",         "资产负债表附注"),
    # ---- 减值/备抵 ----
    ("bad_allowance",       "应收账款坏账准备余额",          "附注"),
    ("credit_loss",         "信用减值损失",                 "利润表"),
    ("inventory_loss",      "存货跌价准备余额",              "附注"),
    # ---- 季度(分季度主要财务数据)----
    ("q1_rev", "第一季度营业收入", "分季度数据"), ("q2_rev", "第二季度营业收入", "分季度数据"),
    ("q3_rev", "第三季度营业收入", "分季度数据"), ("q4_rev", "第四季度营业收入", "分季度数据"),
    ("q1_cost", "第一季度营业成本", "分季度数据"), ("q2_cost", "第二季度营业成本", "分季度数据"),
    ("q3_cost", "第三季度营业成本", "分季度数据"), ("q4_cost", "第四季度营业成本", "分季度数据"),
    ("next_q1_rev", "次年第一季度营业收入(如有)", "分季度数据"),
    # ---- 员工/人均 ----
    ("staff_end",           "期末在职员工人数(人)",          "年报员工情况"),
    ("staff_begin",         "期初在职员工人数(人)",          "年报员工情况"),
]

FIELD_CN = {k: cn for k, cn, _ in FIELDS}
FIELD_SRC = {k: src for k, cn, src in FIELDS}

# 附注/定性类信息(LLM 用文本回答,不要求精确金额)
EXTRA_ITEMS = [
    ("top5_customer_ratio", "前五大客户销售占比(CR5,%)"),
    ("top1_customer_ratio", "第一大客户销售占比(CR1,%)"),
    ("related_sales_ratio", "关联方销售占营业收入比例(%)"),
    ("pledge_ratio",        "实际控制人股权质押比例(%)"),
    ("ar_overdue_note",     "应收账款逾期/账龄结构是否恶化(简述)"),
    ("special_events",      "本年度发生的重大特殊事项(重组、并购、行业周期、政策变化、新产能投产、自然灾害、诉讼和解等,简述)"),
    ("q4_revenue_note",     "第四季度收入集中度的年报解释(如有)"),
]

ALL_ANNUAL_KEYS = [k for k, _, _ in FIELDS if k not in (
    "q1_rev", "q2_rev", "q3_rev", "q4_rev", "q1_cost", "q2_cost", "q3_cost", "q4_cost", "next_q1_rev")]
QUARTER_KEYS = ["q1_rev", "q2_rev", "q3_rev", "q4_rev", "q1_cost", "q2_cost", "q3_cost", "q4_cost", "next_q1_rev"]
