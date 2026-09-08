# 🔍 上市公司年报风险智能识别平台(数智会计大赛项目)

以 **17 项年报舞弊风险规则库** 为标尺,以 **「数值硬规则初筛 + 大模型文本核验」双校验** 为核心的
年报风险识别系统,覆盖 4 步审核闭环:

**① 上传年报 → ② 指标计算与初筛(高风险标红)→ ③ AI 原文核验与最终结论 → ④ 经典案例库**

---

## 一、快速开始(Python 3.10+)

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置大模型(可任选一家;不配置也可用「演示模式」离线体验)
copy .env.example .env      # Windows
# 然后编辑 .env:填 ZHIPU_API_KEY / DASHSCOPE_API_KEY / DEEPSEEK_API_KEY 任一
# 并把 DEMO_MODE 改为 false 即可调用真实大模型

# 3. 启动
streamlit run app.py
```

浏览器打开后,在 **① 上传年报与公司信息** 页面点击
「📥 一键载入演示公司(离线演示)」即可立刻看到完整的四步效果;
也可上传 `docs/sample-inputs/` 中的**真实年报 PDF**(来自两家上市公司的年报与监管公告)
体验「上传 → 抽取 → 计算 → 核验」全流程。

**没有 Python 环境时**:直接双击 `docs/offline-demo.html` 即可在浏览器中查看
平台四步界面与流程的离线演示原型(内嵌示例公司数据,与正式版界面一致)。

> 比赛现场若网络受限:保持 `DEMO_MODE=true`,演示模式全离线可用;
> 网络可用并配置 Key 后,把 `DEMO_MODE` 改为 `false` 即为真实大模型推理。

---

## 二、页面说明(与竞赛四步思路一一对应)

| 页面 | 功能 | 对应项目思路 |
|---|---|---|
| ① 上传年报与公司信息 | 公司名称/代码/行业(证监会门类)/年度;上传年报 PDF(可分卷多选);大模型自动抽取三大报表科目(**万元**),支持 JSON 下载复核与人工修订 | 输入层 |
| ② 指标计算与初筛 | 机器硬规则(~40 指标,实时计算)与**大模型按规则库逐信号全量计算**双轨;结果表内**高风险标红、关注标橙**;机器与 LLM 双值对照 | 第一步:计算风险指标数值,筛出高/关注 |
| ③ AI 原文核验与最终结论 | 对初筛疑点,**按规则库 RAG 关键词自动抓取年报原文段落**,大模型判断:异常产生原因 → 原因类型 → **原因可否接受** → 最终结论(可接受-无问题 / 存疑-关注 / 确定为风险点)→ **需人工复核点**;支持导出 PDF/JSON 评估报告 | 第二步:抓取关键词核查是否特殊事件,可否接受,确定风险点 |
| ④ 经典案例库 | 17 个监管处罚案例(公司 → R 风险编号、违规原因、处罚文号、年报风险信号、决定书链接) | 展示层:哪个公司陷入 R00X、怎么罚 |
| 📚 规则库浏览 | 17 风险 × 113 信号 × 391 指标的公式、阈值、关键词(由 Excel 自动解析) | 专业底座展示 |

---

## 三、项目结构

```
ar-risk-platform/
├─ app.py                     # Streamlit 入口(页面导航)
├─ config.py                  # .env 配置 / 大模型供应商(智谱·通义·DeepSeek·OpenAI兼容)
├─ requirements.txt
├─ .env.example               # 复制为 .env 后填写 Key
├─ core/
│  ├─ fields.py               # 财务科目表 schema(55 项,Y0/Y1/Y2+分季度+附注)
│  ├─ rules.py                # 规则库加载与 prompt 文本化
│  ├─ calculator.py           # 数值硬规则引擎(AST 白名单安全求值 + 阈值判定)
│  ├─ llm.py                  # 大模型客户端(chat/JSON 容错解析/重试)
│  ├─ prompts.py              # 中文提示词:抽取 / 计算 / 核验
│  ├─ extractor.py            # 大模型从年报抽取科目 → 结构化 finance
│  ├─ verify.py               # 双校验编排(Step2 计算 / Step3 核验)
│  ├─ document.py             # PDF→分页文本 / RAG 关键词召回
│  ├─ report.py               # 风险评估 PDF 报告导出(reportlab 中文字体)
│  ├─ ui.py                   # 页面样式/色值/演示公司载入
│  ├─ industry.py             # 行业基准表加载/注入机器引擎(extra.ind_*;②页可人工覆盖)
│  └─ external.py             # 可选联网增强:拉取行业参考 JSON(须人工核对后应用)
├─ views/                     # 六个页面
├─ data/
│  ├─ rules.json              # 规则库(自动生成:17 风险/113 信号/391 指标)
│  ├─ machine_metrics.json    # 机器硬规则指标定义(公式+阈值;行业类引用 extra.ind_*)
│  ├─ cases.json              # 17 个经典案例(与 R001-R017 对应)
│  ├─ industry.json           # 证监会行业门类
│  ├─ industry_baseline.json  # 行业基准参照表(示意参考值,非权威;②页可人工覆盖/联网补充)
│  ├─ raw/                    # 规则库原始 Excel + 解析标签
│  └─ demo/demo_company.json  # 内置演示公司(离线演示全流程)
├─ docs/
│  ├─ sample-inputs/        # 示例输入:真实上市公司年报/公告 PDF(9 份)
│  └─ offline-demo.html     # 离线演示原型(无 Python 时双击浏览器查看四步界面)
└─ scripts/
   ├─ build_rules.ps1       # 规则库 Excel → rules.json(纯 PowerShell,无需 Python)
   ├─ check_json.ps1        # 数据文件合法性自检
   ├─ check_metric_keys.ps1 # 机器指标公式科目引用自检
   └─ final_check.ps1       # 括号配平 + 文件清单自检
```

---

## 四、双校验机制(核心创新点)

1. **数值硬规则(机器)**:`data/machine_metrics.json` 中每个指标 = 公式 + 判定规则,
   直接由财务科目代码计算(净现比、应收增速差、Q4 占比、TATA、存货周转、大存大贷……),
   结果客观可复现、零成本。
2. **大模型全量计算**:把规则库文本 + 科目表发给大模型,对全部 113 个信号逐项
   计算与阈值判定,覆盖需要行业对标、定性判断的指标。
3. 两轨结果**同屏对照**,机器算不了的交给大模型,大模型算的用机器复核——
   大幅压缩幻觉与漏判(对应比赛材料中的“双校验机制落地”)。

第三步核验提示词内置**反幻觉约束**:只许引用年报原文,凡“理由空泛、幅度不匹配、
自相矛盾”即不可接受 → 确定为风险点;每条结论附年报证据原文与人工复核清单。

---

## 五、规则库如何更新

规则库 Excel(17 个 sheet,每个风险一个 sheet)放在 `data/raw/rules.xlsx`;
修改后重新生成结构化 JSON:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_rules.ps1
```

> 说明:解析器已兼容原表三类排版差异(逐条配对表 / 单格合并表 / 档位矩阵表),
> 并对原表少量笔误(如 R002 sheet 内编号残留 R001、R013-S02 拼写)做了归一。

---

## 六、常用配置项(.env)

| 变量 | 说明 |
|---|---|
| `DEMO_MODE` | `true` 演示模式(不调用大模型)/ `false` 调用真实 API |
| `LLM_PROVIDER` | `zhipu`(默认)/ `dashscope` / `deepseek` / `openai` |
| `LLM_MODEL` | 覆盖默认模型,如 `glm-4.5-air`、`qwen-plus`、`deepseek-chat` |
| `ZHIPU_API_KEY` 等 | 对应各家 Key |

**声明**:系统输出为审计线索与辅助意见,标注「需人工复核」的事项必须由专业人员结合
函证、银行流水、合同等外部证据最终确认,不构成审计结论。
