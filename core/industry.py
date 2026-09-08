# -*- coding: utf-8 -*-
"""行业基准参照表:加载、查询、注入机器引擎。

背景:行业类指标(毛利率行业偏离、营收增长偏离、人均产值/薪酬行业倍数、背离指数)
需要『行业人均产值 / 行业人均薪酬 / 行业平均毛利率 / 行业营收增速』等外部基准。
本模块提供:
- 内置基准表(data/industry_baseline.json)的查询(默认值为示意参考,非权威统计);
- 把选定行业的基准以 `extra.ind_*` 键注入 finance,供数值硬规则引擎直接引用;
- 页面人工录入的覆盖值(override)优先于内置默认值,可靠性由录入人背书。

基准注入后:
- machine_metrics.json 中引用 `extra.ind_*` 的指标即可机算转正;
- 行业无基准或某项不适用(值为 None/未录入)时,该键不注入,
  引擎按 requires_extra 缺失自动标『无法计算』,不会误判为正常。
"""
import json
from pathlib import Path

import config

BASELINE_FILE = Path(config.DATA_DIR) / "industry_baseline.json"

# 与 machine_metrics.json 中 extra.ind_* 引用的键一一对应
KEYS = ("per_capita_output", "per_capita_pay", "gross_margin", "rev_growth")


def _load() -> dict:
    with open(BASELINE_FILE, encoding="utf-8") as f:
        return json.load(f)


def names() -> list:
    """基准表已提供参考值的全部行业门类(与 industry.json 枚举一致)。"""
    return list((_load().get("baseline") or {}).keys())


def baseline(industry: str) -> dict:
    """返回某行业的基准值 dict(值可能为 None = 该口径不适用/未提供);行业未知返回 {}。"""
    if not industry:
        return {}
    return (_load().get("baseline") or {}).get(industry) or {}


def inject(finance: dict, industry: str, override: dict = None):
    """把行业基准注入 finance 深拷贝的 extra.ind_* 键(override 人工录入优先)。

    Args:
        finance: 抽取结果 {Y0..Y2, quarter, extra, ...}
        industry: 公司所属行业门类
        override: 页面人工录入的覆盖值 {per_capita_output: 92.0, ...}(仅含用户显式录入键)
    Returns:
        (finance, applied): 注入后的 finance 与最终采用的 {ind_*: 值} 映射
        (供 UI 展示实际采用的基准);行业为空或基准表全缺时返回原 finance。
    """
    ov = {k: v for k, v in (override or {}).items() if v is not None}
    src = {}
    for k in KEYS:
        if k in ov:
            src[k] = ov[k]
        else:
            bv = baseline(industry).get(k)
            if bv is not None:
                src[k] = bv
    if not src:
        return finance, {}
    fin = json.loads(json.dumps(finance, ensure_ascii=False))
    ex = dict(fin.get("extra") or {})
    ex.update({f"ind_{k}": v for k, v in src.items()})
    fin["extra"] = ex
    return fin, {f"ind_{k}": v for k, v in src.items()}
