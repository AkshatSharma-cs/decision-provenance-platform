"""
ReportLab PDF Decision Audit Report Generation.
Produces verifiable decision provenance audit reports for applications.
"""

from __future__ import annotations

import html
import io
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
)

from app.db.models import Application, Decision
from app.services.replay_service import ReplayService


class ReportService:
    """
    Generates downloadable PDF Decision Audit Trail reports.
    """

    @staticmethod
    def generate_audit_report_pdf(db: Session, application_id: str) -> Optional[bytes]:
        replay_data = ReplayService.reconstruct_replay(db, application_id)
        if not replay_data:
            return None

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        
        # Custom palette
        NAVY = colors.HexColor("#12304A")
        SLATE = colors.HexColor("#405466")
        TEAL = colors.HexColor("#0F766E")
        AMBER = colors.HexColor("#B45309")
        RED = colors.HexColor("#B91C1C")
        BG_LIGHT = colors.HexColor("#F5F7FA")

        TEAL_HEX = "#0F766E"
        AMBER_HEX = "#B45309"
        RED_HEX = "#B91C1C"

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontSize=18,
            leading=22,
            textColor=NAVY,
            spaceAfter=4,
        )
        subtitle_style = ParagraphStyle(
            'DocSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            textColor=SLATE,
            spaceAfter=12,
        )
        section_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontSize=12,
            leading=16,
            textColor=NAVY,
            spaceBefore=10,
            spaceAfter=6,
        )
        cell_style = ParagraphStyle(
            'TableCell',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            textColor=NAVY,
        )
        cell_mono = ParagraphStyle(
            'TableCellMono',
            parent=styles['Normal'],
            fontSize=7,
            leading=9,
            fontName="Courier",
            textColor=SLATE,
        )

        story = []

        # 1. Header
        story.append(Paragraph("PROJECT SYNAPSE — EVIDENCE-GROUNDED DECISION AUDIT", title_style))
        story.append(Paragraph("Decision Provenance Platform for AI-Assisted Government Workflows | SIH 2026", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=10))

        # 2. Executive Summary Block
        raw_outcome = replay_data.latest_decision.outcome if replay_data.latest_decision else "PENDING"
        outcome_str = raw_outcome.value if hasattr(raw_outcome, "value") else str(raw_outcome)
        outcome_color_hex = TEAL_HEX if outcome_str == "ELIGIBLE" else (AMBER_HEX if outcome_str == "NEEDS_REVIEW" else RED_HEX)
        
        raw_mode = replay_data.latest_decision.decision_mode if replay_data.latest_decision else "N/A"
        mode_str = raw_mode.value if hasattr(raw_mode, "value") else str(raw_mode)

        summary_data = [
            [
                Paragraph("<b>Application Ref:</b>", cell_style),
                Paragraph(html.escape(replay_data.public_reference), cell_style),
                Paragraph("<b>Final Outcome:</b>", cell_style),
                Paragraph(f"<font color='{outcome_color_hex}'><b>{html.escape(outcome_str)}</b></font>", cell_style),
            ],
            [
                Paragraph("<b>Applicant Name:</b>", cell_style),
                Paragraph(html.escape(replay_data.applicant_name or "N/A"), cell_style),
                Paragraph("<b>Decision Mode:</b>", cell_style),
                Paragraph(html.escape(mode_str), cell_style),
            ],
            [
                Paragraph("<b>Scheme Code:</b>", cell_style),
                Paragraph(html.escape(replay_data.scheme_code), cell_style),
                Paragraph("<b>Policy Version:</b>", cell_style),
                Paragraph(html.escape(replay_data.current_policy_version), cell_style),
            ],
            [
                Paragraph("<b>Audit Status:</b>", cell_style),
                Paragraph("<font color='#0F766E'><b>VERIFIED HASH CHAIN</b></font>" if replay_data.audit_chain_verification.verified else "<font color='#B91C1C'><b>TAMPER DETECTED</b></font>", cell_style),
                Paragraph("<b>Decision Version:</b>", cell_style),
                Paragraph(f"v{replay_data.latest_decision.decision_version if replay_data.latest_decision else 1}", cell_style),
            ]
        ]
        summary_table = Table(summary_data, colWidths=[110, 160, 110, 160])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#D1D5DB")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 10))

        # 3. Documents & Integrity Hashes
        story.append(Paragraph("1. Uploaded Evidence Documents & Cryptographic Hashes", section_style))
        doc_data = [[
            Paragraph("<b>Document Type</b>", cell_style),
            Paragraph("<b>File Name</b>", cell_style),
            Paragraph("<b>SHA-256 Hash</b>", cell_style),
        ]]
        for doc_item in replay_data.documents:
            doc_data.append([
                Paragraph(html.escape(str(doc_item.doc_type)), cell_style),
                Paragraph(html.escape(str(doc_item.file_name)), cell_style),
                Paragraph(html.escape(str(doc_item.file_hash)), cell_mono),
            ])
        doc_table = Table(doc_data, colWidths=[140, 150, 250])
        doc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(doc_table)
        story.append(Spacer(1, 10))

        # 4. Validated Extracted Fields & Evidence Quotes
        story.append(Paragraph("2. Extracted Fields & Grounded Evidence Quotes", section_style))
        fields_data = [[
            Paragraph("<b>Field Name</b>", cell_style),
            Paragraph("<b>Normalized Value</b>", cell_style),
            Paragraph("<b>Trust Status</b>", cell_style),
            Paragraph("<b>Conf.</b>", cell_style),
            Paragraph("<b>Evidence Quote (Ground Truth)</b>", cell_style),
        ]]
        for f in replay_data.extracted_fields:
            status_str = f.status.value if hasattr(f.status, "value") else str(f.status)
            status_color_hex = TEAL_HEX if status_str == "VALIDATED" else (AMBER_HEX if status_str == "OVERRIDDEN" else RED_HEX)
            field_name_str = f.field_name.value if hasattr(f.field_name, "value") else str(f.field_name)
            norm_val_str = str(f.normalized_value) if f.normalized_value is not None else "—"
            quote_str = f.evidence_quote or "No direct text match"

            fields_data.append([
                Paragraph(html.escape(field_name_str), cell_style),
                Paragraph(html.escape(norm_val_str), cell_style),
                Paragraph(f"<font color='{status_color_hex}'>{html.escape(status_str)}</font>", cell_style),
                Paragraph(f"{f.final_confidence:.2f}", cell_style),
                Paragraph(html.escape(quote_str), cell_style),
            ])
        fields_table = Table(fields_data, colWidths=[110, 85, 75, 40, 230])
        fields_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(fields_table)
        story.append(Spacer(1, 10))

        # 5. Deterministic Rules Evaluation
        story.append(Paragraph("3. Deterministic Policy Rules Evaluation (Pure Python)", section_style))
        if replay_data.latest_decision and replay_data.latest_decision.rule_results:
            rules_data = [[
                Paragraph("<b>Rule Code</b>", cell_style),
                Paragraph("<b>Result</b>", cell_style),
                Paragraph("<b>Explanation & Input Snapshot</b>", cell_style),
            ]]
            for r in replay_data.latest_decision.rule_results:
                r_result_str = r.result.value if hasattr(r.result, "value") else str(r.result)
                res_color_hex = TEAL_HEX if r_result_str == "PASS" else (AMBER_HEX if r_result_str == "NEEDS_REVIEW" else RED_HEX)
                explanation_str = f"{r.explanation} ({r.input_snapshot})"

                rules_data.append([
                    Paragraph(html.escape(str(r.rule_code)), cell_style),
                    Paragraph(f"<font color='{res_color_hex}'><b>{html.escape(r_result_str)}</b></font>", cell_style),
                    Paragraph(html.escape(explanation_str), cell_style),
                ])
            rules_table = Table(rules_data, colWidths=[160, 80, 300])
            rules_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ('PADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(rules_table)
        story.append(Spacer(1, 10))

        # 6. Cryptographic Hash-Chain Trail
        story.append(Paragraph("4. Immutable Audit Trail & SHA-256 Hash Chain", section_style))
        audit_data = [[
            Paragraph("<b>Timestamp (UTC)</b>", cell_style),
            Paragraph("<b>Action Type</b>", cell_style),
            Paragraph("<b>Actor</b>", cell_style),
            Paragraph("<b>Entry SHA-256 Hash</b>", cell_style),
        ]]
        for item in replay_data.timeline[:8]:  # show up to first 8 key events
            audit_data.append([
                Paragraph(html.escape(str(item.occurred_at)), cell_mono),
                Paragraph(html.escape(str(item.action_type)), cell_style),
                Paragraph(html.escape(str(item.actor_id)), cell_style),
                Paragraph(html.escape(str(item.entry_hash[:32]) + "..."), cell_mono),
            ])
        audit_table = Table(audit_data, colWidths=[120, 140, 80, 200])
        audit_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(audit_table)
        story.append(Spacer(1, 14))

        # Footer note
        story.append(Paragraph(
            "<i>This official document is generated from an immutable, cryptographically verifiable hash chain. "
            "Any tampering with payloads or event sequences immediately invalidates the signature chain.</i>",
            cell_style
        ))

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
