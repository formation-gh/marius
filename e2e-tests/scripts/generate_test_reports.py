#!/usr/bin/env python3

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import math
import os
import re
import shutil
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
DOCX_PATH = REPORT_DIR / "pv-recette-tests.docx"
PDF_PATH = REPORT_DIR / "pv-recette-tests.pdf"
HTML_INDEX_PATH = REPORT_DIR / "index.html"
SUMMARY_MD_PATH = REPORT_DIR / "summary.md"
SCREENSHOTS_SOURCE_DIR = ROOT / "target" / "screenshots"
SCREENSHOTS_REPORT_DIR = REPORT_DIR / "screenshots"
DEFAULT_PROJECT_NAME = "formation-gh-api"
DEFAULT_TARGET_URL = "https://aouzgaga.github.io/formation-gh-api/"
DEFAULT_ENVIRONMENT = "Application publiée sur GitHub Pages"

# Historique des exécutions : conservé dans le dépôt (hors du dossier `target`,
# qui est ignoré par Git) afin de pouvoir afficher une tendance sur plusieurs
# exécutions successives du pilote de tests.
HISTORY_DIR = ROOT / "history"
HISTORY_PATH = HISTORY_DIR / "history.json"
HISTORY_REPORT_PATH = REPORT_DIR / "history.json"
HISTORY_MAX_ENTRIES = 50


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
    write_docx(DOCX_PATH, metadata, summaries, scenarios, detail_rows)
    write_pdf(PDF_PATH, metadata, summaries, scenarios)
    screenshots_by_method = copy_screenshots()
    history = update_history(metadata, summaries)
    write_html_index(
        HTML_INDEX_PATH, metadata, summaries, scenarios, screenshots_by_method, history, detail_rows
    )
    write_summary_markdown(SUMMARY_MD_PATH, metadata, summaries)

    print(f"Excel généré : {XLSX_PATH}")
    print(f"Word généré : {DOCX_PATH}")
    print(f"PDF généré : {PDF_PATH}")
    print(f"Page HTML générée : {HTML_INDEX_PATH}")
    print(f"Résumé Markdown généré : {SUMMARY_MD_PATH}")


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


def copy_screenshots() -> dict[str, list[Path]]:
    """Copie les captures d'écran dans le dossier de rapport afin qu'elles soient
    publiables (par ex. sur GitHub Pages) aux côtés du rapport HTML, et renvoie,
    pour chaque méthode de test, la liste des fichiers copiés (chemins relatifs
    au dossier de rapport)."""
    screenshots_by_method: dict[str, list[Path]] = {}
    if not SCREENSHOTS_SOURCE_DIR.exists():
        return screenshots_by_method

    if SCREENSHOTS_REPORT_DIR.exists():
        shutil.rmtree(SCREENSHOTS_REPORT_DIR)
    shutil.copytree(SCREENSHOTS_SOURCE_DIR, SCREENSHOTS_REPORT_DIR)

    for method_dir in sorted(SCREENSHOTS_REPORT_DIR.iterdir()):
        if not method_dir.is_dir():
            continue
        images = sorted(method_dir.glob("*.png"))
        if images:
            screenshots_by_method[method_dir.name] = [
                image.relative_to(REPORT_DIR) for image in images
            ]

    return screenshots_by_method


def nettoyer_nom(name: str) -> str:
    """Reproduit la normalisation Java `nettoyerNom` utilisée pour nommer les
    dossiers de captures d'écran (minuscules, séquences non alphanumériques
    remplacées par un unique tiret, tirets de bord retirés)."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return cleaned.strip("-")


def load_history() -> list[dict[str, object]]:
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return data if isinstance(data, list) else []


def update_history(
    metadata: ReportMetadata,
    summaries: list[TestCaseSummary],
) -> list[dict[str, object]]:
    """Ajoute l'exécution courante à l'historique persisté dans le dépôt
    (`history/history.json`) et renvoie l'historique complet (borné aux
    dernières exécutions) afin de l'afficher sur le tableau de bord."""
    total = len(summaries)
    success = sum(1 for summary in summaries if summary.status == "SUCCES")
    failure = sum(1 for summary in summaries if summary.status == "ECHEC")
    ignored = total - success - failure

    entry = {
        "date": metadata.generation_date,
        "execution_reference": metadata.execution_reference,
        "version_label": metadata.version_label,
        "total": total,
        "success": success,
        "failure": failure,
        "ignored": ignored,
    }

    history = load_history()
    history.append(entry)
    history = history[-HISTORY_MAX_ENTRIES:]

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    HISTORY_REPORT_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    return history


def status_badge_color(status: str) -> str:
    return {"OK": "#1a7f37", "Partiel": "#9a6700", "KO": "#cf222e"}.get(status, "#57606a")


def pie_slice_path(
    cx: float,
    cy: float,
    r: float,
    start_fraction: float,
    end_fraction: float,
) -> str:
    """Construit le chemin SVG (`d`) d'une part de camembert allant de
    `start_fraction` à `end_fraction` (valeurs comprises entre 0 et 1)."""

    def point(fraction: float) -> tuple[float, float]:
        angle = (fraction * 360.0 - 90.0) * math.pi / 180.0
        return (cx + r * math.cos(angle), cy + r * math.sin(angle))

    start_x, start_y = point(start_fraction)
    end_x, end_y = point(end_fraction)
    large_arc = 1 if (end_fraction - start_fraction) > 0.5 else 0
    return (
        f"M {cx} {cy} L {start_x:.3f} {start_y:.3f} "
        f"A {r} {r} 0 {large_arc} 1 {end_x:.3f} {end_y:.3f} Z"
    )


def build_pie_chart_svg(success: int, failure: int, ignored: int) -> str:
    """Génère un camembert SVG autonome (sans dépendance JS externe) résumant
    les statuts d'exécution, avec une part par statut."""
    total = success + failure + ignored
    if total == 0:
        return '<p class="empty">Aucune exécution à représenter.</p>'

    segments = [
        ("Succès", success, "#1a7f37"),
        ("Échecs", failure, "#cf222e"),
        ("Ignorés", ignored, "#9a6700"),
    ]
    non_zero_segments = [segment for segment in segments if segment[1] > 0]

    if len(non_zero_segments) == 1:
        # Un seul statut représente 100 % des résultats : les points de
        # départ et de fin d'une part « plein cercle » seraient identiques
        # (angle de -90° dans les deux cas), ce qui produirait un arc
        # dégénéré invisible. On dessine donc directement un cercle plein.
        label, count, color = non_zero_segments[0]
        slices = [
            f'<circle cx="60" cy="60" r="58" fill="{color}">'
            f"<title>{html.escape(label)} : {count} (100%)</title></circle>"
        ]
    else:
        cursor = 0.0
        slices = []
        for label, count, color in segments:
            if count <= 0:
                continue
            fraction = count / total
            slices.append(
                f'<path d="{pie_slice_path(60, 60, 58, cursor, cursor + fraction)}" '
                f'fill="{color}"><title>{html.escape(label)} : {count} ({fraction * 100:.0f}%)</title></path>'
            )
            cursor += fraction

    return (
        '<svg viewBox="0 0 120 120" class="pie-chart" role="img" '
        f'aria-label="Répartition des résultats : {success} succès, {failure} échecs, {ignored} ignorés">'
        + "".join(slices)
        + "</svg>"
    )


def build_history_bars_html(history: list[dict[str, object]]) -> str:
    """Génère un mini graphique en barres (empilées succès/échecs/ignorés)
    représentant l'historique des dernières exécutions."""
    if not history:
        return '<p class="empty">Aucun historique disponible pour le moment.</p>'

    bars = []
    for entry in history:
        total = int(entry.get("total", 0) or 0)
        success = int(entry.get("success", 0) or 0)
        failure = int(entry.get("failure", 0) or 0)
        ignored = int(entry.get("ignored", 0) or 0)
        if total <= 0:
            total = max(success + failure + ignored, 1)
        success_pct = success / total * 100
        failure_pct = failure / total * 100
        ignored_pct = ignored / total * 100
        label = html.escape(str(entry.get("execution_reference") or entry.get("date") or ""))
        date = html.escape(str(entry.get("date", "")))
        bars.append(
            f"""
            <div class="history-bar" title="{label} — {date} — {success}/{total} succès">
              <div class="history-bar-track">
                <div class="history-bar-segment" style="height:{success_pct:.1f}%;background:#1a7f37"></div>
                <div class="history-bar-segment" style="height:{failure_pct:.1f}%;background:#cf222e"></div>
                <div class="history-bar-segment" style="height:{ignored_pct:.1f}%;background:#9a6700"></div>
              </div>
              <span class="history-bar-label">{date or label}</span>
            </div>
            """
        )
    return f'<div class="history-bars">{"".join(bars)}</div>'


def write_html_index(
    path: Path,
    metadata: ReportMetadata,
    summaries: list[TestCaseSummary],
    scenarios: list[ScenarioReport],
    screenshots_by_method: dict[str, list[Path]],
    history: list[dict[str, object]],
    step_rows: list[StepRow],
) -> None:
    """Génère un site HTML autonome (une seule page, sans dépendance externe)
    permettant de piloter la consultation des tests E2E : tableau de bord
    (camembert + légende + historique des exécutions), liste des scénarios
    avec navigation précédent/suivant, étapes détaillées, Gherkin et captures
    d'écran, directement publiable sur GitHub Pages."""
    method_by_case = {summary.case: summary.method for summary in summaries}
    steps_by_method: dict[str, list[StepRow]] = {}
    for step in step_rows:
        steps_by_method.setdefault(step.method, []).append(step)

    total = len(summaries)
    success = sum(1 for summary in summaries if summary.status == "SUCCES")
    failure = sum(1 for summary in summaries if summary.status == "ECHEC")
    ignored = total - success - failure

    scenario_payload = []
    for index, scenario in enumerate(scenarios):
        method = method_by_case.get(scenario.title, "")
        cleaned_method = nettoyer_nom(method)
        screenshots = screenshots_by_method.get(cleaned_method, [])
        scenario_payload.append(
            {
                "index": index,
                "title": scenario.title,
                "status": scenario.status,
                "objective": scenario.objective,
                "expected": scenario.expected,
                "obtained": scenario.obtained,
                "details": scenario.details,
                "gherkin": build_gherkin_text(scenario),
                "steps": [
                    {
                        "step": step.step,
                        "status": step.status,
                        "detail": step.detail,
                        "duration_ms": step.duration_ms,
                    }
                    for step in steps_by_method.get(method, [])
                ],
                "screenshots": [str(image) for image in screenshots],
            }
        )

    app_data = {
        "metadata": {
            "project_name": metadata.project_name,
            "lot_name": metadata.lot_name,
            "version_label": metadata.version_label,
            "environment": metadata.environment,
            "target_url": metadata.target_url,
            "execution_reference": metadata.execution_reference,
            "generation_date": metadata.generation_date,
        },
        "summary": {"total": total, "success": success, "failure": failure, "ignored": ignored},
        "scenarios": scenario_payload,
        "history": history,
    }

    pie_chart_svg = build_pie_chart_svg(success, failure, ignored)
    history_bars_html = build_history_bars_html(history)

    content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Pilote de tests E2E — {html.escape(metadata.project_name)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --ok: #1a7f37; --ko: #cf222e; --partiel: #9a6700; --muted: #57606a;
    --border: #d0d7de; --bg-soft: #f6f8fa;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "Segoe UI", Arial, sans-serif; margin: 0; color: #1f2328;
    background: #ffffff;
  }}
  header.top {{ padding: 1rem 1.5rem; border-bottom: 1px solid var(--border); }}
  header.top h1 {{ margin: 0 0 0.25rem 0; font-size: 1.4rem; }}
  .meta {{ color: var(--muted); font-size: 0.9rem; }}
  nav.tabs {{ display: flex; gap: 0.5rem; padding: 0 1.5rem; border-bottom: 1px solid var(--border); background: var(--bg-soft); }}
  nav.tabs button {{
    border: none; background: transparent; padding: 0.75rem 1rem; cursor: pointer;
    font-size: 0.95rem; color: var(--muted); border-bottom: 3px solid transparent;
  }}
  nav.tabs button.active {{ color: #1f2328; border-bottom-color: #0969da; font-weight: 600; }}
  main {{ padding: 1.5rem; }}
  .view {{ display: none; }}
  .view.active {{ display: block; }}
  .dashboard-grid {{ display: flex; flex-wrap: wrap; gap: 2rem; align-items: flex-start; }}
  .card {{ border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; background: #fff; }}
  .pie-card {{ display: flex; gap: 1.5rem; align-items: center; }}
  .pie-chart {{ width: 150px; height: 150px; flex-shrink: 0; }}
  .legend {{ list-style: none; margin: 0; padding: 0; }}
  .legend li {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; font-size: 0.95rem; }}
  .legend .swatch {{ width: 14px; height: 14px; border-radius: 3px; display: inline-block; }}
  .history-bars {{ display: flex; gap: 0.6rem; align-items: flex-end; height: 160px; overflow-x: auto; padding-top: 0.5rem; }}
  .history-bar {{ display: flex; flex-direction: column; align-items: center; min-width: 28px; }}
  .history-bar-track {{
    width: 20px; height: 120px; background: #eaeef2; border-radius: 3px;
    display: flex; flex-direction: column-reverse; overflow: hidden;
  }}
  .history-bar-label {{ font-size: 0.65rem; color: var(--muted); margin-top: 0.3rem; writing-mode: vertical-rl; }}
  .empty {{ color: var(--muted); font-style: italic; }}
  .links a {{ margin-right: 1rem; }}
  .badge {{ color: #fff; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }}
  .scenarios-layout {{ display: flex; gap: 1.5rem; align-items: flex-start; }}
  .scenario-list {{ list-style: none; margin: 0; padding: 0; width: 320px; flex-shrink: 0; }}
  .scenario-list li {{
    border: 1px solid var(--border); border-radius: 6px; padding: 0.6rem 0.75rem;
    margin-bottom: 0.5rem; cursor: pointer; display: flex; justify-content: space-between;
    align-items: center; gap: 0.5rem;
  }}
  .scenario-list li:hover {{ background: var(--bg-soft); }}
  .scenario-list li.selected {{ border-color: #0969da; background: #ddf4ff; }}
  .scenario-list li span.title {{ font-size: 0.9rem; }}
  .filters {{ display: flex; gap: 0.5rem; margin-bottom: 0.75rem; flex-wrap: wrap; }}
  .filters button {{
    border: 1px solid var(--border); background: #fff; border-radius: 999px; padding: 0.3rem 0.8rem;
    cursor: pointer; font-size: 0.85rem;
  }}
  .filters button.active {{ background: #0969da; color: #fff; border-color: #0969da; }}
  .scenario-detail {{ flex: 1; min-width: 0; }}
  .scenario-detail h2 {{ margin-top: 0; }}
  .nav-buttons {{ display: flex; justify-content: space-between; margin-bottom: 1rem; }}
  .nav-buttons button {{
    border: 1px solid var(--border); background: #fff; border-radius: 6px; padding: 0.5rem 1rem; cursor: pointer;
  }}
  .nav-buttons button:disabled {{ opacity: 0.4; cursor: not-allowed; }}
  table.steps {{ width: 100%; border-collapse: collapse; margin-top: 0.5rem; }}
  table.steps th, table.steps td {{ border: 1px solid var(--border); padding: 0.4rem 0.6rem; font-size: 0.9rem; text-align: left; }}
  table.steps th {{ background: var(--bg-soft); }}
  pre.gherkin {{ background: #0d1117; color: #c9d1d9; padding: 1rem; border-radius: 6px; overflow-x: auto; }}
  .screenshots {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }}
  .thumb {{ height: 140px; border: 1px solid var(--border); border-radius: 4px; }}
  a {{ color: #0969da; }}
  @media (max-width: 800px) {{
    .scenarios-layout {{ flex-direction: column; }}
    .scenario-list {{ width: 100%; }}
  }}
</style>
</head>
<body>
  <header class="top">
    <h1>Pilote de tests E2E — {html.escape(metadata.project_name)}</h1>
    <p class="meta">
      Lot : {html.escape(metadata.lot_name)} — Version : {html.escape(metadata.version_label)} —
      Environnement : {html.escape(metadata.environment)}<br>
      Exécution : {html.escape(metadata.execution_reference)} — Généré le {html.escape(metadata.generation_date)}<br>
      Application testée : <a href="{html.escape(metadata.target_url)}">{html.escape(metadata.target_url)}</a>
    </p>
    <p class="links">
      <a href="e2e-test-steps.csv">CSV détaillé</a>
      <a href="pv-recette-tests.xlsx">Excel</a>
      <a href="pv-recette-tests.docx">Word (PV de recette)</a>
      <a href="pv-recette-tests.pdf">PDF (PV de recette)</a>
    </p>
  </header>

  <nav class="tabs">
    <button type="button" data-view="dashboard" class="active">Tableau de bord</button>
    <button type="button" data-view="scenarios">Scénarios</button>
  </nav>

  <main>
    <section id="view-dashboard" class="view active">
      <div class="dashboard-grid">
        <div class="card pie-card">
          {pie_chart_svg}
          <ul class="legend">
            <li><span class="swatch" style="background:#1a7f37"></span> Succès : <strong>{success}</strong></li>
            <li><span class="swatch" style="background:#cf222e"></span> Échecs : <strong>{failure}</strong></li>
            <li><span class="swatch" style="background:#9a6700"></span> Ignorés : <strong>{ignored}</strong></li>
            <li>Total : <strong>{total}</strong></li>
          </ul>
        </div>
        <div class="card" style="flex:1; min-width: 280px;">
          <h3 style="margin-top:0;">Historique des exécutions</h3>
          {history_bars_html}
        </div>
      </div>
    </section>

    <section id="view-scenarios" class="view">
      <div class="scenarios-layout">
        <div>
          <div class="filters" id="filters">
            <button type="button" data-filter="all" class="active">Tous</button>
            <button type="button" data-filter="OK">Succès</button>
            <button type="button" data-filter="KO">Échecs</button>
            <button type="button" data-filter="Partiel">Partiels</button>
          </div>
          <ul class="scenario-list" id="scenario-list"></ul>
        </div>
        <div class="scenario-detail" id="scenario-detail">
          <p class="empty">Sélectionnez un scénario dans la liste.</p>
        </div>
      </div>
    </section>
  </main>

  <script id="app-data" type="application/json">{json.dumps(app_data, ensure_ascii=False)}</script>
  <script>
{APP_JS}
  </script>
</body>
</html>
"""
    path.write_text(content, encoding="utf-8")


APP_JS = """
(function () {
  var data = JSON.parse(document.getElementById('app-data').textContent);
  var scenarios = data.scenarios;
  var currentFilter = 'all';
  var selectedIndex = scenarios.length ? 0 : -1;

  var statusColors = { OK: '#1a7f37', KO: '#cf222e', Partiel: '#9a6700' };

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  function filteredScenarios() {
    if (currentFilter === 'all') { return scenarios; }
    return scenarios.filter(function (s) { return s.status === currentFilter; });
  }

  function renderList() {
    var list = document.getElementById('scenario-list');
    var items = filteredScenarios();
    list.innerHTML = items.map(function (s) {
      var selected = s.index === selectedIndex ? ' selected' : '';
      var color = statusColors[s.status] || '#57606a';
      return '<li class="' + selected.trim() + '" data-index="' + s.index + '">' +
        '<span class="title">' + escapeHtml(s.title) + '</span>' +
        '<span class="badge" style="background:' + color + '">' + escapeHtml(s.status) + '</span>' +
        '</li>';
    }).join('') || '<li class="empty">Aucun scénario pour ce filtre.</li>';

    Array.prototype.forEach.call(list.querySelectorAll('li[data-index]'), function (el) {
      el.addEventListener('click', function () {
        selectScenario(parseInt(el.getAttribute('data-index'), 10));
      });
    });
  }

  function stepsTable(steps) {
    if (!steps || !steps.length) {
      return '<p class="empty">Aucune étape détaillée enregistrée.</p>';
    }
    var rows = steps.map(function (step) {
      var color = step.status === 'SUCCES' ? '#1a7f37' : '#cf222e';
      return '<tr>' +
        '<td>' + escapeHtml(step.step) + '</td>' +
        '<td><span class="badge" style="background:' + color + '">' + escapeHtml(step.status) + '</span></td>' +
        '<td>' + escapeHtml(step.detail) + '</td>' +
        '<td>' + escapeHtml(step.duration_ms) + ' ms</td>' +
        '</tr>';
    }).join('');
    return '<table class="steps"><thead><tr><th>Étape</th><th>Statut</th><th>Détail</th><th>Durée</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table>';
  }

  function screenshotsHtml(screenshots) {
    if (!screenshots || !screenshots.length) {
      return '<p class="empty">Aucune capture d\\'écran.</p>';
    }
    return '<div class="screenshots">' + screenshots.map(function (src) {
      return '<a href="' + src + '" target="_blank"><img class="thumb" loading="lazy" src="' + src + '" alt=""></a>';
    }).join('') + '</div>';
  }

  function selectScenario(index) {
    selectedIndex = index;
    var scenario = scenarios[index];
    var detail = document.getElementById('scenario-detail');
    if (!scenario) {
      detail.innerHTML = '<p class="empty">Sélectionnez un scénario dans la liste.</p>';
      renderList();
      return;
    }
    var items = filteredScenarios();
    var posInFiltered = items.findIndex(function (s) { return s.index === index; });
    var prev = posInFiltered > 0 ? items[posInFiltered - 1] : null;
    var next = posInFiltered >= 0 && posInFiltered < items.length - 1 ? items[posInFiltered + 1] : null;

    var color = statusColors[scenario.status] || '#57606a';
    detail.innerHTML =
      '<div class="nav-buttons">' +
        '<button type="button" id="btn-prev" ' + (prev ? '' : 'disabled') + '>&laquo; Précédent</button>' +
        '<button type="button" id="btn-next" ' + (next ? '' : 'disabled') + '>Suivant &raquo;</button>' +
      '</div>' +
      '<h2><span class="badge" style="background:' + color + '">' + escapeHtml(scenario.status) + '</span> ' +
        escapeHtml(scenario.title) + '</h2>' +
      '<p><strong>Objectif :</strong> ' + escapeHtml(scenario.objective) + '</p>' +
      '<p><strong>Résultat attendu :</strong> ' + escapeHtml(scenario.expected) + '</p>' +
      '<p><strong>Résultat obtenu :</strong> ' + escapeHtml(scenario.obtained) + '</p>' +
      '<p><strong>Détails :</strong> ' + escapeHtml(scenario.details) + '</p>' +
      '<h3>Gherkin</h3><pre class="gherkin">' + escapeHtml(scenario.gherkin) + '</pre>' +
      '<h3>Étapes</h3>' + stepsTable(scenario.steps) +
      '<h3>Captures d\\'écran</h3>' + screenshotsHtml(scenario.screenshots);

    var prevBtn = document.getElementById('btn-prev');
    var nextBtn = document.getElementById('btn-next');
    if (prevBtn && prev) { prevBtn.addEventListener('click', function () { selectScenario(prev.index); }); }
    if (nextBtn && next) { nextBtn.addEventListener('click', function () { selectScenario(next.index); }); }

    renderList();
    window.location.hash = 'scenario-' + index;
  }

  Array.prototype.forEach.call(document.querySelectorAll('#filters button'), function (btn) {
    btn.addEventListener('click', function () {
      Array.prototype.forEach.call(document.querySelectorAll('#filters button'), function (b) {
        b.classList.remove('active');
      });
      btn.classList.add('active');
      currentFilter = btn.getAttribute('data-filter');
      var items = filteredScenarios();
      if (items.length && !items.some(function (s) { return s.index === selectedIndex; })) {
        selectScenario(items[0].index);
      } else {
        renderList();
      }
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll('nav.tabs button'), function (btn) {
    btn.addEventListener('click', function () {
      Array.prototype.forEach.call(document.querySelectorAll('nav.tabs button'), function (b) {
        b.classList.remove('active');
      });
      Array.prototype.forEach.call(document.querySelectorAll('.view'), function (v) {
        v.classList.remove('active');
      });
      btn.classList.add('active');
      document.getElementById('view-' + btn.getAttribute('data-view')).classList.add('active');
    });
  });

  renderList();
  if (scenarios.length) {
    var hashMatch = /^#scenario-(\\d+)$/.exec(window.location.hash);
    var initialIndex = hashMatch ? parseInt(hashMatch[1], 10) : 0;
    if (!scenarios[initialIndex]) { initialIndex = 0; }
    selectScenario(initialIndex);
    if (hashMatch) {
      document.querySelector('nav.tabs button[data-view="scenarios"]').click();
    }
  }
})();
"""


def write_summary_markdown(
    path: Path,
    metadata: ReportMetadata,
    summaries: list[TestCaseSummary],
) -> None:
    """Génère un résumé Markdown destiné au Job Summary de GitHub Actions, afin
    que le résultat soit visible directement sur la page d'exécution du
    workflow, sans téléchargement."""
    total = len(summaries)
    success = sum(1 for summary in summaries if summary.status == "SUCCES")
    failure = sum(1 for summary in summaries if summary.status == "ECHEC")
    ignored = total - success - failure

    lines = [
        f"## PV de recette — {metadata.project_name}",
        "",
        f"- Exécution : {metadata.execution_reference}",
        f"- Généré le : {metadata.generation_date}",
        f"- Total : {total} — Succès : {success} — Échecs : {failure} — Ignorés : {ignored}",
        "",
        "| Statut | Scénario | Étapes réussies | Durée (ms) |",
        "| --- | --- | --- | --- |",
    ]
    for summary in summaries:
        icon = {"SUCCES": "✅", "ECHEC": "❌", "IGNORE": "⚠️"}.get(summary.status, "❔")
        lines.append(
            f"| {icon} {summary.status} | {summary.case} | {summary.steps_success}/{summary.steps_total} | {summary.duration_ms} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def write_docx(
    path: Path,
    metadata: ReportMetadata,
    summaries: list[TestCaseSummary],
    scenarios: list[ScenarioReport],
    detail_rows: list[StepRow],
) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", docx_content_types_xml())
        archive.writestr("_rels/.rels", docx_root_rels_xml())
        archive.writestr("docProps/core.xml", docx_core_xml(metadata))
        archive.writestr("docProps/app.xml", docx_app_xml())
        archive.writestr("word/document.xml", docx_document_xml(metadata, summaries, scenarios, detail_rows))
        archive.writestr("word/styles.xml", docx_styles_xml())
        archive.writestr("word/settings.xml", docx_settings_xml())
        archive.writestr("word/_rels/document.xml.rels", docx_document_rels_xml())


def docx_document_xml(
    metadata: ReportMetadata,
    summaries: list[TestCaseSummary],
    scenarios: list[ScenarioReport],
    detail_rows: list[StepRow],
) -> str:
    passed_cases = sum(1 for item in scenarios if item.status == "OK")
    failed_cases = sum(1 for item in scenarios if item.status == "KO")
    partial_cases = sum(1 for item in scenarios if item.status == "Partiel")
    anomalies = [scenario for scenario in scenarios if scenario.status != "OK"]
    decision = docx_decision_label(passed_cases, failed_cases, partial_cases)
    if failed_cases:
        decision_color = "B91C1C"
    elif partial_cases:
        decision_color = "C2410C"
    else:
        decision_color = "166534"

    blocks: list[str] = []
    blocks.extend([
        docx_paragraph("🧪 PV DE RECETTE", align="center", bold=True, color="FFFFFF", size=34, shading="1F4E79", spacing_before=120, spacing_after=120),
        docx_paragraph(metadata.project_name, align="center", bold=True, color="0F4C81", size=24, spacing_after=80),
        docx_paragraph("Présentation commerciale et validation métier automatisée", align="center", color="475569", size=16, spacing_after=160),
        docx_paragraph("🎯 Plan de test • 📋 Stratégie de test • ✅ Étapes de test • ✨ Scénarios Gherkin", align="center", color="0F766E", size=12, spacing_after=220),
        docx_table(
            [
                ["Projet", metadata.project_name],
                ["Lot / version", f"{metadata.version_label} / {metadata.lot_name}"],
                ["Environnement", metadata.environment],
                ["URL cible", metadata.target_url],
                ["Référence d'exécution", metadata.execution_reference],
                ["Date de recette", metadata.recipe_date],
                ["Date de génération", metadata.generation_date],
            ],
            widths=[2800, 6226],
            header_fill="0F766E",
            header_text="FFFFFF",
            body_fill="F8FAFC",
            body_text="1F2937",
        ),
        docx_paragraph(" ", spacing_after=120),
        docx_paragraph("🟦 Vue d'ensemble", bold=True, color="1F4E79", size=20, spacing_before=120, spacing_after=60),
        docx_paragraph("Le document synthétise les tests de recette, les parcours couverts, le plan de test associé et les scénarios en Gherkin destinés à la présentation commerciale.", color="334155", size=11, spacing_after=120),
        docx_page_break(),
        docx_paragraph("1. Contexte et objectifs", bold=True, color="1F4E79", size=20, spacing_after=60),
        docx_paragraph("🧭 Contexte métier", bold=True, color="0F766E", size=13, spacing_after=20),
        docx_paragraph("Le PV de recette formalise la validation des parcours critiques de l'application et rend la lecture accessible à un interlocuteur métier ou commercial.", color="334155", size=11, spacing_after=80),
        docx_paragraph("📋 Stratégie de test", bold=True, color="0F766E", size=13, spacing_after=20),
        docx_bullet("Vérifier les parcours principaux dans un navigateur réel en mode automatique."),
        docx_bullet("Contrôler les règles métier visibles par l'utilisateur final."),
        docx_bullet("Tracer les étapes de test et les résultats obtenus pour chaque scénario."),
        docx_bullet("Produire un document lisible, réutilisable dans une validation commerciale."),
        docx_paragraph(" ", spacing_after=60),
        docx_paragraph("2. Plan de test", bold=True, color="1F4E79", size=20, spacing_after=60),
        docx_table(
            [
                ["Scénario", "Statut", "Étapes", "Succès", "Échecs", "Durée", "Commentaire"],
            ]
            + [
                [
                    item.case,
                    docx_status_icon(item.status),
                    str(item.steps_total),
                    str(item.steps_success),
                    str(item.steps_failure),
                    f"{item.duration_ms} ms" if item.duration_ms else "n/a",
                    item.comment,
                ]
                for item in summaries
            ],
            widths=[2600, 1000, 900, 900, 900, 1100, 1626],
            header_fill="1F4E79",
            header_text="FFFFFF",
            body_fill="FFFFFF",
            body_text="1F2937",
        ),
        docx_paragraph(" ", spacing_after=80),
        docx_paragraph("3. Étapes de test", bold=True, color="1F4E79", size=20, spacing_after=60),
        docx_table(
            [["Cas de test", "Étape", "Statut", "Détail", "Durée"]] + [
                [
                    row.case,
                    row.step,
                    docx_status_icon(row.status),
                    row.detail,
                    f"{row.duration_ms} ms" if row.duration_ms else "n/a",
                ]
                for row in detail_rows
            ],
            widths=[2200, 2200, 1000, 2426, 1200],
            header_fill="0F766E",
            header_text="FFFFFF",
            body_fill="F8FAFC",
            body_text="1F2937",
        ),
        docx_paragraph(" ", spacing_after=80),
        docx_paragraph("4. Scénarios Gherkin", bold=True, color="1F4E79", size=20, spacing_after=60),
        docx_table(
            [["Scénario", "Gherkin"]] + [
                [scenario.title, build_gherkin_text(scenario)]
                for scenario in scenarios
            ],
            widths=[2400, 6626],
            header_fill="1F4E79",
            header_text="FFFFFF",
            body_fill="F8FAFC",
            body_text="1F2937",
        ),
    ])

    blocks.extend([
        docx_paragraph(" ", spacing_after=60),
        docx_paragraph("5. Synthèse et décision", bold=True, color="1F4E79", size=20, spacing_after=60),
        docx_table(
            [
                ["Tests OK", "Tests KO", "Tests partiels", "Décision"],
                [str(passed_cases), str(failed_cases), str(partial_cases), f"{decision}"],
            ],
            widths=[1800, 1800, 1800, 3626],
            header_fill="1F4E79",
            header_text="FFFFFF",
            body_fill="FFFFFF",
            body_text=decision_color,
        ),
    ])

    if anomalies:
        blocks.extend([
            docx_paragraph("Réserves / anomalies", bold=True, color="B45309", size=13, spacing_before=40, spacing_after=20),
            docx_table(
                [["Description", "Impact métier", "Priorité"]] + [
                    [
                        scenario.title,
                        scenario.objective if scenario.objective != "À confirmer." else "Impact métier à confirmer.",
                        "Haute" if scenario.status == "KO" else "Moyenne",
                    ]
                    for scenario in anomalies
                ],
                widths=[3600, 3626, 1800],
                header_fill="B45309",
                header_text="FFFFFF",
                body_fill="FFF7ED",
                body_text="7C2D12",
            ),
        ])
    else:
        blocks.append(docx_paragraph("Aucune réserve bloquante ni anomalie métier n'a été constatée.", color="166534", size=11, spacing_after=60))

    blocks.extend([
        docx_paragraph("6. Validation", bold=True, color="1F4E79", size=20, spacing_before=40, spacing_after=60),
        docx_table(
            [
                ["Nom", metadata.validation_name],
                ["Rôle", metadata.validation_role],
                ["Date", metadata.recipe_date],
                ["Signature", metadata.validation_signature],
            ],
            widths=[1800, 7226],
            header_fill="0F766E",
            header_text="FFFFFF",
            body_fill="F8FAFC",
            body_text="1F2937",
        ),
    ])

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<w:body>{''.join(blocks)}{docx_section_properties()}</w:body>"
        '</w:document>'
    )


def docx_decision_label(passed_cases: int, failed_cases: int, partial_cases: int) -> str:
    if failed_cases:
        return "🔴 Recette refusée"
    if partial_cases:
        return "🟠 Recette validée avec réserves"
    return "🟢 Recette validée"


def build_gherkin_text(scenario: ScenarioReport) -> str:
    normalized = scenario.title.lower()
    if "accueil" in normalized or "utilisateurs" in normalized:
        lines = [
            "Étant donné que la page d'accueil est ouverte",
            "Quand l'utilisateur consulte les cartes affichées",
            "Alors les 3 utilisateurs de référence sont visibles",
        ]
    elif "chevauche" in normalized:
        lines = [
            "Étant donné qu'un congé existe déjà pour l'utilisateur",
            "Quand une nouvelle période chevauche ce congé",
            "Alors un message d'erreur est affiché et le congé existant est conservé",
        ]
    elif "trop longue" in normalized:
        lines = [
            "Étant donné qu'une période dépasse la règle métier",
            "Quand l'utilisateur saisit la demande de congé",
            "Alors le bouton de validation reste désactivé",
        ]
    elif "jour ouvré" in normalized or "sans jour" in normalized:
        lines = [
            "Étant donné qu'aucun jour ouvré ne figure dans la période",
            "Quand l'utilisateur tente de valider la demande",
            "Alors la validation est refusée",
        ]
    elif "supprimer" in normalized or "congé" in normalized:
        lines = [
            "Étant donné qu'une fiche utilisateur est ouverte",
            "Quand un congé valide est posé puis rechargé",
            "Alors le congé reste visible et peut être supprimé",
        ]
    elif "introuvable" in normalized or "routes" in normalized:
        lines = [
            "Étant donné qu'une route inconnue est ouverte",
            "Quand l'application charge cette URL",
            "Alors une page introuvable s'affiche",
        ]
    else:
        lines = [
            f"Étant donné le scénario « {scenario.title} »",
            f"Quand le parcours métier est exécuté",
            f"Alors le résultat attendu est : {scenario.expected}",
        ]
    return "\n".join(f"- {line}" for line in lines)


def docx_status_icon(status: str) -> str:
    if status == "SUCCES":
        return "🟢 SUCCES"
    if status == "IGNORE":
        return "🟠 IGNORE"
    return "🔴 ECHEC"


def docx_bullet(text: str) -> str:
    return docx_paragraph(f"• {text}", color="334155", size=11, spacing_after=20)


def docx_table(
    rows: list[list[object]],
    widths: list[int],
    header_fill: str,
    header_text: str,
    body_fill: str,
    body_text: str,
) -> str:
    if not rows:
        return ""

    normalized_widths = widths[:]
    if len(normalized_widths) < len(rows[0]):
        normalized_widths.extend([0] * (len(rows[0]) - len(normalized_widths)))

    table_rows = []
    for row_index, row in enumerate(rows):
        is_header = row_index == 0
        fill = header_fill if is_header else body_fill
        color = header_text if is_header else body_text
        table_rows.append(
            "<w:tr>"
            + "".join(
                docx_table_cell(
                    value=cell,
                    width=normalized_widths[column_index],
                    fill=fill,
                    text_color=color,
                    bold=is_header,
                )
                for column_index, cell in enumerate(row)
            )
            + "</w:tr>"
        )

    tbl_grid = "".join(
        f'<w:gridCol w:w="{width or 2000}"/>' for width in normalized_widths[: len(rows[0])]
    )

    return (
        '<w:tbl>'
        '<w:tblPr><w:tblW w:w="0" w:type="auto"/>'
        '<w:tblLayout w:type="fixed"/>'
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="8" w:space="0" w:color="CBD5E1"/>'
        '<w:left w:val="single" w:sz="8" w:space="0" w:color="CBD5E1"/>'
        '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="CBD5E1"/>'
        '<w:right w:val="single" w:sz="8" w:space="0" w:color="CBD5E1"/>'
        '<w:insideH w:val="single" w:sz="8" w:space="0" w:color="CBD5E1"/>'
        '<w:insideV w:val="single" w:sz="8" w:space="0" w:color="CBD5E1"/>'
        '</w:tblBorders></w:tblPr>'
        f'<w:tblGrid>{tbl_grid}</w:tblGrid>'
        + "".join(table_rows)
        + '</w:tbl>'
    )


def docx_table_cell(value: object, width: int, fill: str, text_color: str, bold: bool) -> str:
    width_xml = f'<w:tcW w:w="{width or 2000}" w:type="dxa"/>'
    if isinstance(value, list):
        lines = [str(item) for item in value]
    else:
        lines = str(value).split("\n")

    paragraphs = "".join(
        docx_paragraph(
            line,
            color=text_color,
            bold=bold,
            size=20,
            spacing_after=0,
            spacing_before=0,
            font="Calibri",
        )
        for line in lines
    )
    return (
        '<w:tc>'
        f'<w:tcPr>{width_xml}<w:shd w:fill="{fill}"/><w:vAlign w:val="center"/></w:tcPr>'
        f"{paragraphs}"
        '</w:tc>'
    )


def docx_paragraph(
    text: str,
    *,
    align: str | None = None,
    bold: bool = False,
    italic: bool = False,
    color: str | None = None,
    size: int | None = None,
    font: str | None = None,
    shading: str | None = None,
    spacing_before: int | None = None,
    spacing_after: int | None = None,
) -> str:
    paragraph_props = []
    if align:
        paragraph_props.append(f'<w:jc w:val="{align}"/>')
    if spacing_before is not None or spacing_after is not None:
        before = 0 if spacing_before is None else spacing_before
        after = 0 if spacing_after is None else spacing_after
        paragraph_props.append(f'<w:spacing w:before="{before}" w:after="{after}"/>')
    if shading:
        paragraph_props.append(f'<w:shd w:fill="{shading}"/>')

    run_props = []
    if bold:
        run_props.append("<w:b/>")
    if italic:
        run_props.append("<w:i/>")
    if color:
        run_props.append(f'<w:color w:val="{color}"/>')
    if size:
        run_props.append(f'<w:sz w:val="{size}"/>')
        run_props.append(f'<w:szCs w:val="{size}"/>')
    if font:
        run_props.append(
            f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}" w:eastAsia="{font}"/>'
        )

    return (
        '<w:p>'
        + (f'<w:pPr>{"".join(paragraph_props)}</w:pPr>' if paragraph_props else "")
        + f'<w:r><w:rPr>{"".join(run_props)}</w:rPr><w:t xml:space="preserve">{xml_escape(text)}</w:t></w:r>'
        '</w:p>'
    )


def docx_page_break() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def docx_section_properties() -> str:
    return (
        '<w:sectPr>'
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
        '<w:cols w:space="708"/>'
        '<w:docGrid w:linePitch="360"/>'
        '</w:sectPr>'
    )


def docx_content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '</Types>'
    )


def docx_root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )


def docx_document_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
        '</Relationships>'
    )


def docx_core_xml(metadata: ReportMetadata) -> str:
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f'<dc:title>PV de recette - {xml_escape(metadata.project_name)}</dc:title>'
        f'<dc:subject>Recette métier</dc:subject>'
        f'<dc:creator>Copilot</dc:creator>'
        f'<cp:lastModifiedBy>Copilot</cp:lastModifiedBy>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
        '</cp:coreProperties>'
    )


def docx_app_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Copilot</Application>'
        '</Properties>'
    )


def docx_settings_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:zoom w:percent="100"/>'
        '<w:compat/>'
        '</w:settings>'
    )


def docx_styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:docDefaults>'
        '<w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:rPrDefault>'
        '<w:pPrDefault><w:pPr><w:spacing w:after="120"/></w:pPr></w:pPrDefault>'
        '</w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/>'
        '<w:qFormat/>'
        '</w:style>'
        '</w:styles>'
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
