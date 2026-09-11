"""Financial calculation validation.

Implements the minimum financial validation rules from the case study spec
(section 4.4) for each document type. Every check reports the formula used,
the operand values, the calculated vs. reported value, the variance and a
PASS / FAIL / NOT_APPLICABLE status. A check is NOT_APPLICABLE (never
FAIL) whenever a field it needs was not present in the source document --
we never assume or invent a value to force a check to run.
"""
from app.core.config import get_settings
from app.services import financial_statement_parser as fsp

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _tolerance(reported: float) -> float:
    settings = get_settings()
    return max(settings.validation_tolerance_abs, abs(reported) * settings.validation_tolerance_pct)


def _check(
    name: str,
    formula: str,
    operands: dict,
    calculated: float | None,
    reported: float | None,
    period: str | None = None,
    not_applicable_reason: str | None = None,
) -> dict:
    if calculated is None or reported is None:
        return {
            "name": name,
            "formula": formula,
            "operands": operands,
            "calculated_value": round(calculated, 2) if calculated is not None else None,
            "reported_value": round(reported, 2) if reported is not None else None,
            "variance": None,
            "status": "NOT_APPLICABLE",
            "period": period,
            "message": not_applicable_reason or "Required field(s) for this check were not found in the document.",
        }
    variance = round(calculated - reported, 2)
    status = "PASS" if abs(variance) <= _tolerance(reported) else "FAIL"
    message = None
    if status == "FAIL":
        message = f"Calculated value differs from reported value by {variance:+.2f} (tolerance exceeded)."
    return {
        "name": name,
        "formula": formula,
        "operands": operands,
        "calculated_value": round(calculated, 2),
        "reported_value": round(reported, 2),
        "variance": variance,
        "status": status,
        "period": period,
        "message": message,
    }


def _sum_required(**operands: float | None) -> tuple[float | None, dict]:
    if any(v is None for v in operands.values()):
        return None, operands
    return sum(operands.values()), operands


def _finalize(checks: list[dict]) -> dict:
    issues = [c["message"] for c in checks if c["status"] == "FAIL" and c.get("message")]
    statuses = {c["status"] for c in checks}
    if not checks:
        overall = "NOT_APPLICABLE"
    elif "FAIL" in statuses:
        overall = "FAIL"
    elif "PASS" in statuses:
        overall = "PASS"
    else:
        overall = "NOT_APPLICABLE"
    return {"checks": checks, "overall_status": overall, "issues": issues}


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


def validate_invoice(extracted_data: dict) -> dict:
    checks: list[dict] = []

    def val(field_name: str) -> float | None:
        f = extracted_data.get(field_name)
        return f.get("value") if isinstance(f, dict) else None

    line_items = extracted_data.get("line_items") or []
    line_item_sum = 0.0
    any_line_amount = False
    for idx, item in enumerate(line_items, start=1):
        qty, unit_price, amount = item.get("quantity"), item.get("unit_price"), item.get("amount")
        if amount is not None:
            line_item_sum += amount
            any_line_amount = True
        if qty is not None and unit_price is not None and amount is not None:
            calculated = qty * unit_price
            checks.append(
                _check(
                    f"line_item_{idx}_total_check",
                    "quantity * unit_price",
                    {"quantity": qty, "unit_price": unit_price},
                    calculated,
                    amount,
                )
            )

    subtotal, tax_amount, discount, total_amount = (
        val("subtotal"), val("tax_amount"), val("discount") or 0.0, val("total_amount"),
    )

    if any_line_amount:
        # GST/VAT-inclusive templates show line totals reconciling straight to
        # the grand total; net-of-tax templates reconcile to the subtotal.
        target_field, target_value = ("subtotal", subtotal) if subtotal is not None else ("total_amount", total_amount)
        checks.append(
            _check(
                "line_items_sum_check",
                f"sum(line_item.amount) ≈ {target_field}",
                {"sum_of_line_items": round(line_item_sum, 2)},
                line_item_sum,
                target_value,
                not_applicable_reason=f"No reported {target_field} to reconcile the line-item sum against.",
            )
        )

    if subtotal is not None and tax_amount is not None:
        calculated = subtotal + tax_amount - discount
        checks.append(
            _check(
                "invoice_total_check",
                "subtotal + tax_amount - discount",
                {"subtotal": subtotal, "tax_amount": tax_amount, "discount": discount},
                calculated,
                total_amount,
                not_applicable_reason="Total amount was not extracted from the document.",
            )
        )

    cash_paid, change = val("cash_paid"), val("change")
    if cash_paid is not None and change is not None and total_amount is not None:
        calculated = cash_paid - total_amount
        checks.append(
            _check(
                "cash_change_check",
                "cash_paid - total_amount",
                {"cash_paid": cash_paid, "total_amount": total_amount},
                calculated,
                change,
            )
        )

    return _finalize(checks)


# ---------------------------------------------------------------------------
# Balance Sheet
# ---------------------------------------------------------------------------


def _period_count(statement: fsp.FinancialStatement) -> int:
    max_values = max((len(li.values) for li in statement.line_items if not li.is_header), default=0)
    return min(max_values, 2) or 1


def _period_label(statement: fsp.FinancialStatement, index: int) -> str:
    if index < len(statement.period_labels):
        return statement.period_labels[index]
    return "current_period" if index == 0 else f"period_{index + 1}"


def validate_balance_sheet(statement: fsp.FinancialStatement) -> dict:
    checks: list[dict] = []
    fl = fsp.find_line

    for idx in range(_period_count(statement)):
        period = _period_label(statement, idx)

        total_assets_item = fl(statement, ["total"], ["assets"])
        total_cl_item = fl(statement, ["total"], ["capital and liabilities"])
        total_assets = total_assets_item.values[idx] if total_assets_item and idx < len(total_assets_item.values) else None
        total_cl = total_cl_item.values[idx] if total_cl_item and idx < len(total_cl_item.values) else None

        checks.append(
            _check(
                "total_capital_liabilities_vs_total_assets",
                "Total Capital & Liabilities ≈ Total Assets",
                {"total_capital_and_liabilities": total_cl, "total_assets": total_assets},
                total_cl,
                total_assets,
                period=period,
            )
        )

        cl_components = fsp.find_lines_in_section(statement, ["capital and liabilities"])
        cl_sum, cl_operands = _components_sum(cl_components, idx)
        checks.append(
            _check(
                "capital_and_liabilities_components_reconciliation",
                "sum(capital & liability components) ≈ reported Total Capital & Liabilities",
                cl_operands,
                cl_sum,
                total_cl,
                period=period,
                not_applicable_reason="Insufficient capital & liability line items were extracted to reconcile.",
            )
        )

        asset_components = fsp.find_lines_in_section(statement, ["assets"])
        asset_sum, asset_operands = _components_sum(asset_components, idx)
        checks.append(
            _check(
                "asset_components_reconciliation",
                "sum(asset components) ≈ reported Total Assets",
                asset_operands,
                asset_sum,
                total_assets,
                period=period,
                not_applicable_reason="Insufficient asset line items were extracted to reconcile.",
            )
        )

    return _finalize(checks)


def _components_sum(components: list[fsp.LineItem], period_index: int) -> tuple[float | None, dict]:
    operands = {}
    total = 0.0
    found_any = False
    for li in components:
        if period_index < len(li.values):
            operands[li.label] = li.values[period_index]
            total += li.values[period_index]
            found_any = True
    if not found_any:
        return None, operands
    return total, operands


# ---------------------------------------------------------------------------
# Profit & Loss
# ---------------------------------------------------------------------------


def validate_profit_and_loss(statement: fsp.FinancialStatement) -> dict:
    checks: list[dict] = []
    fl = fsp.find_line

    lines = {
        "interest_earned": fl(statement, ["interest earned"]),
        "other_income": fl(statement, ["other income"]),
        "total_income": fl(statement, ["total"], ["income"]),
        "interest_expended": fl(statement, ["interest expended"]),
        "operating_expenses": fl(statement, ["operating expenses"]),
        "provisions_and_contingencies": fl(statement, ["provisions and contingencies"]),
        "total_expenditure": fl(statement, ["total"], ["expenditure"]),
        "net_profit_before_minority": fl(statement, ["net profit for the year"]),
        "minority_interest": fl(statement, ["minority interest"]),
        "consolidated_net_profit": fl(statement, ["consolidated profit for the year"]),
        "brought_forward_profit": fl(statement, ["brought forward"]),
        "total_available_for_appropriation": fl(statement, ["total"], ["appropriations"]),
    }

    def v(key: str, idx: int) -> float | None:
        item = lines[key]
        return item.values[idx] if item and idx < len(item.values) else None

    for idx in range(_period_count(statement)):
        period = _period_label(statement, idx)

        interest_earned, other_income = v("interest_earned", idx), v("other_income", idx)
        calc, operands = _sum_required(interest_earned=interest_earned, other_income=other_income)
        checks.append(
            _check(
                "total_income_check", "Interest Earned + Other Income ≈ Total Income",
                operands, calc, v("total_income", idx), period=period,
            )
        )

        calc, operands = _sum_required(
            interest_expended=v("interest_expended", idx),
            operating_expenses=v("operating_expenses", idx),
            provisions_and_contingencies=v("provisions_and_contingencies", idx),
        )
        checks.append(
            _check(
                "total_expenditure_check",
                "Interest Expended + Operating Expenses + Provisions & Contingencies ≈ Total Expenditure",
                operands, calc, v("total_expenditure", idx), period=period,
            )
        )

        total_income, total_expenditure = v("total_income", idx), v("total_expenditure", idx)
        calc = total_income - total_expenditure if total_income is not None and total_expenditure is not None else None
        checks.append(
            _check(
                "net_profit_before_minority_interest_check",
                "Total Income - Total Expenditure ≈ Consolidated Net Profit before Minority Interest",
                {"total_income": total_income, "total_expenditure": total_expenditure},
                calc, v("net_profit_before_minority", idx), period=period,
            )
        )

        profit_before_minority, minority_interest = v("net_profit_before_minority", idx), v("minority_interest", idx)
        calc = (
            profit_before_minority - minority_interest
            if profit_before_minority is not None and minority_interest is not None
            else None
        )
        checks.append(
            _check(
                "consolidated_net_profit_check",
                "Profit before Minority Interest - Minority Interest ≈ Consolidated Net Profit attributable to Group",
                {"profit_before_minority_interest": profit_before_minority, "minority_interest": minority_interest},
                calc, v("consolidated_net_profit", idx), period=period,
            )
        )

        current_profit, brought_forward = v("consolidated_net_profit", idx), v("brought_forward_profit", idx)
        calc, operands = _sum_required(current_profit=current_profit, brought_forward_profit=brought_forward)
        checks.append(
            _check(
                "total_available_for_appropriation_check",
                "Current Profit + Brought Forward Profit ≈ Total Available for Appropriation",
                operands, calc, v("total_available_for_appropriation", idx), period=period,
                not_applicable_reason="Appropriation section fields were not present/extracted for this period.",
            )
        )

    return _finalize(checks)


# ---------------------------------------------------------------------------
# Cash Flow Statement
# ---------------------------------------------------------------------------


def validate_cash_flow_statement(statement: fsp.FinancialStatement) -> dict:
    checks: list[dict] = []
    fl = fsp.find_line

    lines = {
        "operating": fl(statement, ["net cash flow"], ["operating"]),
        "investing": fl(statement, ["net cash flow"], ["investing"]),
        "financing": fl(statement, ["net cash flow"], ["financing"]),
        "fx": fl(statement, ["exchange fluctuation"]),
        "net_change": fl(statement, ["net increase"]),
        "opening": fl(statement, ["as at april"]),
        "amalgamation": fl(statement, ["amalgamation"]),
        "closing": fl(statement, ["as at march"]),
    }

    def v(key: str, idx: int) -> float | None:
        item = lines[key]
        return item.values[idx] if item and idx < len(item.values) else None

    for idx in range(_period_count(statement)):
        period = _period_label(statement, idx)

        operating, investing, financing = v("operating", idx), v("investing", idx), v("financing", idx)
        fx = v("fx", idx) or 0.0
        if operating is not None and investing is not None and financing is not None:
            calc = operating + investing + financing + fx
            operands = {"operating_cash_flow": operating, "investing_cash_flow": investing,
                        "financing_cash_flow": financing, "fx_translation_adjustment": fx}
        else:
            calc = None
            operands = {"operating_cash_flow": operating, "investing_cash_flow": investing,
                        "financing_cash_flow": financing, "fx_translation_adjustment": v("fx", idx)}
        checks.append(
            _check(
                "net_change_in_cash_check",
                "Operating + Investing + Financing Cash Flow + FX/Translation Adjustment ≈ Net Increase in Cash",
                operands, calc, v("net_change", idx), period=period,
            )
        )

        opening, net_change, closing = v("opening", idx), v("net_change", idx), v("closing", idx)
        amalgamation = v("amalgamation", idx) or 0.0
        if opening is not None and net_change is not None:
            calc = opening + net_change + amalgamation
            operands = {"opening_cash": opening, "net_change_in_cash": net_change,
                        "cash_acquired_on_amalgamation": amalgamation}
        else:
            calc = None
            operands = {"opening_cash": opening, "net_change_in_cash": net_change,
                        "cash_acquired_on_amalgamation": v("amalgamation", idx)}
        checks.append(
            _check(
                "closing_cash_check",
                "Opening Cash + Net Increase in Cash + Cash Acquired on Amalgamation/Other Adjustments ≈ Closing Cash",
                operands, calc, closing, period=period,
            )
        )

    return _finalize(checks)


_VALIDATORS = {
    "balance_sheet": validate_balance_sheet,
    "profit_and_loss": validate_profit_and_loss,
    "cash_flow_statement": validate_cash_flow_statement,
}


def validate(document_type: str, extracted_data: dict, statement: fsp.FinancialStatement | None) -> dict:
    if document_type == "invoice":
        return validate_invoice(extracted_data)
    validator = _VALIDATORS.get(document_type)
    if validator is None or statement is None:
        return _finalize([])
    return validator(statement)
