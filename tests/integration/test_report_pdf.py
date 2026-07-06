from __future__ import annotations

import re

import pytest

from src import report


pytestmark = pytest.mark.integration


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_pdf_generation_produces_a_valid_nonempty_document(golden_sar, lang: str):
    pdf = report.build_pdf(golden_sar, lang=lang)
    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 3_000
    assert b"/Type /Page" in pdf


def test_long_report_paginates_without_losing_pdf_integrity(golden_sar):
    golden_sar["key_findings"] = golden_sar["key_findings"] * 8
    golden_sar["recommended_actions"] = golden_sar["recommended_actions"] * 5
    golden_sar["narrative"] = " ".join([golden_sar["narrative"]] * 4)
    pdf = report.build_pdf(golden_sar, lang="en")

    # ReportLab writes one /Type /Page object per page plus /Type /Pages.
    pages = len(re.findall(rb"/Type\s*/Page\b", pdf))
    assert pages >= 2
    assert pdf.rstrip().endswith(b"%%EOF")


def test_pdf_builder_does_not_mutate_report(golden_sar):
    before = repr(golden_sar)
    report.build_pdf(golden_sar, lang="ar")
    assert repr(golden_sar) == before
