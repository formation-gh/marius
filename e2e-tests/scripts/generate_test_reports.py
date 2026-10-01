#!/usr/bin/env python3

from __future__ import annotations

import csv
import datetime as dt
import xml.etree.ElementTree as ET
import zipfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "target" / "reporting"
CSV_PATH = REPORT_DIR / "e2e-test-steps.csv"
SUREFIRE_DIR = ROOT / "target" / "surefire-reports"
XLSX_PATH = REPORT_DIR / "pv-recette-tests.xlsx"
PDF_PATH = REPORT_DIR / "pv-recette-tests.pdf"


@dataclass
class StepRow:
    method: str
    case: str
    step: str
    status: str
    detail: str
    duration_ms: int


@dataclass
class TestCaseSummary:
    method: str
    case: str
    status: str
    steps_total: int
    steps_success: int
    steps_failure: int
    duration_ms: int
    comment: str


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    step_rows = read_step_rows(CSV_PATH)
    xml_cases = read_surefire_cases(SUREFIRE_DIR)
    summaries, _ordered_methods = build_summaries(step_rows, xml_cases)
    detail_rows = step_rows or fallback_detail_rows(xml_cases)

    write_xlsx(XLSX_PATH, summaries, detail_rows)
    write_pdf(PDF_PATH, summaries, detail_rows)

    print(f"Excel généré : {XLSX_PATH}")
    print(f"PDF généré : {PDF_PATH}")


def read_step_rows(path: Path) -> list[StepRow]:
    if not path.exists():
        return []

    rows: list[StepRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for line in reader:
            rows.append(
                StepRow(
                    method=line.get("test_method", "").strip(),
                    case=line.get("test_case", "").strip(),
                    step=line.get("step", "").strip(),
                    status=line.get("status", "").strip(),
                    detail=line.get("detail", "").strip(),
                    duration_ms=int(line.get("duration_ms", "0") or 0),
                )
            )
    return rows


def read_surefire_cases(directory: Path) -> dict[str, dict[str, str]]:
    cases: dict[str, dict[str, str]] = {}
    if not directory.exists():
        return cases

    for xml_path in sorted(directory.glob("TEST-*.xml")):
        try:
            tree = ET.parse(xml_path)
        except ET.ParseError:
            continue

        root = tree.getroot()
        for testcase in root.findall(".//testcase"):
            method = testcase.attrib.get("name", "").strip()
            classname = testcase.attrib.get("classname", "").strip()
            time_ms = int(float(testcase.attrib.get("time", "0") or 0) * 1000)
            status = "SUCCES"
            if testcase.find("failure") is not None or testcase.find("error") is not None:
                status = "ECHEC"
            elif testcase.find("skipped") is not None:
                status = "IGNORE"

            cases[method] = {
                "method": method,
                "case": method,
                "classname": classname,
                "status": status,
                "duration_ms": str(time_ms),
            }

    return cases


def build_summaries(
    step_rows: list[StepRow],
    xml_cases: dict[str, dict[str, str]],
) -> tuple[list[TestCaseSummary], list[str]]:
    ordered_methods: list[str] = []
    cases: OrderedDict[str, dict[str, object]] = OrderedDict()

    for step in step_rows:
        if step.method not in cases:
            cases[step.method] = {"case": step.case or step.method, "steps": []}
            ordered_methods.append(step.method)
        cases[step.method]["steps"].append(step)

    for method, info in xml_cases.items():
        if method not in cases:
            cases[method] = {"case": info.get("case", method), "steps": []}
            ordered_methods.append(method)

    summaries: list[TestCaseSummary] = []
    for method in ordered_methods:
        case_info = cases[method]
        steps = case_info["steps"]
        xml_info = xml_cases.get(method, {})
        status = xml_info.get("status", "SUCCES")
        if steps and status == "SUCCES" and any(step.status != "SUCCES" for step in steps):
            status = "ECHEC"

        steps_total = len(steps)
        steps_success = sum(1 for step in steps if step.status == "SUCCES")
        steps_failure = sum(1 for step in steps if step.status != "SUCCES")
        duration_ms = sum(step.duration_ms for step in steps)
        if not duration_ms and xml_info.get("duration_ms"):
            duration_ms = int(xml_info["duration_ms"])

        comment = "OK"
        if status == "ECHEC":
            comment = "Au moins une étape ou un test a échoué."
        elif status == "IGNORE":
            comment = "Test ignoré."

        summaries.append(
            TestCaseSummary(
                method=method,
                case=str(case_info.get("case", method)),
                status=status,
                steps_total=steps_total,
                steps_success=steps_success,
                steps_failure=steps_failure,
                duration_ms=duration_ms,
                comment=comment,
            )
        )

    return summaries, ordered_methods


def fallback_detail_rows(xml_cases: dict[str, dict[str, str]]) -> list[StepRow]:
    rows: list[StepRow] = []
    for method, info in xml_cases.items():
        rows.append(
            StepRow(
                method=method,
                case=info.get("case", method),
                step="Résultat du test",
                status=info.get("status", "SUCCES"),
                detail="Aucune étape détaillée enregistrée.",
                duration_ms=int(info.get("duration_ms", "0") or 0),
            )
        )
    return rows


def write_xlsx(path: Path, summaries: list[TestCaseSummary], detail_rows: list[StepRow]) -> None:
    summary_headers = [
        "Cas de test",
        "Statut global",
        "Étapes exécutées",
        "Étapes réussies",
        "Étapes en échec",
        "Durée totale (ms)",
        "Commentaire",
    ]
    detail_headers = [
        "Cas de test",
        "Étape",
        "Statut",
        "Détail",
        "Durée (ms)",
    ]

    summary_rows = [[
        item.case,
        item.status,
        item.steps_total,
        item.steps_success,
        item.steps_failure,
        item.duration_ms,
        item.comment,
    ] for item in summaries]

    detail_data = [[
        row.case,
        row.step,
        row.status,
        row.detail,
        row.duration_ms,
    ] for row in detail_rows]

    summary_widths = [
        column_width(summary_headers[0], [row[0] for row in summary_rows], 34),
        column_width(summary_headers[1], [row[1] for row in summary_rows], 16),
        column_width(summary_headers[2], [row[2] for row in summary_rows], 18),
        column_width(summary_headers[3], [row[3] for row in summary_rows], 18),
        column_width(summary_headers[4], [row[4] for row in summary_rows], 18),
        column_width(summary_headers[5], [row[5] for row in summary_rows], 18),
        column_width(summary_headers[6], [row[6] for row in summary_rows], 42),
    ]
    detail_widths = [
        column_width(detail_headers[0], [row[0] for row in detail_data], 34),
        column_width(detail_headers[1], [row[1] for row in detail_data], 38),
        column_width(detail_headers[2], [row[2] for row in detail_data], 16),
        column_width(detail_headers[3], [row[3] for row in detail_data], 52),
        column_width(detail_headers[4], [row[4] for row in detail_data], 16),
    ]

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml())
        archive.writestr("_rels/.rels", root_rels_xml())
        archive.writestr("xl/workbook.xml", workbook_xml(["Synthèse", "Détail"]))
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml())
        archive.writestr("xl/styles.xml", styles_xml())
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            worksheet_xml(summary_headers, summary_rows, summary_widths),
        )
        archive.writestr(
            "xl/worksheets/sheet2.xml",
            worksheet_xml(detail_headers, detail_data, detail_widths),
        )


def worksheet_xml(headers: list[str], rows: list[list[object]], widths: list[int]) -> str:
    rows_xml: list[str] = []
    rows_xml.append(row_xml(1, headers, header=True))
    for index, row in enumerate(rows, start=2):
        rows_xml.append(row_xml(index, row))

    cols_xml = "".join(
        f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>' for idx, width in enumerate(widths, start=1)
    )
    dim_last_row = len(rows) + 1
    dim_last_col = column_letter(len(headers))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="A1:{dim_last_col}{dim_last_row}"/>'
        f"<cols>{cols_xml}</cols>"
        "<sheetViews><sheetView workbookViewId=\"0\"/></sheetViews>"
        "<sheetFormatPr defaultRowHeight=\"15\"/>"
        f"<sheetData>{''.join(rows_xml)}</sheetData>"
        "</worksheet>"
    )


def row_xml(row_number: int, values: list[object], header: bool = False) -> str:
    cells = []
    for column_index, value in enumerate(values, start=1):
        ref = f"{column_letter(column_index)}{row_number}"
        cells.append(cell_xml(ref, value, header=header))
    return f'<row r="{row_number}">{"".join(cells)}</row>'


def cell_xml(ref: str, value: object, header: bool = False) -> str:
    if isinstance(value, (int, float)) and not header:
        return f'<c r="{ref}" t="n"><v>{value}</v></c>'
    text = xml_escape(str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def column_width(header: str, values: list[object], cap: int) -> int:
    width = len(header)
    for value in values:
        width = max(width, len(str(value)))
    return min(width + 2, cap)


def write_pdf(path: Path, summaries: list[TestCaseSummary], detail_rows: list[StepRow]) -> None:
    lines: list[str] = []
    today = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    total_cases = len(summaries)
    passed_cases = sum(1 for item in summaries if item.status == "SUCCES")
    failed_cases = sum(1 for item in summaries if item.status == "ECHEC")
    ignored_cases = sum(1 for item in summaries if item.status == "IGNORE")
    total_steps = sum(item.steps_total for item in summaries)

    lines.extend([
        "PV DE RECETTE - TESTS E2E AUTOMATISES",
        f"Date de génération : {today}",
        f"Cas : {total_cases} | Réussis : {passed_cases} | Échecs : {failed_cases} | Ignorés : {ignored_cases}",
        f"Étapes enregistrées : {total_steps}",
        "",
        "SYNTHÈSE",
        fit_row(["Cas de test", "Statut", "Étapes", "OK", "KO", "Durée", "Commentaire"], [34, 10, 7, 5, 5, 10, 40]),
    ])

    for item in summaries:
        lines.append(
            fit_row(
                [
                    item.case,
                    item.status,
                    item.steps_total,
                    item.steps_success,
                    item.steps_failure,
                    item.duration_ms,
                    item.comment,
                ],
                [34, 10, 7, 5, 5, 10, 40],
            )
        )

    lines.extend([
        "",
        "DÉTAIL DES ÉTAPES",
        fit_row(["Cas de test", "Étape", "Statut", "Détail", "Durée"], [28, 36, 10, 42, 8]),
    ])

    for row in detail_rows:
        lines.append(
            fit_row(
                [row.case, row.step, row.status, row.detail, row.duration_ms],
                [28, 36, 10, 42, 8],
            )
        )

    if failed_cases:
        lines.extend([
            "",
            "CONCLUSION : recette non validée, au moins un test ou une étape est en échec.",
        ])
    else:
        lines.extend([
            "",
            "CONCLUSION : recette validée, tous les tests automatisés sont passés.",
        ])

    build_pdf(path, lines)


def fit_row(values: list[object], widths: list[int]) -> str:
    cells = []
    for value, width in zip(values, widths):
        text = str(value)
        if len(text) > width:
            text = text[: max(0, width - 1)] + "…"
        cells.append(text.ljust(width))
    return " | ".join(cells)


def build_pdf(path: Path, lines: list[str]) -> None:
    page_width = 842
    page_height = 595
    margin_left = 40
    margin_top = 40
    font_size = 10
    leading = 12
    lines_per_page = max(1, (page_height - 2 * margin_top) // leading)

    pages = [
        lines[i : i + lines_per_page]
        for i in range(0, len(lines), lines_per_page)
    ]

    objects: list[bytes] = []

    font_id = 1
    content_ids = list(range(2, 2 + len(pages)))
    page_ids = list(range(2 + len(pages), 2 + 2 * len(pages)))
    pages_id = 2 + 2 * len(pages)
    catalog_id = pages_id + 1

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")

    for page_lines in pages:
        content = build_page_stream(page_lines, page_width, page_height, margin_left, margin_top, font_size, leading)
        objects.append(
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream"
        )

    kids = []
    for page_id, content_id in zip(page_ids, content_ids):
        kids.append(page_id)
        objects.append(
            (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii")
        )

    objects.append(
        f"<< /Type /Pages /Kids [{ ' '.join(f'{kid} 0 R' for kid in kids) }] /Count {len(kids)} >>".encode("ascii")
    )
    objects.append(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))

    xref_positions = [0]
    pdf_bytes = bytearray(b"%PDF-1.4\n")
    for index, obj in enumerate(objects, start=1):
        xref_positions.append(len(pdf_bytes))
        pdf_bytes.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf_bytes.extend(obj)
        pdf_bytes.extend(b"\nendobj\n")

    xref_start = len(pdf_bytes)
    pdf_bytes.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf_bytes.extend(b"0000000000 65535 f \n")
    for position in xref_positions[1:]:
        pdf_bytes.extend(f"{position:010d} 00000 n \n".encode("ascii"))
    pdf_bytes.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )

    path.write_bytes(pdf_bytes)


def build_page_stream(
    page_lines: list[str],
    page_width: int,
    page_height: int,
    margin_left: int,
    margin_top: int,
    font_size: int,
    leading: int,
) -> bytes:
    y = page_height - margin_top
    commands = [
        "BT",
        f"/F1 {font_size} Tf",
        f"{leading} TL",
        f"{margin_left} {y} Td",
    ]

    for index, line in enumerate(page_lines):
        if index > 0:
            commands.append("T*")
        commands.append(f"({pdf_escape(line)}) Tj")

    commands.append("ET")
    return "\n".join(commands).encode("cp1252", errors="replace")


def pdf_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "")
    )


def content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>'
    )


def root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def workbook_xml(sheet_names: list[str]) -> str:
    sheets = []
    for index, sheet_name in enumerate(sheet_names, start=1):
        sheets.append(
            f'<sheet name="{xml_escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(sheets)}</sheets>'
        '</workbook>'
    )


def workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet2.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        '</Relationships>'
    )


def styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><color theme="1"/><name val="Calibri"/>'
        '<family val="2"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def column_letter(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


if __name__ == "__main__":
    main()
