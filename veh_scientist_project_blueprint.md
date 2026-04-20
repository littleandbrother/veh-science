# VEH Scientist Project Blueprint / 项目总控蓝图

## 1. Project Positioning / 项目定位

### 1.1 Project Name / 项目名称
**Mechanism-Grounded Autonomous VEH Scientist**  
**以机制为核心的全自动 VEH Scientist**

### 1.2 One-Sentence Definition / 一句话定义
A persistent engineering research system that starts from a target physical mechanism, proposes candidate vibration energy harvester designs, co-designs structure, transducer, and electrical interface, verifies them through multi-fidelity physics models, and iteratively revises strategies until a feasible design is found.  
一个持续运行的工程研究系统：从目标物理机制出发，提出候选振动能量采集器设计，联合设计结构、换能器与电学接口，并通过多保真物理模型进行验证，不断修正策略，直到找到可行设计。

### 1.3 Core Problem / 核心问题
Most existing automation pipelines either optimize parameters without understanding the physical mechanism, generate ideas without reliable verification, or treat the electrical interface as a post-processing detail.  
现有自动化设计流程通常存在三类问题：只做参数优化而不理解物理机制，只会生成想法却缺乏可靠验证，或者把 electrical interface 当作后处理细节。

This project instead treats VEH design as a **mechanism-realization problem**: first determine whether a mechanism route is viable, then realize it as a feasible engineering design.  
本项目则把 VEH 设计看作一个**机制实现问题**：先判断一条机制路线是否可行，再把它落实为可行的工程设计。

### 1.4 Current Mechanism Focus / 当前机制主线
The initial mechanism focus is **truncation resonance (TR)**: exploit bandgap-localized boundary modes, place transduction where energy is localized, preserve suppression while enabling harvesting, and co-design the electrical interface so that electromechanical coupling remains beneficial.  
当前第一阶段聚焦 **truncation resonance (TR)**：利用带隙内的边界局域模态，在能量局域位置布置换能单元，在保持抑振的同时实现采能，并联合设计 electrical interface，使机电耦合保持有利而非破坏性。

---

## 2. Design Philosophy / 设计理念

### 2.1 Primary Philosophy / 核心哲学
This project is not a parameter optimizer. It is a **mechanism-grounded autonomous engineering scientist**.  
这个项目不是一个简单的参数优化器，而是一个**以机制为核心的自动工程 scientist**。

### 2.2 Four Governing Principles / 四条基本原则

#### Principle 0: Synergy not trade-off / 原则 0：协同而非折衷
Truncation resonance is not a compromise between vibration suppression and energy harvesting. It is a boundary-localized eigenstate inside a phononic bandgap where high-Q resonance and negative transmission co-exist by physical necessity. The output voltage peaks precisely at the TR frequency because the boundary-localized mode maximizes the relative displacement at the piezoelectric port, while the span-wise transmission remains below 0 dB because TR exists inside the stop band. Peak energy harvesting and robust vibration damping are synergistic outcomes of the same underlying physical phenomenon, not competing objectives.  
Truncation resonance 不是在抑振与采能之间做妥协。它是声子 bandgap 内的边界局域化本征态，高 Q 共振与负传输率在物理上必然共存。输出电压恰好在 TR 频率处达到峰值，因为边界局域模态最大化了压电端口处的相对位移；同时 span-wise transmission 保持在 0 dB 以下，因为 TR 存在于 stop band 内部。峰值采能与稳健抑振是同一物理现象的协同结果，而非相互竞争的目标。

#### Principle 1: Mechanism before optimization / 原则 1：先机制，后优化
The system must first decide whether a mechanism-based route is physically meaningful before performing local optimization.  
系统必须先判断某条机制路线是否在物理上成立，再进行局部优化。

#### Principle 2: Verification is part of reasoning / 原则 2：验证是推理的一部分
Verification is not only a final check. Different fidelity models are part of the reasoning loop itself.  
验证不是最后一步的裁判，而是整个推理循环的一部分；不同保真度模型承担不同层级的推理职责。

#### Principle 3: Failure is research signal / 原则 3：失败本身也是研究信号
Failed candidates should not be discarded blindly. They should be converted into reusable memory and future guidance.  
失败候选不能被简单丢弃，而应转化为可复用的记忆与后续指导规则。

### 2.3 Co-Design Principle / 协同设计原则
The system always reasons jointly over **structure, transducer, and electrical interface**.  
系统始终联合考虑 **structure、transducer 与 electrical interface**。

It must avoid the invalid pattern of “design structure first, attach piezo later, then tune load at the end.”  
它必须避免“先设计结构、再贴压电片、最后才调负载”的无效流程。

Instead, the project adopts:  
**structure–transducer–electrical interface co-design**  
因此，本项目采用：  
**结构–换能器–电学接口协同设计**

---

## 2.4 Physical Foundation: TR Mechanism Theory / 物理基础：TR 机制理论

This section establishes the quantitative physical foundation that the entire autonomous system operates upon. All design rules, screening criteria, and verification targets derive from the theoretical framework developed in the core references.  
本节建立整个自动系统运行所依赖的定量物理基础。所有设计规则、筛选标准和验证目标均来源于核心参考文献中发展的理论框架。

### 2.4.1 Diatomic Chain Foundation Model / 双原子链基础模型

The foundational physical model is a periodic diatomic spring-mass chain. A unit cell contains masses (m_a, m_b) and alternating springs (k_a, k_b) with lattice pitch a. The non-dimensional parameters are:  
基础物理模型是一条周期性双原子弹簧-质量链。一个晶胞包含质量 (m_a, m_b) 和交替弹簧 (k_a, k_b)，晶格常数为 a。无量纲参数为：

- alpha = m_b / m_a (mass ratio / 质量比)
- beta = k_b / k_a (stiffness ratio / 刚度比)
- omega_b = sqrt(k_b / m_b) (reference frequency / 参考频率)
- Omega = omega / omega_b (non-dimensional frequency / 无量纲频率)
- delta = m_{a+} / m_a (boundary asymmetry parameter / 边界不对称参数)

The dispersion relation for the infinite chain yields acoustic and optical branches:  
无限链的色散关系给出声学支和光学支：

  Omega^4 - (1+alpha)(1 + 1/beta) Omega^2 + (4 alpha/beta) sin^2(qa/2) = 0

The bandgap is the frequency interval between these branches where no real wavenumber q exists.  
Bandgap 是两个分支之间不存在实波数 q 的频率区间。

### 2.4.2 TR Existence Conditions / TR 存在条件

For a finite chain of N unit cells with a non-periodic boundary mass m_{a+} = delta * m_a, the resonant frequencies satisfy:  
对于 N 个晶胞的有限链，边界质量为 m_{a+} = delta * m_a 时，共振频率满足：

  det A(Omega) = 0

where A(Omega) is the dynamic stiffness matrix of the finite system. A truncation resonance is formally defined as:  
其中 A(Omega) 是有限系统的动刚度矩阵。Truncation resonance 的正式定义为：

  Omega_r is in the bandgap AND det A(Omega_r) = 0

This is the necessary and sufficient condition: TR exists if and only if a natural frequency of the finite chain falls inside a bandgap of the corresponding infinite chain.  
这是充要条件：当且仅当有限链的某个固有频率落入对应无限链的 bandgap 内时，TR 存在。

### 2.4.3 Four-Level Design Parameter Hierarchy / 四层设计参数层次

The design space is organized into a strict hierarchy of roles:  
设计空间按照严格的角色层次组织：

**Level 1 — Switch: delta (boundary asymmetry)**  
- delta = 1: boundary is periodic, TR vanishes (TR is OFF)  
- delta != 1: boundary symmetry is broken, TR can emerge (TR is ON)  
- The V-shaped voltage response around delta = 1 confirms this on/off behavior  
- delta = 1 时边界为周期性，TR 消失；delta != 1 时对称性破缺，TR 可出现  
- 围绕 delta = 1 的 V 型电压响应确认了这种开/关行为

**Level 2 — Tuners: (alpha, beta) (internal mass/stiffness ratios)**  
- alpha and beta control the bandgap location and width  
- Once delta enables TR, (alpha, beta) place Omega_TR at the desired operational frequency  
- Design strategy: use boundary asymmetry to enable TR, then tune the internal cell structure to place the resonance at the target frequency  
- alpha 和 beta 控制 bandgap 位置和宽度  
- 一旦 delta 启用了 TR，(alpha, beta) 将 Omega_TR 放在目标工作频率处

**Level 3 — Matchers: (kappa^2, epsilon) (electromechanical parameters)**  
- kappa^2 = theta^2 / (k_b * C_p): coupling factor  
- epsilon = 1 / (R * C_p * omega_b): electrical damping ratio  
- These parameters control the efficiency of energy transfer from mechanical to electrical domain  
- Impedance matching criterion: epsilon* ~ Omega_TR, i.e., R* ~ 1 / (C_p * omega_TR)  
- kappa^2 = theta^2 / (k_b * C_p)：耦合因子  
- epsilon = 1 / (R * C_p * omega_b)：电学阻尼比  
- 阻抗匹配准则：epsilon* ~ Omega_TR，即 R* ~ 1 / (C_p * omega_TR)

**Level 4 — Q-Amplifier: N (number of unit cells)**  
- Increasing N sharpens the resonance peak (higher Q-factor) because longer chains more effectively isolate the boundary state from far-end reflections  
- TR frequency is largely insensitive to N (boundary-driven phenomenon; frequency converges for N >= 5)  
- Practical minimum: N >= 5 for frequency convergence; N >= 10 for strong Q  
- 增大 N 使共振峰更尖锐（更高 Q 因子），因为更长的链更有效地将边界态与远端反射隔离  
- TR 频率对 N 基本不敏感（边界驱动现象；N >= 5 时频率即收敛）

### 2.4.4 Electromechanical Coupling Model / 机电耦合模型

A piezoelectric patch is placed across the (1-2) cell interface (between mass m_{a,1} and mass m_{b,2}), where TR energy is most concentrated. The model defines:  
压电片跨接第 (1-2) 晶胞界面（质量 m_{a,1} 和 m_{b,2} 之间），即 TR 能量最集中处。模型定义：

- Mechanical port variable: g(t) = u_{a,1}(t) - u_{b,2}(t) (relative displacement / 相对位移)
- Electrical port variable: V(t) (voltage across terminals / 端子电压)
- Force-voltage coupling coefficient: theta (N/V)

**Governing port equations:**  
- Force on m_{a,1}: F_{a,1}^{pz} = +theta * V  
- Force on m_{b,2}: F_{b,2}^{pz} = -theta * V  
- Circuit (KCL): C_p * dV/dt + V/R + theta * dg/dt = 0

**Voltage recovery (frequency domain):**  
  V_hat(omega) = -[i*omega*theta / (i*omega*C_p + 1/R)] * (U_hat_{a,1} - U_hat_{b,2})

**Effective complex dynamic stiffness:**  
  k_{b,eff}(omega) = k_b - [i*omega*theta^2 / (i*omega*C_p + 1/R)]

Non-dimensionalized:  
  k_tilde_{b,eff}(Omega) = 1 - [i*Omega*kappa^2 / (i*Omega + epsilon)]

Physical meaning:  
- Real part Re{k_tilde_{b,eff}}: stiffness modification (stiffening effect) -> causes TR frequency shift  
- Imaginary part Im{k_tilde_{b,eff}} < 0: energy dissipation into the resistor = harvested electrical power  

The imaginary part being negative means the harvesting circuit adds damping, which further enhances vibration attenuation. This is the mathematical proof that harvesting and damping are synergistic.  
虚部为负意味着采能电路增加阻尼，进一步增强振动衰减。这是采能与抑振协同的数学证明。

### 2.4.5 Quantitative Performance Metrics / 定量性能指标

Three metrics define success for any TR-based VEH design:  
三个指标定义了任何基于 TR 的 VEH 设计的成功标准：

**PEF (Power Enhancement Factor / 功率增强因子):**  
  PEF = max P_R(Omega)|_TR / max P_R(Omega)|_PB1

where PB1 denotes the first passband resonance. Reference values from validated models:  
其中 PB1 为第一通带共振。已验证模型中的参考值：
- Diatomic chain baseline parameters: PEF ~ 167  
- Diatomic chain optimized parameters: PEF > 300  
- Timoshenko beam (Al/Epoxy, N=12): PEF ~ 10^2  

**eta (Energy Concentration Ratio / 能量集中比):**  
  eta = E_bar_1 / sum_{i=1}^{N} E_bar_i

where E_bar_i is the cycle-averaged total energy in cell i. TR modes exhibit eta one order of magnitude higher than passband modes. Target: eta > 0.5  
其中 E_bar_i 为第 i 个晶胞中的周期平均总能量。TR 模态的 eta 比通带模态高一个数量级。目标：eta > 0.5

**T(Omega_TR) (Transmission at TR frequency / TR 频率处的传输率):**  
  T(Omega_TR) < 0 dB (must remain below 0 dB for suppression to be valid)

This confirms that span-wise vibration attenuation is maintained at the harvesting frequency.  
这确认了在采能频率处 span-wise 振动衰减被维持。

### 2.4.6 Topological Perspective / 拓扑学视角

Truncation resonances have a deep connection to topological physics, providing both theoretical understanding and practical robustness guarantees.  
Truncation resonance 与拓扑物理学有深层联系，既提供理论理解，也提供实用的鲁棒性保证。

**Phason framework:**  
The spatial phase phi of the property modulation serves as an additional dimension, mapping the 1D periodic beam onto a 2D torus T^2 = [0,2pi] x [0,2pi] in (wavenumber kappa, phason phi) space.  
属性调制的空间相位 phi 作为额外维度，将 1D 周期梁映射到波数-phason 空间中的 2D 环面。

**Chern gap labels:**  
Each bandgap is characterized by a gap label C_g = sum of Chern numbers of bands below the gap. The key result: the number of truncation resonances traversing a bandgap as phi varies over 2pi equals |C_g|.  
每个 bandgap 由 gap label C_g 表征。关键结论：当 phi 变化 2pi 时穿越该 bandgap 的 TR 数目等于 |C_g|。

**Boundary phasons phi_r, phi_l:**  
Left and right boundary truncation resonances can be independently tuned via separate boundary phasons, equivalent to adding a tuning layer at the corresponding end of the structure.  
左右边界的 TR 可以通过独立的边界 phason 分别调谐，等效于在结构相应端添加 tuning layer。

**Design implications:**  
- C_g != 0 guarantees that TR exists in the bandgap (topologically protected)  
- C_g = 0 means TR is not guaranteed (may still appear as non-topological defect modes)  
- Topological protection means TR will not disappear under small parameter perturbations as long as the bandgap does not close  
- However, the exact TR frequency is still sensitive to boundary conditions and phason values  
- The current project adopts topology-agnostic transfer-operator criteria for practical design portability, while retaining topological analysis as an optional deep verification layer  
- C_g != 0 保证 TR 在 bandgap 中存在（拓扑保护）  
- C_g = 0 意味着 TR 不被保证（可能作为非拓扑 defect mode 出现）  
- 拓扑保护意味着只要 bandgap 不闭合，TR 不会因小参数扰动而消失  
- 但 TR 的精确频率仍然对边界条件和 phason 值敏感  
- 本项目采用与拓扑无关的 transfer-operator 准则以保证设计可移植性，同时保留拓扑分析作为可选深层验证

### 2.4.7 TR vs Defect Mode Discrimination / TR 与 Defect Mode 的辨别

Two distinct types of in-gap resonances can appear in finite periodic structures. The system must distinguish them because their design and exploitation strategies differ fundamentally.  
有限周期结构中可出现两种不同类型的 gap 内共振。系统必须加以区分，因为它们的设计与利用策略根本不同。

| Feature | Truncation Resonance | Defect Mode |
|---------|---------------------|-------------|
| Origin | Truncation of finite structure (boundary effect) | Physical defect in periodicity |
| Topology | C_g != 0; frequency traverses gap with phi | C_g = 0 (typically); flat band inside gap |
| Localization | Boundary-localized (exponential decay into bulk) | Defect-site-localized |
| Robustness | Topologically protected (exists as long as gap is open) | Not guaranteed to exist |
| Frequency control | Tune boundary phason phi_r or phi_l | Tune defect parameters |
| Coupling | May couple with defect modes when defect approaches boundary | May couple with TR near boundary |

Identification criterion: if an in-gap resonance frequency traverses the bandgap as the phason phi varies over 2pi, it is a topological TR. If it remains as a flat band, it is a defect mode.  
辨别标准：如果一个 gap 内共振频率随 phason phi 在 2pi 范围内遍历 bandgap，则为拓扑 TR。若保持为 flat band，则为 defect mode。

### 2.4.8 Cross-Model Generality / 跨模型通用性

The TR mechanism is model-agnostic. The core features — boundary localization, co-located attenuation and resonance, synergistic harvesting and damping — have been validated across:  
TR 机制与模型无关。核心特征——边界局域化、衰减与共振共存、采能与抑振协同——已在以下模型中得到验证：

1. **Lumped diatomic chain** (spring-mass, analytical / 集总双原子链)  
2. **Periodic Timoshenko beam** (continuous, TMM / 周期 Timoshenko 梁)  
3. **Experimental bi-material phononic crystal beam** (Al/ABS, measured FRF / 实验双材料声子晶体梁)

This cross-model consistency confirms that TR is a general wave-physics effect, not an artifact of any particular model. The autonomous system should therefore trust mechanism-level predictions from simple models while using complex models for quantitative refinement.  
这种跨模型一致性确认 TR 是一般性的波动物理效应，而非特定模型的产物。因此自动系统应信任简单模型的机制级预测，同时用复杂模型进行定量细化。

---

## 3. System Goal / 系统目标

### 3.1 Functional Goal / 功能目标
Given excitation conditions, constraints, and design objectives, the system should automatically produce one or more feasible VEH designs that:
- satisfy mechanism-consistency checks,
- meet structural and electrical constraints,
- produce useful harvesting output,
- and come with an interpretable evidence chain.  
在给定激励条件、约束与设计目标后，系统应能自动生成一个或多个可行 VEH 设计，这些设计应满足：
- 通过机制一致性检查；
- 满足结构与电学约束；
- 具有可用的采能输出；
- 并附带可解释的证据链。

### 3.1.1 Quantitative Performance Targets (V1) / 定量性能目标 (V1)

For V1 focusing on the TR mechanism, the following quantitative targets are mandatory:  
对于聚焦 TR 机制的 V1，以下定量目标为强制要求：

**Primary targets / 主要目标:**  
- PEF >= 100: harvested power at TR frequency must exceed the first passband resonance power by at least two orders of magnitude  
  PEF >= 100：TR 频率处的采集功率必须超过第一通带共振功率至少两个数量级
- T(Omega_TR) < 0 dB: span-wise transmission at the TR frequency must remain negative, confirming vibration suppression is maintained  
  T(Omega_TR) < 0 dB：TR 频率处的 span-wise 传输率必须为负，确认振动抑制被维持
- eta > 0.5: energy concentration ratio at the boundary cell must exceed 50%, confirming strong boundary localization  
  eta > 0.5：边界晶胞的能量集中比必须超过 50%，确认强边界局域化

**Secondary targets / 次要目标:**  
- TR frequency deviation from target: < 5% relative error after electrical loading  
  TR 频率偏离目标值：加载电学负载后相对误差 < 5%
- Impedance matching quality: |epsilon - Omega_TR| / Omega_TR < 0.2 at optimal load  
  阻抗匹配质量：最优负载处 |epsilon - Omega_TR| / Omega_TR < 0.2

**Baseline definition / 基准定义:**  
Success requires meeting BOTH of the following baselines simultaneously:  
成功需要同时满足以下两条基准：

**Baseline A — Mechanism baseline (机制基准):**  
The same finite periodic structure with delta = 1 (periodic boundary, no TR), harvesting from the first passband resonance (PB1) with optimized load resistance. This isolates the mechanism advantage: how much does TR improve over the best that the same structure can do without TR?  
同一有限周期结构在 delta = 1（周期性边界，无 TR）条件下，从第一通带共振 (PB1) 采能且负载已优化。这隔离了机制优势：相同结构不用 TR 时最好能做到多少？  
- Metric: PEF = P_TR / P_PB1 >= 100  

**Baseline B — Engineering baseline (工程基准):**  
A conventional uniform cantilever beam (non-periodic, single material) with the SAME total mass, total length, total piezoelectric volume, excitation level, load topology, and target frequency window. This answers the engineering question: does the TR beam actually beat the simplest alternative, or does the periodic structure waste material on non-harvesting cells?  
一根常规均匀悬臂梁（非周期，单一材料），具有相同的总质量、总长度、总压电体积、激励水平、负载拓扑和目标频率窗口。这回答了工程问题：TR 梁是否真的优于最简单的替代方案，还是周期结构把材料浪费在了非采能晶胞上？  
- Metric: P_TR / P_conventional >= 1.0 (must not be worse)  
- Preferred: P_TR / P_conventional >= 2.0 (meaningful improvement)  

A design is declared successful only if it passes BOTH baselines. Passing Baseline A alone (high PEF) is insufficient if the absolute power is lower than a simple cantilever. Passing Baseline B alone is insufficient if the mechanism advantage is not demonstrated.  
一个设计只有同时通过两条基准才算成功。仅通过基准 A（高 PEF）但绝对功率低于简单悬臂梁是不够的。仅通过基准 B 但未展示机制优势也是不够的。

### 3.1.2 Equal-Constraint Comparison Rules / 等约束比较规则

Any comparison between a TR beam and any reference design (conventional cantilever, defect-mode harvester, or other metamaterial harvester) is valid ONLY if the following parameters are locked to identical values in both designs. Violating any of these rules renders the comparison unfair and the conclusion unreliable.  
TR 梁与任何参考设计（常规悬臂梁、defect-mode 采集器或其他超材料采集器）之间的比较，仅在以下参数在两个设计中锁定为相同值时才有效。违反任何一条规则都会使比较不公平，结论不可靠。

**Mandatory locked parameters / 必须锁定的参数:**  

| Parameter | Rationale |
|-----------|-----------|
| Total beam mass (including added masses) | Prevents unfair advantage from heavier structure having lower natural frequency and higher strain |
| Total beam length (envelope) | Prevents unfair advantage from longer beam having higher compliance |
| Total piezoelectric volume | Prevents unfair advantage from using more piezo material to boost coupling |
| Excitation level (acceleration amplitude or PSD) | Ensures identical energy input |
| Target frequency window | Ensures designs compete in the same operational regime |
| Load topology (resistive / rectified / storage) | Prevents circuit-level tricks from masking structural performance |
| Load value OR optimization freedom | Either both use fixed R, or both use independently optimized R* |

**Allowed to differ (these are the design freedoms):**  
- Internal structure (periodic vs uniform, mass distribution, stiffness distribution)  
- Piezoelectric placement (location, number of patches)  
- Boundary conditions (if both are structurally feasible)  
- Number of unit cells and cell geometry  
- Material selection within the same material palette  

**Comparison report must include:**  
- Explicit statement of all locked parameters with values  
- Both Baseline A and Baseline B results  
- If any locked parameter differs by more than 2%, flag the comparison as "approximate" with a stated correction factor  
- 比较报告必须包含所有锁定参数及其数值的明确声明

### 3.2 Research Goal / 研究目标
Create a persistent system that continuously improves across tasks by accumulating successful motifs, failure patterns, mechanism rules, electrical interface matching rules, and reusable strategies.  
构建一个可持续演进的系统，使其能够在不同任务中通过积累成功模式、失败模式、机制规则、电学接口匹配规则与可复用策略而不断提升。

---

## 4. High-Level Architecture / 高层架构

### 4.1 Main Modules / 主要模块
1. Task Card Layer / 任务卡层
2. Research Coordinator / 研究协调器
3. Proposal Layer / 方案生成层
4. Candidate Design Pool / 候选设计池
5. Mechanism Screening Layer / 机制筛选层
6. Structure–Transducer–Electrical Interface Co-Design Layer / 结构–换能器–电学接口协同设计层
7. Multi-Fidelity Verification Layer / 多保真验证层
8. Critic and Decision Layer / 批判与决策层
9. Analysis and Report Layer / 分析与报告层
10. Persistent Memory Layer / 持久记忆层

### 4.2 End-to-End Flow / 端到端流程
1. User or benchmark provides a task card. / 用户或 benchmark 提供任务卡。  
2. Coordinator interprets the task and allocates search budget. / 协调器解析任务并分配搜索预算。  
3. Proposal agents generate candidate design families. / 多个 proposal agent 生成候选设计族。  
4. Mechanism screening rejects mechanism-inconsistent candidates. / 机制筛选剔除与目标机制不一致的候选。  
5. Remaining candidates enter structure–transducer–electrical interface co-design. / 剩余候选进入结构–换能器–电学接口协同设计。  
6. Candidates are evaluated by increasingly expensive verification models. / 候选通过逐级升级的验证模型。  
7. Critic decides whether to accept, revise, switch family, or abandon route. / Critic 决定接受、修正、切换设计族，或放弃当前路线。  
8. Analysis compiles results and evidence. / 分析层整理结果与证据链。  
9. Memory stores successful and failed patterns. / 记忆层记录成功与失败模式。  
10. Coordinator launches the next iteration if needed. / 如有需要，协调器发起下一轮迭代。

---

## 5. Module Blueprint / 模块蓝图

## 5.1 Task Card Layer / 任务卡层

### Core Idea / 核心思想
Convert a vague engineering request into a structured machine-readable design problem.  
把模糊的工程需求转化为机器可读、可执行的结构化设计任务。

### Role / 作用
Acts as the canonical input specification for the entire system.  
作为整个系统的统一输入规范。

### Must Contain / 必须包含
- excitation conditions / 激励条件
- objective type / 目标类型
- constraints / 约束条件
- available materials / 可用材料
- fabrication assumptions / 制造假设
- electrical interface assumptions / 电学接口假设
- mechanism preference if specified / 若指定则包含机制偏好

### 5.1.1 Suppression-Harvesting Joint Task Card Fields / 减震-采能联合任务卡字段

For TR-based designs that target simultaneous suppression and harvesting, the task card must additionally include the following joint fields. Missing fields must be flagged as "unspecified" rather than silently defaulted.  
对于以同时抑振和采能为目标的 TR 设计，任务卡还必须包含以下联合字段。缺失字段必须标记为"未指定"，而非静默设置默认值。

```yaml
excitation:
  type: base_acceleration | base_displacement | force
  waveform: harmonic | narrowband_random | broadband_random
  amplitude: <value> <unit>    # e.g., 0.5 g, 0.3 mm
  spectrum: <file_path or inline definition>  # for random excitation

frequency_target:
  band_of_interest: [f_lower, f_upper] Hz
  primary_target_frequency: <value> Hz | "auto" (let system choose)

suppression_requirements:
  suppression_metric: span_wise_transmission | tip_displacement_ratio | transmissibility
  suppression_location: "downstream of cell N" | "far end"
  max_allowed_transmission: <value> dB  # e.g., -10 dB
  suppression_bandwidth: [f_lower, f_upper] Hz
  tr_frequency_exception: true | false  # whether a narrow peak at f_TR is allowed
  max_allowed_displacement: <value> <unit>  # optional absolute bound
  max_allowed_stress: <value> <unit>  # optional structural safety bound

harvesting_requirements:
  target_output: power | current | voltage
  output_type: peak | rms | time_averaged
  minimum_output: <value> <unit>  # e.g., 1.0 mW
  load_topology: resistive | resistive_rectified | capacitive_storage
  load_value: <value> Ohm | "optimize"

comparison_baselines:
  mechanism_baseline:
    type: same_structure_delta_1_PB1
    load: optimized
  engineering_baseline:
    type: conventional_uniform_cantilever
    constraints_locked: [total_mass, total_length, piezo_volume, excitation, load_topology, target_frequency_window]

envelope_constraints:
  total_mass: <value> kg
  total_length: <value> m
  max_cross_section: <value> m^2
  piezo_volume: <value> m^3
  piezo_material: PZT-5A | PZT-5H | custom
```

### Output / 输出
A normalized task card object.  
一个标准化 task card 对象。

### Acceptance Standard / 验收标准
A task card is valid only if the objective is explicit, constraints are explicit or defaulted with traceable assumptions, units are normalized, and ambiguity is tagged rather than hidden.  
只有当目标明确、约束明确或有可追溯默认值、单位规范统一、歧义被明确标记而非隐藏时，任务卡才算有效。

---

## 5.2 Research Coordinator / 研究协调器

### Core Idea / 核心思想
A top-level controller manages research direction, budget, and strategy transitions.  
由一个顶层控制器统一管理研究方向、预算和策略切换。

### Role / 作用
- route tasks / 任务路由
- select proposal sources / 选择 proposal 来源
- decide when to escalate fidelity / 决定何时升级验证保真度
- decide when to revise or switch direction / 决定何时修正或切换方向
- synchronize memory and analysis / 协调记忆与分析

### Acceptance Standard / 验收标准
Coordinator is correct if, for a fixed task and seed, it produces traceable routing decisions, reproducible search plans, and explicit termination reasons.  
对于固定任务和随机种子，若协调器能输出可追踪的路由决策、可复现的搜索计划和明确的终止原因，则认为其设计合格。

---

## 5.3 Proposal Layer / 方案生成层

### Core Idea / 核心思想
Generate candidate design families from complementary sources rather than relying on a single ideation process.  
从互补来源生成候选设计族，而不是依赖单一灵感来源。

### Submodules / 子模块

#### A. Memory-Guided Proposal Agent / 基于记忆的方案生成器
Uses accumulated internal experience.  
利用系统累计的内部经验。

**Role / 作用：**
- warm starts / 提供 warm start
- avoid repeated failures / 避免重复失败
- reuse mechanism-compatible motifs / 复用与机制兼容的成功模式

#### B. Paper-Grounded Proposal Agent / 基于论文的方案生成器
Uses literature-grounded inspiration.  
利用论文与文献中的启发。

**Role / 作用：**
- retrieve related mechanisms / 提取相关机制
- extract reusable structural patterns / 抽取可复用结构模式
- transform literature cases into current-task proposals / 将文献案例映射为当前任务的候选方案

#### C. Brainstorm Proposal Agent / 自由脑暴方案生成器
Provides controlled exploration.  
提供受控的探索性方案生成。

**Role / 作用：**
- propose novel combinations / 提出新组合
- explore uncovered regions / 探索 memory 和 paper 未覆盖的区域
- increase diversity under physical priors / 在物理先验约束下增加多样性

### Output / 输出
Each proposal agent outputs one or more candidate design families, not just single parameter points.  
每个 proposal agent 输出的是一个或多个候选设计族，而不是单个参数点。

### Acceptance Standard / 验收标准
A proposal is accepted only if it includes mechanism rationale, design variables, expected operating regime, and explicit assumptions.  
只有当 proposal 包含机制解释、设计变量、预期工作区间和明确假设时，才可进入候选池。

---

## 5.4 Candidate Design Pool / 候选设计池

### Core Idea / 核心思想
Separate idea generation from evaluation.  
将想法生成与后续评估解耦。

### Role / 作用
Store candidate design families in a standardized representation before verification.  
在验证前，以标准化格式存储候选设计族。

### Each Candidate Must Include / 每个候选必须包含
- structural parameterization / 结构参数化定义
- transducer placement plan / 换能器布置方案
- electrical interface plan / 电学接口方案
- mechanism hypothesis / 机制假设
- refinement range / 后续细化范围

### Acceptance Standard / 验收标准
A candidate family is valid only if all three domains are represented: structure, transducer, and electrical interface.  
只有同时覆盖结构、换能器和电学接口三个域，候选设计族才算有效。

---

## 5.5 Mechanism Screening Layer / 机制筛选层

### Core Idea / 核心思想
Reject candidates that do not satisfy mechanism preconditions before expensive evaluation.  
在昂贵验证之前，先剔除不满足机制前提的候选。

### Role / 作用
For the current TR-focused version, verify:
- whether bandgap behavior exists,
- whether TR is feasible,
- whether localization occurs in a useful region,
- whether suppression is compatible with harvesting.  
对于当前 TR 版本，需要验证：
- 是否存在 bandgap；
- 是否可能形成 TR；
- 局域化是否出现在有用位置；
- 抑振是否与采能兼容。

### Output / 输出
- pass / 通过
- revise / 修正后重试
- reject / 拒绝
- mechanism switch recommended / 建议切换机制路线

### 5.5.1 TR-Specific Screening Criteria / TR 专用筛选标准

For the current TR-focused version, the screening layer must execute the following checks in order:  
对于当前聚焦 TR 的版本，筛选层必须按以下顺序执行检查：

**Gate 1: Bandgap existence (必要条件)**  
- Compute the dispersion relation from (alpha, beta)  
- Verify that a bandgap exists in the frequency range of interest  
- If no bandgap: REJECT (TR is impossible without a stop band)  
- 由 (alpha, beta) 计算色散关系  
- 验证目标频率范围内存在 bandgap  
- 若无 bandgap：REJECT

**Gate 2: Boundary asymmetry (必要条件)**  
- Verify delta != 1  
- If delta = 1: REJECT (periodic boundary extinguishes TR)  
- 验证 delta != 1  
- 若 delta = 1：REJECT（周期性边界消灭 TR）

**Gate 3: TR frequency inside bandgap (必要条件)**  
- Solve det A(Omega) = 0 for the finite chain  
- Verify that at least one root falls inside the bandgap  
- If no root in bandgap: REVISE (adjust delta or alpha/beta)  
- 求解有限链的 det A(Omega) = 0  
- 验证至少一个根落入 bandgap  
- 若无根在 bandgap 内：REVISE

**Gate 4: Energy localization (质量检查)**  
- Compute energy concentration ratio eta for the TR mode  
- If eta < 0.3: REVISE (localization is too weak for effective harvesting)  
- 计算 TR 模态的能量集中比 eta  
- 若 eta < 0.3：REVISE（局域化过弱，无法有效采能）

**Gate 5: Topological classification (可选深层检查)**  
- Compute Chern gap label C_g for the target bandgap  
- C_g != 0: TR is topologically protected (high confidence in robustness)  
- C_g = 0: TR may be a non-topological defect mode (lower robustness, flag for careful sensitivity analysis)  
- 计算目标 bandgap 的 Chern gap label C_g  
- C_g != 0：TR 受拓扑保护（鲁棒性置信度高）  
- C_g = 0：TR 可能是非拓扑 defect mode（鲁棒性较低，标记以进行仔细的灵敏度分析）

**Gate 6: Suppression compatibility (功能检查)**  
- Compute transmission T(Omega_TR) at the TR frequency  
- If T(Omega_TR) >= 0 dB: REVISE (suppression is not maintained; this would indicate TR is actually in a passband, suggesting model inconsistency)  
- 计算 TR 频率处的传输率 T(Omega_TR)  
- 若 T(Omega_TR) >= 0 dB：REVISE（抑振未维持；这表明 TR 实际上在通带内，提示模型不一致）

### Acceptance Standard / 验收标准
The screening layer is useful only if it significantly reduces high-cost evaluations while preserving most truly promising candidates.  
若该层能显著减少高成本验证次数，同时保留大多数真正有潜力的候选，则说明设计成功。

---

## 5.6 Structure–Transducer–Electrical Interface Co-Design Layer / 结构–换能器–电学接口协同设计层

### Core Idea / 核心思想
Treat the VEH as a coupled system rather than independent mechanical and electrical blocks.  
把 VEH 视作一个耦合系统，而不是机械与电学两个独立模块。

### Role / 作用
Jointly refine:
- structural parameters,
- transducer placement and dimensions,
- electrical interface configuration.  
联合细化：
- 结构参数；
- 换能器位置与尺寸；
- 电学接口配置。

### Electrical Interface Subscope / 电学接口子范围
- load resistance / 负载电阻
- rectification option / 整流方案
- storage coupling / 储能耦合
- interface topology / 接口拓扑
- matching assumptions / 匹配假设

### 5.6.1 Electromechanical Co-Design Constraints / 机电协同设计约束

The co-design process must respect the following physics-driven constraints that arise from the electromechanical coupling model (Section 2.4.4):  
协同设计过程必须遵守以下由机电耦合模型（Section 2.4.4）产生的物理约束：

**Constraint 1: TR survival after electrical loading / 加载电学负载后 TR 存活性**  
After connecting the piezoelectric port to a load, the effective interface spring becomes complex-valued: k_tilde_{b,eff}(Omega) = 1 - i*Omega*kappa^2/(i*Omega + epsilon). This modifies the dynamic stiffness matrix A(Omega). The co-design layer must:  
- Re-solve det A_coupled(Omega_r) = 0 using k_tilde_{b,eff} instead of k_b  
- Verify that the coupled TR frequency Omega_r_coupled still lies inside the bandgap  
- If Omega_r_coupled exits the bandgap: reduce kappa^2 (weaker coupling) or adjust (alpha, beta) to widen the bandgap  
连接压电端口到负载后，有效界面弹簧变为复值。协同设计层必须：  
- 用 k_tilde_{b,eff} 替代 k_b 重新求解耦合后的 det A(Omega_r) = 0  
- 验证耦合后的 TR 频率仍在 bandgap 内  
- 若 TR 频率移出 bandgap：降低 kappa^2（减弱耦合）或调整 (alpha, beta) 以拓宽 bandgap

**Constraint 2: Frequency shift bound / 频率偏移约束**  
Monitor |Re{k_tilde_{b,eff}} - 1| as a proxy for TR frequency shift. The stiffening effect from the real part of the coupling should not shift TR frequency by more than 5% of the bandgap width.  
监控 |Re{k_tilde_{b,eff}} - 1| 作为 TR 频率偏移的预警。耦合实部带来的刚度效应导致的 TR 频率偏移不应超过 bandgap 宽度的 5%。

**Constraint 3: Q-factor preservation / Q 因子保持**  
The ratio |Im{k_tilde_{b,eff}}| / Re{k_tilde_{b,eff}} represents the effective loss factor introduced by the electrical circuit. Excessive electrical damping will over-damp the TR mode, reducing voltage output. There exists an optimal point where power is maximized, governed by the impedance matching criterion.  
比值 |Im{k_tilde_{b,eff}}| / Re{k_tilde_{b,eff}} 表示电路引入的有效损耗因子。过度的电学阻尼会过阻尼 TR 模态，降低电压输出。存在一个功率最大化的最优点，由阻抗匹配准则控制。

**Constraint 4: Impedance matching / 阻抗匹配**  
The optimal load resistance follows: R* ~ 1 / (C_p * omega_TR), equivalently epsilon* ~ Omega_TR. The co-design layer must solve for R* given the current (alpha, beta, delta, N) configuration and verify that R* falls within a physically realizable range.  
最优负载电阻遵循：R* ~ 1 / (C_p * omega_TR)，等效地 epsilon* ~ Omega_TR。协同设计层必须根据当前 (alpha, beta, delta, N) 配置求解 R*，并验证 R* 在物理可实现范围内。

**Constraint 5: Coupling strength feasibility / 耦合强度可行性**  
The coupling factor kappa^2 = theta^2 / (k_b * C_p) depends on the piezoelectric material properties and geometry. The co-design layer must verify that the required kappa^2 is achievable with available piezoelectric materials (typical range: kappa^2 ~ 0.01 to 0.1 for PZT ceramics in realistic configurations).  
耦合因子 kappa^2 = theta^2 / (k_b * C_p) 取决于压电材料特性和几何尺寸。协同设计层必须验证所需 kappa^2 在可用压电材料中可实现（PZT 陶瓷在实际配置中的典型范围：kappa^2 ~ 0.01 到 0.1）。

### Acceptance Standard / 验收标准
A co-design state is valid only if all coupled variables are explicit and can be sent forward without hidden assumptions.  
只有当所有耦合变量都被明确表达且可在无隐含假设下传递给后续验证层时，协同设计状态才算有效。

---

## 5.7 Multi-Fidelity Verification Layer / 多保真验证层

### Core Idea / 核心思想
Use the cheapest valid model first, then escalate only when justified.  
先使用成本最低但有效的模型，仅在必要时逐级升级。

### Role / 作用
Provide quantitative evidence at increasing levels of physical fidelity.  
在逐步提升物理保真度的过程中提供定量证据。

### L1: Fast Mechanism Verifier / L1：快速机制验证器
**Purpose / 目的：** rapid mechanism consistency screening. / 快速检查机制一致性。

**Implementation: Diatomic chain model (Section 2 of core reference)**  
- Model: lumped spring-mass chain with N unit cells, boundary mass m_{a+} = delta * m_a  
- Inputs: (alpha, beta, delta, N, kappa^2, epsilon)  
- Computations:  
  (a) Dispersion relation -> bandgap boundaries  
  (b) det A(Omega) = 0 -> all resonant frequencies including TR  
  (c) Mode shapes -> energy concentration ratio eta  
  (d) Voltage recovery V_tilde(Omega) -> voltage spectrum  
  (e) Power P_R(Omega) = |V_tilde|^2 * epsilon -> power spectrum  
- Outputs: bandgap [Omega_lower, Omega_upper], Omega_TR, eta, PEF, T(Omega_TR)  
- Complexity: O(N) matrix assembly + eigenvalue solve  
- Time target: < 1 second  
- 模型：N 个晶胞的集总弹簧-质量链，边界质量 m_{a+} = delta * m_a  
- 时间目标：< 1 秒

### L2: Mid-Fidelity Oracle / L2：中保真 oracle
**Purpose / 目的：** approximate engineering metrics such as power, stress, displacement, and frequency error.  
给出功率、应力、位移、频偏等近似工程指标。

**Implementation: Periodic Timoshenko beam via Transfer Matrix Method (Section 4 of core reference)**  
- Model: bilayer beam with layers A and B, each described by state vector y(x) = [w, phi, V, M]^T  
- State-space form: dy/dx = A(omega) y(x), where A(omega) is the 4x4 system matrix  
- Transfer matrix for uniform layer: T(L,omega) = exp(A(omega) * L)  
- Unit cell transfer matrix: T_cell(omega) = T_B(L_B,omega) * T_A(L_A,omega)  
- Bloch dispersion: det(T_cell - mu * I_4) = 0, mu = exp(ika) -> bandgaps  
- Finite beam: T_N(omega) = T_cell(omega)^N  
- TR criterion: det(C_r * T_N(omega) * B_l) = 0 with frequency inside a stop band  
- Boundary selectors: B_l (left BC) and C_r (right BC) encode free/clamped/pinned  
- Inputs: material properties (E, G, rho, kappa_s, A, I) for each layer, (L_A, L_B, N), BCs  
- Outputs: band structure (Hz), TR frequencies (Hz), transmission T(omega) (dB), mode shapes, harvested power P_R (mW)  
- Complexity: 4x4 matrix exponential per layer, N matrix multiplications  
- Time target: < 10 seconds  
- 模型：双层梁，每层由状态向量 y(x) = [w, phi, V, M]^T 描述  
- 时间目标：< 10 秒

### L3: High-Fidelity FEM + Electrical Interface Validation / L3：高保真 FEM + 电学接口验证
**Purpose / 目的：** final coupled electromechanical confirmation.  
用于最终的机电耦合可行性确认。

**Implementation: Full 3D FEM (e.g., COMSOL) with coupled piezoelectric physics**  
- Validates geometric effects, 3D stress distribution, electrode configuration  
- Includes material nonlinearity if needed  
- Full frequency sweep with coupled electrical circuit  
- Time target: minutes to hours depending on mesh density  
- 验证几何效应、3D 应力分布、电极配置  
- 时间目标：分钟到小时级

### 5.7.1 Inter-Model Consistency Gates / 模型间一致性门

The multi-fidelity pipeline requires explicit consistency checks between adjacent fidelity levels:  
多保真流水线要求在相邻保真度层之间进行明确的一致性检查：

**L1 -> L2 Consistency Gate:**  
- TR frequency: |Omega_TR(L1) - Omega_TR(L2)| / Omega_TR(L2) < 5%  
  Note: L1 uses non-dimensional Omega; L2 uses dimensional omega (Hz). Map via omega = Omega * omega_b.  
- Bandgap boundaries: relative error < 10%  
- Energy localization: if L1 predicts eta > 0.5, L2 must also show strong boundary localization in the mode shape  
- PEF order of magnitude: if L1 predicts PEF > 100, L2 should confirm PEF > 50 (allowing for model fidelity differences)  
- 注：L1 使用无量纲 Omega；L2 使用有量纲 omega (Hz)。通过 omega = Omega * omega_b 映射。

**L2 -> L3 Consistency Gate:**  
- TR frequency: relative error < 3%  
- Peak power: relative error < 30% (FEM captures 3D effects that TMM misses)  
- Transmission at TR: both must show T < 0 dB  
- Mode shape qualitative agreement: boundary localization pattern must match  

**Escalation trigger from L1 to L2:**  
A candidate passes L1 screening (Gates 1-6 from Section 5.5.1) with all gates at PASS status.  
候选通过 L1 筛选（Section 5.5.1 的 Gates 1-6 均为 PASS）时触发升级。

**Escalation trigger from L2 to L3:**  
L2 confirms PEF >= 100, T(Omega_TR) < 0 dB, and the Critic Layer judges the candidate as "promising" with high confidence. L3 is expensive and should only be used for final validation of top candidates.  
L2 确认 PEF >= 100 且 T(Omega_TR) < 0 dB，且 Critic Layer 判断候选为高置信"有潜力"时触发升级。L3 成本高昂，仅用于最终验证顶级候选。

### Acceptance Standard / 验收标准
A candidate can be marked fully feasible only if it passes the highest required fidelity tier for the current experiment tier.  
只有通过当前实验级别所要求的最高保真验证层，候选才可被标记为真正可行。

---

## 5.8 Critic and Decision Layer / 批判与决策层

### Core Idea / 核心思想
The system must explain failure rather than merely report poor performance.  
系统必须解释失败原因，而不只是报告结果不好。

### Role / 作用
- identify failure causes / 识别失败原因
- rank candidates / 排序候选
- decide revise vs switch / 决定局部修正还是切换路线
- decide terminate vs continue / 决定终止还是继续

### Acceptance Standard / 验收标准
A critic decision is acceptable only if it includes the decision type, reason, affected module, and next action.  
只有当 critic 输出包含决策类型、原因、受影响模块和下一步动作时，才算合格。

---

## 5.9 Analysis and Report Layer / 分析与报告层

### Core Idea / 核心思想
Outputs must be engineering-ready, not just numerically best.  
输出必须是工程可用的，而不只是数值上最优。

### Role / 作用
- summarize mechanism explanation / 总结机制解释
- assemble evidence chain / 组织证据链
- produce candidate ranking / 生成候选排序
- create design report / 输出设计报告
- support paper writing or benchmarking / 支持论文写作或 benchmark 分析

### Acceptance Standard / 验收标准
Every final reported design must have mechanism explanation, model evidence, constraint status, and reproducibility metadata.  
每个最终报告的设计都必须包含机制解释、模型证据、约束状态与可复现实验元数据。

---

## 5.10 Persistent Memory Layer / 持久记忆层

### Core Idea / 核心思想
Research improvement comes from preserving trajectories, not just outputs.  
研究能力的提升来自对轨迹的保留，而不是只保存最终输出。

### Memory Categories / 记忆类别
- successful design motifs / 成功设计模式
- failed design patterns / 失败设计模式
- mechanism knowledge / 机制知识
- electrical interface matching rules / 电学接口匹配规则
- reusable refinement strategies / 可复用修正策略

### Acceptance Standard / 验收标准
Memory entries must be structured, tagged, and traceable back to experiments.  
记忆条目必须结构化、可标记，并能追溯到对应实验。

---

## 6. System Collaboration Logic / 系统协作逻辑

### 6.1 Main Cooperation Pattern / 主协作模式
The modules cooperate in the following order: task definition, strategic routing, candidate generation, mechanism gate, co-design, layered verification, critic decision, report and memory update.  
系统模块按如下顺序协作：任务定义、策略路由、候选生成、机制门筛选、协同设计、分层验证、critic 决策、报告与记忆更新。

### 6.2 Persistent Loop Logic / 持续循环逻辑
The system continues iterating until:
- a feasible design is found,
- budget is exhausted,
- the mechanism route is invalidated,
- or no candidate family remains promising.  
系统会持续迭代，直到满足以下之一：
- 找到可行设计；
- 预算耗尽；
- 当前机制路线被证伪；
- 或者没有有希望的候选设计族。

### 6.3 What Makes It a Scientist / 为什么它是 scientist 而不是 solver
The system does not only search. It chooses whether a mechanism route is worth pursuing, interprets failure, changes research strategy, and accumulates transferable knowledge.  
系统不只是搜索参数，它还要判断某条机制路线是否值得继续、解释失败原因、调整研究策略，并积累可迁移知识。

---

## 7. Project Scope and Versioning Strategy / 项目范围与版本策略

### 7.1 Recommended V1 Scope / 建议的 V1 范围
To keep the project executable, V1 should be deliberately narrow.  
为了保证项目可执行，V1 必须有意识地收窄范围。

### V1 Focus / V1 主线
- mechanism: truncation resonance only / 机制：仅限 truncation resonance
- structure family: periodic beam / diatomic-inspired beam / 结构族：周期梁或类双原子梁
- transducer: piezo patch / 换能器：压电片
- electrical interface: resistive and simple rectified interface / 电学接口：阻性负载与简单整流接口
- primary objective: constrained power maximization under suppression constraint / 主目标：在抑振约束下最大化功率

### 7.1.1 V1 Design Space Bounds / V1 设计空间边界

The following bounds define the searchable design space for V1:  
以下边界定义了 V1 的可搜索设计空间：

**Structural parameters / 结构参数:**  
- Number of unit cells: 5 <= N <= 25 (N < 5: TR frequency not converged; N > 25: fabrication impractical for V1)  
- Mass ratio: 0.3 <= alpha <= 3.0  
- Stiffness ratio: 0.3 <= beta <= 3.0  
- Boundary asymmetry: 0.1 <= delta <= 0.9 OR 1.1 <= delta <= 4.0 (exclude delta ~ 1 where TR vanishes)  

**Electromechanical parameters / 机电参数:**  
- Coupling factor: 0.001 <= kappa^2 <= 0.2  
- Electrical damping ratio: determined by impedance matching criterion epsilon* ~ Omega_TR  
- Load resistance: computed from R* = 1 / (C_p * omega_TR)  

**Material palette for Timoshenko beam models / Timoshenko 梁模型材料库:**  
- Substrate options: Aluminum (E=70 GPa, rho=2700 kg/m^3), Steel (E=200 GPa, rho=7800 kg/m^3)  
- Contrast layer options: Epoxy (E=3.5 GPa, rho=1200 kg/m^3), ABS (E=2.4 GPa, rho=1040 kg/m^3), PMMA (E=3.0 GPa, rho=1180 kg/m^3)  
- Piezoelectric: PZT-5A or PZT-5H  
- Volume fraction (contrast layer length / cell pitch): 0.1 <= a_contrast/a <= 0.5  

**Boundary conditions / 边界条件:**  
- Free-clamped (primary, as in core reference validation)  
- Free-free, pinned-pinned (secondary, for robustness checks)

---

## 8. Engineering Design Specification Document / 工程设计规范文档

### 8.1 Repository-Level Design Rules / 仓库级设计规则

#### Rule 1 / 规则 1
Every module must have one clear responsibility.  
每个模块都必须只有一个清晰职责。

#### Rule 2 / 规则 2
Every module boundary must be explicit.  
每个模块边界必须明确。

#### Rule 3 / 规则 3
Assumptions must be logged.  
所有关键假设必须记录。

#### Rule 4 / 规则 4
Reproducibility is mandatory.  
可复现性是硬性要求。

#### Rule 5 / 规则 5
Mechanism reasoning must be inspectable.  
机制推理必须可检查、可追踪。

---

### 8.2 Code Organization Recommendation / 代码组织建议

```text
veh_scientist/
  README.md
  pyproject.toml
  src/
    veh_scientist/
      coordinator/
      taskcard/
      proposals/
      candidates/
      mechanism/
      codesign/
      verifiers/
      critic/
      analysis/
      memory/
      interfaces/
      utils/
  configs/
    tasks/
    experiments/
    models/
  tests/
    unit/
    integration/
    regression/
  docs/
    blueprint/
    api/
    design_notes/
  experiments/
    runs/
    reports/
```

---

### 8.3 Module Design Template / 模块设计模板
Every module should include: purpose, inputs, outputs, assumptions, failure modes, and logging fields.  
每个模块都应包含：用途、输入、输出、假设、失败模式和日志字段。

---

### 8.4 Code Style Rules / 代码风格规范
- Python as orchestration language / Python 作为核心 orchestration 语言
- strict type hints required / 必须使用严格类型标注
- dataclasses or pydantic for interfaces / 接口对象用 dataclass 或 pydantic
- black + ruff + mypy required / 强制使用 black、ruff、mypy

All physics-critical functions must avoid magic numbers and must state units explicitly.  
所有涉及物理关键逻辑的函数都不得使用隐式 magic number，单位必须显式表达。

---

### 8.5 Interface Definition Rules / 接口定义规范
Every module boundary should exchange structured objects whenever possible.  
模块边界尽可能传递结构化对象，而不是松散字典。

Mandatory core interfaces:  
- `TaskCard`  
- `CandidateDesignFamily`  
- `MechanismScreenResult`  
- `CoDesignState`  
- `VerificationResult`  
- `CriticDecision`  
- `MemoryRecord`  
- `AnalysisReport`

Each interface must include schema version, units, provenance, and validation checks.  
每个接口都必须包含 schema 版本、单位、来源信息和校验规则。

---

### 8.6 Module Acceptance Standards / 模块验收标准
Each module must pass its own functional acceptance test and at least one integration test involving its public interface.  
每个模块都必须通过自身功能验收测试，并至少通过一个涉及其公共接口的集成测试。

---

### 8.7 Testing Strategy / 测试策略
- Unit tests / 单元测试
- Integration tests / 集成测试
- Regression tests / 回归测试

No module can be merged without passing lint, type checks, and required tests.  
未经 lint、类型检查和必要测试通过的模块，不得合并。

---

### 8.8 Git and Development Workflow / Git 与开发流程

#### Branch Strategy / 分支策略
- `main`: always stable / 始终稳定
- `dev`: integration branch / 集成分支
- `feature/<module>-<topic>`: feature work / 功能开发分支
- `experiment/<short-name>`: temporary research branches / 临时实验分支

#### Commit Rules / 提交规范
Use conventional commit types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`.  
使用规范化 commit 类型：`feat`、`fix`、`refactor`、`test`、`docs`、`chore`。

#### Pull Request Requirements / PR 要求
Every PR must include purpose, changed modules, interface changes, test evidence, compatibility notes, and reproducibility notes if experiment-related.  
每个 PR 都必须说明目的、变更模块、接口变化、测试证据、兼容性说明，以及实验相关的可复现说明。

#### Experiment Tracking Rule / 实验记录规则
Important experiment results must be tracked through configs, run IDs, reports, and summary markdown files.  
重要实验结果必须通过配置文件、run ID、报告和总结 markdown 文件记录，而不能只写在 commit 信息里。

---

## 9. Suggested Immediate Deliverables / 近期建议交付物

### Blueprint Documents to Create First / 首批建议创建文档
1. `project_blueprint.md` / 项目蓝图  
2. `module_spec.md` / 模块规范  
3. `interface_spec.md` / 接口规范  
4. `dev_workflow.md` / 开发流程规范

### First Functional Milestone / 第一阶段功能里程碑
A narrow V1 demo should be able to:
- ingest a task card,
- generate candidate families,
- run mechanism screening,
- run at least L1 and L2 verification,
- output a critic decision,
- save a memory record,
- generate one report.  
一个收窄范围的 V1 demo 至少应能完成：
- 读取任务卡；
- 生成候选设计族；
- 运行机制筛选；
- 完成至少 L1 和 L2 验证；
- 输出 critic 决策；
- 保存一条 memory record；
- 生成一份报告。

---

## 10. Final Positioning Statement / 最终定位表述
This project should be managed as a persistent engineering research system whose purpose is to convert physically motivated mechanism hypotheses into feasible VEH designs through structured proposal generation, structure–transducer–electrical interface co-design, multi-fidelity verification, critic-guided revision, and reusable memory accumulation.  
本项目应被管理为一个持续运行的工程研究系统，其目标是通过结构化方案生成、结构–换能器–电学接口协同设计、多保真验证、critic 引导修正和可复用记忆积累，把物理机制假设转化为真正可行的 VEH 设计。

---

## 11. Sensitivity, Robustness, and Fabrication Considerations / 灵敏度、鲁棒性与制造考量

### 11.1 Parameter Sensitivity Hierarchy / 参数灵敏度层次

Based on the theoretical framework and validated models, the design parameters have the following sensitivity characteristics:  
基于理论框架和已验证模型，设计参数具有以下灵敏度特征：

**High sensitivity (must be tightly controlled):**  
- delta: controls TR on/off; small changes near delta = 1 cause dramatic voltage changes (V-shaped response)  
- Volume fraction (a_contrast/a): TR frequency is noticeably more sensitive to unit-cell layer dimensions than conventional resonances are; beyond a_contrast/a ~ 0.25, TR may exit the bandgap entirely  
- delta：控制 TR 开/关；在 delta = 1 附近小变化导致电压剧烈变化  
- 体积分数：TR 频率对晶胞层尺寸的敏感度明显高于常规共振

**Medium sensitivity (should be designed with margin):**  
- (alpha, beta): shift bandgap location and TR frequency; +-10% change causes proportional frequency shift  
- kappa^2: affects power output magnitude and optimal load; +-20% changes are acceptable  

**Low sensitivity (robust):**  
- N (number of cells): TR frequency is largely insensitive to N for N >= 5 (boundary-driven phenomenon); increasing N only sharpens the peak  
- Boundary conditions: TR exists under free-free, free-clamped, and pinned-pinned BCs; frequency location shifts but existence is robust  
- N（晶胞数）：N >= 5 时 TR 频率对 N 基本不敏感；增大 N 只使峰更尖锐  
- 边界条件：TR 在 free-free、free-clamped、pinned-pinned 下均存在

### 11.2 Robustness Guarantees from Topology / 拓扑提供的鲁棒性保证

For bandgaps with non-zero Chern gap label (C_g != 0):  
- TR is guaranteed to exist as long as the bandgap remains open  
- Small parameter perturbations will shift TR frequency but cannot eliminate it  
- The number of TR modes traversing the gap equals |C_g| regardless of boundary conditions  
对于 Chern gap label 非零 (C_g != 0) 的 bandgap：  
- 只要 bandgap 保持打开，TR 保证存在  
- 小参数扰动会移动 TR 频率但不能消除它  
- 穿越 gap 的 TR 模态数等于 |C_g|，与边界条件无关

This means the system does NOT need Monte Carlo analysis to verify TR existence — topological protection guarantees it. However, Monte Carlo analysis IS needed to quantify TR frequency drift under manufacturing tolerances, which affects impedance matching quality.  
这意味着系统不需要 Monte Carlo 分析来验证 TR 存在性——拓扑保护已保证。但仍需要 Monte Carlo 分析来量化制造公差下 TR 频率的漂移，这影响阻抗匹配质量。

### 11.3 V1 Fabrication Feasibility Notes / V1 制造可行性说明

The following fabrication considerations should be addressed before any physical prototype:  
在任何物理原型之前，应处理以下制造考量：

- **Periodic beam assembly:** bi-material beams (e.g., Al/ABS) can be fabricated by bonding pre-cut blocks with adhesive, as validated experimentally in the reference literature  
- **Piezoelectric patch bonding:** patch should be placed at the (1-2) cell interface; bonding quality directly affects theta (coupling coefficient) and hence kappa^2  
- **Boundary mass control:** delta is realized by modifying the end mass; precision of delta directly controls TR on/off behavior  
- **Tolerance on periodicity:** imperfect periodicity may introduce additional defect modes; the system should flag candidates where TR frequency is close to bandgap edges (more vulnerable to perturbation)  
- 周期梁组装：双材料梁可通过粘接预切块制造  
- 压电片粘贴：应放置在第 (1-2) 晶胞界面；粘贴质量直接影响耦合系数  
- 边界质量控制：delta 通过修改端部质量实现；delta 的精度直接控制 TR 开/关  
- 周期性公差：不完美周期性可能引入额外 defect mode

### 11.4 Failure Mode Table / 失效模式表

The following table catalogs known failure modes that can degrade or destroy TR-based harvesting performance. The system must check for each of these during verification and flag any that are triggered.  
下表编录了可能降低或破坏基于 TR 的采能性能的已知失效模式。系统必须在验证过程中检查每一种，并标记任何被触发的失效。

| ID | Failure Mode | Root Cause | Detection Method | Mitigation Strategy |
|----|-------------|------------|-----------------|---------------------|
| F1 | TR pulled out of bandgap by electrical coupling | kappa^2 too large; Re{k_tilde_{b,eff}} shifts TR frequency beyond bandgap boundary | Check Omega_TR_coupled vs bandgap bounds after electrical loading | Reduce kappa^2 (thinner piezo, lower d31 material); widen bandgap via (alpha, beta) adjustment |
| F2 | Insufficient boundary localization | delta too close to 1; or N too small for adequate isolation | Compute eta; if eta < 0.3, localization is insufficient | Increase |delta - 1|; increase N to sharpen boundary state |
| F3 | TR peak too narrow for practical use | Very high Q from large N + low damping; 3 dB bandwidth << excitation bandwidth | Compute -3 dB bandwidth of voltage/power peak; compare to excitation spectral width | Accept trade-off (narrowband harvesting); or reduce N for broader peak at cost of lower peak power; or add light structural damping |
| F4 | Bonding layer degradation of coupling | Adhesive layer between piezo patch and substrate acts as compliant shim, reducing effective theta | Compare measured theta vs theoretical theta; ratio < 0.7 indicates bonding issue | Use thinner, stiffer adhesive; apply controlled bonding pressure; include bonding layer in FEM model |
| F5 | Rectification-induced current collapse | Full-bridge rectifier with large C_storage creates voltage threshold; at low excitation, open-circuit voltage < 2*V_diode and no current flows | Simulate rectifier circuit with realistic diode V_forward; check minimum excitation for current onset | Use low-V_forward Schottky diodes; use active rectification (synchronous); size C_storage appropriately |
| F6 | Manufacturing tolerance induces defect mode aliasing | Cell-to-cell parameter variation breaks perfect periodicity, creating unintended defect modes whose frequencies overlap with TR | Compute eigenfrequencies with +-5% random perturbation on cell parameters; check for new in-gap modes near Omega_TR | Design TR frequency away from bandgap center (where defect modes tend to appear); increase N for better TR/defect separation; use Gate 5 topological check |
| F7 | Bandgap closure under loading | Electrical stiffening from large kappa^2 or strong electromechanical coupling modifies the effective dispersion, potentially closing the bandgap | Recompute dispersion relation with k_tilde_{b,eff}; verify bandgap still exists | Limit kappa^2; choose (alpha, beta) giving wider initial bandgap |
| F8 | Multi-TR interference | Multiple TR modes in the same bandgap (|C_g| > 1) may interact destructively when piezo port is shared | Check number of TR modes; if >1, compute relative phases at the piezo port | Design for single-TR operation; or use separate piezo ports for each TR; or select (phi_r, phi_l) to separate TR frequencies |
| F9 | Structural fatigue at boundary | TR concentrates strain energy at boundary; sustained high-Q resonance may cause fatigue failure at the (1-2) interface | Compute max stress at boundary under TR; compare to fatigue endurance limit | Add stress constraint to optimization; choose materials with adequate fatigue life; limit excitation amplitude |
| F10 | Impedance mismatch after frequency drift | Temperature change, aging, or load variation shifts omega_TR, breaking the epsilon* ~ Omega_TR matching condition | Monitor power output; >50% drop from design value indicates mismatch | Design with impedance matching bandwidth margin; use adaptive load matching circuit |

**Usage rule:** Every candidate that passes L2 verification must be checked against ALL failure modes F1-F10. A candidate with any triggered failure mode at "critical" severity is flagged for REVISE; two or more triggered failure modes → REJECT.  
**使用规则：** 每个通过 L2 验证的候选必须针对所有失效模式 F1-F10 进行检查。任何一个"严重"级别的失效模式被触发则标记为 REVISE；两个或以上被触发 → REJECT。

---

## 12. Implementation Status / 实现状态追踪

> 最后更新：2026-04-09

### 12.1 Multi-Fidelity Verification Layer (§5.7) — ✅ 完成

这是目前唯一完整实现的系统层，覆盖 L1→L2→L3 全链路。

#### L1：双原子链模型 (Phase 0)
| 子步骤 | 状态 | 说明 |
|--------|------|------|
| Step 0a：色散关系 + bandgap | ✅ | `src/veh_scientist/verifiers/l1_chain/dispersion.py` |
| Step 0b：有限链特征频率 + TR判别 | ✅ | `src/veh_scientist/verifiers/l1_chain/finite_chain.py` |
| Step 0c-0d：压电耦合 + 功率采集 | ✅ | `src/veh_scientist/verifiers/l1_chain/piezo_harvesting.py` |
| 单元测试 | ✅ 31/31 | `tests/unit/test_dispersion.py` (15) + `test_finite_chain_and_harvesting.py` (16) |
| MATLAB 精度对标 | ✅ | 误差 < 10⁻¹⁰，`scripts/cross_validate_matlab.py` |
| Phase 3 参数扫描 + 失效模式 | ✅ | δ扫描✅ αβ热图✅ ε匹配✅ F1-F6失效验证✅ |

关键性能指标（L1 baseline 参数）：
- PEF ~ 167（TR vs 第一通带共振）
- eta > 0.5（边界能量集中比）
- T(Omega_TR) < 0 dB（抑振维持）

#### L2：Timoshenko 梁 TMM + FEM (Phase 1-2)
| 子步骤 | 状态 | 说明 |
|--------|------|------|
| Step 1a：传递矩阵法 (TMM) | ✅ | `src/veh_scientist/verifiers/l2_beam/tmm.py` |
| Step 1b：Bloch 色散 + bandgap | ✅ | `src/veh_scientist/verifiers/l2_beam/dispersion.py` |
| Step 1c-1d：FEM + 压电 + 频率扫描 | ✅ | `src/veh_scientist/verifiers/l2_beam/beam_analysis.py` |
| 双基准比较系统 (Phase 2) | ✅ | `src/veh_scientist/verifiers/l2_beam/baseline_comparison.py` |
| 单元测试 | ✅ 12/12 | `tests/unit/test_l2_beam.py` |
| MATLAB new_bc.m 对标 | ✅ | 与参考脚本误差 < 机器精度 |

设计参数（Al/Epoxy 参考配置）：
- L_A=80mm, L_B=20mm, b=25mm, h=5mm
- Al: E=68.9GPa, ρ=2700, ν=0.33
- Epoxy: E=2.4GPa, ρ=1040, ν=0.35
- PZT-5H: d₃₁=-274e-12, ε₃₃=3400ε₀, R_load=1MΩ
- TMM Bandgap 1: [399.4, 955.6] Hz；TR at 532.5 Hz

#### L3：COMSOL 3D 结构验证 (Phase 4)
| 子步骤 | 状态 | 说明 |
|--------|------|------|
| 3D 周期梁几何构建 | ✅ | `src/veh_scientist/verifiers/l3_comsol/periodic_beam_comsol.py` |
| 特征频率求解 (30 modes) | ✅ | 6.5s，COMSOL 6.2 + mph 1.3.1 |
| 频域位移 FRF 扫描 | ✅ | 17.4s，80 频率点 |
| Bandgap 交叉验证 | ✅ | 上界误差 4.7%（≤10% 准则）✅ |
| 模型文件保存 | ✅ | `results/phase4/periodic_beam.mph` |

L3 验证结论：
- COMSOL 3D bandgap 上界 1000.7 Hz vs L2 TMM 955.6 Hz，误差 **4.7% ✅**
- 下界差异大（81.4%）属于预期物理现象（3D 包含扭转/面内模态）

---

### 12.2 其他系统层 — ⏳ 尚未实现

| 模块 | 蓝图章节 | 状态 | 优先级 |
|------|---------|------|--------|
| Task Card Layer | §5.1 | ❌ 未实现 | 高 |
| Research Coordinator | §5.2 | ❌ 未实现 | 高 |
| Proposal Layer | §5.3 | ❌ 未实现 | 中 |
| Candidate Design Pool | §5.4 | ❌ 未实现 | 中 |
| **Mechanism Screening Layer** | **§5.5** | **❌ 未实现** | **最高（下一步）** |
| Co-Design Layer | §5.6 | ❌ 未实现 | 中 |
| Critic and Decision Layer | §5.8 | ❌ 未实现 | 中 |
| Analysis and Report Layer | §5.9 | ❌ 未实现 | 低 |
| Persistent Memory Layer | §5.10 | ❌ 未实现 | 中 |

---

### 12.3 V1 Demo 里程碑进度 / First Functional Milestone Progress

参照 §9 的 V1 Demo 要求：

| 需求 | 状态 | 说明 |
|------|------|------|
| 读取任务卡 | ❌ | Task Card 结构未定义 |
| 生成候选设计族 | ❌ | Proposal Layer 未实现 |
| 运行机制筛选 | ⚠️ 工具就绪，门控未封装 | L1 verifier 已实现 Gates 1-4 所需的所有计算，但未封装为 Gate 决策逻辑 |
| L1 + L2 验证 | ✅ | 完整实现，带测试套件 |
| L3 验证 | ✅ | COMSOL 结构验证完成 |
| 输出 Critic 决策 | ❌ | Critic Layer 未实现 |
| 保存 Memory Record | ❌ | Memory Layer 未实现 |
| 生成报告 | ⚠️ 基础版 | Phase 脚本生成 markdown 报告，未集成为标准 AnalysisReport 接口 |

**当前阶段结论：** 多保真验证层（L1/L2/L3）全部完成，物理建模基础稳固。  
**瓶颈：** 缺少将物理计算工具组织为自主科学家循环的上层逻辑。

---

## 12.4 下一步建议 → Mechanism Screening Layer (§5.5)

**理由：** 机制筛选层直接调用已完成的 L1 verifier，是连接物理计算工具与候选评估决策的最短桥梁。实现后即可构建 `候选参数 → Gates 1-6 → pass/revise/reject` 的完整判决链，为后续加入 Proposal 和 Coordinator 奠定接口基础。

实现范围（严格对应 §5.5.1 的 Gates）：

```
src/veh_scientist/mechanism/
├── screening.py          # MechanismScreener 主类：运行 Gates 1-6
├── gates.py              # 六个独立 Gate 函数，每个返回 GateResult
└── screen_result.py      # MechanismScreenResult dataclass
```

每个 Gate 的输入/输出已在蓝图中完全定义，实现工作量清晰有界。

---

## 13. Core References / 核心参考文献

The following references form the theoretical foundation of this project. All design rules, screening criteria, model specifications, and performance metrics in this blueprint are derived from these works.  
以下参考文献构成本项目的理论基础。本蓝图中所有设计规则、筛选标准、模型规范和性能指标均源自这些工作。

### Reference 1 (Core design framework / 核心设计框架)
"Synergistic Vibration Suppression and Energy Harvesting using Truncation Resonance"  
- Establishes the diatomic chain model with piezoelectric port  
- Derives the four-level design parameter hierarchy (delta, alpha/beta, kappa^2/epsilon, N)  
- Proves synergistic co-location of harvesting and attenuation  
- Provides impedance matching criterion: epsilon* ~ Omega_TR  
- Validates cross-model generality (chain -> Timoshenko beam)  
- Demonstrates PEF ~ 10^2 over first passband resonance  

### Reference 2 (Topological foundations / 拓扑基础)
Rosa, Davis, Liu, Ruzzene, Hussein. "Material vs. structure: Topological origins of band-gap truncation resonances in periodic structures." arXiv:2301.00101, 2022.  
- Establishes phason framework for TR characterization  
- Derives Chern gap labels predicting number of TR modes per bandgap  
- Introduces boundary phasons for independent TR control at each boundary  
- Demonstrates TR frequency convergence for N >= 5 cells  
- Distinguishes topological TR from non-topological defect modes  
- Provides experimental validation on Al/ABS phononic crystal beams

