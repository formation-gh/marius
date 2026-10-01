#!/usr/bin/env python3

from __future__ import annotations

import csv
import datetime as dt
import os
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
DEFAULT_PROJECT_NAME = "formation-gh-api"
DEFAULT_TARGET_URL = "https://aouzgaga.github.io/formation-gh-api/"
DEFAULT_ENVIRONMENT = "Application publiée sur GitHub Pages"


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


@dataclass
class ScenarioReport:
    title: str
    objective: str
    expected: str
    obtained: str
    status: str
    details: str
    step_count: int


@dataclass
class ReportMetadata:
    project_name: str
    lot_name: str
    version_label: str
    environment: str
    target_url: str
    recipe_date: str
    generation_date: str
    execution_reference: str
    validation_name: str
    validation_role: str
    validation_signature: str


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    step_rows = read_step_rows(CSV_PATH)
    xml_cases = read_surefire_cases(SUREFIRE_DIR)
    summaries, _ordered_methods = build_summaries(step_rows, xml_cases)
    metadata = collect_metadata()
    scenarios = build_scenario_reports(summaries, step_rows)
    detail_rows = step_rows or fallback_detail_rows(xml_cases)

    write_xlsx(XLSX_PATH, summaries, detail_rows)
    write_pdf(PDF_PATH, metadata, summaries, scenarios)

    print(f"Excel généré : {XLSX_PATH}")
    print(f"PDF généré : {PDF_PATH}")


def collect_metadata() -> ReportMetadata:
    today = dt.datetime.now().strftime("%d/%m/%Y")
    generation_date = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    commit_sha = os.environ.get("GITHUB_SHA", "").strip()
    short_sha = commit_sha[:7] if commit_sha else ""
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    workflow = os.environ.get("GITHUB_WORKFLOW", "").strip()
    project_name = os.environ.get("PV_PROJECT_NAME", "").strip() or DEFAULT_PROJECT_NAME
    lot_name = os.environ.get("PV_LOT_NAME", "").strip() or os.environ.get("GITHUB_REF_NAME", "").strip() or "non renseigné"
    version_label = os.environ.get("PV_VERSION_LABEL", "").strip()
    if not version_label and short_sha:
        version_label = f"commit {short_sha}"
    if not version_label:
        version_label = "non renseigné"

    environment = os.environ.get("PV_ENVIRONMENT", "").strip() or DEFAULT_ENVIRONMENT
    target_url = os.environ.get("PV_TARGET_URL", "").strip() or DEFAULT_TARGET_URL
    execution_reference = os.environ.get("PV_EXECUTION_REFERENCE", "").strip()
    if not execution_reference and workflow and run_number:
        execution_reference = f"{workflow} #{run_number}"
    elif not execution_reference and run_id:
        execution_reference = f"run GitHub Actions #{run_id}"
    if not execution_reference:
        execution_reference = "non renseigné"

    return ReportMetadata(
        project_name=project_name,
        lot_name=lot_name,
        version_label=version_label,
        environment=environment,
        target_url=target_url,
        recipe_date=today,
        generation_date=generation_date,
        execution_reference=execution_reference,
        validation_name=os.environ.get("PV_VALIDATION_NAME", "").strip() or "non renseigné",
        validation_role=os.environ.get("PV_VALIDATION_ROLE", "").strip() or "non renseigné",
        validation_signature=os.environ.get("PV_VALIDATION_SIGNATURE", "").strip() or "non renseigné",
    )


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


def build_scenario_reports(
    summaries: list[TestCaseSummary],
    step_rows: list[StepRow],
) -> list[ScenarioReport]:
    step_groups: dict[str, list[StepRow]] = {}
    for row in step_rows:
        step_groups.setdefault(row.method, []).append(row)

    reports: list[ScenarioReport] = []
    for summary in summaries:
        business = business_texts(summary.case)
        obtained = business["obtained_ok"]
        status = scenario_status(summary)
        failed_details = [
            row.detail for row in step_groups.get(summary.method, []) if row.status != "SUCCES" and row.detail
        ]
        if status != "OK":
            if failed_details:
                obtained = failed_details[0]
            else:
                obtained = business["obtained_ko"]
        elif summary.status == "IGNORE":
            obtained = business["obtained_partial"]

        if status == "Partiel" and failed_details:
            obtained = failed_details[0]

        detail_parts = [
            f"{summary.steps_success}/{summary.steps_total} étape(s) réussie(s)",
            f"Durée totale : {summary.duration_ms} ms" if summary.duration_ms else "Durée totale : non renseigné",
        ]
        if failed_details:
            detail_parts.append(f"Anomalie observée : {failed_details[0]}")

        reports.append(
            ScenarioReport(
                title=summary.case or summary.method,
                objective=business["objective"],
                expected=business["expected"],
                obtained=obtained,
                status=status,
                details=" | ".join(detail_parts),
                step_count=summary.steps_total,
            )
        )

    return reports


def business_texts(case_name: str) -> dict[str, str]:
    normalized = case_name.strip()
    scenarios = {
        "La page d'accueil affiche les utilisateurs": {
            "objective": "Vérifier que l'accueil présente les utilisateurs attendus.",
            "expected": "Les trois utilisateurs de référence sont visibles et la page se charge correctement.",
            "obtained_ok": "Le scénario a été exécuté avec succès. Les trois utilisateurs attendus sont visibles.",
            "obtained_ko": "Le comportement observé n'est pas conforme aux attentes métier.",
            "obtained_partial": "Le scénario a été partiellement exécuté ; le résultat complet est à confirmer.",
        },
        "Un utilisateur peut poser, recharger puis supprimer un congé": {
            "objective": "Vérifier le cycle complet de gestion d'un congé pour un utilisateur.",
            "expected": "Le congé peut être posé, persisté après rechargement puis supprimé sans anomalie.",
            "obtained_ok": "Le scénario a été exécuté avec succès. Le congé a pu être posé, conservé puis supprimé.",
            "obtained_ko": "Le comportement observé n'est pas conforme aux attentes métier.",
            "obtained_partial": "Le scénario a été partiellement exécuté ; la conformité complète est à confirmer.",
        },
        "Une période sans jour ouvré est refusée": {
            "objective": "Vérifier qu'une demande de congé sans jour ouvré n'est pas validable.",
            "expected": "La validation reste empêchée et un message de guidage apparaît.",
            "obtained_ok": "Le scénario a été exécuté avec succès. La période sans jour ouvré a été refusée.",
            "obtained_ko": "Le comportement observé n'est pas conforme aux attentes métier.",
            "obtained_partial": "Le scénario a été partiellement exécuté ; le refus attendu est à confirmer.",
        },
        "Une période qui chevauche un congé affiche une erreur": {
            "objective": "Vérifier qu'un chevauchement avec un congé existant est signalé clairement.",
            "expected": "Un message d'erreur s'affiche et le congé déjà posé reste inchangé.",
            "obtained_ok": "Le scénario a été exécuté avec succès. Le chevauchement a été refusé et le congé existant a été conservé.",
            "obtained_ko": "Le comportement observé n'est pas conforme aux attentes métier.",
            "obtained_partial": "Le scénario a été partiellement exécuté ; la gestion du chevauchement est à confirmer.",
        },
        "Une période trop longue désactive le bouton": {
            "objective": "Vérifier que les demandes dépassant la règle métier ne peuvent pas être validées.",
            "expected": "Le bouton de validation reste désactivé lorsque la période est trop longue.",
            "obtained_ok": "Le scénario a été exécuté avec succès. Le bouton de validation est resté désactivé.",
            "obtained_ko": "Le comportement observé n'est pas conforme aux attentes métier.",
            "obtained_partial": "Le scénario a été partiellement exécuté ; la limite métier est à confirmer.",
        },
        "Les routes inconnues affichent la page introuvable": {
            "objective": "Vérifier qu'une route inconnue renvoie vers une page claire et compréhensible.",
            "expected": "Une page introuvable s'affiche avec un message explicite.",
            "obtained_ok": "Le scénario a été exécuté avec succès. La page introuvable a bien été affichée.",
            "obtained_ko": "Le comportement observé n'est pas conforme aux attentes métier.",
            "obtained_partial": "Le scénario a été partiellement exécuté ; l'affichage attendu est à confirmer.",
        },
    }
    return scenarios.get(
        normalized,
        {
            "objective": "À confirmer.",
            "expected": "À confirmer.",
            "obtained_ok": "Le scénario a été exécuté avec succès.",
            "obtained_ko": "Le comportement observé n'est pas conforme aux attentes métier.",
            "obtained_partial": "Le scénario a été partiellement exécuté ; le résultat est à confirmer.",
        },
    )


def scenario_status(summary: TestCaseSummary) -> str:
    if summary.status == "SUCCES":
        return "OK"
    if summary.status == "IGNORE":
        return "Partiel"
    if summary.steps_success > 0 and summary.steps_failure > 0:
        return "Partiel"
    return "KO"


def append_wrapped_field(lines: list[str], label: str, value: str, indent: str = "", width: int = 94) -> None:
    prefix = f"{indent}{label} : "
    wrapped = _wrap_text(value, max(24, width - len(prefix)))
    if not wrapped:
        lines.append(prefix.rstrip())
        return
    lines.append(prefix + wrapped[0])
    for part in wrapped[1:]:
        lines.append(f"{indent}{' ' * (len(label) + 3)}{part}")


def _wrap_text(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


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


def write_pdf(path: Path, metadata: ReportMetadata, summaries: list[TestCaseSummary], scenarios: list[ScenarioReport]) -> None:
    lines: list[str] = []
    passed_cases = sum(1 for item in scenarios if item.status == "OK")
    failed_cases = sum(1 for item in scenarios if item.status == "KO")
    partial_cases = sum(1 for item in scenarios if item.status == "Partiel")
    anomalies = [scenario for scenario in scenarios if scenario.status != "OK"]
    decision = "Recette validée"
    if failed_cases:
        decision = "Recette refusée"
    elif partial_cases:
        decision = "Recette validée avec réserves"

    lines.extend([
        f"PV de recette – {metadata.project_name}",
        "",
        "CONTEXTE",
    ])
    append_wrapped_field(lines, "Présentation du sujet recetté", "validation métier automatisée des parcours principaux de l'application.")
    append_wrapped_field(lines, "Objectif métier", "vérifier la conformité des parcours essentiels pour l'utilisateur final et la gestion des congés.")
    append_wrapped_field(lines, "Version / lot concerné", f"{metadata.version_label} / {metadata.lot_name}")
    append_wrapped_field(lines, "Environnement concerné", metadata.environment)
    append_wrapped_field(lines, "URL concernée", metadata.target_url)

    lines.extend([
        "",
        "PÉRIMÈTRE DE LA RECETTE",
    ])
    append_wrapped_field(lines, "Fonctionnalités testées", "consultation de l'accueil, consultation d'un utilisateur, pose d'un congé, contrôle des règles métier et page introuvable.")
    append_wrapped_field(lines, "Fonctionnalités hors périmètre", "non renseigné.")

    lines.extend([
        "",
        "CONDITIONS DE RECETTE",
    ])
    append_wrapped_field(lines, "Environnement", metadata.environment)
    append_wrapped_field(lines, "Données utilisées", "données de démonstration de l'application.")
    append_wrapped_field(lines, "Pré-requis éventuels", "non renseigné.")
    append_wrapped_field(lines, "Date de la recette", metadata.recipe_date)
    append_wrapped_field(lines, "Référence d'exécution", metadata.execution_reference)
    append_wrapped_field(lines, "Date de génération du PV", metadata.generation_date)

    lines.extend(["", "SCÉNARIOS EXÉCUTÉS"])

    for index, scenario in enumerate(scenarios, start=1):
        lines.append(f"{index}. Intitulé : {scenario.title}")
        append_wrapped_field(lines, "Objectif", scenario.objective, indent="   ")
        append_wrapped_field(lines, "Résultat attendu", scenario.expected, indent="   ")
        append_wrapped_field(lines, "Résultat obtenu", scenario.obtained, indent="   ")
        append_wrapped_field(lines, "Statut", scenario.status, indent="   ")
        lines.append("")

    lines.extend([
        "SYNTHÈSE DES RÉSULTATS",
        f"Tests OK : {passed_cases}",
        f"Tests KO : {failed_cases}",
        f"Tests partiels : {partial_cases}",
        "Points de vigilance : les résultats partiels ou non conformes doivent être traités avant validation définitive.",
        f"Anomalies constatées : {len(anomalies)}",
        "",
        "RÉSERVES / ANOMALIES / ACTIONS CORRECTIVES",
    ])

    if anomalies:
        lines.append(fit_row(["Description", "Impact métier", "Priorité", "Responsable", "Date de correction"], [34, 28, 10, 16, 16]))
        for scenario in anomalies:
            priority = "Haute" if scenario.status == "KO" else "Moyenne"
            impact = scenario.objective if scenario.objective != "À confirmer." else "Impact métier à confirmer."
            lines.append(
                fit_row(
                    [
                        scenario.title,
                        impact,
                        priority,
                        "non renseigné",
                        "non renseigné",
                    ],
                    [34, 28, 10, 16, 16],
                )
            )
    else:
        lines.append("Aucune réserve bloquante ni anomalie métier n'a été constatée.")

    lines.extend([
        "",
        "CONCLUSION",
        f"Avis de recette : {decision}.",
        f"Décision proposée : {decision}.",
    ])
    if decision == "Recette refusée":
        lines.append("Justification : au moins un scénario métier présente un écart par rapport aux attentes définies.")
    elif decision == "Recette validée avec réserves":
        lines.append("Justification : les parcours principaux sont conformes, mais des points de vigilance demeurent.")
    else:
        lines.append("Justification : le comportement observé est conforme aux attentes métier sur le périmètre testé.")

    lines.extend([
        "",
        "VALIDATION",
        f"Nom : {metadata.validation_name}",
        f"Rôle : {metadata.validation_role}",
        f"Date : {metadata.recipe_date}",
        f"Signature : {metadata.validation_signature}",
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
