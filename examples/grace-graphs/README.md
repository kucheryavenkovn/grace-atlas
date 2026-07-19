# GRACE graphs (generated)

Source artifacts:

- `requirements`: `D:/git/video2pptx/tools/grace_atlas/tests/fixtures/minimal/requirements.xml` — **OK**
- `development_plan`: `D:/git/video2pptx/tools/grace_atlas/tests/fixtures/minimal/development-plan.xml` — **OK**
- `knowledge_graph`: `D:/git/video2pptx/tools/grace_atlas/tests/fixtures/minimal/knowledge-graph.xml` — **OK**
- `verification_plan`: `D:/git/video2pptx/tools/grace_atlas/tests/fixtures/minimal/verification-plan.xml` — **OK**
- `technology`: `D:/git/video2pptx/tools/grace_atlas/tests/fixtures/minimal/docs/technology.xml` — **MISSING**
- `operational_packets`: `D:/git/video2pptx/tools/grace_atlas/tests/fixtures/minimal/docs/operational-packets.xml` — **MISSING**

Modules: **4** · depends: **2** · V-M: **2** · UC: **2** · Phases: **2** · Steps: **2**

Regenerate (DOT + PNG + SVG + Mermaid):

```powershell
python tools/grace_graphs/generate_grace_graphs.py --project-root .
```

PNG/SVG require [Graphviz](https://graphviz.org/) (`dot` on PATH).

## Diagrams

### overview

- Graphviz DOT: [`dot/overview.dot`](dot/overview.dot)
- SVG: [`svg/overview.svg`](svg/overview.svg)
- PNG: [`png/overview.png`](png/overview.png)

![GRACE Overview](png/overview.png)

- Mermaid: [`mermaid/overview.mmd`](mermaid/overview.mmd)
- Mermaid (preview): [`mermaid/overview.md`](mermaid/overview.md)

**GRACE Overview** — nodes=8 edges=7

```mermaid
%% GRACE Overview
flowchart TB
  CriticalFlows["CriticalFlows<br/>1"]
  CrossLinks["CrossLinks<br/>1"]
  DataFlows["DataFlows<br/>1"]
  DependsEdges["depends_on<br/>2"]
  Modules["Modules<br/>4"]
  Phases["Phases<br/>2"]
  UseCases["UseCases<br/>2"]
  Verifications["Verifications<br/>2"]

  Modules -->|has| DependsEdges
  Modules -->|verified_by| Verifications
  Modules -->|linked| CrossLinks
  UseCases -->|related| DataFlows
  UseCases -->|covered_by| CriticalFlows
  Phases -->|implements| Modules
  CriticalFlows -->|checks| Verifications
```

### modules-deps

- Graphviz DOT: [`dot/modules-deps.dot`](dot/modules-deps.dot)
- SVG: [`svg/modules-deps.svg`](svg/modules-deps.svg)
- PNG: [`png/modules-deps.png`](png/modules-deps.png)

![GRACE Module Dependencies](png/modules-deps.png)

- Mermaid: [`mermaid/modules-deps.mmd`](mermaid/modules-deps.mmd)
- Mermaid (preview): [`mermaid/modules-deps.md`](mermaid/modules-deps.md)

**GRACE Module Dependencies** — nodes=4 edges=2

```mermaid
%% GRACE Module Dependencies
flowchart LR
  M_CORE["M-CORE<br/>Core<br/>[implemented]"]
  M_HELPER["M-HELPER<br/>Helper<br/>[implemented]"]
  M_MISSING_FILE["M-MISSING-FILE<br/>MissingFile<br/>[implemented]"]
  M_UNVERIFIED["M-UNVERIFIED<br/>Unverified<br/>[implemented]"]

  M_HELPER -->|depends_on| M_CORE
  M_UNVERIFIED -->|depends_on| M_CORE
```

### modules-deps-core

- Graphviz DOT: [`dot/modules-deps-core.dot`](dot/modules-deps-core.dot)
- SVG: [`svg/modules-deps-core.svg`](svg/modules-deps-core.svg)
- PNG: [`png/modules-deps-core.png`](png/modules-deps-core.png)

![GRACE Module Dependencies](png/modules-deps-core.png)

- Mermaid: [`mermaid/modules-deps-core.mmd`](mermaid/modules-deps-core.mmd)
- Mermaid (preview): [`mermaid/modules-deps-core.md`](mermaid/modules-deps-core.md)

**GRACE Module Dependencies** — nodes=3 edges=2

```mermaid
%% GRACE Module Dependencies
flowchart LR
  M_CORE["M-CORE<br/>Core<br/>[implemented]"]
  M_HELPER["M-HELPER<br/>Helper<br/>[implemented]"]
  M_UNVERIFIED["M-UNVERIFIED<br/>Unverified<br/>[implemented]"]

  M_HELPER -->|depends_on| M_CORE
  M_UNVERIFIED -->|depends_on| M_CORE
```

### modules-verification

- Graphviz DOT: [`dot/modules-verification.dot`](dot/modules-verification.dot)
- SVG: [`svg/modules-verification.svg`](svg/modules-verification.svg)
- PNG: [`png/modules-verification.png`](png/modules-verification.png)

![GRACE Modules ↔ Verification](png/modules-verification.png)

- Mermaid: [`mermaid/modules-verification.mmd`](mermaid/modules-verification.mmd)
- Mermaid (preview): [`mermaid/modules-verification.md`](mermaid/modules-verification.md)

**GRACE Modules ↔ Verification** — nodes=6 edges=3

```mermaid
%% GRACE Modules ↔ Verification
flowchart LR
  M_CORE["M-CORE<br/>Core"]
  M_HELPER["M-HELPER<br/>Helper"]
  M_MISSING_FILE["M-MISSING-FILE<br/>MissingFile"]
  M_UNVERIFIED["M-UNVERIFIED<br/>Unverified"]
  V_M_CORE["V-M-CORE<br/>[passed]"]
  V_M_HELPER["V-M-HELPER<br/>[passed]"]

  M_CORE -->|verified_by| V_M_CORE
  M_HELPER -->|verified_by| V_M_HELPER
  M_MISSING_FILE -->|verified_by| V_M_CORE
```

### use-cases-flows

- Graphviz DOT: [`dot/use-cases-flows.dot`](dot/use-cases-flows.dot)
- SVG: [`svg/use-cases-flows.svg`](svg/use-cases-flows.svg)
- PNG: [`png/use-cases-flows.png`](png/use-cases-flows.png)

![GRACE Use Cases ↔ Flows](png/use-cases-flows.png)

- Mermaid: [`mermaid/use-cases-flows.mmd`](mermaid/use-cases-flows.mmd)
- Mermaid (preview): [`mermaid/use-cases-flows.md`](mermaid/use-cases-flows.md)

**GRACE Use Cases ↔ Flows** — nodes=4 edges=3

```mermaid
%% GRACE Use Cases ↔ Flows
flowchart LR
  DF_001["DF-001<br/>DetectPipeline"]
  UC_001["UC-001<br/>Runs detect"]
  UC_ORPHAN["UC-ORPHAN<br/>Orphan use case"]
  VF_001["VF-001<br/>DetectHappyPath"]

  UC_001 -->|related_flow| DF_001
  VF_001 -->|uses| UC_001
  VF_001 -->|data_flow| DF_001
```

### phases-steps

- Graphviz DOT: [`dot/phases-steps.dot`](dot/phases-steps.dot)
- SVG: [`svg/phases-steps.svg`](svg/phases-steps.svg)
- PNG: [`png/phases-steps.png`](png/phases-steps.png)

![GRACE Phases and Steps](png/phases-steps.png)

- Mermaid: [`mermaid/phases-steps.mmd`](mermaid/phases-steps.mmd)
- Mermaid (preview): [`mermaid/phases-steps.md`](mermaid/phases-steps.md)

**GRACE Phases and Steps** — nodes=6 edges=4

```mermaid
%% GRACE Phases and Steps
flowchart TB
  Phase_1["Phase-1<br/>Foundation<br/>[done]"]
  Phase_2["Phase-2<br/>Current<br/>[in_progress]"]
  V_M_CORE["V-M-CORE"]
  V_M_HELPER["V-M-HELPER"]
  step_1_1["step-1.1<br/>Core<br/>[done]"]
  step_2_1["step-2.1<br/>Work<br/>[in_progress]"]

  Phase_1 -->|contains| step_1_1
  step_1_1 -->|verified_by| V_M_CORE
  Phase_2 -->|contains| step_2_1
  step_2_1 -->|verified_by| V_M_HELPER
```

### cross-links

- Graphviz DOT: [`dot/cross-links.dot`](dot/cross-links.dot)
- SVG: [`svg/cross-links.svg`](svg/cross-links.svg)
- PNG: [`png/cross-links.png`](png/cross-links.png)

![GRACE CrossLinks (knowledge-graph)](png/cross-links.png)

- Mermaid: [`mermaid/cross-links.mmd`](mermaid/cross-links.mmd)
- Mermaid (preview): [`mermaid/cross-links.md`](mermaid/cross-links.md)

**GRACE CrossLinks (knowledge-graph)** — nodes=2 edges=1

```mermaid
%% GRACE CrossLinks (knowledge-graph)
flowchart LR
  M_CORE["M-CORE"]
  M_HELPER["M-HELPER"]

  M_HELPER -->|uses helper utilities| M_CORE
```

