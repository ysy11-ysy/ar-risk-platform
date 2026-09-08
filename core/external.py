# -*- coding: utf-8 -*-
"""可选联网增强:从可配置 JSON 源拉取行业参考值,仅供人工核对后应用。

定位:联网只作『行业基准表』的可选补充,绝不自动进入机器判定——拉取结果必须在
②页 由人工核对来源与口径后点『应用联网值』才生效(写入 ind_override,可靠性由人背书)。

设计约束:
- 不内置任何第三方数据源。中国公开免费的『行业人均产值/毛利率』结构化接口不可靠且
  口径不一(统计局城镇工资 ≠ 年报人均薪酬),硬接会造成虚假精确,故数据地址由使用者
  填写(公司数据网关/付费库导出/行业协会导出的 JSON)。
- 失败、超时、HTTP 错误、JSON 格式不符、行业不匹配一律返回 None,绝不阻塞主流程,
  页面继续使用内置基准/人工录入值。
"""
import logging

log = logging.getLogger(__name__)

KEYS = ("per_capita_output", "per_capita_pay", "gross_margin", "rev_growth")


def fetch_ref(url, expect_industry=None, timeout=8.0):
    """拉取并校验行业参考 JSON。

    期望格式(自定义、受控):
        {"industry": "制造业", "source": "来源说明", "as_of": "口径/截至时间",
         "values": {"per_capita_output": 88.0, "per_capita_pay": 9.8,
                    "gross_margin": 21.0, "rev_growth": 4.5}}   # values 可只含部分键

    Returns:
        校验通过的 dict {industry, source, as_of, values} 或 None。
    """
    if not url or not str(url).strip().lower().startswith(("http://", "https://")):
        return None
    try:
        import requests
        r = requests.get(str(url).strip(), timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 (AR-Risk-Platform/1.0)"})
        if r.status_code != 200:
            log.warning("external ref HTTP %s for %s", r.status_code, url)
            return None
        obj = r.json()
    except Exception as e:  # 网络/超时/解析异常均静默降级
        log.warning("external ref fetch failed for %s: %s", url, e)
        return None
    vals = obj.get("values") if isinstance(obj, dict) else None
    if not isinstance(vals, dict):
        log.warning("external ref bad shape from %s", url)
        return None
    good = {}
    for k in KEYS:
        v = vals.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            good[k] = float(v)
    if not good:
        log.warning("external ref no usable values from %s", url)
        return None
    industry = str(obj.get("industry") or expect_industry or "").strip()
    if expect_industry and industry and industry != expect_industry:
        log.warning("external ref industry mismatch: %s != %s", industry, expect_industry)
        return None  # 行业不匹配,拒绝采用,防止张冠李戴
    return {
        "industry": industry,
        "source": str(obj.get("source") or "")[:120],
        "as_of": str(obj.get("as_of") or "")[:60],
        "values": good,
    }
