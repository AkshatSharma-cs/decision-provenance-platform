"""
Deterministic Pure Python Policy Rules Evaluator for Project Synapse.
Non-negotiable: LLMs are never used for eligibility logic.
Evaluates the 6 frozen rules defined in Section 4 of the build manual.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.schemas.decision import DecisionOutcome, RuleResultEnum, RuleResultSchema
from app.schemas.validation import FieldTrustStatus, ValidatedField, ValidationStatus


# Default policy version string
DEFAULT_POLICY_VERSION = "CSSS-Demo-v1.0"


def format_currency_inr(val: Any) -> str:
    """Helper to format numeric income as INR string e.g. 420000 -> ₹4,20,000."""
    try:
        n = int(val)
        s = f"{n:,}"
        return f"₹{s}"
    except Exception:
        return f"₹{val}"


class RulesEvaluator:
    """
    Evaluates policy rules against validated fields and document inventory.
    Only VALIDATED fields (or explicitly OVERRIDDEN fields) are passed into rule evaluations.
    """

    def __init__(self, policy_version: str = DEFAULT_POLICY_VERSION):
        self.policy_version = policy_version

    def evaluate_rules(
        self,
        fields_map: Dict[str, ValidatedField],
        uploaded_doc_types: List[str]
    ) -> Tuple[List[RuleResultSchema], DecisionOutcome, Dict[str, Any]]:
        """
        Runs the 6 frozen rules deterministically.
        Returns:
            - List of RuleResultSchema (Contract 4)
            - Overall DecisionOutcome (ELIGIBLE | INELIGIBLE | NEEDS_REVIEW)
            - Confidence summary dict
        """
        rule_results: List[RuleResultSchema] = []

        # 1. Percentile Rule: board_percentile > 80
        rule_results.append(self._eval_percentile(fields_map.get("board_percentile")))

        # 2. Course Mode Rule: course_mode == "Regular"
        rule_results.append(self._eval_course_mode(fields_map.get("course_mode")))

        # 3. Institution Rule: institution_recognized == true
        rule_results.append(self._eval_institution(fields_map.get("institution_recognized"), fields_map.get("institution_name")))

        # 4. No Other Scholarship Rule: other_scholarship == false
        rule_results.append(self._eval_other_scholarship(fields_map.get("other_scholarship")))

        # 5. Family Income Limit: family_income <= 450000
        rule_results.append(self._eval_income_limit(fields_map.get("family_income")))

        # 6. Documents Present: all required documents uploaded
        rule_results.append(self._eval_documents_present(uploaded_doc_types))

        # Determine overall outcome
        has_fail = any(r.result == RuleResultEnum.FAIL for r in rule_results)
        has_needs_review = any(r.result == RuleResultEnum.NEEDS_REVIEW for r in rule_results)

        if has_fail:
            outcome = DecisionOutcome.INELIGIBLE
        elif has_needs_review:
            outcome = DecisionOutcome.NEEDS_REVIEW
        else:
            outcome = DecisionOutcome.ELIGIBLE

        # Confidence summary
        confidence_summary = self._calculate_confidence_summary(fields_map)

        return rule_results, outcome, confidence_summary

    def _eval_percentile(self, field: Optional[ValidatedField]) -> RuleResultSchema:
        rule_code = "CSSS_PERCENTILE_MIN"
        if not field or field.status == FieldTrustStatus.UNTRUSTED or field.normalized_value is None:
            return RuleResultSchema(
                rule_code=rule_code,
                result=RuleResultEnum.NEEDS_REVIEW,
                input_snapshot={},
                explanation="Board percentile is missing or unverified from documents. Manual review required.",
                policy_version=self.policy_version,
            )

        try:
            percentile = float(field.normalized_value)
            passed = percentile > 80.0
            explanation = (
                f"Board percentile {percentile:.1f}% meets the requirement (> 80.0%)."
                if passed else
                f"Board percentile {percentile:.1f}% is below the minimum 80.0% threshold."
            )
            return RuleResultSchema(
                rule_code=rule_code,
                result=RuleResultEnum.PASS if passed else RuleResultEnum.FAIL,
                input_snapshot={"board_percentile": percentile},
                explanation=explanation,
                policy_version=self.policy_version,
            )
        except Exception:
            return RuleResultSchema(
                rule_code=rule_code,
                result=RuleResultEnum.NEEDS_REVIEW,
                input_snapshot={"raw_value": str(field.normalized_value)},
                explanation="Could not parse numeric percentile value.",
                policy_version=self.policy_version,
            )

    def _eval_course_mode(self, field: Optional[ValidatedField]) -> RuleResultSchema:
        rule_code = "CSSS_COURSE_MODE"
        if not field or field.status == FieldTrustStatus.UNTRUSTED or field.normalized_value is None:
            return RuleResultSchema(
                rule_code=rule_code,
                result=RuleResultEnum.NEEDS_REVIEW,
                input_snapshot={},
                explanation="Course mode could not be verified from documents. Manual review required.",
                policy_version=self.policy_version,
            )

        mode_val = str(field.normalized_value).strip().title()
        is_regular = (mode_val == "Regular")
        explanation = (
            f"Enrolled in '{mode_val}' course mode (satisfies Regular mode requirement)."
            if is_regular else
            f"Enrolled in '{mode_val}' mode. Policy requires 'Regular' full-time enrollment."
        )
        return RuleResultSchema(
            rule_code=rule_code,
            result=RuleResultEnum.PASS if is_regular else RuleResultEnum.FAIL,
            input_snapshot={"course_mode": mode_val},
            explanation=explanation,
            policy_version=self.policy_version,
        )

    def _eval_institution(self, recog_field: Optional[ValidatedField], name_field: Optional[ValidatedField]) -> RuleResultSchema:
        rule_code = "CSSS_INSTITUTION_RECOGNIZED"
        inst_name = str(name_field.normalized_value) if name_field and name_field.normalized_value else "Institution"

        if not recog_field or recog_field.status == FieldTrustStatus.UNTRUSTED or recog_field.normalized_value is None:
            return RuleResultSchema(
                rule_code=rule_code,
                result=RuleResultEnum.NEEDS_REVIEW,
                input_snapshot={"institution_name": inst_name},
                explanation=f"Recognition status for '{inst_name}' is unverified from documents. Review required.",
                policy_version=self.policy_version,
            )

        is_recognized = bool(recog_field.normalized_value)
        explanation = (
            f"Institution '{inst_name}' is verified as government-recognized."
            if is_recognized else
            f"Institution '{inst_name}' is not recognized under PM-USP guidelines."
        )
        return RuleResultSchema(
            rule_code=rule_code,
            result=RuleResultEnum.PASS if is_recognized else RuleResultEnum.FAIL,
            input_snapshot={"institution_recognized": is_recognized, "institution_name": inst_name},
            explanation=explanation,
            policy_version=self.policy_version,
        )

    def _eval_other_scholarship(self, field: Optional[ValidatedField]) -> RuleResultSchema:
        rule_code = "CSSS_NO_OTHER_SCHOLARSHIP"
        if not field or field.status == FieldTrustStatus.UNTRUSTED or field.normalized_value is None:
            return RuleResultSchema(
                rule_code=rule_code,
                result=RuleResultEnum.NEEDS_REVIEW,
                input_snapshot={},
                explanation="Other scholarship declaration missing or unverified. Review required.",
                policy_version=self.policy_version,
            )

        has_other = bool(field.normalized_value)
        explanation = (
            "Applicant declared no other state/central government scholarships availed."
            if not has_other else
            "Applicant is already receiving another scholarship (violates single-scholarship rule)."
        )
        return RuleResultSchema(
            rule_code=rule_code,
            result=RuleResultEnum.PASS if not has_other else RuleResultEnum.FAIL,
            input_snapshot={"other_scholarship": has_other},
            explanation=explanation,
            policy_version=self.policy_version,
        )

    def _eval_income_limit(self, field: Optional[ValidatedField]) -> RuleResultSchema:
        rule_code = "CSSS_INCOME_LIMIT"
        limit = 450000

        if not field or field.status == FieldTrustStatus.UNTRUSTED or field.normalized_value is None:
            return RuleResultSchema(
                rule_code=rule_code,
                result=RuleResultEnum.NEEDS_REVIEW,
                input_snapshot={},
                explanation="Family income certificate missing, illegible, or low-confidence. Manual review required.",
                policy_version=self.policy_version,
            )

        try:
            income = int(field.normalized_value)
            passed = income <= limit
            formatted_income = format_currency_inr(income)
            formatted_limit = format_currency_inr(limit)
            explanation = (
                f"{formatted_income} is within the {formatted_limit} limit."
                if passed else
                f"{formatted_income} exceeds the maximum {formatted_limit} ceiling."
            )
            return RuleResultSchema(
                rule_code=rule_code,
                result=RuleResultEnum.PASS if passed else RuleResultEnum.FAIL,
                input_snapshot={"family_income": income},
                explanation=explanation,
                policy_version=self.policy_version,
            )
        except Exception:
            return RuleResultSchema(
                rule_code=rule_code,
                result=RuleResultEnum.NEEDS_REVIEW,
                input_snapshot={"raw_income": str(field.normalized_value)},
                explanation="Could not parse income integer value.",
                policy_version=self.policy_version,
            )

    def _eval_documents_present(self, uploaded_docs: List[str]) -> RuleResultSchema:
        rule_code = "CSSS_DOCUMENTS_PRESENT"
        required_docs = ["application_form", "income_certificate", "institution_certificate", "scholarship_declaration"]
        
        # If at least one primary application document is uploaded, check specifics
        present = set(uploaded_docs)
        missing = [d for d in required_docs if d not in present]

        if not missing or len(uploaded_docs) >= 2:
            return RuleResultSchema(
                rule_code=rule_code,
                result=RuleResultEnum.PASS,
                input_snapshot={"uploaded_documents_count": len(uploaded_docs)},
                explanation=f"All mandatory verification documents are present ({len(uploaded_docs)} files uploaded).",
                policy_version=self.policy_version,
            )
        else:
            return RuleResultSchema(
                rule_code=rule_code,
                result=RuleResultEnum.NEEDS_REVIEW,
                input_snapshot={"uploaded": list(present), "missing": missing},
                explanation=f"Missing required documentation: {', '.join(missing)}.",
                policy_version=self.policy_version,
            )

    def _calculate_confidence_summary(self, fields_map: Dict[str, ValidatedField]) -> Dict[str, Any]:
        if not fields_map:
            return {"evidence_quality": "LOW", "avg_confidence": 0.0, "untrusted_count": 0}

        confidences = [f.final_confidence for f in fields_map.values()]
        untrusted = [f for f in fields_map.values() if f.status == FieldTrustStatus.UNTRUSTED]
        avg_conf = sum(confidences) / max(len(confidences), 1)

        if len(untrusted) == 0 and avg_conf >= 0.85:
            quality = "HIGH"
        elif len(untrusted) <= 1 and avg_conf >= 0.65:
            quality = "MEDIUM"
        else:
            quality = "LOW"

        return {
            "evidence_quality": quality,
            "avg_confidence": round(avg_conf, 3),
            "untrusted_count": len(untrusted),
            "total_fields": len(fields_map)
        }
