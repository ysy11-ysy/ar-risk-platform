# -*- coding: utf-8 -*-
"""数值硬规则引擎:对可量化的核心指标做代码级计算与初筛。

- 指标定义位于 data/machine_metrics.json(变量空间 y0/y1/y2 + q = 季度字典)
- 表达式求值采用 AST 白名单,不允许任意代码执行
- 与"大模型逐信号计算"互为双校验:机器算不出的(定性/需行业数据)标 NA,由 LLM 补
"""
import ast
import json
import operator
from pathlib import Path

import config

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}
_CMP = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
    ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
}
_ALLOWED_FUNCS = {"avg", "max", "min", "abs", "sum"}


def _num(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _calc(node, env):
    if isinstance(node, ast.Expression):
        return _calc(node.body, env)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.Attribute):
        obj = _calc(node.value, env)
        if isinstance(obj, dict):
            return obj.get(node.attr)
        return None
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        a, b = _calc(node.left, env), _calc(node.right, env)
        if a is None or b is None:
            return None
        return _OPS[type(node.op)](a, b)
    if isinstance(node, ast.UnaryOp):
        v = _calc(node.operand, env)
        if v is None:
            return None
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        a, b = _calc(node.left, env), _calc(node.comparators[0], env)
        if a is None or b is None:
            return None
        return _CMP[type(node.ops[0])](a, b)
    if isinstance(node, ast.BoolOp):
        vals = [_calc(x, env) for x in node.values]
        if isinstance(node.op, ast.And):
            return all(vals)
        return any(vals)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
        args = [_calc(a, env) for a in node.args]
        nums = [_num(a) for a in args]
        fn = node.func.id
        if fn == "avg":
            nums = [n for n in nums if n is not None]
            return sum(nums) / len(nums) if nums else None
        if fn in ("max", "min", "sum", "abs"):
            import builtins
            g = getattr(builtins, fn)
            if fn == "abs":
                return g(nums[0]) if nums and nums[0] is not None else None
            nums = [n for n in nums if n is not None]
            return g(nums) if nums else None
    raise ValueError(f"表达式包含不支持的语法: {ast.dump(node)}")


def eval_expr(expr: str, env: dict):
    """安全求值。环境值 dict 支持 None;除零/缺值一律返回 None。"""
    if not expr or not expr.strip():
        return None
    try:
        tree = ast.parse(expr.strip(), mode="eval")
        return _calc(tree, env)
    except (ValueError, ZeroDivisionError, SyntaxError, TypeError):
        return None


def _load_metrics() -> list:
    path = config.METRICS_FILE
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("metrics", [])


def build_env(finance: dict) -> dict:
    """finance: 抽取结果 {Y0:{...},Y1:{...},Y2:{...},quarter:{...}} -> 求值环境。"""
    env = {"y0": finance.get("Y0") or {}, "y1": finance.get("Y1") or {},
           "y2": finance.get("Y2") or {}, "q": finance.get("quarter") or {},
           "extra": finance.get("extra") or {}}
    return env


def judge(metric: dict, value, env: dict) -> str:
    """返回 高风险/关注/正常/未触发。value=None -> 未触发。"""
    if value is None:
        return "未触发"
    env2 = dict(env)
    env2["v"] = value
    for rule in metric.get("rules", []):
        cond = rule.get("cond")
        if not cond:
            continue
        ok = eval_expr(cond, env2)
        if ok:
            return rule["level"]
    return "正常"


def run_machine(finance: dict, risk_ids=None) -> list:
    """计算全部(或指定风险)机器指标。返回行:
    {risk_id, signal_id, signal_name, indicator, value, unit, level, basis, expr, machine: True}"""
    env = build_env(finance)
    out = []
    for m in _load_metrics():
        if risk_ids and m.get("risk_id") not in risk_ids:
            continue
        val = eval_expr(m.get("formula", ""), env)
        if val is not None and isinstance(val, float):
            val = round(val, 4)
        lv = judge(m, val, env)
        out.append({
            "risk_id": m.get("risk_id"), "signal_id": m.get("signal_id"),
            "signal_name": m.get("signal_name", ""),
            "indicator": m.get("name"), "value": val, "unit": m.get("unit", ""),
            "level": lv, "basis": m.get("basis", ""), "expr": m.get("formula", ""),
            "machine": True, "metric_id": m.get("id"),
        })
    return out
