#!/usr/bin/env python3
"""Multi-port live Counseling Booking Service websites («여백 상담실 · 1:1 상담 예약»)
powered by each experimental condition's generated backend (Cond 0 ~ Cond 5).

Port Allocation:
- 8100: Master Comparison Hub (All 12 runs overview + direct website links)
- 8110: Small-Scale V1 Cond 0 (no_design)        — 여백 상담실 웹사이트 (V1)
- 8111: Small-Scale V1 Cond 1 (cond1_generic)    — 여백 상담실 웹사이트 (V1)
- 8112: Small-Scale V1 Cond 2 (cond2_contract)   — 여백 상담실 웹사이트 (V1)
- 8113: Small-Scale V1 Cond 3 (cond3_invariant)  — 여백 상담실 웹사이트 (V1)
- 8114: Small-Scale V1 Cond 4 (cond4_flow)       — 여백 상담실 웹사이트 (V1)
- 8115: Small-Scale V1 Cond 5 (cond5_profiled)   — 여백 상담실 웹사이트 (V1)
- 8120: Large-Scale V2 Cond 0 (no_design)        — 여백 상담실 웹사이트 (V2 통합본)
- 8121: Large-Scale V2 Cond 1 (cond1_generic)    — 여백 상담실 웹사이트 (V2 통합본)
- 8122: Large-Scale V2 Cond 2 (cond2_contract)   — 여백 상담실 웹사이트 (V2 통합본)
- 8123: Large-Scale V2 Cond 3 (cond3_invariant)  — 여백 상담실 웹사이트 (V2 통합본)
- 8124: Large-Scale V2 Cond 4 (cond4_flow)       — 여백 상담실 웹사이트 (V2 통합본)
- 8125: Large-Scale V2 Cond 5 (cond5_profiled)   — 여백 상담실 웹사이트 (V2 통합본)
"""

from __future__ import annotations

import dataclasses
import html
import importlib
import json
import multiprocessing
import os
import sqlite3
import sys
import tempfile
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# Ensure SQLite connections created in __init__ can be safely used across HTTP requests
_ORIG_SQLITE_CONNECT = sqlite3.connect


def _patched_sqlite_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
    kwargs.setdefault("check_same_thread", False)
    return _ORIG_SQLITE_CONNECT(database, *args, **kwargs)


sqlite3.connect = _patched_sqlite_connect  # type: ignore[assignment]

ROOT_DIR = Path(__file__).resolve().parent.parent
PROTOTYPE_CSS_PATH = ROOT_DIR / "prototype" / "counseling-booking" / "static" / "styles.css"
BASE_PROTOTYPE_CSS = PROTOTYPE_CSS_PATH.read_text(encoding="utf-8") if PROTOTYPE_CSS_PATH.exists() else ""

COUNSELOR_CATALOG: list[dict[str, str]] = [
    {
        "counselor_id": "counselor-garam",
        "name": "김가람 상담사",
        "specialty": "커리어 · 직무 스트레스",
        "intro": "업무 과부하, 이직 고민, 번아웃 회복을 구조적으로 정리합니다.",
    },
    {
        "counselor_id": "counselor-haneul",
        "name": "박하늘 상담사",
        "specialty": "관계 · 정서 회복",
        "intro": "대인관계 피로, 불안, 일상 리듬 회복을 차분하게 돕습니다.",
    },
    {
        "counselor_id": "counselor-seoyoon",
        "name": "이서윤 상담사",
        "specialty": "수면 · 번아웃 클리닉",
        "intro": "만성 피로와 수면 리듬 불균형, 정서적 소진을 세심하게 케어합니다.",
    },
]

DEMO_DATES = ["2026-05-11", "2026-05-12", "2026-05-13"]
DEMO_TIMES = ["10:00:00", "11:00:00", "14:00:00", "15:00:00", "16:00:00"]

RUN_CONFIGS: list[dict[str, Any]] = [
    {
        "id": "small_cond0",
        "scale": "small",
        "cond_num": 0,
        "cond_name": "no_design",
        "short_label": "Cond 0 · No Design",
        "title": "여백 상담실 (소규모 V1 · Cond 0 No Design)",
        "port": 8110,
        "run_dir": "research/runs/20261012T111933Z_track2_no_design_r001_d53d733a",
        "module_name": "counseling.service",
        "class_name": "CounselingService",
        "agent_pytest": "10 / 10 (100%)",
        "impl_status": "completed (4 steps, 10.6m)",
        "summary": "설계 단계 없이 즉시 구현. 단순 도메인(테이블 2개)에서는 4스텝 만에 6대 기능 모두 정상 작동.",
    },
    {
        "id": "small_cond1",
        "scale": "small",
        "cond_num": 1,
        "cond_name": "cond1_generic",
        "short_label": "Cond 1 · Generic",
        "title": "여백 상담실 (소규모 V1 · Cond 1 Generic Design)",
        "port": 8111,
        "run_dir": "research/runs/20261013T115013Z_track2_cond1_generic_r001_c96880ae",
        "module_name": "counseling.service",
        "class_name": "CounselingService",
        "agent_pytest": "10 / 12 (83.3%)",
        "impl_status": "step_limit (15 steps, 33.6m)",
        "summary": "자유 형식 마크다운 설계. 웹사이트 5대 기능은 정상 작동하나 매 호출 새 커넥션을 열어 :memory: 모드는 미지원.",
    },
    {
        "id": "small_cond2",
        "scale": "small",
        "cond_num": 2,
        "cond_name": "cond2_contract",
        "short_label": "Cond 2 · Contract",
        "title": "여백 상담실 (소규모 V1 · Cond 2 Contract Design)",
        "port": 8112,
        "run_dir": "research/runs/20261013T122410Z_track2_cond2_contract_r001_38979f94",
        "module_name": "counseling_service",
        "class_name": "CounselingService",
        "agent_pytest": "11 / 11 (100%)",
        "impl_status": "completed (11 steps, 29.7m)",
        "summary": "인터페이스·스키마 계약 설계. Dataclass(Slot, Booking)와 예외 계층으로 6대 요구사항 100% 정상 작동.",
    },
    {
        "id": "small_cond3",
        "scale": "small",
        "cond_num": 3,
        "cond_name": "cond3_invariant",
        "short_label": "Cond 3 · Invariant",
        "title": "여백 상담실 (소규모 V1 · Cond 3 Invariant Design)",
        "port": 8113,
        "run_dir": "research/runs/20261013T125431Z_track2_cond3_invariant_r001_61262488",
        "module_name": "counseling_service",
        "class_name": "CounselingService",
        "agent_pytest": "0 / 11 (테스트 예외명 불일치)",
        "impl_status": "step_limit (15 steps, 38.7m)",
        "summary": "상담 엔진(counseling_service.py) 본체는 :memory: 포함 6대 기능이 웹사이트에서 100% 정상 작동함.",
    },
    {
        "id": "small_cond4",
        "scale": "small",
        "cond_num": 4,
        "cond_name": "cond4_flow",
        "short_label": "Cond 4 · Flow ⭐",
        "title": "여백 상담실 (소규모 V1 · Cond 4 Flow Design ⭐)",
        "port": 8114,
        "run_dir": "research/runs/20261014T164845Z_track2_cond4_flow_r001_3468b58f",
        "module_name": "counseling",
        "class_name": "CounselingService",
        "agent_pytest": "8 / 8 (100%)",
        "impl_status": "completed (7 steps, 10.5m, 33.2k tok)",
        "summary": "기능별 실행 플로우(Step 1~3) 설계. 설계 기반 조건 중 최단 시간(10.5분)·최소 토큰으로 6대 기능 100% 완벽 동작!",
    },
    {
        "id": "small_cond5",
        "scale": "small",
        "cond_num": 5,
        "cond_name": "cond5_profiled",
        "short_label": "Cond 5 · Profiled",
        "title": "여백 상담실 (소규모 V1 · Cond 5 Profiled Design)",
        "port": 8115,
        "run_dir": "research/runs/20261013T133544Z_track2_cond4_profiled_r001_c96ed0f4",
        "module_name": "counseling.service",
        "class_name": "CounselingService",
        "agent_pytest": "0 / 12 (초기화 메서드 오타)",
        "impl_status": "step_limit (15 steps, 44.5m)",
        "summary": "과잉 모듈화 중 DatabaseManager._initialize_db vs _init_db 오타로 인해 원본 코드는 초기화 시 에러 발생 (상단 보정 스위치로 체험 가능).",
    },
    {
        "id": "large_cond0",
        "scale": "large",
        "cond_num": 0,
        "cond_name": "no_design",
        "short_label": "Cond 0 · No Design",
        "title": "여백 상담실 V2 (대규모 · Cond 0 No Design)",
        "port": 8120,
        "run_dir": "research/runs/20261014T120559Z_track2_no_design_r001_ef7cf9fa",
        "module_name": "counseling_engine",
        "class_name": "CounselingBookingEngine",
        "agent_pytest": "8 / 8 (100%)",
        "impl_status": "completed (7 steps, 28.2m, 63.9k tok)",
        "summary": "기본 예약·대기열은 작동하나, 취소된 예약의 멱등키(idempotency_key) 재전송 시 상담권이 이중 차감되는 버그 존재.",
    },
    {
        "id": "large_cond1",
        "scale": "large",
        "cond_num": 1,
        "cond_name": "cond1_generic",
        "short_label": "Cond 1 · Generic",
        "title": "여백 상담실 V2 (대규모 · Cond 1 Generic Design)",
        "port": 8121,
        "run_dir": "research/runs/20261014T123515Z_track2_cond1_generic_r001_50ab54a7",
        "module_name": "counseling_engine",
        "class_name": "CounselingBookingEngine",
        "agent_pytest": "6 / 8 (75.0%)",
        "impl_status": "step_limit (15 steps, 42.1m, 138.2k tok)",
        "summary": "대기열이 없는 예약을 취소할 때 슬롯을 AVAILABLE로 되돌리는 로직을 누락하여, 취소 후에도 슬롯이 '예약 마감'으로 굳어버리는 버그 존재!",
    },
    {
        "id": "large_cond2",
        "scale": "large",
        "cond_num": 2,
        "cond_name": "cond2_contract",
        "short_label": "Cond 2 · Contract",
        "title": "여백 상담실 V2 (대규모 · Cond 2 Contract Design)",
        "port": 8122,
        "run_dir": "research/runs/20261014T132638Z_track2_cond2_contract_r001_8aa82474",
        "module_name": "counseling_engine",
        "class_name": "CounselingBookingEngine",
        "agent_pytest": "8 / 8 (100%)",
        "impl_status": "completed (12 steps, 59.5m, 126.2k tok)",
        "summary": "인터페이스 계약 설계로 슬롯 복원 버그는 해결했으나 59.5분 소요. 취소된 멱등키 재호출 시 UNIQUE IntegrityError 발생.",
    },
    {
        "id": "large_cond3",
        "scale": "large",
        "cond_num": 3,
        "cond_name": "cond3_invariant",
        "short_label": "Cond 3 · Invariant",
        "title": "여백 상담실 V2 (대규모 · Cond 3 Invariant Design)",
        "port": 8123,
        "run_dir": "research/runs/20261014T142644Z_track2_cond3_invariant_r001_41f6db1b",
        "module_name": "counseling_engine",
        "class_name": "CounselingBookingEngine",
        "agent_pytest": "8 / 8 (100%)",
        "impl_status": "completed (7 steps, 31.3m, 67.6k tok)",
        "summary": "상태 전이·불변식 설계로 시간·토큰 47% 절감 및 표준 회계 대사 완비. 단, 취소된 예약의 멱등키 재사용 시 신규 예약 중복 생성.",
    },
    {
        "id": "large_cond4",
        "scale": "large",
        "cond_num": 4,
        "cond_name": "cond4_flow",
        "short_label": "Cond 4 · Flow ⭐",
        "title": "여백 상담실 V2 (대규모 · Cond 4 Flow Design ⭐ 최우수)",
        "port": 8124,
        "run_dir": "research/runs/20261014T145844Z_track2_cond4_flow_r001_a90209d0",
        "module_name": "counseling_engine",
        "class_name": "CounselingBookingEngine",
        "agent_pytest": "8 / 8 (100%)",
        "impl_status": "completed (10 steps, 28.3m, 최소 출력 16.1k tok)",
        "summary": "기능별 실행 플로우(Step 1~N) 설계로 최소 출력 토큰(16.1k)·28.3분 완주 및 취소된 예약 멱등키 재전송 방어까지 8/8 전 항목 완벽 작동!",
    },
    {
        "id": "large_cond5",
        "scale": "large",
        "cond_num": 5,
        "cond_name": "cond5_profiled",
        "short_label": "Cond 5 · Profiled",
        "title": "여백 상담실 V2 (대규모 · Cond 5 Profiled Design)",
        "port": 8125,
        "run_dir": "research/runs/20261014T152831Z_track2_cond5_profiled_r001_1fbf66c8",
        "module_name": "counseling_engine",
        "class_name": "CounselingBookingEngine",
        "agent_pytest": "8 / 8 (표준 테스트 기준 통과)",
        "impl_status": "step_limit (15 steps, 34.4m, 146.5k tok)",
        "summary": "단일 파일 강제 프로파일이 적용된 엔진(counseling_engine.py) 본체가 정상 작동하며 웹사이트 7/8 주요 기능 통과.",
    },
]


def serialize_obj(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, sqlite3.Row):
        return dict(obj)
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return {str(k): serialize_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [serialize_obj(x) for x in obj]
    if hasattr(obj, "__dict__"):
        return {k: serialize_obj(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    return str(obj)


def read_sqlite_tables(db_path: str) -> dict[str, list[dict[str, Any]]]:
    if not db_path or not os.path.exists(db_path):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        tables = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        for t in tables:
            rows = conn.execute(f"SELECT * FROM {t}").fetchall()
            out[t] = [dict(r) for r in rows]
        conn.close()
    except Exception as e:
        out["_error"] = [{"error": str(e)}]
    return out


def load_run_files(cfg: dict[str, Any]) -> dict[str, str]:
    run_path = ROOT_DIR / cfg["run_dir"]
    files: dict[str, str] = {}
    design_spec = run_path / "design" / "design_spec.json"
    if design_spec.exists():
        files["design/design_spec.json"] = design_spec.read_text(encoding="utf-8", errors="replace")
    design_file = run_path / "design" / "design_output.md"
    if design_file.exists():
        files["design/design_output.md"] = design_file.read_text(encoding="utf-8", errors="replace")
    impl_dir = run_path / "implementation"
    if impl_dir.exists():
        for root, _dirs, fnames in os.walk(impl_dir):
            if ".agent" in root or "__pycache__" in root or ".pytest_cache" in root:
                continue
            for fn in sorted(fnames):
                if fn.endswith((".py", ".json", ".md")):
                    p = Path(root) / fn
                    rel = str(p.relative_to(impl_dir))
                    files[rel] = p.read_text(encoding="utf-8", errors="replace")
    return files


def run_small_verification(cls: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if cls is None:
        return [
            {
                "id": f"REQ-{i}",
                "name": title,
                "passed": False,
                "expected": "정상 동작",
                "actual": "엔진 모듈 로드 실패",
            }
            for i, title in enumerate(
                [
                    "상담 슬롯 등록 및 날짜별 가용 슬롯 조회",
                    "예약 생성 및 가용 슬롯 목록에서 즉시 제외",
                    "동일 슬롯 중복 예약(Double Booking) 차단 불변식",
                    "예약 단건 조회 및 이메일 본인 확인 검증",
                    "예약 취소 시 슬롯 가용성 즉시 복구 및 재예약 허용",
                    "SQLite :memory: 인메모리 단일 커넥션 유지",
                ],
                start=1,
            )
        ]

    # Check 1
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            svc = cls(tf.name)
            svc.add_available_slot("COUNSELOR_A", "2026-05-10T10:00:00")
            svc.add_available_slot("COUNSELOR_A", "2026-05-10T14:00:00")
            slots = serialize_obj(svc.query_available_slots("COUNSELOR_A", "2026-05-10"))
            passed = isinstance(slots, list) and len(slots) == 2
            results.append({
                "id": "REQ-1",
                "name": "상담 슬롯 등록 및 날짜별 가용 슬롯 조회",
                "passed": passed,
                "expected": "2개의 가용 슬롯 반환",
                "actual": f"반환된 슬롯 {len(slots) if isinstance(slots, list) else 0}개",
            })
    except Exception as e:
        results.append({
            "id": "REQ-1",
            "name": "상담 슬롯 등록 및 날짜별 가용 슬롯 조회",
            "passed": False,
            "expected": "2개의 가용 슬롯 반환",
            "actual": f"{type(e).__name__}: {e}",
        })

    # Check 2
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            svc = cls(tf.name)
            svc.add_available_slot("COUNSELOR_A", "2026-05-10T10:00:00")
            b = serialize_obj(svc.create_booking("COUNSELOR_A", "2026-05-10T10:00:00", "홍길동", "hong@example.com"))
            bid = b["booking_id"] if isinstance(b, dict) else str(b)
            slots_after = serialize_obj(svc.query_available_slots("COUNSELOR_A", "2026-05-10"))
            passed = bool(bid) and len(slots_after) == 0
            results.append({
                "id": "REQ-2",
                "name": "예약 생성 및 가용 슬롯 목록에서 즉시 제외",
                "passed": passed,
                "expected": "booking_id 발급 & 잔여 가용 슬롯 0개",
                "actual": f"booking_id={bid[:12]}..., 잔여 슬롯={len(slots_after)}개",
            })
    except Exception as e:
        results.append({
            "id": "REQ-2",
            "name": "예약 생성 및 가용 슬롯 목록에서 즉시 제외",
            "passed": False,
            "expected": "booking_id 발급 & 잔여 가용 슬롯 0개",
            "actual": f"{type(e).__name__}: {e}",
        })

    # Check 3
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            svc = cls(tf.name)
            svc.add_available_slot("COUNSELOR_A", "2026-05-10T10:00:00")
            svc.create_booking("COUNSELOR_A", "2026-05-10T10:00:00", "홍길동", "hong@example.com")
            rejected = False
            err_msg = ""
            try:
                svc.create_booking("COUNSELOR_A", "2026-05-10T10:00:00", "김철수", "kim@example.com")
            except Exception as inner_e:
                rejected = True
                err_msg = f"{type(inner_e).__name__}: {inner_e}"
            results.append({
                "id": "REQ-3",
                "name": "동일 슬롯 중복 예약(Double Booking) 차단 불변식",
                "passed": rejected,
                "expected": "중복 예약 시 예외 발생으로 차단",
                "actual": f"차단 성공 ({err_msg})" if rejected else "오류: 중복 예약 허용됨",
            })
    except Exception as e:
        results.append({
            "id": "REQ-3",
            "name": "동일 슬롯 중복 예약(Double Booking) 차단 불변식",
            "passed": False,
            "expected": "중복 예약 시 예외 발생으로 차단",
            "actual": f"{type(e).__name__}: {e}",
        })

    # Check 4
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            svc = cls(tf.name)
            svc.add_available_slot("COUNSELOR_A", "2026-05-10T10:00:00")
            b = serialize_obj(svc.create_booking("COUNSELOR_A", "2026-05-10T10:00:00", "홍길동", "hong@example.com"))
            bid = b["booking_id"] if isinstance(b, dict) else str(b)
            ok_lookup = serialize_obj(svc.lookup_booking(bid, "hong@example.com"))
            wrong_blocked = False
            try:
                res = svc.lookup_booking(bid, "hacker@example.com")
                if res is None:
                    wrong_blocked = True
            except Exception:
                wrong_blocked = True
            passed = (ok_lookup is not None) and wrong_blocked
            results.append({
                "id": "REQ-4",
                "name": "예약 단건 조회 및 이메일 본인 확인 검증",
                "passed": passed,
                "expected": "본인 이메일 조회 성공 & 타인 이메일 조회 차단",
                "actual": f"본인 조회={ok_lookup is not None}, 타인 이메일 차단={wrong_blocked}",
            })
    except Exception as e:
        results.append({
            "id": "REQ-4",
            "name": "예약 단건 조회 및 이메일 본인 확인 검증",
            "passed": False,
            "expected": "본인 이메일 조회 성공 & 타인 이메일 조회 차단",
            "actual": f"{type(e).__name__}: {e}",
        })

    # Check 5
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            svc = cls(tf.name)
            svc.add_available_slot("COUNSELOR_A", "2026-05-10T10:00:00")
            b = serialize_obj(svc.create_booking("COUNSELOR_A", "2026-05-10T10:00:00", "홍길동", "hong@example.com"))
            bid = b["booking_id"] if isinstance(b, dict) else str(b)
            svc.cancel_booking(bid, "hong@example.com")
            slots_restored = serialize_obj(svc.query_available_slots("COUNSELOR_A", "2026-05-10"))
            passed = len(slots_restored) == 1
            results.append({
                "id": "REQ-5",
                "name": "예약 취소 시 슬롯 가용성 즉시 복구 및 재예약 허용",
                "passed": passed,
                "expected": "취소 후 가용 슬롯 1개로 복원",
                "actual": f"취소 후 가용 슬롯={len(slots_restored)}개",
            })
    except Exception as e:
        results.append({
            "id": "REQ-5",
            "name": "예약 취소 시 슬롯 가용성 즉시 복구 및 재예약 허용",
            "passed": False,
            "expected": "취소 후 가용 슬롯 1개로 복원",
            "actual": f"{type(e).__name__}: {e}",
        })

    # Check 6
    try:
        svc = cls(":memory:")
        svc.add_available_slot("COUNSELOR_A", "2026-05-10T10:00:00")
        slots = serialize_obj(svc.query_available_slots("COUNSELOR_A", "2026-05-10"))
        passed = isinstance(slots, list) and len(slots) == 1
        results.append({
            "id": "REQ-6",
            "name": "SQLite :memory: 인메모리 단일 커넥션 유지",
            "passed": passed,
            "expected": ":memory: 모드에서 테이블 및 슬롯 유지",
            "actual": f":memory: 조회 성공 (슬롯 {len(slots)}개)",
        })
    except Exception as e:
        results.append({
            "id": "REQ-6",
            "name": "SQLite :memory: 인메모리 단일 커넥션 유지",
            "passed": False,
            "expected": ":memory: 모드에서 테이블 및 슬롯 유지",
            "actual": f"실패 ({type(e).__name__}: {e})",
        })

    return results


def run_large_verification(cls: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if cls is None:
        return []

    # REQ-1
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            eng = cls(tf.name)
            eng.register_counselor("C-1", "김상담", "불안/스트레스")
            eng.add_slot("C-1", "2026-06-01T10:00:00")
            eng.add_slot("C-1", "2026-06-01T11:00:00")
            eng.block_slot("C-1", "2026-06-01T11:00:00")
            avail = serialize_obj(eng.query_available_slots("C-1", "2026-06-01"))
            eng.issue_session_pass("hong@example.com", 2, "req1-pass")
            blocked_rejected = False
            try:
                eng.create_booking("C-1", "2026-06-01T11:00:00", "홍길동", "hong@example.com", "req1-bk")
            except Exception:
                blocked_rejected = True
            passed = len(avail) == 1 and avail[0]["start_time"] == "2026-06-01T10:00:00" and blocked_rejected
            results.append({
                "id": "REQ-1",
                "name": "상담사 프로필 등록 및 슬롯 수명주기 (AVAILABLE / BLOCKED 차단)",
                "passed": passed,
                "expected": "BLOCKED 제외 가용 슬롯 1개 조회 & BLOCKED 슬롯 예약 차단",
                "actual": f"가용 슬롯={len(avail)}개, BLOCKED 예약 차단={blocked_rejected}",
            })
    except Exception as e:
        results.append({
            "id": "REQ-1",
            "name": "상담사 프로필 등록 및 슬롯 수명주기 (AVAILABLE / BLOCKED 차단)",
            "passed": False,
            "expected": "BLOCKED 제외 가용 슬롯 1개 조회 & BLOCKED 슬롯 예약 차단",
            "actual": f"{type(e).__name__}: {e}",
        })

    # REQ-2
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            eng = cls(tf.name)
            eng.issue_session_pass("hong@example.com", 3, "pass-idem-1")
            eng.issue_session_pass("hong@example.com", 3, "pass-idem-1")
            p_info = serialize_obj(eng.get_session_pass("hong@example.com"))
            passed = p_info["remaining_sessions"] == 3 and p_info["used_sessions"] == 0
            results.append({
                "id": "REQ-2",
                "name": "선불 상담권(Session Pass) 발급 및 중복 Idempotency Key 멱등성 방어",
                "passed": passed,
                "expected": "동일 멱등키 2회 호출 시 1회만 반영 (잔여=3, 사용=0)",
                "actual": f"remaining_sessions={p_info.get('remaining_sessions')}, used_sessions={p_info.get('used_sessions')}",
            })
    except Exception as e:
        results.append({
            "id": "REQ-2",
            "name": "선불 상담권(Session Pass) 발급 및 중복 Idempotency Key 멱등성 방어",
            "passed": False,
            "expected": "동일 멱등키 2회 호출 시 1회만 반영 (잔여=3, 사용=0)",
            "actual": f"{type(e).__name__}: {e}",
        })

    # REQ-3
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            eng = cls(tf.name)
            eng.register_counselor("C-1", "김상담", "우울")
            eng.add_slot("C-1", "2026-06-01T10:00:00")
            eng.issue_session_pass("hong@example.com", 2, "p-1")
            b1 = serialize_obj(eng.create_booking("C-1", "2026-06-01T10:00:00", "홍길동", "hong@example.com", "bk-idem-1"))
            b2 = serialize_obj(eng.create_booking("C-1", "2026-06-01T10:00:00", "홍길동", "hong@example.com", "bk-idem-1"))
            p_after = serialize_obj(eng.get_session_pass("hong@example.com"))
            avail = serialize_obj(eng.query_available_slots("C-1", "2026-06-01"))
            logs = serialize_obj(eng.get_booking_audit_log(b1["booking_id"]))
            ev_types = [l.get("event_type") or l.get("action") for l in logs]
            passed = (
                b1["booking_id"] == b2["booking_id"]
                and p_after["remaining_sessions"] == 1
                and p_after["used_sessions"] == 1
                and len(avail) == 0
                and len(logs) == 1
            )
            results.append({
                "id": "REQ-3",
                "name": "예약 확정 시 상담권 차감(-1), 슬롯 BOOKED 전환 및 감사 로그 기록",
                "passed": passed,
                "expected": "잔여 상담권=1, 사용=1, 가용 슬롯=0, 감사 로그 1건",
                "actual": f"잔여={p_after.get('remaining_sessions')}, 사용={p_after.get('used_sessions')}, 가용슬롯={len(avail)}, 감사로그={ev_types}",
            })
    except Exception as e:
        results.append({
            "id": "REQ-3",
            "name": "예약 확정 시 상담권 차감(-1), 슬롯 BOOKED 전환 및 감사 로그 기록",
            "passed": False,
            "expected": "잔여 상담권=1, 사용=1, 가용 슬롯=0, 감사 로그 1건",
            "actual": f"{type(e).__name__}: {e}",
        })

    # REQ-4
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            eng = cls(tf.name)
            eng.register_counselor("C-1", "김상담", "진로")
            eng.add_slot("C-1", "2026-06-01T10:00:00")
            eng.add_slot("C-1", "2026-06-01T14:00:00")
            eng.issue_session_pass("hong@example.com", 1, "p-1")
            b1 = serialize_obj(eng.create_booking("C-1", "2026-06-01T10:00:00", "홍길동", "hong@example.com", "bk-1"))
            eng.reschedule_booking(b1["booking_id"], "hong@example.com", "C-1", "2026-06-01T14:00:00")
            avail = serialize_obj(eng.query_available_slots("C-1", "2026-06-01"))
            p_after = serialize_obj(eng.get_session_pass("hong@example.com"))
            logs = serialize_obj(eng.get_booking_audit_log(b1["booking_id"]))
            ev_types = [l.get("event_type") or l.get("action") for l in logs]
            passed = (
                len(avail) == 1
                and avail[0]["start_time"] == "2026-06-01T10:00:00"
                and p_after["remaining_sessions"] == 0
                and p_after["used_sessions"] == 1
                and len(logs) == 2
            )
            results.append({
                "id": "REQ-4",
                "name": "예약 일정 변경(Reschedule) 시 슬롯 맞교환·상담권 보존·감사 로그 기록",
                "passed": passed,
                "expected": "10:00 슬롯 AVAILABLE 복귀, 14:00 BOOKED, 잔여상담권=0(사용=1), 로그 2건",
                "actual": f"가용슬롯={[s.get('start_time') for s in avail]}, 잔여상담권={p_after.get('remaining_sessions')}, 로그={ev_types}",
            })
    except Exception as e:
        results.append({
            "id": "REQ-4",
            "name": "예약 일정 변경(Reschedule) 시 슬롯 맞교환·상담권 보존·감사 로그 기록",
            "passed": False,
            "expected": "10:00 슬롯 AVAILABLE 복귀, 14:00 BOOKED, 잔여상담권=0(사용=1), 로그 2건",
            "actual": f"{type(e).__name__}: {e}",
        })

    # REQ-5
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            eng = cls(tf.name)
            eng.register_counselor("C-1", "김상담", "대인관계")
            eng.add_slot("C-1", "2026-06-01T10:00:00")
            eng.issue_session_pass("hong@example.com", 1, "p-1")
            b1 = serialize_obj(eng.create_booking("C-1", "2026-06-01T10:00:00", "홍길동", "hong@example.com", "bk-1"))
            eng.cancel_booking(b1["booking_id"], "hong@example.com")
            avail = serialize_obj(eng.query_available_slots("C-1", "2026-06-01"))
            p_after = serialize_obj(eng.get_session_pass("hong@example.com"))
            passed = len(avail) == 1 and p_after["remaining_sessions"] == 1 and p_after["used_sessions"] == 0
            results.append({
                "id": "REQ-5",
                "name": "예약 취소 시 슬롯 가용성(AVAILABLE) 복원 및 상담권(+1) 복구 (대기열 없을 때)",
                "passed": passed,
                "expected": "취소 후 가용 슬롯 1개(AVAILABLE) 복원 & 잔여 상담권 1회 복구",
                "actual": f"취소 후 가용 슬롯={len(avail)}개, 잔여 상담권={p_after.get('remaining_sessions')}회"
                + (" (🚨 슬롯 상태 AVAILABLE 미복원 버그!)" if len(avail) == 0 else ""),
            })
    except Exception as e:
        results.append({
            "id": "REQ-5",
            "name": "예약 취소 시 슬롯 가용성(AVAILABLE) 복원 및 상담권(+1) 복구 (대기열 없을 때)",
            "passed": False,
            "expected": "취소 후 가용 슬롯 1개(AVAILABLE) 복원 & 잔여 상담권 1회 복구",
            "actual": f"{type(e).__name__}: {e}",
        })

    # REQ-6
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            eng = cls(tf.name)
            eng.register_counselor("C-1", "김상담", "불안")
            eng.add_slot("C-1", "2026-06-01T10:00:00")
            eng.issue_session_pass("hong@example.com", 1, "p-hong")
            eng.issue_session_pass("wait1@example.com", 1, "p-w1")
            eng.issue_session_pass("wait2@example.com", 1, "p-w2")
            b1 = serialize_obj(eng.create_booking("C-1", "2026-06-01T10:00:00", "홍길동", "hong@example.com", "bk-hong"))
            eng.join_waitlist("C-1", "2026-06-01T10:00:00", "대기자1", "wait1@example.com")
            eng.join_waitlist("C-1", "2026-06-01T10:00:00", "대기자2", "wait2@example.com")
            eng.cancel_booking(b1["booking_id"], "hong@example.com")
            p_hong = serialize_obj(eng.get_session_pass("hong@example.com"))
            p_w1 = serialize_obj(eng.get_session_pass("wait1@example.com"))
            p_w2 = serialize_obj(eng.get_session_pass("wait2@example.com"))
            avail = serialize_obj(eng.query_available_slots("C-1", "2026-06-01"))
            passed = (
                p_hong["remaining_sessions"] == 1
                and p_w1["remaining_sessions"] == 0
                and p_w2["remaining_sessions"] == 1
                and len(avail) == 0
            )
            results.append({
                "id": "REQ-6",
                "name": "만석 슬롯 대기열(Waitlist) 선착순(FIFO) 자동 승격 및 상담권 자동 차감",
                "passed": passed,
                "expected": "취소 시 1순위(wait1) 자동 예약 승격(잔여 0), 2순위 대기 유지(잔여 1)",
                "actual": f"홍길동 잔여={p_hong.get('remaining_sessions')}, 1순위 잔여={p_w1.get('remaining_sessions')}, 2순위 잔여={p_w2.get('remaining_sessions')}",
            })
    except Exception as e:
        results.append({
            "id": "REQ-6",
            "name": "만석 슬롯 대기열(Waitlist) 선착순(FIFO) 자동 승격 및 상담권 자동 차감",
            "passed": False,
            "expected": "취소 시 1순위(wait1) 자동 예약 승격(잔여 0), 2순위 대기 유지(잔여 1)",
            "actual": f"{type(e).__name__}: {e}",
        })

    # REQ-7
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            eng = cls(tf.name)
            eng.register_counselor("C-1", "김상담", "불안")
            eng.add_slot("C-1", "2026-06-01T10:00:00")
            eng.add_slot("C-1", "2026-06-01T11:00:00")
            eng.add_slot("C-1", "2026-06-01T14:00:00")
            eng.block_slot("C-1", "2026-06-01T14:00:00")
            eng.issue_session_pass("a@example.com", 3, "pa")
            eng.issue_session_pass("b@example.com", 2, "pb")
            eng.create_booking("C-1", "2026-06-01T10:00:00", "고객A", "a@example.com", "bka")
            b_b = serialize_obj(eng.create_booking("C-1", "2026-06-01T11:00:00", "고객B", "b@example.com", "bkb"))
            eng.cancel_booking(b_b["booking_id"], "b@example.com")
            rec = serialize_obj(eng.get_system_reconciliation())
            expected_keys = {
                "total_issued_sessions",
                "total_remaining_sessions",
                "total_used_sessions",
                "active_confirmed_bookings",
                "booked_slots_count",
                "is_balanced",
            }
            has_std_keys = expected_keys.issubset(set(rec.keys()))
            is_bal = rec.get("is_balanced") is True
            passed = (
                has_std_keys
                and is_bal
                and rec.get("total_issued_sessions") == 5
                and rec.get("total_remaining_sessions") == 4
                and rec.get("total_used_sessions") == 1
                and rec.get("active_confirmed_bookings") == 1
                and rec.get("booked_slots_count") == 1
            )
            results.append({
                "id": "REQ-7",
                "name": "전역 회계·슬롯 정합성 대사(get_system_reconciliation) 표준 스키마 & 불변식",
                "passed": passed,
                "expected": "is_balanced=True & 6대 표준 키 일치",
                "actual": json.dumps(rec, ensure_ascii=False),
            })
    except Exception as e:
        results.append({
            "id": "REQ-7",
            "name": "전역 회계·슬롯 정합성 대사(get_system_reconciliation) 표준 스키마 & 불변식",
            "passed": False,
            "expected": "is_balanced=True & 6대 표준 키 일치",
            "actual": f"{type(e).__name__}: {e}",
        })

    # REQ-8
    try:
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            eng = cls(tf.name)
            eng.register_counselor("C-1", "김상담", "스트레스")
            eng.add_slot("C-1", "2026-06-01T10:00:00")
            eng.issue_session_pass("hong@example.com", 2, "p-replay")
            b1 = serialize_obj(eng.create_booking("C-1", "2026-06-01T10:00:00", "홍길동", "hong@example.com", "replay-key-1"))
            eng.cancel_booking(b1["booking_id"], "hong@example.com")
            b_replay = serialize_obj(eng.create_booking("C-1", "2026-06-01T10:00:00", "홍길동", "hong@example.com", "replay-key-1"))
            p_after = serialize_obj(eng.get_session_pass("hong@example.com"))
            passed = (
                b_replay["booking_id"] == b1["booking_id"]
                and p_after["remaining_sessions"] == 2
            )
            results.append({
                "id": "REQ-8",
                "name": "취소된 예약의 Idempotency Key 재전송 시 이중 예약·상담권 재차감 방어 (Flow 설계 핵심 차이)",
                "passed": passed,
                "expected": "기존 취소된 예약(동일 booking_id) 그대로 반환 & 상담권 잔여=2 유지",
                "actual": f"동일 booking_id={b_replay.get('booking_id') == b1.get('booking_id')}, 상태={b_replay.get('status')}, 잔여상담권={p_after.get('remaining_sessions')}회",
            })
    except Exception as e:
        results.append({
            "id": "REQ-8",
            "name": "취소된 예약의 Idempotency Key 재전송 시 이중 예약·상담권 재차감 방어 (Flow 설계 핵심 차이)",
            "passed": False,
            "expected": "기존 취소된 예약(동일 booking_id) 그대로 반환 & 상담권 잔여=2 유지",
            "actual": f"🚨 예외 크래시 발생 ({type(e).__name__}: {e})",
        })

    return results


class ConditionWebsiteBackend:
    """Adapts each condition's generated CounselingService (V1) or CounselingBookingEngine (V2)
    to power the live «여백 상담실 · 1:1 상담 예약» website UI.
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.db_file = tempfile.NamedTemporaryFile(prefix=f"yeobaek_{cfg['id']}_", suffix=".db", delete=False)
        self.db_path = self.db_file.name
        self.db_file.close()
        self.patch_typo = False
        self.cls = self._load_class()
        self.instance: Any = None
        self.init_error: str | None = None
        self.verifications = (
            run_large_verification(self.cls) if cfg["scale"] == "large" else run_small_verification(self.cls)
        )
        self.files = load_run_files(cfg)
        self.reset_and_seed()

    def _load_class(self) -> Any:
        if not self.cfg["module_name"]:
            return None
        impl_dir = str((ROOT_DIR / self.cfg["run_dir"] / "implementation").resolve())
        if not os.path.exists(impl_dir):
            self.init_error = "implementation 디렉터리가 없습니다."
            return None
        if impl_dir not in sys.path:
            sys.path.insert(0, impl_dir)
        try:
            mod = importlib.import_module(self.cfg["module_name"])
            return getattr(mod, self.cfg["class_name"])
        except Exception:
            self.init_error = traceback.format_exc()
            return None

    def toggle_typo_patch(self, enable: bool) -> dict[str, Any]:
        self.patch_typo = enable
        if self.cfg["id"] == "small_cond5":
            try:
                db_mod = importlib.import_module("counseling.database")
                db_cls = getattr(db_mod, "DatabaseManager", None)
                if db_cls is not None:
                    if enable and hasattr(db_cls, "_init_db"):
                        setattr(db_cls, "_initialize_db", getattr(db_cls, "_init_db"))
                    elif not enable and hasattr(db_cls, "_initialize_db"):
                        delattr(db_cls, "_initialize_db")
            except Exception:
                pass
        return self.reset_and_seed()

    def reset_and_seed(self) -> dict[str, Any]:
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass
        if self.cls is None:
            return {"ok": False, "error": self.init_error or "엔진 클래스를 불러올 수 없습니다."}
        try:
            self.instance = self.cls(self.db_path)
            self.init_error = None
        except Exception as e:
            self.instance = None
            self.init_error = f"{type(e).__name__}: {e}"
            return {"ok": False, "error": self.init_error}

        try:
            if self.cfg["scale"] == "large":
                for c in COUNSELOR_CATALOG:
                    self.instance.register_counselor(c["counselor_id"], c["name"], c["specialty"])
                for c in COUNSELOR_CATALOG[:2]:
                    for d in DEMO_DATES:
                        for t in DEMO_TIMES:
                            self.instance.add_slot(c["counselor_id"], f"{d}T{t}")
                for t in ["10:00:00", "14:00:00", "16:00:00"]:
                    self.instance.add_slot("counselor-seoyoon", f"2026-05-11T{t}")

                # Issue initial prepaid session passes
                self.instance.issue_session_pass("minji@example.com", 3, "seed-pass-minji")
                self.instance.issue_session_pass("junho@example.com", 2, "seed-pass-junho")
                self.instance.issue_session_pass("soyul@example.com", 2, "seed-pass-soyul")

                # Seed 1: 김민지 books 11:00 (with 박소율 waiting in FIFO waitlist on 11:00)
                self.instance.create_booking(
                    "counselor-garam",
                    "2026-05-11T11:00:00",
                    "김민지",
                    "minji@example.com",
                    "seed-bk-minji-1100",
                )
                self.instance.join_waitlist(
                    "counselor-garam",
                    "2026-05-11T11:00:00",
                    "박소율",
                    "soyul@example.com",
                )
                # Seed 2: 이준호 books 15:00 (NO waitlist on 15:00 -> cancelling this tests empty-waitlist slot restoration!)
                self.instance.create_booking(
                    "counselor-garam",
                    "2026-05-11T15:00:00",
                    "이준호",
                    "junho@example.com",
                    "seed-bk-junho-1500",
                )
            else:
                for c in COUNSELOR_CATALOG[:2]:
                    for d in DEMO_DATES:
                        for t in DEMO_TIMES:
                            self.instance.add_available_slot(c["counselor_id"], f"{d}T{t}")
                # Seed 1 sample booking on 2026-05-11T11:00:00
                self.instance.create_booking(
                    "counselor-garam",
                    "2026-05-11T11:00:00",
                    "김민지",
                    "minji@example.com",
                )
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"초기 데이터 세팅 오류 ({type(e).__name__}): {e}"}

    def get_counselors(self) -> list[dict[str, str]]:
        if self.cfg["scale"] == "large":
            tables = read_sqlite_tables(self.db_path)
            db_counselors = tables.get("counselors", [])
            if db_counselors:
                intro_map = {c["counselor_id"]: c["intro"] for c in COUNSELOR_CATALOG}
                out = []
                for row in db_counselors:
                    cid = str(row.get("counselor_id") or row.get("id"))
                    out.append({
                        "counselor_id": cid,
                        "name": str(row.get("name", cid)),
                        "specialty": str(row.get("specialty", "심리 상담")),
                        "intro": intro_map.get(cid, "1:1 맞춤형 개인 심리 및 라이프 상담을 진행합니다."),
                    })
                return out
            return COUNSELOR_CATALOG
        return COUNSELOR_CATALOG[:2]

    def get_slots_for_date(self, counselor_id: str, date_str: str) -> dict[str, Any]:
        if self.instance is None:
            return {"ok": False, "error": self.init_error or "엔진 미초기화", "slots": []}
        try:
            avail_raw = serialize_obj(self.instance.query_available_slots(counselor_id, date_str))
            avail_times = set()
            if isinstance(avail_raw, list):
                for item in avail_raw:
                    if isinstance(item, dict) and item.get("start_time"):
                        avail_times.add(str(item["start_time"]))
                    elif isinstance(item, str):
                        avail_times.add(item)

            tables = read_sqlite_tables(self.db_path)
            all_db_slots = tables.get("slots", [])
            waitlist_rows = tables.get("waitlist", []) or tables.get("waitlists", []) or tables.get("waitlist_entries", [])

            # Count active waitlist entries per slot
            waitlist_count_by_time: dict[str, int] = {}
            slot_id_to_time: dict[Any, str] = {}
            for s in all_db_slots:
                sid = s.get("slot_id") or s.get("id")
                st = str(s.get("start_time", ""))
                if sid is not None:
                    slot_id_to_time[sid] = st

            for w in waitlist_rows:
                w_status = str(w.get("status", "WAITING")).upper()
                if w_status not in ("WAITING", "PENDING", "ACTIVE", ""):
                    continue
                w_time = str(w.get("start_time") or slot_id_to_time.get(w.get("slot_id"), ""))
                w_cid = str(w.get("counselor_id") or counselor_id)
                if w_cid == counselor_id and w_time.startswith(date_str):
                    waitlist_count_by_time[w_time] = waitlist_count_by_time.get(w_time, 0) + 1

            slots_for_day: list[dict[str, Any]] = []
            seen_times: set[str] = set()
            for s in all_db_slots:
                if str(s.get("counselor_id")) == counselor_id and str(s.get("start_time", "")).startswith(date_str):
                    st = str(s["start_time"])
                    seen_times.add(st)
                    raw_status = str(s.get("status", "")).upper()
                    is_avail = st in avail_times
                    if is_avail:
                        ui_status = "AVAILABLE"
                    elif raw_status == "BLOCKED":
                        ui_status = "BLOCKED"
                    else:
                        ui_status = "BOOKED"
                    slots_for_day.append({
                        "counselor_id": counselor_id,
                        "start_time": st,
                        "time_label": st[11:16] if len(st) >= 16 else st,
                        "status": ui_status,
                        "raw_db_status": raw_status or ("BOOKED" if s.get("is_booked") else "AVAILABLE"),
                        "waitlist_count": waitlist_count_by_time.get(st, 0),
                    })

            # Fallback if table wasn't named 'slots'
            for st in sorted(avail_times):
                if st not in seen_times and st.startswith(date_str):
                    slots_for_day.append({
                        "counselor_id": counselor_id,
                        "start_time": st,
                        "time_label": st[11:16] if len(st) >= 16 else st,
                        "status": "AVAILABLE",
                        "raw_db_status": "AVAILABLE",
                        "waitlist_count": 0,
                    })

            slots_for_day.sort(key=lambda x: x["start_time"])
            return {"ok": True, "slots": slots_for_day, "available_count": len(avail_times)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "slots": []}

    def enrich_booking(self, b: dict[str, Any]) -> dict[str, Any]:
        out = dict(b)
        tables = read_sqlite_tables(self.db_path)
        slots = tables.get("slots", [])
        if (not out.get("start_time") or not out.get("counselor_id")) and out.get("slot_id") is not None:
            for s in slots:
                sid = s.get("slot_id") if "slot_id" in s else s.get("id")
                if str(sid) == str(out.get("slot_id")):
                    out.setdefault("counselor_id", s.get("counselor_id"))
                    out.setdefault("start_time", s.get("start_time"))
                    break
        cid = str(out.get("counselor_id", ""))
        cname = next((c["name"] for c in self.get_counselors() if c["counselor_id"] == cid), cid)
        out["counselor_name"] = cname
        st = str(out.get("start_time", ""))
        out["date"] = st[:10] if len(st) >= 10 else ""
        out["time_label"] = st[11:16] if len(st) >= 16 else st
        return out

    def get_recent_bookings(self) -> list[dict[str, Any]]:
        tables = read_sqlite_tables(self.db_path)
        bookings = tables.get("bookings", [])
        enriched = [self.enrich_booking(b) for b in bookings]
        enriched.reverse()
        return enriched

    def get_all_passes(self) -> list[dict[str, Any]]:
        tables = read_sqlite_tables(self.db_path)
        for tname in ("session_passes", "passes", "client_passes"):
            if tname in tables:
                return tables[tname]
        return []

    def get_waitlist_rows(self) -> list[dict[str, Any]]:
        tables = read_sqlite_tables(self.db_path)
        for tname in ("waitlist", "waitlists", "waitlist_entries"):
            if tname in tables:
                return tables[tname]
        return []

    def get_reconciliation(self) -> dict[str, Any] | None:
        if self.cfg["scale"] != "large" or self.instance is None:
            return None
        try:
            return serialize_obj(self.instance.get_system_reconciliation())
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}", "is_balanced": False}

    def get_full_state(self, counselor_id: str, date_str: str, client_email: str = "") -> dict[str, Any]:
        slot_data = self.get_slots_for_date(counselor_id, date_str)
        pass_info = None
        if self.cfg["scale"] == "large" and self.instance is not None and client_email:
            try:
                pass_info = serialize_obj(self.instance.get_session_pass(client_email))
            except Exception:
                pass_info = {"client_email": client_email, "remaining_sessions": 0, "used_sessions": 0}
        return {
            "ok": self.instance is not None,
            "init_error": self.init_error,
            "patch_typo": self.patch_typo,
            "scale": self.cfg["scale"],
            "counselors": self.get_counselors(),
            "slots": slot_data.get("slots", []),
            "available_count": slot_data.get("available_count", 0),
            "recent_bookings": self.get_recent_bookings(),
            "passes": self.get_all_passes(),
            "client_pass": pass_info,
            "waitlist": self.get_waitlist_rows(),
            "reconciliation": self.get_reconciliation(),
            "tables": read_sqlite_tables(self.db_path),
        }

    def handle_api_post(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if path == "/api/reset":
            res = self.reset_and_seed()
            return (200 if res.get("ok") else 400), {
                **res,
                "message": "초기 상담 일정 및 샘플 예약 데이터로 초기화되었습니다.",
            }

        if path == "/api/toggle-patch":
            enable = bool(payload.get("enable", True))
            res = self.toggle_typo_patch(enable)
            msg = (
                "DatabaseManager._initialize_db = _init_db 1줄 보정이 적용되어 웹사이트가 활성화되었습니다."
                if enable
                else "원본 코드 상태(보정 해제)로 전환되었습니다."
            )
            return 200, {**res, "message": msg, "patch_typo": self.patch_typo}

        if self.instance is None:
            return 500, {"ok": False, "error": f"엔진 초기화 실패 상태입니다: {self.init_error}"}

        try:
            if path == "/api/bookings":
                cid = str(payload.get("counselor_id", "")).strip()
                st = str(payload.get("start_time", "")).strip()
                name = str(payload.get("client_name", "")).strip()
                email = str(payload.get("client_email", "")).strip()
                if not cid or not st or not name or not email:
                    return 400, {"ok": False, "error": "상담사, 상담 시간, 이름, 이메일을 모두 입력해 주세요."}

                if self.cfg["scale"] == "large":
                    idem_key = str(payload.get("idempotency_key", "")).strip() or f"web-bk-{int(time.time()*1000)}"
                    res = serialize_obj(self.instance.create_booking(cid, st, name, email, idem_key))
                    bk = self.enrich_booking(res if isinstance(res, dict) else {"booking_id": str(res)})
                    pass_after = serialize_obj(self.instance.get_session_pass(email))
                    return 201, {
                        "ok": True,
                        "booking": bk,
                        "client_pass": pass_after,
                        "message": f"상담 예약이 확정되었습니다. (잔여 상담권: {pass_after.get('remaining_sessions')}회)",
                    }
                else:
                    res = serialize_obj(self.instance.create_booking(cid, st, name, email))
                    bid = res["booking_id"] if isinstance(res, dict) else str(res)
                    looked_up = serialize_obj(self.instance.lookup_booking(bid, email))
                    bk = self.enrich_booking(
                        looked_up
                        if isinstance(looked_up, dict)
                        else {"booking_id": bid, "counselor_id": cid, "start_time": st, "client_name": name, "client_email": email, "status": "CONFIRMED"}
                    )
                    return 201, {
                        "ok": True,
                        "booking": bk,
                        "message": "상담 예약이 완료되었습니다.",
                    }

            if path == "/api/bookings/lookup":
                bid = str(payload.get("booking_id", "")).strip()
                email = str(payload.get("client_email", "")).strip()
                if not bid or not email:
                    return 400, {"ok": False, "error": "예약 번호와 이메일을 모두 입력해 주세요."}
                res = serialize_obj(self.instance.lookup_booking(bid, email))
                if not res:
                    return 404, {"ok": False, "error": "일치하는 예약 정보를 찾을 수 없거나 이메일이 일치하지 않습니다."}
                bk = self.enrich_booking(res)
                audit_logs = []
                if self.cfg["scale"] == "large":
                    try:
                        audit_logs = serialize_obj(self.instance.get_booking_audit_log(bid))
                    except Exception:
                        audit_logs = []
                return 200, {
                    "ok": True,
                    "booking": bk,
                    "audit_logs": audit_logs,
                    "message": "예약 정보를 확인했습니다.",
                }

            if path == "/api/bookings/cancel":
                bid = str(payload.get("booking_id", "")).strip()
                email = str(payload.get("client_email", "")).strip()
                if not bid or not email:
                    return 400, {"ok": False, "error": "예약 번호와 이메일을 모두 입력해 주세요."}
                res = serialize_obj(self.instance.cancel_booking(bid, email))
                # Fetch updated booking record from DB or lookup
                tables = read_sqlite_tables(self.db_path)
                db_bk = next(
                    (b for b in tables.get("bookings", []) if str(b.get("booking_id") or b.get("id")) == bid),
                    None,
                )
                bk = self.enrich_booking(
                    db_bk
                    if db_bk
                    else (res if isinstance(res, dict) else {"booking_id": bid, "client_email": email, "status": "CANCELLED"})
                )
                audit_logs = []
                rec = None
                extra_notice = ""
                if self.cfg["scale"] == "large":
                    try:
                        audit_logs = serialize_obj(self.instance.get_booking_audit_log(bid))
                    except Exception:
                        audit_logs = []
                    rec = self.get_reconciliation()
                    if rec and not rec.get("is_balanced", True):
                        extra_notice = " 🚨 [주의: 이 조건(Cond 1)의 엔진은 대기열이 없을 때 취소된 슬롯을 AVAILABLE로 복원하지 않아 슬롯이 여전히 '예약 마감(BOOKED)'으로 남고 회계 대사(is_balanced=False)가 깨졌습니다!]"
                return 200, {
                    "ok": True,
                    "booking": bk,
                    "audit_logs": audit_logs,
                    "reconciliation": rec,
                    "message": "예약이 취소되었습니다." + extra_notice,
                }

            if path == "/api/bookings/reschedule":
                bid = str(payload.get("booking_id", "")).strip()
                email = str(payload.get("client_email", "")).strip()
                new_cid = str(payload.get("new_counselor_id", "")).strip()
                new_st = str(payload.get("new_start_time", "")).strip()
                if not bid or not email or not new_cid or not new_st:
                    return 400, {"ok": False, "error": "변경할 상담사와 새로운 시간을 선택해 주세요."}
                res = serialize_obj(self.instance.reschedule_booking(bid, email, new_cid, new_st))
                bk = self.enrich_booking(res if isinstance(res, dict) else {"booking_id": bid})
                audit_logs = serialize_obj(self.instance.get_booking_audit_log(bid))
                return 200, {
                    "ok": True,
                    "booking": bk,
                    "audit_logs": audit_logs,
                    "message": f"예약 일정이 {bk.get('date')} {bk.get('time_label')}으로 변경되었습니다. (추가 상담권 차감 없음)",
                }

            if path == "/api/bookings/replay-cancelled":
                bid = str(payload.get("booking_id", "")).strip()
                tables = read_sqlite_tables(self.db_path)
                db_bk = next(
                    (b for b in tables.get("bookings", []) if str(b.get("booking_id") or b.get("id")) == bid),
                    None,
                )
                if not db_bk:
                    return 404, {"ok": False, "error": "원본 예약을 찾을 수 없습니다."}
                bk_info = self.enrich_booking(db_bk)
                idem_key = str(db_bk.get("idempotency_key", ""))
                email = str(db_bk.get("client_email", ""))
                name = str(db_bk.get("client_name", "고객"))
                cid = str(bk_info.get("counselor_id", "counselor-garam"))
                st = str(bk_info.get("start_time", ""))
                pass_before = serialize_obj(self.instance.get_session_pass(email))
                replayed = serialize_obj(self.instance.create_booking(cid, st, name, email, idem_key))
                pass_after = serialize_obj(self.instance.get_session_pass(email))
                same_id = str(replayed.get("booking_id")) == bid
                no_extra_deduct = pass_before.get("remaining_sessions") == pass_after.get("remaining_sessions")
                passed_guard = same_id and no_extra_deduct
                msg = (
                    f"✅ [멱등성 방어 성공!] 취소된 예약의 멱등키({idem_key})로 재요청했으나 신규 예약을 중복 생성하지 않고 기존 취소 레코드({bid[:8]}...)를 그대로 반환했습니다. (상담권 잔여 {pass_after.get('remaining_sessions')}회 보존)"
                    if passed_guard
                    else f"🚨 [멱등성 방어 실패!] 취소된 예약의 멱등키({idem_key})를 무시하고 새 예약({str(replayed.get('booking_id'))[:8]}...)을 중복 생성하여 상담권이 또 차감되었습니다! (잔여 {pass_before.get('remaining_sessions')}회 → {pass_after.get('remaining_sessions')}회)"
                )
                return 200, {
                    "ok": passed_guard,
                    "booking": self.enrich_booking(replayed),
                    "message": msg,
                }

            if path == "/api/waitlist":
                cid = str(payload.get("counselor_id", "")).strip()
                st = str(payload.get("start_time", "")).strip()
                name = str(payload.get("client_name", "")).strip()
                email = str(payload.get("client_email", "")).strip()
                if not cid or not st or not name or not email:
                    return 400, {"ok": False, "error": "대기열 신청을 위해 이름과 이메일을 모두 입력해 주세요."}
                res = serialize_obj(self.instance.join_waitlist(cid, st, name, email))
                return 201, {
                    "ok": True,
                    "waitlist_entry": res,
                    "message": f"{st[:10]} {st[11:16]} 만석 슬롯 대기열에 등록되었습니다. 기존 예약 취소 시 선착순(FIFO)으로 자동 승격됩니다.",
                }

            if path == "/api/passes/issue":
                email = str(payload.get("client_email", "")).strip()
                cnt = int(payload.get("sessions_to_add", 1))
                idem_key = str(payload.get("idempotency_key", "")).strip() or f"pass-{int(time.time()*1000)}"
                if not email or cnt <= 0:
                    return 400, {"ok": False, "error": "고객 이메일과 충전할 상담권 횟수(1 이상)를 입력해 주세요."}
                self.instance.issue_session_pass(email, cnt, idem_key)
                p_info = serialize_obj(self.instance.get_session_pass(email))
                return 200, {
                    "ok": True,
                    "client_pass": p_info,
                    "message": f"{email} 고객님의 상담권 지갑 조회/충전 완료 (현재 잔여: {p_info.get('remaining_sessions')}회, 누적 사용: {p_info.get('used_sessions')}회, 멱등키: {idem_key})",
                }

            if path == "/api/slots/add":
                cid = str(payload.get("counselor_id", "")).strip()
                st = str(payload.get("start_time", "")).strip()
                if len(st) == 16:
                    st = st + ":00"
                if self.cfg["scale"] == "large":
                    res = serialize_obj(self.instance.add_slot(cid, st))
                else:
                    res = serialize_obj(self.instance.add_available_slot(cid, st))
                return 201, {
                    "ok": True,
                    "slot": res,
                    "message": f"새로운 상담 가능 슬롯({st[:10]} {st[11:16]})이 개설되었습니다.",
                }

            if path == "/api/slots/block":
                cid = str(payload.get("counselor_id", "")).strip()
                st = str(payload.get("start_time", "")).strip()
                res = serialize_obj(self.instance.block_slot(cid, st))
                return 200, {
                    "ok": True,
                    "slot": res,
                    "message": f"슬롯({st[:10]} {st[11:16]})이 상담사 일정 마감(BLOCKED) 처리되었습니다.",
                }

            if path == "/api/counselors/register":
                cid = str(payload.get("counselor_id", "")).strip()
                name = str(payload.get("name", "")).strip()
                spec = str(payload.get("specialty", "")).strip()
                res = serialize_obj(self.instance.register_counselor(cid, name, spec))
                return 201, {
                    "ok": True,
                    "counselor": res,
                    "message": f"신규 상담사({name} · {spec})가 등록되었습니다.",
                }

            return 404, {"ok": False, "error": f"지원하지 않는 요청 경로입니다: {path}"}
        except Exception as e:
            return 400, {"ok": False, "error": f"{type(e).__name__}: {e}"}


WEBSITE_EXTRA_CSS = """
.cond-ribbon {
  background: #173d3a;
  color: #f5f7f3;
  padding: 8px 18px;
  font-size: 0.82rem;
  border-bottom: 1px solid rgba(255,255,255,0.14);
}
.cond-ribbon-inner {
  width: min(1140px, calc(100% - 32px));
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.cond-links {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.cond-pill {
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(255,255,255,0.1);
  color: #e2ece9;
  text-decoration: none;
  font-weight: 600;
  font-size: 0.76rem;
  transition: background 140ms ease;
}
.cond-pill:hover {
  background: rgba(255,255,255,0.22);
}
.cond-pill.active {
  background: #d9f06a;
  color: #173d3a;
  font-weight: 700;
}
.cond-pill.hub {
  background: #ed8c70;
  color: #173d3a;
  font-weight: 700;
}
.cond-banner {
  width: min(1140px, calc(100% - 32px));
  margin: 14px auto 0;
  padding: 12px 18px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(22, 40, 38, 0.12);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.slot-button.waitlist-mode {
  border-color: #d97706;
  background: rgba(254, 243, 199, 0.85);
  color: #92400e;
  cursor: pointer;
}
.slot-button.blocked-slot {
  background: rgba(22, 40, 38, 0.08);
  color: rgba(22, 40, 38, 0.4);
  border-style: dashed;
  cursor: not-allowed;
}
.pass-wallet-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(23, 61, 58, 0.06);
  border: 1px solid rgba(23, 61, 58, 0.14);
}
.mini-btn {
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid rgba(23, 61, 58, 0.25);
  background: #fff;
  color: #173d3a;
  font-weight: 700;
  font-size: 0.82rem;
  cursor: pointer;
}
.mini-btn:hover {
  background: #d9f06a;
}
.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}
.booking-chip {
  padding: 7px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(22, 40, 38, 0.15);
  font-size: 0.83rem;
  cursor: pointer;
  text-align: left;
  transition: transform 120ms ease, border-color 120ms ease;
}
.booking-chip:hover {
  transform: translateY(-1px);
  border-color: #173d3a;
  background: #fff;
}
.audit-timeline {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid rgba(22, 40, 38, 0.12);
}
.audit-item {
  display: flex;
  justify-content: space-between;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(22, 40, 38, 0.04);
  font-size: 0.83rem;
  margin-top: 6px;
}
.reconcile-box {
  padding: 14px 18px;
  border-radius: 16px;
  margin-bottom: 16px;
  border: 1px solid rgba(31, 106, 74, 0.3);
  background: rgba(31, 106, 74, 0.08);
}
.reconcile-box.unbalanced {
  border-color: rgba(163, 58, 43, 0.45);
  background: rgba(163, 58, 43, 0.1);
}
.code-pre {
  background: #162826;
  color: #f5f7f3;
  padding: 16px;
  border-radius: 14px;
  overflow-x: auto;
  font-size: 0.82rem;
  line-height: 1.5;
  max-height: 520px;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.data-table th, .data-table td {
  padding: 8px 10px;
  border-bottom: 1px solid rgba(22, 40, 38, 0.12);
  text-align: left;
}
.data-table th {
  color: #5b6966;
  font-weight: 700;
  background: rgba(22, 40, 38, 0.04);
}
"""


def render_yeobaek_website(cfg: dict[str, Any], verifications: list[dict[str, Any]], files: dict[str, str]) -> str:
    is_large = cfg["scale"] == "large"
    passed_cnt = sum(1 for v in verifications if v["passed"])
    total_cnt = len(verifications)

    small_links = "".join(
        f'<a href="http://127.0.0.1:{c["port"]}" class="cond-pill {"active" if c["port"] == cfg["port"] else ""}">V1 C{c["cond_num"]} (:{c["port"]})</a>'
        for c in RUN_CONFIGS
        if c["scale"] == "small"
    )
    large_links = "".join(
        f'<a href="http://127.0.0.1:{c["port"]}" class="cond-pill {"active" if c["port"] == cfg["port"] else ""}">V2 C{c["cond_num"]} (:{c["port"]})</a>'
        for c in RUN_CONFIGS
        if c["scale"] == "large"
    )

    ver_rows_html = ""
    for v in verifications:
        badge = (
            '<span style="color:#1f6a4a;font-weight:700;">PASS</span>'
            if v["passed"]
            else '<span style="color:#a33a2b;font-weight:700;">FAIL</span>'
        )
        ver_rows_html += f"""
        <tr>
          <td><strong>{html.escape(v['id'])}</strong></td>
          <td>{html.escape(v['name'])}</td>
          <td>{badge}</td>
          <td>{html.escape(v['expected'])}</td>
          <td><code>{html.escape(v['actual'])}</code></td>
        </tr>
        """

    files_html = ""
    for fname, content in files.items():
        files_html += f"""
        <div class="surface-card" style="margin-bottom:16px;">
          <h3 style="margin-top:0;">📄 {html.escape(fname)} ({len(content.splitlines())} lines)</h3>
          <pre class="code-pre">{html.escape(content)}</pre>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(cfg['title'])} — 여백 상담실</title>
  <style>
  {BASE_PROTOTYPE_CSS}
  {WEBSITE_EXTRA_CSS}
  </style>
</head>
<body>
  <!-- 상단 조건 전환 바 -->
  <div class="cond-ribbon">
    <div class="cond-ribbon-inner">
      <div>
        <strong>🔬 현재 구동 중인 백엔드:</strong>
        <span style="color:#d9f06a;font-weight:700;margin-left:4px;">:{cfg['port']} {html.escape(cfg['title'])}</span>
        <span style="margin-left:8px;opacity:0.85;">(검증 {passed_cnt}/{total_cnt} 통과 · {html.escape(cfg['impl_status'])})</span>
      </div>
      <div class="cond-links">
        <a href="http://127.0.0.1:8100" class="cond-pill hub">🏠 전체 포트 비교 허브 (:8100)</a>
        <span style="opacity:0.4;">|</span>
        {small_links}
        <span style="opacity:0.4;">|</span>
        {large_links}
      </div>
    </div>
  </div>

  <!-- 현재 조건 요약 배너 -->
  <div class="cond-banner">
    <div>
      <span class="pill" style="margin-right:8px;">PORT :{cfg['port']} · {html.escape(cfg['short_label'])}</span>
      <strong style="font-size:0.95rem;">{html.escape(cfg['summary'])}</strong>
    </div>
    <div style="display:flex;gap:8px;align-items:center;">
      {"<button id='patch-typo-btn' class='mini-btn' style='background:#d9f06a;' onclick='toggleTypoPatch()'>🔧 오타 1줄 보정(_initialize_db → _init_db) 켜서 사이트 체험하기</button>" if cfg['id'] == 'small_cond5' else ""}
      <button class="mini-btn" onclick="resetWebsiteData()">🔄 초기 상담 일정 데이터로 리셋</button>
    </div>
  </div>

  <div class="page-shell">
    <header class="site-header">
      <div class="brand-lockup">
        <span class="brand-mark">여백 상담실</span>
        <span class="brand-subtitle">{'1:1 상담 예약 · 선불 상담권 · 만석 대기열 서비스 (V2)' if is_large else '1:1 상담 예약 (V1)'}</span>
      </div>

      <nav class="top-tabs" aria-label="주요 메뉴">
        <button class="top-tab is-active" type="button" data-tab="book" onclick="switchMainTab('book')">
          {'상담 예약 · 대기열' if is_large else '상담 예약'}
        </button>
        <button class="top-tab" type="button" data-tab="manage" onclick="switchMainTab('manage')">
          {'예약 조회 · 취소 · 일정변경' if is_large else '예약 조회·취소'}
        </button>
        {'''<button class="top-tab" type="button" data-tab="wallet" onclick="switchMainTab('wallet')">선불 상담권 지갑</button>''' if is_large else ''}
        <button class="top-tab" type="button" data-tab="admin" onclick="switchMainTab('admin')">
          {'상담사 일정 · 회계 대사' if is_large else '상담사 일정 개설'}
        </button>
        <button class="top-tab" type="button" data-tab="inspect" onclick="switchMainTab('inspect')">
          🔍 구현 코드·DB·검증 ({passed_cnt}/{total_cnt})
        </button>
      </nav>
    </header>

    <!-- 엔진 초기화 오류 알림창 (Cond 5 원본 모드 등) -->
    <div id="engine-error-banner" class="surface-card is-hidden" style="margin-bottom:20px;border-color:rgba(163,58,43,0.45);background:rgba(163,58,43,0.08);">
      <h3 style="margin:0 0 8px 0;color:#a33a2b;">🚨 이 조건의 생성된 백엔드 엔진 초기화 중 오류가 발생했습니다</h3>
      <p id="engine-error-text" style="margin:0;font-family:monospace;font-size:0.9rem;color:#a33a2b;"></p>
    </div>

    <section class="hero-panel">
      <div class="hero-copy">
        <p class="eyebrow">{'PREPAID SESSION PASS & WAITLIST BOOKING' if is_large else 'DIRECT COUNSELING BOOKING'}</p>
        <h1>복잡한 절차 없이, 상담 시간만 고르세요</h1>
        <p class="hero-description">
          {'선불 상담권 잔여 횟수를 확인하고 원하는 상담 시간을 선택해 즉시 예약하거나, 마감된 인기 시간대에 대기열(FIFO 자동 승격)을 걸 수 있습니다.' if is_large else '상담사와 날짜를 고른 뒤 비어 있는 시간을 선택하면 바로 예약할 수 있습니다. 예약 번호와 이메일만 있으면 조회와 취소도 같은 화면에서 끝납니다.'}
        </p>
        <div class="hero-highlights" aria-label="서비스 안내">
          <span class="pill">50분 개인 상담</span>
          <span class="pill">{'선불 상담권 차감·복구 & 대기열 자동 승격' if is_large else '예약 번호 즉시 발급'}</span>
          <span class="pill">이메일 본인 확인 후 조회·취소</span>
        </div>
      </div>

      <aside class="hero-aside" aria-label="상담사 소개">
        <p class="aside-title">상담사 안내</p>
        <div id="counselor-overview" class="counselor-overview"></div>
      </aside>
    </section>

    <main class="workspace">
      <!-- TAB 1: 상담 예약 (및 V2 대기열) -->
      <section id="panel-book" class="tab-panel">
        <div class="booking-grid">
          <article class="surface-card step-card">
            <div class="section-heading">
              <div>
                <p class="step-label">STEP 1</p>
                <h2>상담사와 날짜 선택</h2>
              </div>
              <span id="availability-badge" class="availability-badge">가능 시간 확인 중</span>
            </div>

            <div class="control-row">
              <label class="field">
                <span>상담사</span>
                <select id="counselor-select" onchange="onFilterChange()"></select>
              </label>

              <label class="field">
                <span>상담 날짜</span>
                <select id="date-select" onchange="onFilterChange()">
                  <option value="2026-05-11">2026-05-11 (월)</option>
                  <option value="2026-05-12">2026-05-12 (화)</option>
                  <option value="2026-05-13">2026-05-13 (수)</option>
                </select>
              </label>
            </div>

            <div id="counselor-Focus" class="counselor-Focus"></div>

            <div class="slot-section">
              <div class="slot-header">
                <h3>시간 선택</h3>
                <p>{'예약 가능 시간은 즉시 예약되며, 예약 마감(주황색) 시간을 클릭하면 만석 대기열(Waitlist) 신청이 가능합니다.' if is_large else '예약이 완료된 시간은 선택할 수 없으며, 취소되면 즉시 다시 열립니다.'}</p>
              </div>
              <div id="slot-grid" class="slot-grid" role="listbox" aria-label="상담 가능 시간"></div>
            </div>
          </article>

          <article class="surface-card form-card">
            <div class="section-heading">
              <div>
                <p class="step-label">STEP 2</p>
                <h2 id="step2-title">예약자 정보 입력</h2>
              </div>
            </div>

            <div id="selected-slot-banner" class="selected-slot-banner is-empty">
              아직 선택한 상담 시간이 없습니다. 왼쪽에서 시간을 먼저 골라 주세요.
            </div>

            <form id="booking-form" class="stack-form" onsubmit="submitBookingOrWaitlist(event)">
              <label class="field">
                <span>이름</span>
                <input id="client-name" name="client_name" type="text" value="김민지" placeholder="예: 김민지" required />
              </label>

              <label class="field">
                <span>이메일</span>
                <input id="client-email" name="client_email" type="email" value="minji@example.com" placeholder="예: minji@example.com" oninput="onClientEmailInput()" required />
              </label>

              {'''
              <div class="pass-wallet-bar">
                <div>
                  <span style="font-size:0.82rem;color:#5b6966;display:block;">선택 고객 선불 상담권 잔액 (get_session_pass)</span>
                  <strong id="live-pass-badge" style="font-size:0.95rem;color:#173d3a;">조회 중...</strong>
                </div>
                <button type="button" class="mini-btn" onclick="quickTopUpPass()">+ 상담권 1회 즉시 충전</button>
              </div>

              <label class="field" id="idem-field-wrap">
                <span>예약 멱등성 키 (Idempotency Key · 중복 클릭 방지 테스트용)</span>
                <div style="display:flex;gap:6px;">
                  <input id="booking-idem-key" type="text" value="" placeholder="자동 생성됨 (동일 키 재전송 테스트 가능)" />
                  <button type="button" class="mini-btn" onclick="regenIdemKey()">새 키</button>
                </div>
              </label>
              ''' if is_large else ''}

              <button id="submit-booking" class="primary-button" type="submit" disabled>
                선택한 시간으로 예약 확정
              </button>
            </form>

            <div id="booking-feedback" class="feedback is-hidden" role="status" aria-live="polite"></div>

            <section id="booking-confirmation" class="confirmation-card is-hidden" aria-live="polite">
              <div class="confirmation-header">
                <p class="eyebrow">BOOKING CONFIRMED</p>
                <h3>예약이 완료되었습니다</h3>
              </div>
              <dl id="confirmation-details" class="detail-list"></dl>
              <div class="confirmation-actions">
                <button id="go-to-manage" class="secondary-button" type="button" onclick="openBookingInManageTab()">
                  예약 조회·취소 화면에서 보기
                </button>
              </div>
            </section>
          </article>
        </div>
      </section>

      <!-- TAB 2: 예약 조회 · 취소 (및 V2 일정변경 / 감사로그) -->
      <section id="panel-manage" class="tab-panel is-hidden">
        <div class="manage-grid">
          <article class="surface-card">
            <div class="section-heading">
              <div>
                <p class="step-label">LOOKUP</p>
                <h2>예약 조회</h2>
              </div>
            </div>

            <form id="lookup-form" class="stack-form" onsubmit="submitLookup(event)">
              <label class="field">
                <span>예약 번호</span>
                <input id="lookup-booking-id" name="booking_id" type="text" placeholder="예: 예약 완료 시 발급된 번호" required />
              </label>

              <label class="field">
                <span>예약 시 입력한 이메일</span>
                <input id="lookup-email" name="client_email" type="email" placeholder="예: minji@example.com" required />
              </label>

              <button class="primary-button" type="submit">예약 내역 불러오기</button>
            </form>

            <div id="lookup-feedback" class="feedback is-hidden" role="status" aria-live="polite"></div>

            <div style="margin-top:20px;padding-top:16px;border-top:1px solid rgba(22,40,38,0.12);">
              <span style="font-size:0.84rem;font-weight:700;color:#5b6966;">💡 현재 등록된 예약 빠른 선택 (클릭 시 위 입력칸에 자동 입력 및 조회)</span>
              <div id="quick-booking-chips" class="chip-list"></div>
            </div>
          </article>

          <article class="surface-card">
            <div class="section-heading">
              <div>
                <p class="step-label">RESERVATION STATUS</p>
                <h2>예약 상세 및 취소{' · 일정 변경' if is_large else ''}</h2>
              </div>
            </div>

            <div id="lookup-empty" class="empty-state">
              왼쪽에서 예약 번호와 이메일을 입력하거나 빠른 선택 칩을 클릭하면 현재 예약 상태와 취소 버튼이 표시됩니다.
            </div>

            <section id="lookup-result" class="confirmation-card is-hidden" aria-live="polite">
              <div class="confirmation-header">
                <p id="lookup-status-pill" class="status-pill">예약 확정</p>
                <h3 id="lookup-title">예약 정보를 확인했습니다</h3>
              </div>
              <dl id="lookup-details" class="detail-list"></dl>

              <div class="confirmation-actions" style="display:flex;gap:10px;flex-wrap:wrap;">
                <button id="cancel-booking-button" class="danger-button" type="button" onclick="submitCancelBooking()">
                  이 예약 취소
                </button>
                {'''
                <button id="replay-cancelled-button" class="secondary-button is-hidden" type="button" onclick="submitReplayCancelledBooking()" style="border-color:#d97706;color:#92400e;">
                  ⚡ 취소된 예약 멱등키 재전송 테스트 (REQ-8 검증)
                </button>
                ''' if is_large else ''}
              </div>

              {'''
              <!-- V2 일정 변경(Reschedule) 박스 -->
              <div id="reschedule-box" style="margin-top:18px;padding-top:14px;border-top:1px solid rgba(22,40,38,0.12);">
                <h4 style="margin:0 0 8px 0;font-size:0.94rem;">🔄 다른 시간으로 일정 변경 (reschedule_booking · 상담권 추가 차감 없음)</h4>
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                  <select id="reschedule-counselor" style="flex:1;min-width:140px;padding:8px 10px;border-radius:10px;border:1px solid rgba(22,40,38,0.2);"></select>
                  <select id="reschedule-date" style="width:135px;padding:8px 10px;border-radius:10px;border:1px solid rgba(22,40,38,0.2);">
                    <option value="2026-05-11">2026-05-11</option>
                    <option value="2026-05-12">2026-05-12</option>
                    <option value="2026-05-13">2026-05-13</option>
                  </select>
                  <select id="reschedule-time" style="width:110px;padding:8px 10px;border-radius:10px;border:1px solid rgba(22,40,38,0.2);">
                    <option value="10:00:00">10:00</option>
                    <option value="11:00:00">11:00</option>
                    <option value="14:00:00">14:00</option>
                    <option value="15:00:00">15:00</option>
                    <option value="16:00:00">16:00</option>
                  </select>
                  <button type="button" class="secondary-button" onclick="submitRescheduleBooking()">일정 변경 실행</button>
                </div>
              </div>

              <!-- V2 감사 로그(Audit Log) 타임라인 -->
              <div id="audit-log-box" class="audit-timeline">
                <strong style="font-size:0.86rem;color:#5b6966;">📋 예약 상태 전이 감사 로그 (get_booking_audit_log)</strong>
                <div id="audit-log-list"></div>
              </div>
              ''' if is_large else ''}
            </section>
          </article>
        </div>
      </section>

      <!-- TAB 3 (V2 전용): 선불 상담권 지갑 -->
      {'''
      <section id="panel-wallet" class="tab-panel is-hidden">
        <div class="manage-grid">
          <article class="surface-card">
            <div class="section-heading">
              <div>
                <p class="step-label">SESSION PASS WALLET</p>
                <h2>선불 상담권 충전 및 멱등성 검증</h2>
              </div>
            </div>
            <form class="stack-form" onsubmit="submitIssuePass(event)">
              <label class="field">
                <span>고객 이메일</span>
                <input id="wallet-email" type="email" value="minji@example.com" required />
              </label>
              <label class="field">
                <span>충전할 상담권 횟수 (sessions_to_add)</span>
                <input id="wallet-count" type="number" value="2" min="1" max="20" required />
              </label>
              <label class="field">
                <span>충전 요청 멱등성 키 (Idempotency Key · 동일 키 중복 호출 시 1회만 충전됨)</span>
                <input id="wallet-idem-key" type="text" value="pass-topup-101" required />
              </label>
              <button class="primary-button" type="submit">선불 상담권 발급 / 충전하기</button>
            </form>
            <div id="wallet-feedback" class="feedback is-hidden"></div>
          </article>

          <article class="surface-card">
            <div class="section-heading">
              <div>
                <p class="step-label">CLIENT PASS BALANCES</p>
                <h2>전체 고객 상담권 지갑 현황</h2>
              </div>
            </div>
            <div id="wallet-table-wrap"></div>
          </article>
        </div>
      </section>
      ''' if is_large else ''}

      <!-- TAB 4: 상담사 일정 개설 · 관리자 -->
      <section id="panel-admin" class="tab-panel is-hidden">
        <div id="reconcile-admin-banner"></div>
        <div class="manage-grid">
          <article class="surface-card">
            <div class="section-heading">
              <div>
                <p class="step-label">SCHEDULE MANAGEMENT</p>
                <h2>상담 가능 시간 개설 {'및 슬롯 차단' if is_large else ''}</h2>
              </div>
            </div>
            <form class="stack-form" onsubmit="submitAddSlot(event)">
              <label class="field">
                <span>상담사</span>
                <select id="admin-counselor"></select>
              </label>
              <label class="field">
                <span>날짜</span>
                <input id="admin-date" type="date" value="2026-05-11" required />
              </label>
              <label class="field">
                <span>시간 (30분 단위)</span>
                <select id="admin-time">
                  <option value="09:00:00">09:00</option>
                  <option value="09:30:00">09:30</option>
                  <option value="10:00:00">10:00</option>
                  <option value="11:00:00">11:00</option>
                  <option value="13:00:00">13:00</option>
                  <option value="14:00:00">14:00</option>
                  <option value="15:00:00">15:00</option>
                  <option value="16:00:00">16:00</option>
                  <option value="17:00:00">17:00</option>
                </select>
              </label>
              <div style="display:flex;gap:10px;flex-wrap:wrap;">
                <button class="primary-button" type="submit">상담 가능 슬롯 추가</button>
                {'''<button class="secondary-button" type="button" onclick="submitBlockSlot()">선택 슬롯 마감(BLOCKED) 처리</button>''' if is_large else ''}
              </div>
            </form>
            <div id="admin-feedback" class="feedback is-hidden"></div>
          </article>

          <article class="surface-card">
            <div class="section-heading">
              <div>
                <p class="step-label">CURRENT SCHEDULE & WAITLIST</p>
                <h2>전체 예약 및 대기열 현황</h2>
              </div>
            </div>
            <div id="admin-bookings-wrap"></div>
          </article>
        </div>
      </section>

      <!-- TAB 5: 구현 코드 · DB · 요구사항 검증표 -->
      <section id="panel-inspect" class="tab-panel is-hidden">
        <div class="surface-card" style="margin-bottom:18px;">
          <h2 style="margin-top:0;">✅ 브리프 요구사항 자동 검증 결과 ({passed_cnt} / {total_cnt} 통과)</h2>
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:70px;">ID</th>
                <th style="width:280px;">검증 항목</th>
                <th style="width:70px;">상태</th>
                <th>기대 결과</th>
                <th>실제 실행 결과</th>
              </tr>
            </thead>
            <tbody>{ver_rows_html}</tbody>
          </table>
        </div>

        <div class="surface-card" style="margin-bottom:18px;">
          <h2 style="margin-top:0;">🗄️ 실시간 SQLite 데이터베이스 테이블 원본</h2>
          <div id="raw-db-tables"></div>
        </div>

        <div>
          <h2>📄 에이전트가 생성한 설계 산출물 & 파이썬 소스코드</h2>
          {files_html}
        </div>
      </section>
    </main>
  </div>

  <script>
  const IS_LARGE = { 'true' if is_large else 'false' };
  let appState = {{
    counselors: [],
    selectedCounselorId: 'counselor-garam',
    selectedDate: '2026-05-11',
    selectedSlot: null, // {{ start_time, time_label, status }}
    currentLookupBooking: null,
    slots: [],
    recentBookings: [],
    patchTypo: false,
  }};

  function genIdemKey(prefix = 'web-bk') {{
    return prefix + '-' + Math.floor(100000 + Math.random() * 900000);
  }}

  function regenIdemKey() {{
    const el = document.getElementById('booking-idem-key');
    if (el) el.value = genIdemKey('web-bk');
  }}

  function switchMainTab(tabName) {{
    document.querySelectorAll('.top-tab').forEach(btn => {{
      btn.classList.toggle('is-active', btn.dataset.tab === tabName);
    }});
    ['book', 'manage', 'wallet', 'admin', 'inspect'].forEach(name => {{
      const panel = document.getElementById('panel-' + name);
      if (panel) panel.classList.toggle('is-hidden', name !== tabName);
    }});
  }}

  function showFeedback(elId, message, tone = 'success') {{
    const el = document.getElementById(elId);
    if (!el) return;
    if (!message) {{
      el.textContent = '';
      el.className = 'feedback is-hidden';
      return;
    }}
    el.textContent = message;
    el.className = `feedback is-${{tone}}`;
  }}

  async function refreshState() {{
    const emailEl = document.getElementById('client-email');
    const clientEmail = emailEl ? emailEl.value.trim() : 'minji@example.com';
    const qs = new URLSearchParams({{
      counselor_id: appState.selectedCounselorId,
      date: appState.selectedDate,
      client_email: clientEmail,
    }});
    const res = await fetch('/api/state?' + qs.toString());
    const data = await res.json();

    appState.patchTypo = Boolean(data.patch_typo);
    const patchBtn = document.getElementById('patch-typo-btn');
    if (patchBtn) {{
      patchBtn.textContent = appState.patchTypo
        ? '🚨 보정 해제하고 원본 코드 에러 상태 보기'
        : '🔧 오타 1줄 보정(_initialize_db → _init_db) 켜서 사이트 체험하기';
    }}

    const errBanner = document.getElementById('engine-error-banner');
    const errText = document.getElementById('engine-error-text');
    if (data.init_error) {{
      errBanner.classList.remove('is-hidden');
      errText.textContent = data.init_error;
    }} else {{
      errBanner.classList.add('is-hidden');
    }}

    appState.counselors = data.counselors || [];
    appState.slots = data.slots || [];
    appState.recentBookings = data.recent_bookings || [];

    renderCounselors();
    renderSlots();
    renderPassBadge(data.client_pass);
    renderQuickBookingChips();
    renderWalletTable(data.passes || []);
    renderAdminSection(data);
    renderRawDbTables(data.tables || {{}});
  }}

  function renderCounselors() {{
    const overviewEl = document.getElementById('counselor-overview');
    const selectEl = document.getElementById('counselor-select');
    const adminSelectEl = document.getElementById('admin-counselor');
    const reschedSelectEl = document.getElementById('reschedule-counselor');

    if (overviewEl) {{
      overviewEl.innerHTML = appState.counselors.map(c => `
        <div class="counselor-card ${{c.counselor_id === appState.selectedCounselorId ? 'is-selected' : ''}}"
             style="cursor:pointer;"
             onclick="selectCounselor('${{c.counselor_id}}')">
          <strong>${{c.name}}</strong>
          <span class="counselor-specialty">${{c.specialty}}</span>
          <p>${{c.intro}}</p>
        </div>
      `).join('');
    }}

    const optionsHtml = appState.counselors.map(c =>
      `<option value="${{c.counselor_id}}" ${{c.counselor_id === appState.selectedCounselorId ? 'selected' : ''}}>${{c.name}} · ${{c.specialty}}</option>`
    ).join('');

    if (selectEl && selectEl.innerHTML !== optionsHtml) selectEl.innerHTML = optionsHtml;
    if (adminSelectEl && !adminSelectEl.innerHTML) adminSelectEl.innerHTML = optionsHtml;
    if (reschedSelectEl && !reschedSelectEl.innerHTML) reschedSelectEl.innerHTML = optionsHtml;

    const current = appState.counselors.find(c => c.counselor_id === appState.selectedCounselorId);
    const focusEl = document.getElementById('counselor-Focus');
    if (focusEl && current) {{
      focusEl.innerHTML = `<strong>${{current.name}}</strong><span>${{current.specialty}}</span><p>${{current.intro}}</p>`;
    }}
  }}

  function selectCounselor(cid) {{
    appState.selectedCounselorId = cid;
    appState.selectedSlot = null;
    const selectEl = document.getElementById('counselor-select');
    if (selectEl) selectEl.value = cid;
    updateSelectedSlotBanner();
    refreshState();
  }}

  function onFilterChange() {{
    const cSel = document.getElementById('counselor-select');
    const dSel = document.getElementById('date-select');
    if (cSel) appState.selectedCounselorId = cSel.value;
    if (dSel) appState.selectedDate = dSel.value;
    appState.selectedSlot = null;
    updateSelectedSlotBanner();
    refreshState();
  }}

  function renderSlots() {{
    const gridEl = document.getElementById('slot-grid');
    const badgeEl = document.getElementById('availability-badge');
    if (!gridEl) return;

    const availCount = appState.slots.filter(s => s.status === 'AVAILABLE').length;
    if (badgeEl) {{
      badgeEl.textContent = availCount > 0 ? `예약 가능 ${{availCount}}개` : '예약 가능한 시간 없음';
    }}

    if (appState.slots.length === 0) {{
      gridEl.innerHTML = `<div class="empty-state">이 날짜에는 개설된 상담 일정이 없습니다.</div>`;
      return;
    }}

    gridEl.innerHTML = appState.slots.map(slot => {{
      const isSelected = appState.selectedSlot && appState.selectedSlot.start_time === slot.start_time;
      if (slot.status === 'AVAILABLE') {{
        return `
          <button type="button"
                  class="slot-button is-available ${{isSelected ? 'is-selected' : ''}}"
                  onclick="onSelectSlot('${{slot.start_time}}', '${{slot.time_label}}', 'AVAILABLE')">
            <span class="slot-time">${{slot.time_label}}</span>
            <span class="slot-state">${{isSelected ? '선택됨 · 예약 가능' : '예약 가능'}}</span>
          </button>
        `;
      }} else if (slot.status === 'BOOKED') {{
        if (IS_LARGE) {{
          const wCnt = slot.waitlist_count || 0;
          return `
            <button type="button"
                    class="slot-button waitlist-mode ${{isSelected ? 'is-selected' : ''}}"
                    onclick="onSelectSlot('${{slot.start_time}}', '${{slot.time_label}}', 'BOOKED')">
              <span class="slot-time">${{slot.time_label}}</span>
              <span class="slot-state">예약 마감 · 대기열 신청 (대기 ${{wCnt}}명)</span>
            </button>
          `;
        }} else {{
          return `
            <button type="button" class="slot-button is-booked" disabled>
              <span class="slot-time">${{slot.time_label}}</span>
              <span class="slot-state">예약 마감</span>
            </button>
          `;
        }}
      }} else {{
        return `
          <button type="button" class="slot-button blocked-slot" disabled>
            <span class="slot-time">${{slot.time_label}}</span>
            <span class="slot-state">상담사 마감 (BLOCKED)</span>
          </button>
        `;
      }}
    }}).join('');
  }}

  function onSelectSlot(startTime, timeLabel, status) {{
    appState.selectedSlot = {{ start_time: startTime, time_label: timeLabel, status }};
    regenIdemKey();
    updateSelectedSlotBanner();
    renderSlots();
  }}

  function updateSelectedSlotBanner() {{
    const banner = document.getElementById('selected-slot-banner');
    const submitBtn = document.getElementById('submit-booking');
    const step2Title = document.getElementById('step2-title');
    const idemWrap = document.getElementById('idem-field-wrap');
    const counselor = appState.counselors.find(c => c.counselor_id === appState.selectedCounselorId);
    const cname = counselor ? counselor.name : appState.selectedCounselorId;

    if (!appState.selectedSlot) {{
      banner.className = 'selected-slot-banner is-empty';
      banner.textContent = '아직 선택한 상담 시간이 없습니다. 왼쪽에서 시간을 먼저 골라 주세요.';
      submitBtn.disabled = true;
      submitBtn.textContent = '선택한 시간으로 예약 확정';
      if (step2Title) step2Title.textContent = '예약자 정보 입력';
      return;
    }}

    if (appState.selectedSlot.status === 'BOOKED' && IS_LARGE) {{
      banner.className = 'selected-slot-banner';
      banner.style.background = 'rgba(254, 243, 199, 0.9)';
      banner.textContent = `[만석 대기열 신청] ${{cname}} · ${{appState.selectedDate}} ${{appState.selectedSlot.time_label}} (취소 발생 시 1순위 자동 예약 승격)`;
      submitBtn.disabled = false;
      submitBtn.textContent = '이 시간대 대기열(Waitlist) 등록하기';
      if (step2Title) step2Title.textContent = '대기열 신청자 정보 입력';
      if (idemWrap) idemWrap.style.display = 'none';
    }} else {{
      banner.className = 'selected-slot-banner';
      banner.style.background = '';
      banner.textContent = `${{cname}} · ${{appState.selectedDate}} ${{appState.selectedSlot.time_label}} 상담 (50분)을 선택하셨습니다.`;
      submitBtn.disabled = false;
      submitBtn.textContent = '선택한 시간으로 예약 확정';
      if (step2Title) step2Title.textContent = '예약자 정보 입력';
      if (idemWrap) idemWrap.style.display = 'grid';
    }}
  }}

  function renderPassBadge(passInfo) {{
    const el = document.getElementById('live-pass-badge');
    if (!el || !passInfo) return;
    const rem = passInfo.remaining_sessions ?? 0;
    const used = passInfo.used_sessions ?? 0;
    el.innerHTML = `잔여 <b>${{rem}}회</b> (사용 ${{used}}회)`;
    el.style.color = rem > 0 ? '#1f6a4a' : '#a33a2b';
  }}

  function onClientEmailInput() {{
    if (IS_LARGE) refreshState();
  }}

  async function quickTopUpPass() {{
    const email = document.getElementById('client-email').value.trim();
    if (!email) {{
      showFeedback('booking-feedback', '먼저 고객 이메일을 입력해 주세요.', 'error');
      return;
    }}
    const res = await fetch('/api/passes/issue', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        client_email: email,
        sessions_to_add: 1,
        idempotency_key: genIdemKey('quick-pass'),
      }}),
    }});
    const data = await res.json();
    if (data.ok) {{
      showFeedback('booking-feedback', data.message, 'success');
      await refreshState();
    }} else {{
      showFeedback('booking-feedback', data.error, 'error');
    }}
  }}

  async function submitBookingOrWaitlist(e) {{
    e.preventDefault();
    if (!appState.selectedSlot) return;
    const name = document.getElementById('client-name').value.trim();
    const email = document.getElementById('client-email').value.trim();
    const idemEl = document.getElementById('booking-idem-key');
    const idemKey = idemEl && idemEl.value.trim() ? idemEl.value.trim() : genIdemKey('web-bk');

    if (appState.selectedSlot.status === 'BOOKED' && IS_LARGE) {{
      const res = await fetch('/api/waitlist', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          counselor_id: appState.selectedCounselorId,
          start_time: appState.selectedSlot.start_time,
          client_name: name,
          client_email: email,
        }}),
      }});
      const data = await res.json();
      if (data.ok) {{
        showFeedback('booking-feedback', data.message, 'success');
        await refreshState();
      }} else {{
        showFeedback('booking-feedback', data.error, 'error');
      }}
      return;
    }}

    const res = await fetch('/api/bookings', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        counselor_id: appState.selectedCounselorId,
        start_time: appState.selectedSlot.start_time,
        client_name: name,
        client_email: email,
        idempotency_key: idemKey,
      }}),
    }});
    const data = await res.json();
    if (!data.ok) {{
      showFeedback('booking-feedback', data.error, 'error');
      return;
    }}

    showFeedback('booking-feedback', data.message, 'success');
    const bk = data.booking;
    appState.currentLookupBooking = bk;
    const confCard = document.getElementById('booking-confirmation');
    const confDetails = document.getElementById('confirmation-details');
    confCard.classList.remove('is-hidden');
    confDetails.innerHTML = buildBookingDetailItems(bk);

    document.getElementById('lookup-booking-id').value = bk.booking_id || bk.id || '';
    document.getElementById('lookup-email').value = bk.client_email || email;

    appState.selectedSlot = null;
    updateSelectedSlotBanner();
    await refreshState();
  }}

  function buildBookingDetailItems(bk) {{
    const bid = bk.booking_id || bk.id || '';
    const statusText = bk.status === 'CONFIRMED' ? '예약 확정 (CONFIRMED)' : '예약 취소됨 (CANCELLED)';
    const rows = [
      ['예약 번호', bid],
      ['예약 상태', statusText],
      ['상담사', bk.counselor_name || bk.counselor_id || '-'],
      ['상담 일정', `${{bk.date || ''}} ${{bk.time_label || bk.start_time || ''}}`],
      ['예약자', `${{bk.client_name || '-'}} (${{bk.client_email || '-'}})`],
    ];
    if (bk.idempotency_key) {{
      rows.push(['멱등성 키', bk.idempotency_key]);
    }}
    return rows.map(([dt, dd]) => `<div><dt>${{dt}}</dt><dd>${{dd}}</dd></div>`).join('');
  }}

  function openBookingInManageTab() {{
    switchMainTab('manage');
    if (appState.currentLookupBooking) {{
      loadBookingIntoManageView(
        appState.currentLookupBooking.booking_id || appState.currentLookupBooking.id,
        appState.currentLookupBooking.client_email
      );
    }}
  }}

  function renderQuickBookingChips() {{
    const wrap = document.getElementById('quick-booking-chips');
    if (!wrap) return;
    if (appState.recentBookings.length === 0) {{
      wrap.innerHTML = `<span style="font-size:0.82rem;color:#5b6966;">현재 생성된 예약이 없습니다.</span>`;
      return;
    }}
    wrap.innerHTML = appState.recentBookings.map(b => {{
      const bid = b.booking_id || b.id || '';
      const stBadge = b.status === 'CONFIRMED' ? '🟢 확정' : '⚪ 취소됨';
      return `
        <button type="button" class="booking-chip"
                onclick="loadBookingIntoManageView('${{bid}}', '${{b.client_email}}')">
          <strong>${{stBadge}} · ${{b.client_name || '고객'}}</strong> (${{b.client_email}})<br/>
          <span style="color:#5b6966;">${{b.counselor_name || b.counselor_id}} · ${{b.date}} ${{b.time_label}}</span>
        </button>
      `;
    }}).join('');
  }}

  async function loadBookingIntoManageView(bookingId, clientEmail) {{
    document.getElementById('lookup-booking-id').value = bookingId;
    document.getElementById('lookup-email').value = clientEmail;
    await performLookup(bookingId, clientEmail);
  }}

  async function submitLookup(e) {{
    e.preventDefault();
    const bid = document.getElementById('lookup-booking-id').value.trim();
    const email = document.getElementById('lookup-email').value.trim();
    await performLookup(bid, email);
  }}

  async function performLookup(bid, email) {{
    const res = await fetch('/api/bookings/lookup', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ booking_id: bid, client_email: email }}),
    }});
    const data = await res.json();
    if (!data.ok) {{
      showFeedback('lookup-feedback', data.error, 'error');
      return;
    }}
    showFeedback('lookup-feedback', data.message, 'success');
    renderManageBookingCard(data.booking, data.audit_logs || []);
  }}

  function renderManageBookingCard(bk, auditLogs) {{
    appState.currentLookupBooking = bk;
    document.getElementById('lookup-empty').classList.add('is-hidden');
    const resultCard = document.getElementById('lookup-result');
    resultCard.classList.remove('is-hidden');

    const pill = document.getElementById('lookup-status-pill');
    const title = document.getElementById('lookup-title');
    const cancelBtn = document.getElementById('cancel-booking-button');
    const replayBtn = document.getElementById('replay-cancelled-button');
    const reschedBox = document.getElementById('reschedule-box');

    const isConfirmed = bk.status === 'CONFIRMED';
    pill.textContent = isConfirmed ? '예약 확정' : '예약 취소됨';
    pill.className = `status-pill ${{isConfirmed ? 'is-confirmed' : 'is-cancelled'}}`;
    title.textContent = isConfirmed ? '예약이 확정된 상태입니다' : '취소가 완료된 예약입니다';
    document.getElementById('lookup-details').innerHTML = buildBookingDetailItems(bk);

    cancelBtn.disabled = !isConfirmed;
    cancelBtn.textContent = isConfirmed ? '이 예약 취소' : '이미 취소된 예약입니다';

    if (replayBtn) {{
      replayBtn.classList.toggle('is-hidden', isConfirmed);
    }}
    if (reschedBox) {{
      reschedBox.style.display = isConfirmed ? 'block' : 'none';
    }}

    const auditListEl = document.getElementById('audit-log-list');
    if (auditListEl) {{
      if (!auditLogs || auditLogs.length === 0) {{
        auditListEl.innerHTML = `<div style="font-size:0.82rem;color:#5b6966;margin-top:6px;">기록된 감사 로그가 없습니다.</div>`;
      }} else {{
        auditListEl.innerHTML = auditLogs.map((log, idx) => {{
          const ev = log.event_type || log.action || 'EVENT';
          const det = log.details || log.note || log.new_start_time || '';
          return `
            <div class="audit-item">
              <span><b>#${{idx + 1}} ${{ev}}</b> ${{det ? '— ' + det : ''}}</span>
              <span style="color:#5b6966;">${{log.created_at || log.timestamp || ''}}</span>
            </div>
          `;
        }}).join('');
      }}
    }}
  }}

  async function submitCancelBooking() {{
    if (!appState.currentLookupBooking) return;
    const bid = appState.currentLookupBooking.booking_id || appState.currentLookupBooking.id;
    const email = appState.currentLookupBooking.client_email;
    const res = await fetch('/api/bookings/cancel', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ booking_id: bid, client_email: email }}),
    }});
    const data = await res.json();
    if (!data.ok) {{
      showFeedback('lookup-feedback', data.error, 'error');
      return;
    }}
    const tone = data.message.includes('🚨') ? 'error' : 'success';
    showFeedback('lookup-feedback', data.message, tone);
    renderManageBookingCard(data.booking, data.audit_logs || []);
    await refreshState();
  }}

  async function submitRescheduleBooking() {{
    if (!appState.currentLookupBooking) return;
    const bid = appState.currentLookupBooking.booking_id || appState.currentLookupBooking.id;
    const email = appState.currentLookupBooking.client_email;
    const newCid = document.getElementById('reschedule-counselor').value;
    const newDate = document.getElementById('reschedule-date').value;
    const newTime = document.getElementById('reschedule-time').value;
    const newStartTime = `${{newDate}}T${{newTime}}`;

    const res = await fetch('/api/bookings/reschedule', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        booking_id: bid,
        client_email: email,
        new_counselor_id: newCid,
        new_start_time: newStartTime,
      }}),
    }});
    const data = await res.json();
    if (!data.ok) {{
      showFeedback('lookup-feedback', data.error, 'error');
      return;
    }}
    showFeedback('lookup-feedback', data.message, 'success');
    renderManageBookingCard(data.booking, data.audit_logs || []);
    await refreshState();
  }}

  async function submitReplayCancelledBooking() {{
    if (!appState.currentLookupBooking) return;
    const bid = appState.currentLookupBooking.booking_id || appState.currentLookupBooking.id;
    const res = await fetch('/api/bookings/replay-cancelled', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ booking_id: bid }}),
    }});
    const data = await res.json();
    if (data.error) {{
      showFeedback('lookup-feedback', `🚨 [예외 크래시 발생] ${{data.error}}`, 'error');
      return;
    }}
    showFeedback('lookup-feedback', data.message, data.ok ? 'success' : 'error');
    await refreshState();
  }}

  async function submitIssuePass(e) {{
    e.preventDefault();
    const email = document.getElementById('wallet-email').value.trim();
    const cnt = Number(document.getElementById('wallet-count').value);
    const key = document.getElementById('wallet-idem-key').value.trim();
    const res = await fetch('/api/passes/issue', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ client_email: email, sessions_to_add: cnt, idempotency_key: key }}),
    }});
    const data = await res.json();
    if (!data.ok) {{
      showFeedback('wallet-feedback', data.error, 'error');
      return;
    }}
    showFeedback('wallet-feedback', data.message, 'success');
    await refreshState();
  }}

  function renderWalletTable(passes) {{
    const wrap = document.getElementById('wallet-table-wrap');
    if (!wrap) return;
    if (passes.length === 0) {{
      wrap.innerHTML = `<div class="empty-state">발급된 상담권 내역이 없습니다.</div>`;
      return;
    }}
    wrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>고객 이메일</th>
            <th>잔여 횟수 (remaining)</th>
            <th>사용 횟수 (used)</th>
          </tr>
        </thead>
        <tbody>
          ${{passes.map(p => `
            <tr>
              <td><strong>${{p.client_email}}</strong></td>
              <td style="color:#1f6a4a;font-weight:700;">${{p.remaining_sessions}}회</td>
              <td>${{p.used_sessions}}회</td>
            </tr>
          `).join('')}}
        </tbody>
      </table>
    `;
  }}

  async function submitAddSlot(e) {{
    e.preventDefault();
    const cid = document.getElementById('admin-counselor').value;
    const d = document.getElementById('admin-date').value;
    const t = document.getElementById('admin-time').value;
    const res = await fetch('/api/slots/add', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ counselor_id: cid, start_time: `${{d}}T${{t}}` }}),
    }});
    const data = await res.json();
    showFeedback('admin-feedback', data.ok ? data.message : data.error, data.ok ? 'success' : 'error');
    if (data.ok) await refreshState();
  }}

  async function submitBlockSlot() {{
    const cid = document.getElementById('admin-counselor').value;
    const d = document.getElementById('admin-date').value;
    const t = document.getElementById('admin-time').value;
    const res = await fetch('/api/slots/block', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ counselor_id: cid, start_time: `${{d}}T${{t}}` }}),
    }});
    const data = await res.json();
    showFeedback('admin-feedback', data.ok ? data.message : data.error, data.ok ? 'success' : 'error');
    if (data.ok) await refreshState();
  }}

  function renderAdminSection(data) {{
    const recWrap = document.getElementById('reconcile-admin-banner');
    if (recWrap && data.reconciliation) {{
      const r = data.reconciliation;
      const ok = Boolean(r.is_balanced);
      const issued = r.total_issued_sessions ?? r.total_issued_passes ?? 0;
      const rem = r.total_remaining_sessions ?? r.total_remaining_passes ?? 0;
      const used = r.total_used_sessions ?? 0;
      const activeBk = r.active_confirmed_bookings ?? r.active_bookings ?? 0;
      const bookedSlots = r.booked_slots_count ?? r.booked_slots ?? 0;
      recWrap.innerHTML = `
        <div class="reconcile-box ${{ok ? '' : 'unbalanced'}}">
          <strong style="font-size:1rem;">${{ok ? '✅ 전역 상담권 원장·슬롯 정합성 대사 정상 (is_balanced = True)' : '🚨 전역 상담권 원장·슬롯 정합성 불일치 발생! (is_balanced = False)'}}</strong>
          <div style="font-size:0.88rem;margin-top:6px;color:#162826;">
            총 발급 상담권: <b>${{issued}}회</b> = 잔여 합계(<b>${{rem}}회</b>) + 사용 합계(<b>${{used}}회</b>) &nbsp;|&nbsp;
            사용 합계(<b>${{used}}</b>) == 활성 확정 예약(<b>${{activeBk}}건</b>) == 예약 마감 슬롯(<b>${{bookedSlots}}개</b>)
          </div>
        </div>
      `;
    }}

    const wrap = document.getElementById('admin-bookings-wrap');
    if (!wrap) return;
    const bks = data.recent_bookings || [];
    const waits = data.waitlist || [];
    let html = `<h4 style="margin:0 0 8px 0;">최근 예약 목록 (${{bks.length}}건)</h4>`;
    if (bks.length === 0) {{
      html += `<p style="color:#5b6966;font-size:0.86rem;">예약 내역이 없습니다.</p>`;
    }} else {{
      html += `<table class="data-table"><thead><tr><th>상태</th><th>상담사</th><th>일시</th><th>예약자</th></tr></thead><tbody>` +
        bks.map(b => `<tr><td><b>${{b.status}}</b></td><td>${{b.counselor_name}}</td><td>${{b.date}} ${{b.time_label}}</td><td>${{b.client_name}} (${{b.client_email}})</td></tr>`).join('') +
        `</tbody></table>`;
    }}

    if (IS_LARGE) {{
      html += `<h4 style="margin:18px 0 8px 0;">만석 슬롯 대기열 (Waitlist · ${{waits.length}}건)</h4>`;
      if (waits.length === 0) {{
        html += `<p style="color:#5b6966;font-size:0.86rem;">대기열 신청 내역이 없습니다.</p>`;
      }} else {{
        html += `<table class="data-table"><thead><tr><th>상태</th><th>대기자</th><th>이메일</th><th>정보</th></tr></thead><tbody>` +
          waits.map(w => `<tr><td><b>${{w.status || 'WAITING'}}</b></td><td>${{w.client_name}}</td><td>${{w.client_email}}</td><td><code>${{w.start_time || ('slot #' + w.slot_id)}}</code></td></tr>`).join('') +
          `</tbody></table>`;
      }}
    }}
    wrap.innerHTML = html;
  }}

  function renderRawDbTables(tables) {{
    const wrap = document.getElementById('raw-db-tables');
    if (!wrap) return;
    const names = Object.keys(tables);
    if (names.length === 0) {{
      wrap.innerHTML = `<p style="color:#5b6966;">생성된 SQLite 테이블이 없습니다.</p>`;
      return;
    }}
    wrap.innerHTML = names.map(t => {{
      const rows = tables[t] || [];
      if (rows.length === 0) {{
        return `<div style="margin-bottom:14px;"><strong>테이블 <code>${{t}}</code> (0 rows)</strong></div>`;
      }}
      const cols = Object.keys(rows[0]);
      return `
        <div style="margin-bottom:18px;overflow-x:auto;">
          <div style="margin-bottom:6px;"><strong>테이블 <code>${{t}}</code> (${{rows.length}} rows)</strong></div>
          <table class="data-table">
            <thead><tr>${{cols.map(c => `<th>${{c}}</th>`).join('')}}</tr></thead>
            <tbody>
              ${{rows.map(r => `<tr>${{cols.map(c => `<td>${{r[c] === null ? 'NULL' : String(r[c])}}</td>`).join('')}}</tr>`).join('')}}
            </tbody>
          </table>
        </div>
      `;
    }}).join('');
  }}

  async function resetWebsiteData() {{
    await fetch('/api/reset', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: '{{}}' }});
    document.getElementById('booking-confirmation').classList.add('is-hidden');
    showFeedback('booking-feedback', '초기 상담 일정 및 샘플 데이터로 리셋되었습니다.', 'success');
    await refreshState();
  }}

  async function toggleTypoPatch() {{
    const res = await fetch('/api/toggle-patch', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ enable: !appState.patchTypo }}),
    }});
    const data = await res.json();
    showFeedback('booking-feedback', data.message, 'success');
    await refreshState();
  }}

  window.addEventListener('DOMContentLoaded', () => {{
    regenIdemKey();
    refreshState();
  }});
  </script>
</body>
</html>
"""


def serve_condition_port(cfg: dict[str, Any]) -> None:
    backend = ConditionWebsiteBackend(cfg)
    page_html = render_yeobaek_website(cfg, backend.verifications, backend.files)

    class WebsiteHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/summary":
                body = json.dumps(
                    {
                        "id": cfg["id"],
                        "title": cfg["title"],
                        "short_label": cfg["short_label"],
                        "port": cfg["port"],
                        "scale": cfg["scale"],
                        "cond_num": cfg["cond_num"],
                        "cond_name": cfg["cond_name"],
                        "agent_pytest": cfg["agent_pytest"],
                        "impl_status": cfg["impl_status"],
                        "summary": cfg["summary"],
                        "verifications": backend.verifications,
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/api/state":
                qs = parse_qs(parsed.query)
                cid = qs.get("counselor_id", ["counselor-garam"])[0]
                date_str = qs.get("date", ["2026-05-11"])[0]
                email = qs.get("client_email", ["minji@example.com"])[0]
                state = backend.get_full_state(cid, date_str, email)
                body = json.dumps(state, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return

            body = page_html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {}
            status_code, res = backend.handle_api_post(parsed.path, payload)
            body = json.dumps(res, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", cfg["port"]), WebsiteHandler)
    server.serve_forever()


def render_hub_page() -> str:
    import urllib.request

    summaries = []
    for cfg in RUN_CONFIGS:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{cfg['port']}/api/summary", timeout=2) as resp:
                summaries.append(json.loads(resp.read().decode("utf-8")))
        except Exception:
            summaries.append({**cfg, "verifications": []})

    def build_rows(scale: str) -> str:
        out = ""
        for s in [x for x in summaries if x["scale"] == scale]:
            vers = s.get("verifications", [])
            passed = sum(1 for v in vers if v["passed"])
            total = len(vers)
            color = "#1f6a4a" if passed == total and total > 0 else ("#b45309" if passed >= 6 else "#a33a2b")
            out += f"""
            <tr>
              <td>
                <a href="http://127.0.0.1:{s['port']}" class="primary-button" style="display:inline-block;padding:8px 14px;text-decoration:none;font-size:0.86rem;">
                  🌐 :{s['port']} 사이트 열기
                </a>
              </td>
              <td><strong>{html.escape(s['short_label'])}</strong><br/><code style="font-size:0.78rem;color:#5b6966;">{html.escape(s['cond_name'])}</code></td>
              <td><strong style="color:{color};">{passed} / {total} 통과</strong></td>
              <td><code>{html.escape(s['agent_pytest'])}</code><br/><span style="font-size:0.78rem;color:#5b6966;">{html.escape(s['impl_status'])}</span></td>
              <td style="font-size:0.86rem;">{html.escape(s['summary'])}</td>
            </tr>
            """
        return out

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <title>여백 상담실 — 조건별 예약 웹사이트 전체 포털 (:8100)</title>
  <style>
  {BASE_PROTOTYPE_CSS}
  {WEBSITE_EXTRA_CSS}
  </style>
</head>
<body>
  <div class="page-shell">
    <header class="site-header">
      <div class="brand-lockup">
        <span class="brand-mark">여백 상담실 · 조건별 예약 사이트 포털 (:8100)</span>
        <span class="brand-subtitle">소규모 V1 (:8110~:8115) & 대규모 V2 (:8120~:8125) 총 12개 예약 사이트 라이브 구동 중</span>
      </div>
    </header>

    <div class="surface-card" style="margin-bottom:24px;">
      <p class="eyebrow">COUNSELING BOOKING WEBSITES (LARGE-SCALE V2)</p>
      <h2 style="margin:6px 0 12px 0;">🏥 대규모 예약 서비스 V2 웹사이트 (상담사·슬롯 + 선불 상담권 지갑 + 만석 대기열 자동승격 + 일정변경) — :8120 ~ :8125</h2>
      <table class="data-table">
        <thead>
          <tr>
            <th style="width:155px;">예약 사이트 접속</th>
            <th style="width:170px;">설계 조건</th>
            <th style="width:110px;">요구사항 검증</th>
            <th style="width:170px;">Pytest / 소요 시간</th>
            <th>사이트에서 직접 확인할 수 있는 구현 차이점</th>
          </tr>
        </thead>
        <tbody>{build_rows("large")}</tbody>
      </table>
    </div>

    <div class="surface-card">
      <p class="eyebrow">COUNSELING BOOKING WEBSITES (SMALL-SCALE V1)</p>
      <h2 style="margin:6px 0 12px 0;">📅 소규모 예약 서비스 V1 웹사이트 (기본 1:1 상담 시간 선택 · 예약 · 조회 · 취소) — :8110 ~ :8115</h2>
      <table class="data-table">
        <thead>
          <tr>
            <th style="width:155px;">예약 사이트 접속</th>
            <th style="width:170px;">설계 조건</th>
            <th style="width:110px;">요구사항 검증</th>
            <th style="width:170px;">Pytest / 소요 시간</th>
            <th>사이트에서 직접 확인할 수 있는 구현 차이점</th>
          </tr>
        </thead>
        <tbody>{build_rows("small")}</tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""


def serve_hub_port(port: int = 8100) -> None:
    class HubHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            body = render_hub_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", port), HubHandler)
    server.serve_forever()


def main() -> None:
    procs: list[multiprocessing.Process] = []
    for cfg in RUN_CONFIGS:
        p = multiprocessing.Process(target=serve_condition_port, args=(cfg,), daemon=True)
        p.start()
        procs.append(p)
        print(f"[STARTED] :{cfg['port']} -> {cfg['title']} ({cfg['id']})", flush=True)

    print("[STARTED] :8100 -> Yeobaek Counseling Website Portal", flush=True)
    serve_hub_port(8100)


if __name__ == "__main__":
    main()
