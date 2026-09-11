"""Extraction-service tests run against the real sample documents shipped in
sample_documents/, so they double as a regression check on OCR + parsing."""
from app.services import extraction_service as es
from app.services import ocr_service


def _content(sample_docs_dir, filename, mime):
    data = (sample_docs_dir / filename).read_bytes()
    return ocr_service.extract_document_content(data, mime)


def test_extract_balance_sheet_core_fields(sample_docs_dir):
    content = _content(sample_docs_dir, "balance_sheet_2020.pdf", "application/pdf")
    result = es.extract("balance_sheet", content)
    data = result.extracted_data

    assert data["statement_title"] == "Consolidated Balance Sheet"
    assert data["currency"] == "INR"
    assert data["total_assets"]["value"] == 15_808_304_373.0
    assert data["capital_and_liabilities_total"]["value"] == 15_808_304_373.0
    assert len(data["line_items"]) > 10


def test_extract_profit_and_loss_core_fields(sample_docs_dir):
    content = _content(sample_docs_dir, "profit_and_loss_2020.pdf", "application/pdf")
    result = es.extract("profit_and_loss", content)
    data = result.extracted_data

    assert data["interest_earned"]["value"] == 1_221_892_915.0
    assert data["other_income"]["value"] == 248_789_748.0
    assert data["total_income"]["value"] == 1_470_682_663.0
    assert data["consolidated_net_profit"]["value"] == 272_539_506.0


def test_extract_cash_flow_statement_core_fields(sample_docs_dir):
    content = _content(sample_docs_dir, "cash_flow_statement_2020.pdf", "application/pdf")
    result = es.extract("cash_flow_statement", content)
    data = result.extracted_data

    assert data["operating_cash_flow"]["value"] == -168_690_920.0
    assert data["investing_cash_flow"]["value"] == -16_169_244.0
    assert data["financing_cash_flow"]["value"] == 243_944_969.0
    assert data["opening_cash"]["value"] == 818_176_423.0
    assert data["closing_cash"]["value"] == 879_401_119.0


def test_extract_invoice_fields_from_scanned_image(sample_docs_dir):
    content = _content(sample_docs_dir, "invoice_template_sample.jpg", "image/jpeg")
    result = es.extract("invoice", content)
    data = result.extracted_data

    assert data["invoice_number"]["value"] == "94404257"
    assert data["invoice_date"]["value"] == "2013-03-07"
    assert data["vendor_name"]["value"] == "Cruz PLC"
    assert data["customer_name"]["value"] == "Sandoval-Phillips"
    assert data["total_amount"]["value"] == 138.9
    assert len(data["line_items"]) == 7


def test_missing_fields_are_null_not_invented(sample_docs_dir):
    """A receipt with no customer name printed on it must report null, not a guess."""
    content = _content(sample_docs_dir, "invoice_receipt_sample1.jpg", "image/jpeg")
    result = es.extract("invoice", content)
    assert result.extracted_data["customer_name"] is None
