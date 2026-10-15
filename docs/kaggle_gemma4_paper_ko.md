# 규칙보다 순서가 중요하다: Gemma 4 31B 기반 다중 테이블 트랜잭션 코딩을 위한 실행 흐름 명세 연구

**부제:** 로컬 에이전트 하네스에서의 설계 표현 방식, 정보량 통제 절제 실험 및 반복 실행 안정성 분석

---

## 1. 초록 (Abstract)

엔지니어링 현장에서는 로컬 오픈웨이트 모델에게 코드 작성을 맡기기 전에 사전 설계(upfront design) 단계를 두는 경우가 많다. 본 연구는 로컬 환경에서 구동되는 **Gemma 4 31B-IT** 모델(`temperature = 0.2`, `12,288` 토큰 컨텍스트)이 15스텝의 도구 호출 예산 안에서 SQLite 다중 테이블 트랜잭션 예약 엔진을 구축할 때, 사전 설계 산출물의 표현 방식이 구현 정확도와 토큰 비용에 미치는 영향을 분석한다. 단일 턴 설계(Designer) 세션과 5개의 워크스페이스 격리 파일·테스트 도구만 갖춘 코딩(Coder) 세션을 분리한 2단계 로컬 평가 하네스를 통해, 두 가지 규모의 1:1 심리상담 예약 벤치마크—소규모 과업(2개 테이블, 5개 공개 메서드, 6개 검증 항목) 및 대규모 과업(4대 서브시스템, 7개 상호 결합 테이블, 13개 공개 메서드, 선불 상담권 원장·원자적 일정 변경·선입선출 대기열 자동 승격·교차 테이블 정합성 대사·취소된 예약의 멱등 재호출을 검증하는 8개 항목)—에 걸쳐 **총 22회의 엔드투엔드(end-to-end) 실행**을 수행했다. 6가지 설계 표현 수준, 순수 무설계(no-design) 베이스라인, 정보량을 100% 통제한 비순서형(unordered) 대조 실험, 그리고 대규모 핵심 조건들의 `n = 3` 반복 실험을 분석한 결과 다음 네 가지 사실을 확인했다.
1. **자유 형식 산문 설계는 두 규모 모두에서 무설계 베이스라인보다 성능이 낮다.** 15스텝 상한을 모두 소진하고 총 토큰을 59%~219% 더 소비하며, 조건 분기 누락 버그를 유발해 대규모 과업 검증 점수가 무설계(`7/8`)보다 낮은 `6/8`에 그쳤다.
2. **선언적 상태 불변식(declarative state invariants)은 반복 실행(`n = 3`)에서 심각한 불안정성을 보인다.** 1차 실행에서는 `67,569` 토큰으로 `7/8`을 통과했으나, 2·3차 실행에서는 상담권 발급 중 발생한 SQLite 이중 합산(double-counting) 자기 교정 버그로 인해 각각 `146,112` 토큰과 `154,716` 토큰을 소모하며 `1/8`로 급락했다(평균 `3.00 ± 3.46 / 8`).
3. **번호가 부여된 실행 흐름 명세(`Step 1` → `Step N`)가 정확도와 실행 안정성을 동시에 극대화한다.** 소규모 과업에서 전 조건 최저 비용(`33,219` 토큰, `7` 스텝, `6/6`)을 기록했고, 대규모 과업에서도 최고 검증 점수(`7.67 ± 0.58 / 8`, 3회 중 2회 `8/8` 만점)와 함께 **총 토큰 `83,878 ± 3,302` (`CV = 3.9%`)**, **코더 출력 토큰 `16,560 ± 418` (`CV = 2.5%`)**을 달성하여 다른 반복 실행 조건 대비 총 토큰 표준편차를 12.9배~14.9배 줄였다.
4. **정보량 통제 절제 실험을 통해 생명주기 버그를 막는 핵심 요인이 문구(정보량)가 아니라 단계 순서(step ordering)임을 입증했다.** 코더에게 동일한 JSON 문장, 스키마, 그리고 무조건적 조회 규칙(`"If idempotency_key exists in bookings, return existing booking."`)을 그대로 제공하되 단계 번호(`1..6`)만 제거하고 불릿 순서를 섞자, `8/8` 만점 통과율이 `2/3` (`66.7%`)에서 `1/3` (`33.3%`)로 절반 감소했고 총 토큰 표준편차는 12.9배(`± 3,302` → `± 42,688`) 폭증했다.

---

## 2. 서론 (Introduction)

Gemma 4 31B-IT와 같은 30B급 오픈웨이트 모델은 단일 워크스테이션에서 다단계 코딩 에이전트 워크플로를 수행할 수 있으며, 실무에서는 흔히 명세를 작성하는 *Designer* 단계와 코드를 작성·검증하는 *Coder* 단계로 역할을 나눈다. 그러나 사전 설계 명세의 형식은 자유 산문과 정적 스키마 계약부터 선언적 상태 불변식, 번호가 매겨진 실행 흐름에 이르기까지 매우 다양하다. 제한된 컨텍스트 창(`12,288` 토큰)과 스텝 예산(`15` 스텝) 아래에서 로컬 31B 모델은 날카로운 트레이드오프에 직면한다. 장황한 명세는 실행 중 대화 압축(history compaction)과 도구 호출 JSON 잘림(truncation)을 유발하는 반면, 상태 전이 순서가 생략된 명세는 다중 테이블 SQLite 정합성 버그를 낳는다.

본 연구는 외부 상용 프레임워크의 자동 재시도 보조 없이 순수 로컬 하네스에서 다음 두 가지 연구 질문에 답한다.
1. **표현 방식(Representation):** 점진적으로 구조화된 6가지 설계 표현 방식은 소규모 및 대규모 트랜잭션 코딩 벤치마크에서 검증 정확도와 토큰 비용에 어떤 영향을 미치는가?
2. **작동 기제(Content vs. Order):** 번호가 부여된 실행 흐름 명세가 선언적 불변식 조건에서도 실패하던 생명주기 버그를 해결할 때, 그 효과는 추가된 도메인 문구(정보량) 때문인가, 아니면 `Step 1` → `Step N`의 시계열적 배치 순서 때문인가?

---

## 3. 연구 방법론 (Methodology)

### 3.1 실험 하네스 및 모델 추론 환경

총 22회의 모든 실험은 로컬 `llama.cpp`(`llama-server`, `/v1/chat/completions`, 단일 슬롯 `-np 1`)에서 구동된 **Gemma 4 31B-IT** (`Q4_K_M` GGUF) 모델을 사용했으며, `temperature = 0.2`, `context_length = 12,288` 토큰(한계 근접 시 초기 프롬프트와 최근 6개 메시지를 보존하고 이전 대화를 요약하는 history compaction 작동), 최대 `15` 스텝 예산을 동일하게 적용했다.
- **Stage 1 (Designer):** 과업 요구사항과 조건별 설계 지침을 입력받아 도구 없이 단일 턴에 구조화된 JSON 설계 명세(`design_spec.json`)와 마크다운 문서를 생성한다.
- **Stage 2 (Coder):** Designer의 추론 문맥 없이 과업 요구사항과 Stage 1 설계 산출물만 전달받아 격리된 워크스페이스에서 코드를 구현·검증한다. 코더에게는 역할별로 격리된 5개 도구만 제공된다: (1) 파일 탐색(`list_files`, `read_file`), (2) 파일 전체 작성 및 부분 치환(`write_file`, `replace_text`), (3) 단위 테스트 실행(`run_tests`, `pytest` 실행 결과 반환).

### 3.2 벤치마크 아키텍처 및 표준 검증 스위트

두 벤치마크 모두 1:1 심리상담 서비스("여백 상담소")를 위한 Python 3.11+ 및 SQLite 기반 백엔드 엔진(`counseling_engine.py`, 파일 경로 및 단일 커넥션 `:memory:` 영속성 지원)과 단위 테스트 스위트(`test_counseling.py`)를 처음부터 작성하도록 요구한다.

#### 소규모 과업 (Small-Scale Task, V1): 2개 테이블, 5개 공개 메서드, 6개 검증 요구사항
`CounselingService` (`counseling_engine.py`)는 2개 테이블(`slots`, `bookings`)과 **5개 공개 메서드**(`add_available_slot`, `query_available_slots`, `create_booking`, `lookup_booking`, `cancel_booking`)를 관리한다. 6개 표준 검증 항목은 다음과 같다: `REQ-1` 상담사 슬롯 등록(`add_available_slot`) 및 필터 조회(`query_available_slots`); `REQ-2` 예약 생성(`create_booking`) 및 가용 목록 제외; `REQ-3` 동일 시간 중복 슬롯 생성 및 이중 예약 차단; `REQ-4` `lookup_booking` 호출 시 `client_email` 본인 확인 검증; `REQ-5` 예약 취소(`cancel_booking`, `client_email` 대조) 시 슬롯 가용성 복구 및 재예약 허용; `REQ-6` `:memory:` 단일 커넥션 영속성 유지.

#### 대규모 과업 (Large-Scale Task, V2): 4대 서브시스템, 7개 상호 결합 테이블, 13개 공개 메서드, 8개 검증 요구사항
`CounselingBookingEngine` (`counseling_engine.py`)은 **4대 서브시스템**과 **13개 공개 메서드**에 걸쳐 **7개의 상호 결합된 테이블**(`counselors`, `slots`, `session_passes`, `pass_ledger`, `bookings`, `waitlist`, `audit_logs`)을 조율한다.
1. **Subsystem A — 상담사 및 슬롯 생명주기 (`counselors`, `slots`):** `register_counselor`, `add_slot` (`AVAILABLE` 슬롯 생성), `block_slot` (`AVAILABLE` → `BLOCKED` 전환; 이미 예약된 `BOOKED` 슬롯은 차단 거부), `query_available_slots` (**`REQ-1`**).
2. **Subsystem B — 선불 상담권 및 멱등 원장 (`session_passes`, `pass_ledger`):** `issue_session_pass` (`remaining_sessions` 충전 및 `pass_ledger`에 `ISSUE`, `delta_sessions = +N` 기록; 동일한 `idempotency_key` 재호출 시 중복 충전 없이 기존 잔여 횟수 반환) 및 `get_session_pass` (**`REQ-2`**).
3. **Subsystem C — 예약 생성 및 원자적 일정 변경 사가 (`bookings`):** `create_booking` (`idempotency_key` 검증 후 슬롯 `AVAILABLE` 및 상담권 `remaining_sessions >= 1` 확인, 슬롯 `BOOKED` 전환, 상담권 `-1` 차감 및 `USE` 원장 기록, `CONFIRMED` 예약 생성, `BOOKING_CREATED` 감사 로그 기록; 잔여 횟수 부족 시 전체 롤백 [`REQ-3`]), `lookup_booking` (`client_email` 검증), `reschedule_booking` (추가 상담권 차감 없이 기존 슬롯을 `AVAILABLE`로 해제하고 신규 가용 슬롯을 `BOOKED`로 점유하는 원자적 스왑 수행 및 `BOOKING_RESCHEDULED` 기록; 실패 시 기존 예약 보존 [`REQ-4`]).
4. **Subsystem D — 선입선출 대기열 자동 승격, 감사 로그 및 정합성 대사 (`waitlist`, `audit_logs`):** `join_waitlist` (`BOOKED` 슬롯에 대해 잔여 상담권 `>= 1`인 고객을 선입선출 `WAITING` 상태로 등록), `cancel_booking` (`CONFIRMED` 예약을 `CANCELLED`로 전환하고 취소 고객에게 상담권 `+1` `RESTORE` 원장 및 `BOOKING_CANCELLED` 로그를 기록한 뒤 FIFO 대기열 상태에 따라 분기: 적격 `WAITING` 대기자가 없으면 슬롯을 `AVAILABLE`로 복원[`REQ-5`]하고, 적격 대기자가 있으면 잔여 횟수 0인 대기자들을 `EXPIRED` 처리한 뒤 1순위 적격 대기자를 `PROMOTED`로 전환·상담권 `-1` `USE` 차감·신규 `CONFIRMED` 예약 생성 및 `WAITLIST_PROMOTED` 로그 기록 후 슬롯 상태를 `BOOKED`로 유지[`REQ-6`]), `get_booking_audit_log`, `get_system_reconciliation` (`total_issued_sessions == total_remaining_sessions + total_used_sessions` 및 `total_used_sessions == active_confirmed_bookings == booked_slots_count` 성립 시 `is_balanced: True` 반환 [`REQ-7`]).
- **`REQ-8` (취소된 예약의 멱등키 재호출 보호):** `idempotency_key = "k1"`로 생성된 예약이 취소(`status = 'CANCELLED'`, 슬롯 `AVAILABLE` 복귀)된 이후 동일한 `idempotency_key = "k1"`로 `create_booking`을 다시 호출하면, 상담권을 재차감하거나 `UNIQUE(idempotency_key)` 제약 조건 충돌로 크래시하지 않고 기존의 취소된 예약 레코드(동일 `booking_id`)를 그대로 반환해야 한다.

### 3.3 실험 조건 및 정보량 통제 절제(Ablation) 설계

|실험 조건|실행 모드|Stage 2 (Coder)에 전달되는 명세 형식|
|:---|:---:|:---|
|**Cond 0-Pure (`Direct`)**|1-Stage|**순수 무설계 베이스라인.** Stage 1 생략(`0` 설계 토큰); 코더가 원본 요구사항만 직접 수신.|
|**Cond 0-Min (`Unprimed`)**|2-Stage|**최소 패스스루 베이스라인.** 형식 제약 없는 최소 프롬프트로 Stage 1 실행.|
|**Cond 1 (`Free-Form Prose`)**|2-Stage|**자유 형식 산문 설계.** 마크다운 기반의 일반적인 아키텍처 및 컴포넌트 서술.|
|**Cond 2 (`Static Contracts`)**|2-Stage|**정적 구조 계약.** 명시적 SQLite 스키마, 메서드 시그니처, 입출력 타입 및 예외 조건.|
|**Cond 3 (`State Invariants`)**|2-Stage|**선언적 상태 불변식.** 정적 계약 + 테이블 간 보존 방정식 및 허용/금지 상태 전이 규칙.|
|**Cond 4-Flow (`Execution Flow`)**|2-Stage|**실행 흐름 명세.** 정적 계약 + 메서드별 번호가 매겨진 실행 파이프라인(`Step 1` → `Step N`).|
|**Cond 4-Unordered (`Shuffled`)**|Fixed-S2|**정보량 통제 절제.** `Cond 4-Flow` (`r1`)의 `design_spec.json`에서 단계 번호(`1..6`)만 제거하고 불릿 순서를 섞어 고정 입력.|
|**Cond 5 (`Profiled Flow`)**|2-Stage|**행동 프로파일 결합 명세.** 전체 명세 + 코더 행동 수칙 및 자기 검증 체크리스트 추가.|

*참고: V1 `Cond 0-Pure` 초기 실행은 40스텝 상한에서 9스텝 만에 조기 완료되었으며, 턴당 `max_output_tokens`는 V1 `Cond 1`~`Cond 3` 및 `Cond 5`에서 `3,584`, V1 `Cond 4-Flow` 및 V2 전체 실행에서 `4,608`로 설정되었다.*

---

## 4. 실험 결과 (Results)

모든 실행은 에이전트가 자체 작성한 테스트(**Agent Pytest**)와 독립적인 **표준 검증 스위트**(V1 `REQ-1`–`REQ-6`, V2 `REQ-1`–`REQ-8`; `Total Tokens = Design In + Design Out + Impl In + Impl Out`)로 평가되었다.

### 4.1 소규모(V1) 대 대규모(V2) 단일 실행 비교 (`r1`)

#### 표 1: 소규모 과업 실험 결과 (V1, 2개 테이블, 5개 메서드, 6개 검증 요구사항)

|Condition|Status|Design In|Design Out|Design Time|Steps (Tools)|Impl In|Impl Out|Total Tokens|Total Time|Agent Pytest|Standard Verify|
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
|**Cond 0-Pure (`No Design`)**|`completed`|0|0|0.0s|9 (8)|44,221|5,648|49,869|8.7m|10/10|**6/6**|
|**Cond 1 (`Free-Form Prose`)**|`step_limit`|1,271|2,035|173.6s|15 (15)|67,215|8,973|79,494|17.8m|10/12|**6/6***|
|**Cond 2 (`Static Contracts`)**|`completed`|1,308|2,547|217.9s|11 (10)|50,205|16,036|70,096|27.9m|11/11|**6/6**|
|**Cond 3 (`State Invariants`)**|`step_limit`|1,328|2,663|230.0s|15 (15)|84,413|19,091|107,495|39.0m|0/11†|**6/6**|
|**Cond 4-Flow (`Execution Flow`)** ⭐|`completed`|1,715|2,009|172.5s|**7 (6)**|**24,142**|**5,353**|**33,219**|**10.5m**|8/8|**6/6**|
|**Cond 5 (`Profiled Flow`)**|`step_limit`|1,409|2,501|241.2s|15 (15)|65,576|6,826|76,312|17.5m|0/12‡|0/6 (6/6‡)|

*\*V1 `Cond 1`은 초기에 메서드마다 새 `sqlite3.connect()`를 열어 `:memory:` 상태를 잃었으나 Step 14에서 `self._conn`을 캐싱해 `6/6`을 통과했으며, 중복 취소 예외 분기에 임포트되지 않은 `CounselingError`를 남겨 자체 테스트는 `10/12`에 그쳤다.*  
*†V1 `Cond 3`은 엔진 검증 `6/6`을 통과했으나, 테스트 파일이 `BookingVerificationError`를 임포트한 반면 엔진은 `PermissionError`를 발생시켜 15스텝을 소진했다.*  
*‡V1 `Cond 5`는 DB 초기화를 별도 헬퍼 클래스 `DatabaseManager`로 분리하면서 생성자 7행에 `self._initialize_db()`, 8행에 `self._init_db()`를 연달아 적고 실제 메서드는 15행에 `def _init_db(self):`만 정의하여 `AttributeError`로 실패했다(7행 제거 시 `6/6` 통과).*

#### 표 2: 대규모 과업 1차 실험 결과 (V2, 7개 테이블, 13개 메서드, 8개 검증 요구사항, `r1`)

|Condition|Status|Design In|Design Out|Design Time|Steps (Tools)|Impl In|Impl Out|Total Tokens|Total Time|Agent Pytest|Standard Verify|Failed Reqs|
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
|**Cond 0-Pure (`Direct`)**|`completed`|0|0|0.0s|6 (5)|30,999|12,383|43,382|19.3m|8/8|7/8|`REQ-8`|
|**Cond 0-Min (`Unprimed`)**|`completed`|3,967|2,537|261.9s|7 (5)|42,005|15,389|63,898|28.2m|8/8|7/8|`REQ-8`|
|**Cond 1 (`Free-Form Prose`)**|`step_limit`|4,014|2,542|212.9s|15 (14)|105,782|25,892|138,230|42.1m|6/8|6/8|`REQ-5, REQ-7`|
|**Cond 2 (`Static Contracts`)**|`completed`|4,091|2,068|190.1s|12 (11)|80,475|39,609|126,243|59.5m|8/8|7/8|`REQ-8`|
|**Cond 3 (`State Invariants`)**|`completed`|4,135|2,141|180.3s|7 (5)|41,439|19,854|67,569|31.3m|8/8|7/8|`REQ-8`|
|**Cond 4-Flow (`Execution Flow`)** ⭐|`completed`|4,501|1,547|285.8s|10 (8)|63,150|16,134|85,332|28.3m|8/8|**8/8**|**None (100%)**|
|**Cond 5 (`Profiled Flow`)**|`step_limit`|4,329|1,353|116.2s|15 (15)|96,795|54,413|156,890|79.1m|—§|7/8|`REQ-8`|

*§V2 `Cond 5`는 반복적인 출력 토큰 잘림과 대화 압축(`54,413` 코더 출력 토큰)에 빠져 `test_counseling.py`를 생성하기 전에 15스텝 상한에 도달했으며, 최종 `counseling_engine.py`는 `7/8`을 통과했다.*

### 4.2 다중 반복 실행(`n = 3`) 및 정보량 통제 절제 실험 (`Cond 4-Unordered`)

단일 실행의 우연성을 배제하고 순서 효과를 엄밀히 분리하기 위해 대규모 과업(V2)의 4개 핵심 그룹—**Cond 0-Pure**, **Cond 3 Invariant**, **Cond 4-Flow**, 그리고 **Cond 4-Unordered**(`Cond 4-Flow` `r1`의 `design_spec.json`에서 문장과 스키마는 100% 보존하되 `1..6` 단계 번호만 지우고 불릿 순서를 섞어 `create_booking`의 멱등키 검사를 `Step 1`에서 슬롯 확인·상담권 확인·트랜잭션 기록 뒤인 5번째 불릿으로 이동)—에 대해 각각 `n = 3`회 반복 실행(`r1`~`r3`)을 수행했다.

#### 표 3: 대규모 과업(V2) 반복 실행 안정성 및 정보량 통제 비교 (`n = 3` per Group)

|Group (`n = 3` on Large-Scale V2)|Per-Run Verify (`r1, r2, r3`)|Mean Verify|8/8 (`REQ-8`) Pass Rate|Impl Steps|Impl Out Tokens|Total Tokens|Total Time|
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
|**`Cond 0-Pure` (Direct, 0 design tok)**|`7/8, 7/8, 7/8`|`7.00 ± 0.00`|`0/3 (0.0%)`|`10.00 ± 4.58`|`25,775 ± 19,505`|`83,419 ± 49,236`|`40.6 ± 30.7m`|
|**`Cond 3 Invariant` (2-stage)**|`7/8, 1/8, 1/8`|`3.00 ± 3.46`|`0/3 (0.0%)`|`12.33 ± 4.62`|`27,626 ± 7,784`|`122,799 ± 48,024`|`46.4 ± 15.4m`|
|**`Cond 4-Unordered` (Fixed Shuffled)**|`8/8, 7/8, 7/8`|`7.33 ± 0.58`|`1/3 (33.3%)`|`9.33 ± 4.16`|`22,653 ± 10,584`|`88,325 ± 42,688`|`34.4 ± 16.2m`|
|**`Cond 4-Flow` (`Step 1..N`)** ⭐|**`8/8, 7/8, 8/8`**|**`7.67 ± 0.58`**|**`2/3 (66.7%)`**|**`8.67 ± 1.15`**|**`16,560 ± 418`**|**`83,878 ± 3,302`**|**`30.9 ± 3.0m`**|

### 4.3 생성 코드 및 실행 트레이스 기반 5대 근본 원인(Root-Cause) 분석

22개 실행 전체의 `counseling_engine.py` 코드와 스텝별 JSONL 트레이스를 전수 조사한 결과, 표 1~3의 수치 차이를 설명하는 5가지 구체적 메커니즘을 확인했다.

#### 메커니즘 1: 자유 산문 설계에서의 분기 누락 버그 (`Cond 1`, `REQ-5` 및 `REQ-7` 실패)
V2 `Cond 1`에서 `cancel_booking`(전체 188행 중 133~146행)은 대기열 승격과 슬롯 상태 복구를 코더가 자체 정의한 내부 헬퍼 메서드 `_process_waitlist(self, counselor_id, start_time)`(148~168행)에 위임한다. 자유 산문 설계서가 대기열 승격이라는 긍정 경로(positive path) 설명에 치중하고 분기별 사후 조건을 번호로 나열하지 않았기 때문에, 코더는 `while waitlist_entry:` 루프 안에서 승격 시 슬롯을 `'BOOKED'`로 유지하는 쿼리만 작성하고 **승격할 대기자가 없을 때 `slots.status = 'AVAILABLE'`로 되돌리는 폴백(fallback) 쿼리를 누락**했다.
```python
# Large-Scale V2 Cond 1: counseling_engine.py (lines 148-168)
def _process_waitlist(self, counselor_id: str, start_time: str):
    waitlist_entry = self.conn.execute(
        "SELECT * FROM waitlist WHERE counselor_id=? AND start_time=? AND status='WAITING' ORDER BY created_at ASC LIMIT 1",
        (counselor_id, start_time)
    ).fetchone()
    while waitlist_entry:
        ...
        if remaining >= 1:
            ...
            self.conn.execute("UPDATE slots SET status='BOOKED' WHERE counselor_id=? AND start_time=?", (counselor_id, start_time))
            break
        else:
            self.conn.execute("UPDATE waitlist SET status='EXPIRED' WHERE waitlist_id=?", (waitlist_entry["waitlist_id"],))
            waitlist_entry = ...
    # BUG: 승격된 대기자가 없을 때 `UPDATE slots SET status='AVAILABLE'`로 복구하는 폴백 분기 누락
```
그 결과 대기자가 없는 예약이 취소된 후에도 슬롯이 영구히 `'BOOKED'` 상태로 남아 `REQ-5`와 `REQ-7`이 동시 실패했다.

#### 메커니즘 2: 선언적 불변식 조건에서의 코드 생성 중 자기 교정(Mid-Generation Self-Correction) 버그 (`Cond 3`, `r2` & `r3`)
`Cond 3 Invariant`에서 Stage 1은 절차적 순서 대신 선언적 보존 법칙을 제공한다. 1차 실행(`r1`)은 `67,569` 토큰으로 `7/8`을 통과했으나, `r2`와 `r3`는 각각 `146,112` 토큰과 `154,716` 토큰(15스텝)을 소모하며 `1/8`로 붕괴했다. 두 실행 모두에서 코더는 `write_file` 도구 호출 중 `issue_session_pass` 내부에 `INSERT OR REPLACE`를 먼저 출력한 뒤, 생성 도중 `REPLACE`가 기존 잔여 횟수를 덮어쓴다는 사실을 깨닫고 주석(`# Correcting to:`)과 함께 `UPDATE` 문을 바로 아래에 이어 썼다. 자기회귀(autoregressive) 모델은 단일 도구 호출 안에서 이미 출력한 토큰을 지울 수 없기 때문에 두 쿼리가 모두 실행되었다.
```python
# Large-Scale V2 Cond 3 (r2 lines 68-73 of 197; r3 lines 63-69 of 177): Double-Counting Bug
self.conn.execute("INSERT OR REPLACE INTO session_passes (client_email, remaining_sessions, used_sessions) VALUES (?, ?, ?)", 
                 (client_email, sessions_to_add, 0))
# Note: INSERT OR REPLACE is simplified; should be UPDATE if exists.
# Correcting to:
self.conn.execute("UPDATE session_passes SET remaining_sessions = remaining_sessions + ? WHERE client_email = ?", (sessions_to_add, client_email))
```
이로 인해 최초 3회권 발급 시 `remaining_sessions = 3`이 삽입된 직후 `+3`이 추가되어 잔여 횟수가 6회로 부풀려졌고, `REQ-2`부터 `REQ-8`까지 연쇄 실패했다. (단일 `write_file` 호출 중 이미 출력한 라인을 취소하지 못하는 동일한 현상이 V1 `Cond 5`의 `DatabaseManager.__init__`에서도 발생하여, 7행에 `self._initialize_db()`, 8행에 `self._init_db()`를 적고 15행에는 `def _init_db(self):`만 정의하는 결과를 낳았다.) 반면 `Cond 4-Flow`는 `issue_session_pass`를 `Step 1 (pass_ledger 중복 확인) -> Step 2 (유효성 검증) -> Step 3 (원자적 Upsert)`로 사전 기획하여 전 실행에서 `REQ-1`~`REQ-7`을 100% 통과했다.

#### 메커니즘 3: 취소된 예약의 멱등키 재호출 시 조기 조건 결합(Premature Predicate Conjoining, `REQ-8`)
실행 흐름 명세가 주어지지 않은 상태에서 `REQ-8`에 실패한 V2의 9개 실행 전원—`Cond 0-Pure` (`r1` 80행, `r2` 84행, `r3` 84행), `Cond 0-Min` (80행), `Cond 2` (99행), `Cond 3` (`r1` 98행, `r2` 86행, `r3` 79행), `Cond 5` (87행)—에서 코더는 `create_booking` 내부에 토씨까지 동일한 결함 쿼리를 작성했다.
```python
# Cond 0-Pure (r1 L80, r2 L84, r3 L84), Cond 0-Min (L80), Cond 2 (L99), Cond 3 (r1 L98, r2 L86, r3 L79), Cond 5 (L87) 공통 버그
existing = self.conn.execute(
    "SELECT * FROM bookings WHERE idempotency_key = ? AND status = 'CONFIRMED'",
    (idempotency_key,),
).fetchone()
```
조회 조건에 `AND status = 'CONFIRMED'`를 성급하게 결합한 탓에 이미 `'CANCELLED'`로 바뀐 기존 예약을 찾지 못하고 넘어갔으며, 곧바로 `UNIQUE(idempotency_key)` 충돌 크래시나 상담권 이중 차감을 일으켰다.

#### 메커니즘 4: 정보량 통제 절제 실험을 통한 인과 증명 (`Cond 4-Flow` 대 `Cond 4-Unordered`)
`Cond 4-Flow`에서는 `r1`(82행)과 `r3`(82행)가 `8/8` 만점(`REQ-8` 통과)을 기록했다. Stage 1이 `create_booking`의 `Step 1`에 멱등키 검사를 배치하자 Stage 2 코더가 상태 필터 없는 `WHERE idempotency_key = ?` 쿼리를 생성했기 때문이다(`r2` 75행에서는 코더가 `AND status = 'CONFIRMED'`를 덧붙여 `7/8` 기록).

`Cond 4-Flow` `r1`이 `REQ-8`을 통과한 이유가 `Step 1`이라는 위치가 아니라 문구 자체 때문인지 검증하기 위해, `Cond 4-Unordered` (`n = 3`)는 `r1`의 JSON 텍스트(`"If idempotency_key exists in bookings, return existing booking."`)를 100% 그대로 유지하되 `1..6` 단계 번호만 지우고 해당 항목을 `Step 1`에서 `create_booking`의 마지막(5번째) 불릿(슬롯 가용성 검증·상담권 검증·트랜잭션 기록 뒤)으로 이동시켰다.
- **`Cond 4-Unordered`의 3회 중 2회 실행(`r2` 77행 및 `r3` 95행)**에서 코더는 상태 조건이 없는 동일한 문장(`"If idempotency_key exists in bookings, return existing booking."`)을 전달받았음에도 `WHERE idempotency_key = ? AND status = 'CONFIRMED'`를 생성하여 `REQ-8`에 실패했다(`Cond 4-Flow` 통과율 `2/3` 대비 `1/3`).
- 단계 번호를 제거하자 실행 안정성도 무너졌다. `Cond 4-Unordered`의 `r3`는 14스텝과 `136,352` 토큰(코더 출력 `34,778` 토큰)을 소모하며 그룹 총 토큰 표준편차를 `Cond 4-Flow` 대비 12.9배(`± 3,302` → `± 42,688`) 폭증시켰다. 자기회귀 코더는 `def create_booking(...)` 본문을 위에서 아래로 생성하므로, 진입 가드 규칙이 `Step 1`에 놓여야 함수 첫머리를 생성하는 시점의 어텐션 위치와 일치하게 된다.

#### 메커니즘 5: 과잉 프로파일링 프롬프트에서의 출력 잘림 및 대화 압축 루프 (`Cond 5`)
V2 `Cond 5`에서는 행동 수칙과 체크리스트가 추가되면서 Stage 2 코더가 출력 잘림 및 대화 압축 루프에 빠졌다(`15` 스텝, 코더 출력 `54,413` 토큰, 총 `156,890` 토큰). 15스텝 중 7개 스텝에서 `write_file` 호출이 토큰 한계에 도달했는데—Step 2, 5, 6, 7, 10, 12에서는 `max_output_tokens = 4,608` 상한에, Step 15에서는 `12,288` 컨텍스트 상한(입력 `9,610` + 출력 `2,678`)에 걸려—`Invalid tool JSON: Unterminated string` 오류를 반환했다. 이 실패한 대형 출력들이 컨텍스트를 채우면서 Step 5, 10, 12 직후 총 3차례 대화 압축(compaction)이 발동했고, 코더는 `run_tests`를 단 한 번도 호출하지 못한 채 `counseling_engine.py` 전체를 5번(Step 3, 4, 9, 11, 13: `6,194` → `14,639` → `15,471` → `16,616` → `15,189`자) 덮어쓰며 예산을 소진했다.

---

## 5. 고찰 및 결론 (Discussion and Conclusion)

### 5.1 로컬 Gemma 4 코딩 에이전트를 위한 엔지니어링 설계 지침
1. **자유 형식 산문 설계(`Cond 1`)를 배제하라.** 무설계(`Cond 0-Pure`) 대비 토큰을 59%~219% 더 소모할 뿐 아니라 조건 분기 누락 버그(`_process_waitlist`)를 유발한다.
2. **선언적 불변식(`Cond 3`) 대신 번호가 부여된 실행 흐름 명세(`Cond 4-Flow`)를 사용하라.** 코드 생성 중 자기 교정으로 인한 SQL 이중 합산 버그를 막아 대규모 검증 점수를 `3.00 ± 3.46 / 8`에서 `7.67 ± 0.58 / 8`로 끌어올리고 코더 출력 토큰 변동계수를 `CV = 2.5%` (`16,560 ± 418` 토큰)로 억제한다.
3. **진입 가드(entry guard) 조건은 반드시 `Step 1`에 배치하라.** `Cond 4-Unordered` 대조 실험이 보여주듯, 동일한 무조건적 조회 규칙(`"If idempotency_key exists in bookings, return existing booking."`)이라도 실행 순서에서 뒤로 밀려나면 3회 중 2회에서 활성 상태 조건(`AND status = 'CONFIRMED'`)과 잘못 결합된다.
4. **`12k` 컨텍스트 환경에서는 설계 출력을 `1,500`~`2,500` 토큰 이내로 유지하라.** 과도한 행동 수칙 결합(`Cond 5`, `156,890` 토큰)은 `4,608` 출력 토큰 잘림과 대화 압축 루프를 초래한다.

### 5.2 연구의 한계 및 재현성 (Limitations and Reproducibility)
본 연구는 로컬 양자화 하드웨어의 15스텝 예산 아래 단일 파일 SQLite 엔진과 핵심 조건별 `n = 3` 반복 실험을 범위로 한다. 총 22개 실행 디렉터리, `design_spec.json` 명세서, `counseling_engine.py` 구현 코드, JSONL 트레이스 및 표준 검증 스크립트 전체가 결정론적 재현을 위해 보존되어 있다.

### 참고문헌 (References)
1. Gemma Team, Google DeepMind. *Gemma 4 Technical Report.* arXiv:2607.02770 (2026); and *Gemma: Open Models Based on Gemini Research and Technology.* arXiv:2403.08295 (2024).
2. Markowitz, E., Perozzi, B., Rózemberczki, B., Cameron, G., Hemmati, H., Li, Y., Galkin, M., Farhadi, M., Holbrook, R., & Oldacre, A. *Google - The Gemma 4 Developer Agent Paper Track.* Kaggle (2026).
3. Hong, S., et al. *MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework.* ICLR (2024).
4. Pei, K., et al. *Can Large Language Models Reason about Program Invariants?* ICML (2023).
5. Olausson, T. X., et al. *Is Self-Repair a Silver Bullet for Code Generation?* ICLR (2024).
6. Jimenez, C. E., et al. *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?* ICLR (2024).
