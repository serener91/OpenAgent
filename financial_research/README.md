# Financial Researcher

## Executive Summary

**Financial Researcher**는 기업에 대한 금융/재무 관련 분석을 위해 설계된 **End-to-End 멀티 에이전트 시스템**입니다. 단순한 텍스트 생성을 넘어, 계획 수립부터 병렬 정보 수집, 다단계 검증 및 문서화까지의 전 과정을 역할 기반(Role-based) 에이전트들이 분담하여 수행합니다.

---

## 1. System Architecture

복잡한 Workflow를 세분화하고, 각 단계의 책임과 실패 지점을 명확히 분리한 다음과 같은 구조를 가집니다.


**Logic Flow**

```
    ["User Query"]
         |
    [Planner (Task Decomposition)]
         |
    [Parallel Search (Information Gathering)]
         |
    [Writer (Drafting): Sub-agents (Financial analyst & Risk analyst)]
         |
    [Auditor (Quality / Compliance Check)]
         |    
    "(Feedback Loop - Self Improvement)"
         |    
    [Formatter (Organize the writing into markdown)]
         |    
    [Final Report (.md)]
```

---

## 2. Technical Points

### **2.1 역할 기반 Task 분리**
각 에이전트는 독립된 책임을 가지며, 이는 시스템 확장성을 더하며, 효율적인 디버깅이 가능케 합니다:
* **Planner**: 검색 쿼리를 생성하고 데이터 분석 계획 수립.
* **Search**: 인터넷 검색을 통한 관련 정보 수집 (병렬 처리).
* **Writer**: Subagents(Financial analyst & Risk analyst)을 활용 하여 수집된 근거 기반 초안 작성.
* **Auditor**: Writer가 작성한 주장의 타당성, 일관성, 근거 유무 검증.
* **Formatter**: 마크다운 형식의 최종 리포트 변환.

### **2.2 Pydantic 기반 Structured Handoff**
에이전트 간 데이터 전달 시 **Typed Schema**를 사용하여 인터페이스를 규격화했습니다.
* `FinancialSearchPlan`, `VerificationResult` 등 명확한 Contract를 통해 단계별 출력 데이터의 무결성을 보장하여 Handoff로 발생하는 불안정을 감소.
* LLM의 자율성에 의존하지 않고 시스템 설계 내에서 실행 흐름 통제.

### **2.3 비동기 및 실행 제어**
`asyncio`를 활용하여 네트워크 I/O 성능을 최적화하고 운영 안정성을 확보했습니다.
* **Bounded Concurrency**: `asyncio.Semaphore`를 사용하여 동시 검색 수를 제한, Fan-Out으로 인한 Rate Limit 및 리소스 고갈을 방지.
* **Partial Success**: 일부 검색 실패가 전체 워크플로우 중단으로 이어지지 않도록 예외 처리.

### **2.4 Audit-Driven Rewrite Loop**
시스템의 품질 관리 알고리즘으로, Auditor가 초안을 검토한 후 피드백을 전달하여 Writer가 수정하는 루프를 수행합니다.
* **Quality Gate**: 근거 없는 주장이나 모순을 필터링.
* **Bounded Loop**: 피드백 루프 횟수를 제한하여 시스템이 무한 루프로 인한 Hang 상태에 빠지지않게 예방.

### **2.5 Langfuse 기반 Observability**
멀티 에이전트 시스템의 블랙박스 문제를 해결하기 위해 **Observability Layer**를 통합했습니다.
* 각 에이전트의 Input/Output 및 실행 시간 추적.
* 병목 지점 파악 및 비용 최적화를 위한 데이터 확보.

---

## 3. Implementation Details

| 항목 | 기술 스택                          |
| :--- |:-------------------------------|
| **Language** | Python                         |
| **Orchestration** | OpenAI Agents SDK              |
| **Data Validation** | Pydantic (Structured Output)   |
| **Observability** | Langfuse                       |

---

## 4. Business Value & Outcome

* **신뢰성 확보**: Feedback Loop를 통해 LLM의 Hallucination을 최소화하고 Fact 중심의 리포트 생성.
* **효율성 증대**: 반복적인 시장 조사 및 리포트 작성 업무를 자동화.
* **유연한 확장**: 새로운 도구(예: Valuation API, Sentiment 분석)를 Specialist Tool 형태로 쉽게 통합 가능.


## 5. Limitation

Financial Researcher는 agent system을 설계하면서 마주칠수 있는 문제 (Infinite Loop, Hallucination, Broken Communication, high operational costs) 등을
어떠한 방식으로 해결할 수 있는지에 대해 다룹니다. 

이 시스템을 기반으로 목적에 맞게 Agent Harness (Prompt, Tool, Guardrail 등)을 구성한다면 Production-Level에서 사용 가능한 시스템으로 구현할 수 있습니다.


## 6. Example

### [NVIDIA - Fourth quarter of fiscal 2025](./outputs/nvidia_fy2025_q4.md)

### [System Tracing](./outputs/tracing.png)





