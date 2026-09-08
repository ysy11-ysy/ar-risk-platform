# -*- coding: utf-8 -*-
"""R001 基准校验:用固定『高鸿股份(000851)2021 年报』财务输入跑机器硬规则,
与期望表(data/baseline/expected_r001.json)比对,定位每次改公式/改输入后哪些指标变了。

用法(需 python 环境,在仓库根目录运行):
    python scripts/check_baseline.py            # 运行机器指标并与期望表 diff
    python scripts/check_baseline.py --update   # 用当前机器输出刷新期望表(改口径/改输入后重标定)

说明:
- 期望表首次由 --update 生成;生成后请人工逐项核对数值(对照豆包复核报告/年报原文),
  确认无误后才作为回归基准。之后每次改动公式,跑一次本脚本即可看到『哪几个指标被改动了』。
- 这是两人协作调试的『唯一锚点』:基准输入固定 -> 公式确定 -> 输出确定,
  谁改了什么、是否改坏,一跑便知。
"""
import json
import sys
from pathlib import Path

# Windows 控制台默认 GBK,无法打印 ⚠/✅ 等字符:强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from core import calculator, rules  # noqa: E402

BASELINE = ROOT / "data" / "baseline" / "gaohong_000851_2021.json"
EXPECTED = ROOT / "data" / "baseline" / "expected_r001.json"


def machine_rows():
    """R001 机器行:可机算 + 需外部数据 分开返回。"""
    fin = json.loads(BASELINE.read_text(encoding="utf-8"))
    rows = calculator.run_machine(fin, ["R001"])
    calcable = [r for r in rows if not r.get("needs_external")]
    ext = [r for r in rows if r.get("needs_external")]
    return fin, calcable, ext


def snapshot(calcable):
    out = []
    for r in sorted(calcable, key=lambda x: x["metric_id"]):
        out.append({"metric_id": r["metric_id"], "indicator": r["indicator"],
                    "unit": r["unit"], "value": r["value"], "level": r["level"],
                    "basis": r["basis"]})
    return out


def report_gap(fin):
    """列出规则库 R001 9 大信号中机器尚未覆盖的信号(交大模型兜底)。"""
    r001 = next(r for r in rules.risks() if r["id"] == "R001")
    sig_ids = [s["id"] for s in r001["signals"]]
    covered = {row["signal_id"] for row in calculator.run_machine(fin, ["R001"])}
    gap = [sid for sid in sig_ids if sid not in covered]
    if gap:
        print("规则库 R001 中机器尚未覆盖的信号(由大模型计算/需外部文本):"
              + ", ".join(gap))


def main():
    update = "--update" in sys.argv
    fin, calcable, ext = machine_rows()
    snap = snapshot(calcable)

    if update or not EXPECTED.exists():
        EXPECTED.parent.mkdir(parents=True, exist_ok=True)
        EXPECTED.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已生成期望表: {EXPECTED}")
        print(f"机器可算 R001 指标 {len(snap)} 个;需外部数据 {len(ext)} 个"
              + (f"({', '.join(x['indicator'] for x in ext)})" if ext else ""))
        print("⚠ 请人工逐项核对期望表数值(对照豆包复核报告/年报原文),确认无误后再把它当回归基准。")
        report_gap(fin)
        return

    exp = json.loads(EXPECTED.read_text(encoding="utf-8"))
    exp_by = {e["metric_id"]: e for e in exp}
    n_diff = 0
    for r in calcable:
        rid = r["metric_id"]
        e = exp_by.get(rid)
        if e is None:
            print(f"[新增] {rid} {r['indicator']} = {r['value']} {r['unit']} ({r['level']})")
            n_diff += 1
            continue
        if e.get("value") != r["value"] or e.get("level") != r["level"]:
            print(f"[变动] {rid} {r['indicator']}: 期望 {e.get('value')} {e.get('unit')} ({e.get('level')})"
                  f" -> 当前 {r['value']} {r['unit']} ({r['level']})")
            n_diff += 1
    for e in exp:
        if e["metric_id"] not in {r["metric_id"] for r in calcable}:
            print(f"[移除] {e['metric_id']} {e['indicator']}(期望表有、当前已不输出)")
            n_diff += 1
    print(f"\n机器可算 R001 指标 {len(calcable)} 个;与期望不一致 {n_diff} 处。"
          + ("✅ 全部一致,公式未被意外改动。" if n_diff == 0 else "⚠ 有不一致,请定位改动原因。"))
    report_gap(fin)


if __name__ == "__main__":
    main()
