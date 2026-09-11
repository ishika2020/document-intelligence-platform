"""Unit tests for file validation and financial calculation validation."""
from app.services import financial_validation_service as fvs
from app.services.document_validation_service import validate_file


# ---------------------------------------------------------------------------
# File validation
# ---------------------------------------------------------------------------


def test_empty_file_fails_validation():
    result = validate_file("empty.pdf", "application/pdf", b"")
    assert result.status == "FAIL"
    assert result.is_supported is False


def test_unsupported_file_type_fails_validation():
    result = validate_file("notes.txt", "text/plain", b"just some plain text, not a real document")
    assert result.status == "FAIL"
    assert result.is_supported is False
    assert "supported" in result.reason.lower()


def test_corrupted_pdf_fails_validation():
    result = validate_file("broken.pdf", "application/pdf", b"%PDF-1.4\nthis is not a real pdf body")
    assert result.status == "FAIL"
    assert result.is_supported is True  # magic bytes matched PDF
    assert result.is_readable is False


def test_valid_native_pdf_passes_validation(sample_docs_dir):
    data = (sample_docs_dir / "balance_sheet_2020.pdf").read_bytes()
    result = validate_file("balance_sheet_2020.pdf", "application/pdf", data)
    assert result.status == "PASS"
    assert result.page_count == 1


def test_valid_jpeg_passes_validation(sample_docs_dir):
    data = (sample_docs_dir / "invoice_template_sample.jpg").read_bytes()
    result = validate_file("invoice.jpg", "image/jpeg", data)
    assert result.status == "PASS"
    assert result.file_type == "image/jpeg"
    assert result.page_count == 1


def test_file_type_is_sniffed_not_trusted_from_extension(sample_docs_dir):
    """A PDF's real magic bytes should be detected even if the client lies
    about the content type / extension (defends against unsafe uploads)."""
    data = (sample_docs_dir / "balance_sheet_2020.pdf").read_bytes()
    result = validate_file("balance_sheet.exe", "application/octet-stream", data)
    assert result.file_type == "application/pdf"
    assert result.status == "PASS"


# ---------------------------------------------------------------------------
# Financial validation: invoice
# ---------------------------------------------------------------------------


def _field(value):
    return {"value": value}


def test_invoice_total_check_passes_within_tolerance():
    extracted = {
        "subtotal": _field(100.0),
        "tax_amount": _field(5.0),
        "discount": _field(0.0),
        "total_amount": _field(105.0),
    }
    result = fvs.validate_invoice(extracted)
    check = next(c for c in result["checks"] if c["name"] == "invoice_total_check")
    assert check["status"] == "PASS"
    assert result["overall_status"] == "PASS"


def test_invoice_total_check_fails_when_totals_dont_reconcile():
    extracted = {
        "subtotal": _field(100.0),
        "tax_amount": _field(5.0),
        "discount": _field(0.0),
        "total_amount": _field(999.0),  # way off
    }
    result = fvs.validate_invoice(extracted)
    check = next(c for c in result["checks"] if c["name"] == "invoice_total_check")
    assert check["status"] == "FAIL"
    assert result["overall_status"] == "FAIL"
    assert result["issues"]


def test_invoice_validation_not_applicable_when_fields_missing():
    extracted = {"subtotal": None, "tax_amount": None, "discount": _field(0.0), "total_amount": None}
    result = fvs.validate_invoice(extracted)
    assert result["checks"] == []
    assert result["overall_status"] == "NOT_APPLICABLE"


def test_invoice_line_item_quantity_times_price_check():
    extracted = {
        "subtotal": None,
        "tax_amount": None,
        "discount": _field(0.0),
        "total_amount": None,
        "line_items": [{"description": "Widget", "quantity": 3, "unit_price": 10.0, "amount": 30.0}],
    }
    result = fvs.validate_invoice(extracted)
    check = next(c for c in result["checks"] if c["name"] == "line_item_1_total_check")
    assert check["status"] == "PASS"
    assert check["calculated_value"] == 30.0


def test_invoice_cash_change_check():
    extracted = {
        "subtotal": None,
        "tax_amount": None,
        "discount": _field(0.0),
        "total_amount": _field(9.0),
        "cash_paid": _field(50.0),
        "change": _field(41.0),
    }
    result = fvs.validate_invoice(extracted)
    check = next(c for c in result["checks"] if c["name"] == "cash_change_check")
    assert check["status"] == "PASS"


# ---------------------------------------------------------------------------
# Financial validation tolerance behaviour
# ---------------------------------------------------------------------------


def test_tolerance_is_relative_for_large_values():
    # 1% of 10,000,000 = 100,000 -- a variance smaller than that should PASS.
    check = fvs._check("x", "a ≈ b", {}, 10_050_000.0, 10_000_000.0)
    assert check["status"] == "PASS"


def test_tolerance_fails_outside_relative_band():
    check = fvs._check("x", "a ≈ b", {}, 10_500_000.0, 10_000_000.0)
    assert check["status"] == "FAIL"


def test_not_applicable_when_calculated_or_reported_missing():
    check = fvs._check("x", "a ≈ b", {"a": None}, None, 100.0)
    assert check["status"] == "NOT_APPLICABLE"
