# VEH Scientist Agent Instructions

本文档整理当前 `VEH Scientist` cockpit 中 11 个 agent 的实际指令来源与运行方式。这里的“指令”不是每个 agent 一份独立 prompt 文件，而是由以下三部分组合而成：

1. 共享 `system prompt`
2. 动态拼接的 `user/context prompt`
3. slot 级别的 `prompt_brief`

如果远程模型未配置、未启用，或请求失败，则会退回到本地 `fallback` 文本生成逻辑。

---

## 1. 共享 Prompt 框架

### 1.1 Shared System Prompt

所有远程 agent 共用同一条 system prompt：

```text
You are generating short dashboard utterances for a scientific design cockpit. Return valid JSON only. Each value must be 1-3 concise sentences, technically grounded, and specific to the provided context.
```

这条 system prompt 的硬约束有三条：

- 只能返回合法 JSON
- 每个 agent 的输出限制为 1 到 3 句
- 内容必须技术上具体，并贴合当前 round 上下文

### 1.2 Shared Dynamic Context Header

所有远程 agent 的 user prompt 都会先注入同一份 round 上下文，结构如下：

```text
Task: {task description or task_id}
Round: {round_id}
Target output: {target_output}
Target band: {f_low}-{f_high} Hz
Candidate: {candidate summary or "No candidate selected."}
Screening: {screen verdict + TR + eta + failed gates}
Verification:
- {tier}: {verification summary}
Critic: {decision + reason + next action}
Recent user guidance:
- {guidance 1}
- {guidance 2}
...
```

其中关键动态字段包括：

- `Task`
- `Round`
- `Target output`
- `Target band`
- `Candidate`
- `Screening`
- `Verification`
- `Critic`
- `Recent user guidance`

### 1.3 Shared Slot Packing Format

在共享上下文之后，运行时会把一个或多个 slot 打包进同一次请求里。对应的 user prompt 尾部形态如下：

```text
Slots to fill:
- {slot_id}: {slot prompt_brief} Agent label: {agent_name}.
- {slot_id}: {slot prompt_brief} Agent label: {agent_name}.
...

Return a JSON object whose keys are the slot ids and whose values are the agent messages.
```

因此，远程模型看到的并不是“你现在只扮演 mechanism agent”，而是：

- 先知道共享 scientific dashboard 约束
- 再读到本轮完整上下文
- 再读到某个 slot 的职责摘要
- 最后按 `slot_id -> utterance` 的 JSON 输出

---

## 2. Role Agents

Role Agents 一共有 5 个：

- `mechanism`
- `structure`
- `critic`
- `paper`
- `verifier`

---

### 2.1 `mechanism` / Mechanism Agent

#### Slot Metadata

- Slot ID: `mechanism`
- Mode: `role`
- Agent Name: `Mechanism`
- Label: `Mechanism Agent`
- Purpose: `Explain the screening physics and TR / bandgap logic.`

#### Slot Prompt Brief

```text
Focus on bandgaps, localization, suppression, and why a candidate passes or fails the mechanism gates.
```

#### Effective Remote Prompt

远程模型实际接收到的 slot 级指令可读版如下：

```text
Use the shared scientific cockpit system prompt.

Read the current round context:
- task
- round
- target output
- target band
- candidate summary
- screening verdict
- verification summary
- critic summary
- recent user guidance

Then fill slot `mechanism`:
Focus on bandgaps, localization, suppression, and why a candidate passes or fails the mechanism gates.
Agent label: Mechanism.

Return JSON:
{
  "mechanism": "<1-3 sentence message>"
}
```

#### Fallback Behavior

如果不走远程模型，`Mechanism Agent` 使用本地逻辑：

- 若没有 screening result，则输出：
  - `Mechanism screening has not produced any result yet.`
- 若有 screening result，则输出：
  - `Mechanism verdict is {verdict}.`
  - `Gate summary: G1=pass/revise, G2=..., ...`
  - `TR={tr_frequency} Hz, eta={eta}.`

它的 fallback 本质上是一个 screening 摘要器，不会额外做创造性扩展。

---

### 2.2 `structure` / Structure Agent

#### Slot Metadata

- Slot ID: `structure`
- Mode: `role`
- Agent Name: `Structure`
- Label: `Structure Agent`
- Purpose: `Summarize candidate geometry and structural tuning decisions.`

#### Slot Prompt Brief

```text
Focus on alpha, beta, delta, N, and how the proposed structure should be revised.
```

#### Effective Remote Prompt

```text
Use the shared scientific cockpit system prompt.

Read the full round context.

Then fill slot `structure`:
Focus on alpha, beta, delta, N, and how the proposed structure should be revised.
Agent label: Structure.

Return JSON:
{
  "structure": "<1-3 sentence message>"
}
```

#### Fallback Behavior

- 若当前 round 没有 selected candidate，则输出：
  - `No candidate was selected in this round.`
- 若有 candidate，则输出：
  - candidate id
  - `alpha / beta / delta / N / kappa2`
  - assumptions 列表

典型 fallback 形态：

```text
Selected {candidate_id} with alpha={alpha}, beta={beta}, delta={delta}, N={N}, and kappa2={kappa2}. Assumptions: {assumptions}
```

它的 fallback 是参数与假设的结构化汇总。

---

### 2.3 `critic` / Critic Agent

#### Slot Metadata

- Slot ID: `critic`
- Mode: `role`
- Agent Name: `Critic`
- Label: `Critic Agent`
- Purpose: `Judge risk, baseline gaps, and next action.`

#### Slot Prompt Brief

```text
Focus on the main technical risk, decision rationale, and the most valuable next action.
```

#### Effective Remote Prompt

```text
Use the shared scientific cockpit system prompt.

Read the full round context.

Then fill slot `critic`:
Focus on the main technical risk, decision rationale, and the most valuable next action.
Agent label: Critic.

Return JSON:
{
  "critic": "<1-3 sentence message>"
}
```

#### Fallback Behavior

- 若当前没有 critic decision，则输出：
  - `No critic decision is available.`
- 若有 critic decision，则直接输出：

```text
Decision is {decision}. {reason} Next: {next_action}
```

它的 fallback 非常直接，就是把 critic 的最终裁决压缩成一句决策摘要。

---

### 2.4 `paper` / Paper Agent

#### Slot Metadata

- Slot ID: `paper`
- Mode: `role`
- Agent Name: `Paper`
- Label: `Paper Agent`
- Purpose: `Produce a concise literature-style framing note.`

#### Slot Prompt Brief

```text
Frame the round like a short literature note: mechanism intuition, known tradeoff, and what evidence is still missing.
```

#### Effective Remote Prompt

```text
Use the shared scientific cockpit system prompt.

Read the full round context.

Then fill slot `paper`:
Frame the round like a short literature note: mechanism intuition, known tradeoff, and what evidence is still missing.
Agent label: Paper.

Return JSON:
{
  "paper": "<1-3 sentence message>"
}
```

#### Fallback Behavior

本地 fallback 优先取 candidate 的第一条 assumption；如果没有，则使用默认机制提示：

```text
TR-enabled localization can improve harvesting only if suppression margin survives.
```

然后拼成一条 literature-style note：

```text
Literature-style note: {mechanism_hint} The main uncertainty remains whether the localized mode keeps engineering-level output gains.
```

所以 `Paper Agent` 的 fallback 不是引用文献，而是生成一个“像论文导言摘要一样”的 framing 句子。

---

### 2.5 `verifier` / Verifier Planner

#### Slot Metadata

- Slot ID: `verifier`
- Mode: `role`
- Agent Name: `Verifier Planner`
- Label: `Verifier Planner`
- Purpose: `Interpret verification outputs and escalation path.`

#### Slot Prompt Brief

```text
Focus on L1/L2/L3 evidence, what has been verified, and whether higher fidelity is still needed.
```

#### Effective Remote Prompt

```text
Use the shared scientific cockpit system prompt.

Read the full round context.

Then fill slot `verifier`:
Focus on L1/L2/L3 evidence, what has been verified, and whether higher fidelity is still needed.
Agent label: Verifier Planner.

Return JSON:
{
  "verifier": "<1-3 sentence message>"
}
```

#### Fallback Behavior

- 若没有任何 verification result，则输出：
  - `No verification tier has run yet.`
- 若已有 verification，则把所有 tier 的验证摘要拼起来：

```text
{tier} {status}. {details or metric summary}
```

例如会组合成类似：

```text
L1 pass. ...
L2 warn. ...
L3 fail. ...
```

它的 fallback 更像一个 verification timeline summarizer。

---

## 3. Multi-LLM Agents

Multi-LLM Agents 一共有 6 个：

- `gpt_scientist`
- `claude_scientist`
- `qwen_scientist`
- `gemini_scientist`
- `grok_scientist`
- `deepseek_scientist`

这些 slot 的远程 prompt 结构与 Role Agents 相同，差别只在 `prompt_brief` 和 fallback 风格。

---

### 3.1 `gpt_scientist` / GPT-Scientist

#### Slot Metadata

- Slot ID: `gpt_scientist`
- Mode: `llm`
- Agent Name: `GPT-Scientist`
- Label: `GPT-Scientist`
- Purpose: `Provide a concise round-level synthesis.`

#### Slot Prompt Brief

```text
Give a balanced synthesis of the round and a practical next move.
```

#### Effective Remote Prompt

```text
Use the shared scientific cockpit system prompt.

Read the full round context.

Then fill slot `gpt_scientist`:
Give a balanced synthesis of the round and a practical next move.
Agent label: GPT-Scientist.

Return JSON:
{
  "gpt_scientist": "<1-3 sentence message>"
}
```

#### Fallback Behavior

默认 fallback 是最通用的一条 round synthesis：

```text
Round synthesis: {candidate_label} currently leads this round, with critic outcome {decision}. The next move should stay aligned with the requested output objective.
```

---

### 3.2 `claude_scientist` / Claude-Scientist

#### Slot Metadata

- Slot ID: `claude_scientist`
- Mode: `llm`
- Agent Name: `Claude-Scientist`
- Label: `Claude-Scientist`
- Purpose: `Stress-test assumptions and edge cases.`

#### Slot Prompt Brief

```text
Focus on hidden assumptions, edge cases, and missing evidence.
```

#### Effective Remote Prompt

```text
Use the shared scientific cockpit system prompt.

Read the full round context.

Then fill slot `claude_scientist`:
Focus on hidden assumptions, edge cases, and missing evidence.
Agent label: Claude-Scientist.

Return JSON:
{
  "claude_scientist": "<1-3 sentence message>"
}
```

#### Fallback Behavior

```text
The current round centers on {candidate_label}. The main unresolved issue is whether the evidence is strong enough beyond screening to justify {decision}.
```

它的 fallback 重心是“证据是否足够”，而不是“参数怎么改”。

---

### 3.3 `qwen_scientist` / Qwen-Scientist

#### Slot Metadata

- Slot ID: `qwen_scientist`
- Mode: `llm`
- Agent Name: `Qwen-Scientist`
- Label: `Qwen-Scientist`
- Purpose: `Summarize with implementation-oriented tradeoffs.`

#### Slot Prompt Brief

```text
Focus on engineering feasibility, implementation cost, and concrete parameter moves.
```

#### Effective Remote Prompt

```text
Use the shared scientific cockpit system prompt.

Read the full round context.

Then fill slot `qwen_scientist`:
Focus on engineering feasibility, implementation cost, and concrete parameter moves.
Agent label: Qwen-Scientist.

Return JSON:
{
  "qwen_scientist": "<1-3 sentence message>"
}
```

#### Fallback Behavior

```text
Implementation view: {candidate_label} is useful only if the parameter move is fabricable and keeps baseline advantages. Prioritize the smallest structural change that addresses the failing gate.
```

它的 fallback 明显偏“工程落地”和“小步修正”。

---

### 3.4 `gemini_scientist` / Gemini-Scientist

#### Slot Metadata

- Slot ID: `gemini_scientist`
- Mode: `llm`
- Agent Name: `Gemini-Scientist`
- Label: `Gemini-Scientist`
- Purpose: `Summarize evidence and experimental next steps.`

#### Slot Prompt Brief

```text
Focus on evidence quality, missing experiments, and what to validate next.
```

#### Effective Remote Prompt

```text
Use the shared scientific cockpit system prompt.

Read the full round context.

Then fill slot `gemini_scientist`:
Focus on evidence quality, missing experiments, and what to validate next.
Agent label: Gemini-Scientist.

Return JSON:
{
  "gemini_scientist": "<1-3 sentence message>"
}
```

#### Fallback Behavior

```text
Evidence summary for {candidate_label}: screening plus verification suggest {decision}. The next step should close the highest-fidelity evidence gap.
```

它的 fallback 是最标准的 evidence-gap 视角。

---

### 3.5 `grok_scientist` / Grok-Scientist

#### Slot Metadata

- Slot ID: `grok_scientist`
- Mode: `llm`
- Agent Name: `Grok-Scientist`
- Label: `Grok-Scientist`
- Purpose: `Highlight contrarian possibilities and failure modes.`

#### Slot Prompt Brief

```text
Focus on alternative interpretations and ways the current conclusion could be wrong.
```

#### Effective Remote Prompt

```text
Use the shared scientific cockpit system prompt.

Read the full round context.

Then fill slot `grok_scientist`:
Focus on alternative interpretations and ways the current conclusion could be wrong.
Agent label: Grok-Scientist.

Return JSON:
{
  "grok_scientist": "<1-3 sentence message>"
}
```

#### Fallback Behavior

```text
A contrarian read: {candidate_label} may simply be sitting on a fragile TR configuration. I would challenge the suppression margin and gap-depth assumptions first.
```

它的 fallback 会默认从反例、脆弱性和“现在可能判断错了”切入。

---

### 3.6 `deepseek_scientist` / Deepseek-Scientist

#### Slot Metadata

- Slot ID: `deepseek_scientist`
- Mode: `llm`
- Agent Name: `Deepseek-Scientist`
- Label: `Deepseek-Scientist`
- Purpose: `Offer parameter-search style guidance.`

#### Slot Prompt Brief

```text
Focus on parameter search direction, ranking, and the highest-yield next candidate.
```

#### Effective Remote Prompt

```text
Use the shared scientific cockpit system prompt.

Read the full round context.

Then fill slot `deepseek_scientist`:
Focus on parameter search direction, ranking, and the highest-yield next candidate.
Agent label: Deepseek-Scientist.

Return JSON:
{
  "deepseek_scientist": "<1-3 sentence message>"
}
```

#### Fallback Behavior

```text
Search direction: rank delta, N, and kappa2 as the next tuning knobs for {candidate_label}. Push the parameter that most directly improves the failing metric.
```

它的 fallback 是最明确的“参数搜索器”。

---

## 4. 11 个 Agent 的最短摘要表

| Slot ID | Agent Name | 核心关注点 | Fallback 风格 |
| --- | --- | --- | --- |
| `mechanism` | Mechanism | bandgap / localization / suppression / gate pass-fail | screening 摘要 |
| `structure` | Structure | alpha / beta / delta / N / kappa2 / 几何改法 | 参数汇总 |
| `critic` | Critic | 技术风险 / 决策理由 / next action | 裁决压缩 |
| `paper` | Paper | 文献式 framing / intuition / tradeoff / 缺证据 | literature-style note |
| `verifier` | Verifier Planner | L1/L2/L3 证据与升阶策略 | verification 摘要 |
| `gpt_scientist` | GPT-Scientist | 平衡总结 + 务实下一步 | 通用 synthesis |
| `claude_scientist` | Claude-Scientist | 隐藏假设 / 边界条件 / 证据不足 | 证据强度质疑 |
| `qwen_scientist` | Qwen-Scientist | 可制造性 / 实现成本 / 参数动作 | 工程落地 |
| `gemini_scientist` | Gemini-Scientist | 证据质量 / 缺实验 / 下一步验证 | evidence gap |
| `grok_scientist` | Grok-Scientist | 替代解释 / 反例 / 失败模式 | contrarian critique |
| `deepseek_scientist` | Deepseek-Scientist | 参数搜索方向 / 排序 / highest-yield candidate | 参数搜索 |

---

## 5. 一个重要限制

当前系统里，agent 的“完整指令”并不是用户可在 UI 中单独编辑的独立 prompt 文件。

目前真正可配置的只有：

- `provider`
- `base_url`
- `api_key`
- `model_name`
- `enabled`

而真正决定 agent 行为的文案，仍然写死在两处：

- `src/veh_scientist/agents/definitions.py`
- `src/veh_scientist/agents/runtime.py`

也就是说：

- 你现在可以给不同 slot 接不同模型
- 但不能在 UI 里直接改单个 slot 的 prompt brief
- 如果要改 agent 指令，仍然需要改代码

---

## 6. 如果后续要继续增强

下一步如果要把这套系统做成“真正可定制 agent prompt”，建议再拆成三层：

1. `shared_system_prompt`
2. `slot_prompt_template`
3. `fallback_template`

并把它们都持久化到配置文件里，而不是继续硬编码在 Python 源码中。
