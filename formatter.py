"""Format raw chunks into the Unity RAG KnowledgeChunk JSON schema.

Includes automatic German medical tag detection so the chunks integrate
seamlessly with the Unity MedicalExam RAG system.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

from chunker import RawChunk

# ---------------------------------------------------------------------------
# German medical keyword → scenario tag mapping
# ---------------------------------------------------------------------------

_GERMAN_TAG_MAP: Dict[str, List[str]] = {
    # History & interview
    "anamnese": ["anamnese", "patient_history"],
    "anamnesegespräch": ["anamnese", "patient_history"],
    "vorgeschichte": ["anamnese", "patient_history"],
    "eigenanamnese": ["anamnese", "patient_history"],
    "familienanamnese": ["anamnese", "patient_history"],
    "sozialanamnese": ["anamnese", "patient_history"],
    # Examination
    "untersuchung": ["examination", "physical_exam"],
    "körperliche untersuchung": ["examination", "physical_exam"],
    "befund": ["examination", "findings"],
    "auskultation": ["examination", "cardiac_auscultation"],
    # Diagnosis
    "diagnose": ["diagnosis", "differential_diagnosis"],
    "differentialdiagnose": ["differential_diagnosis"],
    "diagnostik": ["diagnosis"],
    "befundbericht": ["diagnosis", "report"],
    # Therapy & treatment
    "therapie": ["therapy", "treatment"],
    "behandlung": ["therapy", "treatment"],
    "medikament": ["pharmacology", "medication"],
    "medikamente": ["pharmacology", "medication"],
    "pharmakologie": ["pharmacology"],
    "chirurgie": ["surgery"],
    "operation": ["surgery"],
    # Emergency
    "notfall": ["emergency", "emergency_medicine"],
    "notaufnahme": ["emergency", "emergency_medicine"],
    "reanimation": ["emergency", "resuscitation"],
    "erste hilfe": ["emergency", "first_aid"],
    # Specialties
    "kardiologie": ["cardiology", "cardiovascular"],
    "neurologie": ["neurology"],
    "schlaganfall": ["neurology", "stroke"],
    "orthopädie": ["orthopedics"],
    "pneumologie": ["pulmonology"],
    "gastroenterologie": ["gastroenterology"],
    "pädiatrie": ["pediatrics"],
    "gynäkologie": ["gynecology"],
    "psychiatrie": ["psychiatry"],
    "dermatologie": ["dermatology"],
    "urologie": ["urology"],
    "onkologie": ["oncology"],
    "hämatologie": ["hematology"],
    "endokrinologie": ["endocrinology"],
    "rheumatologie": ["rheumatology"],
    "nephrologie": ["nephrology"],
    "infektiologie": ["infectious_disease"],
    # Communication / FSP specifics
    "arztbrief": ["medical_letter", "documentation"],
    "arzt-patient": ["patient_communication"],
    "aufklärungsgespräch": ["patient_communication", "informed_consent"],
    "fachsprachprüfung": ["fsp", "medical_german"],
    "fachsprache": ["fsp", "medical_german"],
    "kommunikation": ["patient_communication"],
    "übergabe": ["professional_handover"],
    "visite": ["ward_round"],
    "epikrise": ["documentation", "discharge_summary"],
    # Anatomy / physiology
    "anatomie": ["anatomy"],
    "physiologie": ["physiology"],
    "pathologie": ["pathology"],
    "pathophysiologie": ["pathophysiology"],
    # Diagnostics
    "labor": ["laboratory", "lab_values"],
    "laborwerte": ["laboratory", "lab_values"],
    "röntgen": ["radiology", "imaging"],
    "bildgebung": ["radiology", "imaging"],
    "ekg": ["cardiology", "ecg"],
    "sonographie": ["imaging", "ultrasound"],
}

# Pre-compile for fast matching (longest first to avoid partial matches)
_sorted_keys = sorted(_GERMAN_TAG_MAP.keys(), key=len, reverse=True)
_TAG_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _sorted_keys) + r")\b",
    re.IGNORECASE,
)


def _detect_tags(text: str) -> List[str]:
    """Scan text for German medical keywords and return matching tags."""
    found: set[str] = set()
    for match in _TAG_PATTERN.finditer(text):
        keyword = match.group(1).lower()
        tags = _GERMAN_TAG_MAP.get(keyword, [])
        found.update(tags)
    return sorted(found)


def _clean_filename(name: str) -> str:
    """Turn a filename into a safe document-id prefix."""
    name = os.path.splitext(name)[0]
    name = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]+", "_", name)
    name = name.strip("_").lower()
    return name[:60] if name else "document"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class FormattedChunk:
    document_id: str
    category: str
    scenario_tags: List[str]
    clinical_context: str
    section_title: str
    content: str
    token_count: int
    page_start: int
    page_end: int

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "category": self.category,
            "scenario_tags": self.scenario_tags,
            "clinical_context": self.clinical_context,
            "section_title": self.section_title,
            "content": self.content,
            "token_count": self.token_count,
            "page_start": self.page_start,
            "page_end": self.page_end,
        }


from dataclasses import dataclass  # noqa: E402 (already imported but keep for clarity)


def format_chunks(
    raw_chunks: List[RawChunk],
    filename: str,
    category: Optional[str] = None,
    extra_tags: Optional[List[str]] = None,
) -> List[FormattedChunk]:
    """Convert raw chunks into fully-formatted output matching Unity schema.

    Parameters
    ----------
    raw_chunks : list of RawChunk
    filename : original PDF filename (used for document_id prefix)
    category : user-supplied category; auto-detected if None
    extra_tags : additional scenario tags to merge with auto-detected ones
    """

    doc_prefix = _clean_filename(filename)
    extra = set(t.lower().strip() for t in (extra_tags or []) if t.strip())
    result: List[FormattedChunk] = []

    for idx, chunk in enumerate(raw_chunks):
        # Auto-detect tags from content + section title
        auto_tags = set(_detect_tags(chunk.text))
        auto_tags.update(_detect_tags(chunk.section_title))
        auto_tags.update(_detect_tags(chunk.parent_chapter))
        all_tags = sorted(auto_tags | extra) or ["general_medical"]

        # Auto-detect category from parent chapter if not provided
        cat = category
        if not cat:
            chapter_tags = _detect_tags(chunk.parent_chapter)
            cat = chapter_tags[0].replace("_", " ").title() if chapter_tags else "Medical Knowledge"

        # Clinical context from section title + chapter
        clinical_ctx = f"{chunk.parent_chapter} — {chunk.section_title}".strip(" —")

        doc_id = f"{doc_prefix}_ch{idx:04d}"

        result.append(FormattedChunk(
            document_id=doc_id,
            category=cat,
            scenario_tags=all_tags,
            clinical_context=clinical_ctx,
            section_title=chunk.section_title,
            content=chunk.text,
            token_count=chunk.token_count,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
        ))

    return result
