from __future__ import annotations

import hashlib
import re
from typing import Any

PREFIX = "api:windows_host / windows_host."
PROJECT_ACTIONS = frozenset({"project_create", "project_update", "project_environment", "project_test"})
PROJECT_CRITERIA_ACTIONS = PROJECT_ACTIONS | {"project_package"}
MAX_CRITERIA_ITEMS = 32


def intact(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if "source_integrity" not in result:
        return True
    integrity = result["source_integrity"]
    return isinstance(integrity, dict) and integrity.get("unchanged") is True


def approved_criteria(results: list[dict[str, Any]]) -> tuple[list[dict[str, str]], bool, str | None]:
    source_result = next((
        item for item in reversed(results)
        if item.get("name") in {PREFIX + action for action in PROJECT_CRITERIA_ACTIONS}
        and item.get("status") == "completed"
        and isinstance(item.get("approved_criteria"), str)
    ), None)
    if source_result is None:
        return [], False, None
    lines = []
    for line in source_result["approved_criteria"].splitlines():
        criterion = re.sub(r"^\d+[.)]\s*", "", line.strip()).lstrip("-*• ").strip()
        if criterion:
            lines.append(criterion)
    fingerprint = source_result.get("criteria_request_sha256")
    if not isinstance(fingerprint, str) or re.fullmatch(r"[a-f0-9]{64}", fingerprint) is None:
        fingerprint = None
    return (
        [
            {"id": f"C{index}", "text": criterion, "status": "not_verified"}
            for index, criterion in enumerate(lines[:MAX_CRITERIA_ITEMS], 1)
        ],
        len(lines) > MAX_CRITERIA_ITEMS,
        fingerprint,
    )


def criteria_headers(criteria: list[dict[str, str]], truncated: bool) -> list[str]:
    if not criteria:
        return []
    checklist = "\n".join(
        f"{item['id']}: HENÜZ DOĞRULANMADI — {item['text']}" for item in criteria
    )
    longest_backtick_run = max((len(run) for run in re.findall(r"`+", checklist)), default=0)
    fence = "`" * max(3, longest_backtick_run + 1)
    headers = [
        "Proje kaydından taşınan model ölçüt taslağı (tamlık ve doğruluk doğrulanmadı):",
        f"{fence}text\n{checklist}\n{fence}",
    ]
    if truncated:
        headers.append("Ölçüt listesi 32 maddeyle sınırlandı; devamı gösterilmiyor.")
    return headers


def _inline_code(value: str, limit: int) -> str:
    text = " ".join(value.split())[:limit]
    fence = "`" * (max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    padding = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{padding}{text}{padding}{fence}"


def _code_block(value: str) -> str:
    fence = "`" * max(3, max((len(run) for run in re.findall(r"`+", value)), default=0) + 1)
    return f"\n{fence}\n{value}\n{fence}"


def acceptance_review_summary(review: dict[str, Any]) -> list[str]:
    result = review.get("result")
    if (
        review.get("status") != "completed" or not isinstance(result, dict)
        or result.get("advisory_only") is not True or not isinstance(result.get("report"), dict)
    ):
        return [
            "Kabul incelemesi: başarısız veya geçersiz sonuç; gereksinimler bağımsız kabul edilmiş sayılmaz.",
        ]
    report = result["report"]
    coverage = report.get("request_coverage")
    coverage_status = coverage.get("status") if isinstance(coverage, dict) else None
    if coverage_status not in {
        "no_obvious_gaps", "gaps_found", "incomplete_original_request", "original_request_unavailable",
    }:
        coverage_status = "durum bilinmiyor"
    lines = [
        "Kabul incelemesi (istemciden bildirilen tavsiye; bağımsız doğrulama değildir): "
        + coverage_status,
    ]
    summary = report.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines.append("İnceleme özeti: " + _inline_code(summary, 600))
    criteria = report.get("criteria")
    if isinstance(criteria, list):
        lines.append("Ölçüt değerlendirmeleri (tavsiye; hiçbiri doğrulanmış değildir):")
        for criterion in criteria[:32]:
            if not isinstance(criterion, dict):
                continue
            criterion_id = criterion.get("id")
            assessment = criterion.get("assessment")
            rationale = criterion.get("rationale")
            if not all(isinstance(value, str) for value in (criterion_id, assessment, rationale)):
                continue
            evidence = criterion.get("evidence")
            source_details = ""
            if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict):
                path, quote = evidence[0].get("path"), evidence[0].get("quote")
                test_id = evidence[0].get("test_id")
                if isinstance(path, str):
                    source_details = "\n  Kaynak: " + _inline_code(path, 60)
                    if isinstance(test_id, str):
                        source_details += "\n  Test kimliği: " + _inline_code(test_id, 120)
                    if isinstance(quote, str):
                        source_details += "\n  Alıntı:" + _code_block(quote)
            lines.append(
                f"- {_inline_code(criterion_id, 12)} ({_inline_code(assessment, 24)}): "
                + _inline_code(rationale, 120) + source_details
            )
    omissions = coverage.get("omissions", []) if isinstance(coverage, dict) else []
    if isinstance(omissions, list):
        for omission in omissions[:8]:
            if not isinstance(omission, dict):
                continue
            quote = omission.get("quote")
            rationale = omission.get("rationale")
            if isinstance(quote, str) and isinstance(rationale, str):
                lines.append(
                    "Olası istek kapsamı açığı: " + _inline_code(quote, 180)
                    + " — " + _inline_code(rationale, 240)
                )
    findings = report.get("findings", [])
    if isinstance(findings, list):
        for finding in findings[:4]:
            if not isinstance(finding, dict):
                continue
            severity = finding.get("severity")
            finding_summary = finding.get("summary")
            if isinstance(severity, str) and isinstance(finding_summary, str):
                lines.append(
                    f"İnceleme bulgusu ({_inline_code(severity, 24)}): "
                    + _inline_code(finding_summary, 240)
                )
    return lines


def apply_program_verification(
    response: dict[str, Any], results: list[dict[str, Any]], original_request: str = "",
) -> dict[str, Any]:
    """Summarize current client-reported execution, never infer requirement coverage."""
    reply = dict(response)
    headers = []
    operations = [
        item for item in results if item.get("name") in {PREFIX + action for action in PROJECT_ACTIONS}
    ]
    if operations:
        criteria, criteria_truncated, criteria_request_hash = approved_criteria(results)
        hash_source = "client_reported_project_marker" if criteria_request_hash else None
        if criteria and criteria_request_hash is None and original_request:
            criteria_request_hash = hashlib.sha256(original_request.encode("utf-8")).hexdigest()
            hash_source = "current_turn_message_fallback"
        latest = operations[-1]
        tests = [item for item in operations if item["name"] == PREFIX + "project_test"]
        test = tests[-1] if tests else None
        evidence = (test or latest)["result"]
        passed = bool(
            test is latest and latest["status"] == "completed" and intact(evidence)
            and evidence.get("passed") is True
        )
        status = "passed" if passed else ("failed" if test is latest else "not_verified")
        reply["program_verification"] = {
            "tests_passed": passed, "test_status": status, "evidence": evidence,
            "requirements_status": "not_verified",
            "criteria": criteria, "criteria_truncated": criteria_truncated,
            "criteria_source": "client_reported_project_marker" if criteria else None,
            "criteria_coverage_verified": False,
            "criteria_request_sha256": criteria_request_hash,
            "criteria_request_hash_source": hash_source,
            "unverified": ["requirement_coverage", "independent_acceptance", "execution_isolation"],
            "scope": "Current client-reported unittest results only; not independent acceptance or a sandbox.",
        }
        acceptance_reviews = [
            item for item in results if item.get("name") == "planner / independent acceptance review"
        ]
        if acceptance_reviews:
            review = acceptance_reviews[-1]
            review_result = review.get("result")
            review_report = (
                review_result.get("report")
                if isinstance(review_result, dict) and isinstance(review_result.get("report"), dict)
                else None
            )
            reply["program_verification"]["acceptance_review"] = {
                "status": "available" if (
                    review_report is not None and review.get("status") == "completed"
                    and isinstance(review_result, dict) and review_result.get("advisory_only") is True
                ) else "failed",
                "source": "client_reported_advisory",
                "advisory_only": True,
                "criteria_coverage_verified": False,
                "request_coverage_status": (
                    review_result.get("request_coverage_status")
                    if isinstance(review_result, dict) else None
                ),
                "report": review_report,
            }
            headers.extend(acceptance_review_summary(review))
        verdict = "Program testleri GEÇTİ" if passed else "Program testleri BAŞARISIZ / doğrulanamadı"
        headers.extend([
            "[Doğrulanmış araç durumu: " + verdict + "]",
            "Gereksinimler: HENÜZ DOĞRULANMADI. Geçen testler tüm kabul maddelerinin kanıtı değildir.",
            "Doğrulanamayanlar: gereksinim kapsamı, bağımsız kabul ve çalıştırma izolasyonu.",
        ])
        headers.extend(criteria_headers(criteria, criteria_truncated))
    packages = [item for item in results if item.get("name") == PREFIX + "project_package"]
    if packages:
        package = packages[-1]
        position = max(index for index, item in enumerate(results) if item["name"] == PREFIX + "project_package")
        changed_after_package = any(
            item.get("name") in {PREFIX + action for action in PROJECT_ACTIONS - {"project_test"}}
            for item in results[position + 1:]
        )
        verified = (
            package["status"] == "completed" and intact(package["result"])
            and package["result"].get("packaged") is True and not changed_after_package
        )
        reply["package_verification"] = {
            "verified": verified, "evidence": package["result"], "requirements_status": "not_verified",
        }
        verdict = "EXE paketleme ve açılış testi GEÇTİ" if verified else "EXE paketleme BAŞARISIZ / doğrulanamadı"
        headers.append("[Doğrulanmış araç durumu: " + verdict + "]")
        if not operations:
            criteria, criteria_truncated, criteria_request_hash = approved_criteria(results)
            headers.append("Gereksinimler: HENÜZ DOĞRULANMADI. Paketleme tüm kabul maddelerinin kanıtı değildir.")
            if criteria:
                reply["package_verification"].update(
                    criteria=criteria, criteria_truncated=criteria_truncated,
                    criteria_source="client_reported_project_marker",
                    criteria_coverage_verified=False, criteria_request_sha256=criteria_request_hash,
                    criteria_request_hash_source="client_reported_project_marker" if criteria_request_hash else None,
                )
                headers.extend(criteria_headers(criteria, criteria_truncated))
    if headers and isinstance(reply.get("message"), dict):
        reply["message"] = {
            **reply["message"],
            "content": "\n".join(headers) + "\n\nModel açıklaması (kabul kanıtı değildir):\n\n"
            + reply["message"].get("content", ""),
        }
    return reply
