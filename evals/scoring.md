# ExplainFlow 评测评分标准

## 评测目标

对每道标杆题目生成的 Explain Graph 和 Storyboard 进行人工评分，作为质量基线。

## 评分维度（满分 100）

### 1. Explain Graph 质量（40分）

| 维度 | 分值 | 标准 |
|---|---|---|
| 概念完整性 | 15 | 是否覆盖了 `expected_concepts` 中的核心概念 |
| 逻辑关系准确性 | 10 | edges 中的关系是否符合实际认知 |
| 教学顺序合理性 | 10 | teach_order 是否符合从浅到深的教学逻辑 |
| 公式准确性 | 5 | 公式节点的 LaTeX 是否与 golden_formula 一致 |

### 2. Storyboard 质量（40分）

| 维度 | 分值 | 标准 |
|---|---|---|
| 旁白通顺度 | 15 | 旁白是否口语化、流畅，适合 B 站风格 |
| 教学逻辑 | 10 | 场景之间是否有合理的过渡和递进 |
| 时长控制 | 8 | 总时长是否在目标时长 ±20s 以内 |
| 动画指令合理性 | 7 | 动画类型选择是否合适 |

### 3. 整体体验（20分）

| 维度 | 分值 | 标准 |
|---|---|---|
| 初学者可理解性 | 10 | 一个只懂 Python 的人能否看懂 |
| 信息密度 | 5 | 不过于简单（<60分）也不过于复杂（>80分） |
| 发布可用性 | 5 | 不经修改直接发 B 站的可接受程度 |

## 评测流程

1. 对每道题运行：`POST /explain/graph` → `POST /planner/storyboard`
2. 人工阅读生成结果，按上述维度打分
3. 记录到 `evals/results/{eval_id}_score.json`
4. 每次模型/Prompt 改动后重新跑评测，对比分数变化

## 评分记录格式

```json
{
  "eval_id": "eval_001",
  "model": "deepseek-chat",
  "timestamp": "2026-05-16T12:00:00Z",
  "scores": {
    "graph_completeness": 14,
    "graph_relations": 8,
    "graph_order": 9,
    "graph_formula": 5,
    "storyboard_narration": 13,
    "storyboard_logic": 9,
    "storyboard_duration": 7,
    "storyboard_animations": 6,
    "overall_beginner": 9,
    "overall_density": 4,
    "overall_publishable": 4
  },
  "total": 88,
  "notes": "公式场景旁白略显生硬，建议加更多比喻"
}
```
