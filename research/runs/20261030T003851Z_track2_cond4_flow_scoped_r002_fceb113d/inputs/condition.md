# Condition 4-Flow-Scoped: Functional Execution Flow Blueprint with Method-Scoped Disambiguation

In this condition, the Designer stage specifies data/interface contracts, domain invariants, explicit step-by-step execution flows, and explicit method-scoped disambiguation rules to prevent cross-method invariant bleeding.

## Specific Scope Rule for create_booking:
create_booking에만 적용: idempotency_key로 예약을 조회할 때는 예약 상태를 조건에 넣지 않는다. 같은 키의 예약이 취소 상태여도 기존 예약을 반환하고, 슬롯 확인이나 상담권 차감은 다시 하지 않는다. status == 'CONFIRMED' 검사는 예약 변경·취소 가능 여부를 판단할 때만 적용한다.
(Scope: When querying bookings by idempotency_key in create_booking, do not filter by booking status; return existing booking even if cancelled, without re-checking slot or deducting sessions. Checking status == 'CONFIRMED' applies strictly when determining reschedule or cancellation eligibility.)
