# /code/evaluation/main.py

"""
+-----------------------------------------------------------------------------+
|                         EVALUATION PIPELINE                                |
+-----------------------------------------------------------------------------+

Evaluation Scorer and Usage Analysis for Ghost Data Still Exists
Computes accuracy metrics and extracts real token/prompt cost metrics
from UsageTracker to update evaluation_report.md and usage_report.md.
"""

# Python Libraries
import json
from collections import Counter, defaultdict
from pathlib import Path

# Vendor Libraries
import pandas as pd
from sklearn.metrics import classification_report

# Local Libraries
from src.constants import (
    DATASET_PATH,
    INPUT_PRICE_PER_MTOK,
    OUTPUT_COLUMNS,
    OUTPUT_FILEPATH,
    OUTPUT_PRICE_PER_MTOK,
    STEP_AGENT_PHASE_ORDER,
    USE_SAMPLE,
)
from src.issues import ERROR, summarize_issues
from src.usage_tracker import UsageTracker
from src.utils import normalize_resource

# A predicted step is correct only if all of these match (step_no is the
# position, scored separately by the sequence check).
STEP_FIELDS = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")
# Fields scored individually once two steps are paired on (phase, resource_id).
PAIRED_FIELDS = ("system_id", "operation", "state", "evidence_id")


# --- ANSI Styling Helpers ---
class Style:
    HEADER = "\033[95m\033[1m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


GENERATED_OUTPUT_PATH = OUTPUT_FILEPATH
# Only the 32 sample cases have labels; the 518 evaluation cases do not.
REFERENCE_OUTPUT_PATH = DATASET_PATH / "sample_output.csv" if USE_SAMPLE else None


def report_token_usage(tracker: UsageTracker):
    """Prints a styled, readable token usage and prompt cost report."""
    print(
        f"\n{Style.HEADER}============================================================"
    )
    print(" 📊 MODEL USAGE & TOKEN COST REPORT")
    print(f"============================================================{Style.RESET}")

    by_model = tracker.by_model()
    if not by_model:
        print(
            f"{Style.DIM}ℹ️ No external LLM model calls recorded during this run.{Style.RESET}"
        )
        return

    totals = tracker.totals()

    print(f"\n{Style.CYAN}{Style.BOLD}📈 Overall Token Summary{Style.RESET}")
    print(f"  • Total Model Calls:     {Style.BOLD}{totals.calls}{Style.RESET}")
    print(f"  • Input Tokens:          {totals.input_tokens:,}")
    print(f"  • Output Tokens:         {totals.output_tokens:,}")
    print(
        f"  • Total Tokens:          {Style.GREEN}{totals.total_tokens:,}{Style.RESET}"
    )
    if totals.calls > 0:
        avg_tokens = totals.total_tokens / totals.calls
        print(f"  • Avg Tokens / Call:     {avg_tokens:.2f}")

    print(f"\n{Style.CYAN}{Style.BOLD}🤖 Per-Model Breakdown{Style.RESET}")
    for model_name, usage in by_model.items():
        print(
            f"\n  {Style.BOLD}Model:{Style.RESET} {Style.YELLOW}{model_name}{Style.RESET}"
        )
        print(f"    - Calls:         {usage.calls}")
        print(f"    - Input Tokens:  {usage.input_tokens:,}")
        print(f"    - Output Tokens: {usage.output_tokens:,}")
        print(f"    - Total Tokens:  {usage.total_tokens:,}")

        least = usage.least
        most = usage.most

        if usage.calls:
            print(f"\n    {Style.GREEN}🔹 Least Expensive Prompt:{Style.RESET}")
            print(f"       • Response ID: {least.get('response_id') or 'N/A'}")
            print(f"       • Tokens Used: {least.get('tokens')}")
            print(
                f"       • Prompt:      {Style.DIM}{least.get('prompt', '')}{Style.RESET}"
            )

        if usage.calls:
            print(f"\n    {Style.RED}🔺 Most Expensive Prompt:{Style.RESET}")
            print(f"       • Response ID: {most.get('response_id') or 'N/A'}")
            print(f"       • Tokens Used: {most.get('tokens')}")
            print(
                f"       • Prompt:      {Style.DIM}{most.get('prompt', '')}{Style.RESET}"
            )


USAGE_REPORT_PATH = Path(__file__).parent / "usage_report.md"


def estimate_cost(input_tokens: int, output_tokens: int) -> float | None:
    """USD estimate, or None when prices are not configured in .env."""
    if not (INPUT_PRICE_PER_MTOK and OUTPUT_PRICE_PER_MTOK):
        return None
    return (
        input_tokens * float(INPUT_PRICE_PER_MTOK)
        + output_tokens * float(OUTPUT_PRICE_PER_MTOK)
    ) / 1_000_000


def write_usage_report(tracker: UsageTracker, request_count: int) -> None:
    """Writes usage_report.md from the tracker's real counts (never estimated)."""
    by_model = tracker.by_model()
    totals = tracker.totals()
    cost = estimate_cost(totals.input_tokens, totals.output_tokens)
    fmt = lambda v: "price not configured" if v is None else f"${v:.6f}"

    lines = [
        "# Usage Report — 👻 Ghost Data Still Exists 👻",
        "",
        f"Generated by `code/evaluation/main.py` from `UsageTracker` after a run of "
        f"**{request_count} requests** ({'sample' if USE_SAMPLE else 'full dataset'}).",
        "Token counts are copied from each API response, not estimated.",
        "",
        "## Model information",
        "",
        "Provider: Google Gemini (Interactions API). Only request-intent classification",
        "uses a model; all other logic is deterministic Python.",
        "",
        "## Execution stats",
        "",
        "| Model | Calls | Input tokens | Output tokens | Total tokens |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, u in by_model.items():
        lines.append(
            f"| {name} | {u.calls} | {u.input_tokens:,} | {u.output_tokens:,} | {u.total_tokens:,} |"
        )
    lines.append(
        f"| **Overall** | {totals.calls} | {totals.input_tokens:,} | "
        f"{totals.output_tokens:,} | {totals.total_tokens:,} |"
    )
    per_request = totals.total_tokens / request_count if request_count else 0
    per_call = totals.total_tokens / totals.calls if totals.calls else 0
    lines += [
        "",
        f"- Requests processed: {request_count}",
        f"- Total tokens per request (total ÷ requests): {per_request:.2f}",
        f"- Average tokens per model call: {per_call:.2f}",
        "",
        "## Cost estimate",
        "",
        f"- Input price per 1M tokens: {INPUT_PRICE_PER_MTOK or 'not configured'}",
        f"- Output price per 1M tokens: {OUTPUT_PRICE_PER_MTOK or 'not configured'}",
        f"- Estimated total cost: {fmt(cost)}",
        f"- Estimated cost per request: {fmt(cost / request_count if cost is not None and request_count else None)}",
        "",
        "## Least and most expensive prompts",
        "",
    ]
    if not by_model:
        lines.append(
            "No model calls were recorded in this run, so there are no prompts to show. "
            "See the run warnings in `evaluation_report.md`."
        )
    for name, u in by_model.items():
        for label, d in (("Least expensive", u.least), ("Most expensive", u.most)):
            lines += [
                f"### {name}: {label}",
                "",
                f"- Response ID: {d.get('response_id') or 'N/A'}",
                f"- Tokens: {d.get('tokens')}",
                "",
                "```text",
                str(d.get("prompt", "")),
                "```",
                "",
            ]
    USAGE_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"ℹ️ Usage report written to {USAGE_REPORT_PATH}")


def report_run_issues():
    """Lists every warning/error collected during this run, grouped by message."""
    print(f"\n{Style.HEADER}⚠️  RUN WARNINGS & ERRORS{Style.RESET}")
    issues = summarize_issues()
    if not issues:
        print(f"  {Style.GREEN}None.{Style.RESET}")
        return
    for level, message, count in issues:
        color = Style.RED if level == ERROR else Style.YELLOW
        print(f"  {color}[{level}] x{count}{Style.RESET} {message}")


def parse_steps(raw) -> list[dict]:
    """steps_json cell -> list of step dicts ([] if empty or unparsable)."""
    try:
        steps = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return steps if isinstance(steps, list) else []


def step_key(step: dict) -> tuple:
    return (
        str(step.get("phase", "")).strip().lower(),
        str(step.get("system_id", "")).strip().lower(),
        normalize_resource(step.get("resource_id")),
        str(step.get("operation", "")).strip().lower(),
        str(step.get("state", "")).strip().lower(),
        str(step.get("evidence_id", "")).strip().lower(),
    )


def prf(tp: int, n_pred: int, n_true: int) -> tuple[float, float, float]:
    """Precision, recall, F1. Two empty lists are a perfect match (NOT_APPLICABLE)."""
    if n_pred == 0 and n_true == 0:
        return 1.0, 1.0, 1.0
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_true if n_true else 0.0
    f1 = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0
    return p, r, f1


def pair_steps(pred_steps: list[dict], true_steps: list[dict]):
    """One-to-one pairs of (pred, true) sharing (phase, resource_id), in order."""
    groups = defaultdict(lambda: ([], []))
    for s in pred_steps:
        groups[(s.get("phase"), s.get("resource_id"))][0].append(s)
    for s in true_steps:
        groups[(s.get("phase"), s.get("resource_id"))][1].append(s)
    return [pair for preds, trues in groups.values() for pair in zip(preds, trues)]


def print_distribution(pred_df: pd.DataFrame):
    """Production mode: there are no labels, so show the status distribution only."""
    print(
        f"\n{Style.HEADER}👻 GHOST DATA AUDIT (PRODUCTION MODE: distribution only) 👻 {Style.RESET}"
    )
    counts = pred_df["deletion_status"].value_counts()
    for status, n in counts.items():
        print(f"  • {status}: {n}")
    print(f"  • Total rows: {len(pred_df)}")


def evaluate_predictions(pred_df: pd.DataFrame, true_df: pd.DataFrame):
    """Evaluates case, step, field and sequence accuracy against sample answers."""
    print(
        f"\n{Style.HEADER}============================================================"
    )
    print(" 👻 GHOST DATA AUDIT SCORER (SAMPLE MODE) 👻")
    print(f"============================================================{Style.RESET}")

    # Validate output schema against OUTPUT_COLUMNS constant
    for col in OUTPUT_COLUMNS:
        if col not in pred_df.columns:
            print(
                f"{Style.YELLOW}⚠️ Warning: Expected column '{col}' missing from generated output.{Style.RESET}"
            )

    merged = pd.merge(pred_df, true_df, on="case_id", suffixes=("_pred", "_true"))

    if merged.empty:
        print(
            f"{Style.RED}❌ Error: No matching case_ids found between predictions and reference ground truth.{Style.RESET}"
        )
        return

    # 1. Case-Level Status Accuracy
    y_true = merged["deletion_status_true"]
    y_pred = merged["deletion_status_pred"]

    print(f"\n{Style.CYAN}{Style.BOLD}🎯 1. Case-Level Status Accuracy{Style.RESET}")
    correct_cases = int((y_true == y_pred).sum())
    total_cases = len(y_true)
    accuracy = correct_cases / total_cases

    acc_color = (
        Style.GREEN
        if accuracy >= 0.9
        else (Style.YELLOW if accuracy >= 0.7 else Style.RED)
    )
    print(
        f"  • Overall Accuracy: {acc_color}{Style.BOLD}{accuracy * 100:.2f}%{Style.RESET} ({correct_cases}/{total_cases} cases)"
    )

    # Only labels with real cases, so an absent class does not drag the macro average.
    labels = sorted(set(y_true))
    print(f"\n{Style.BOLD}Classification Report:{Style.RESET}")
    print(classification_report(y_true, y_pred, labels=labels, zero_division=0))

    # 2. Step-Level & Field-Level Accuracy
    print(
        f"{Style.CYAN}{Style.BOLD}📋 2. Step-Level & Field-Level Accuracy{Style.RESET}"
    )
    precisions, recalls, f1s = [], [], []
    field_hits = Counter()
    paired_total = 0
    pred_total = true_total = 0

    for _, row in merged.iterrows():
        pred_steps = parse_steps(row["steps_json_pred"])
        true_steps = parse_steps(row["steps_json_true"])

        diagnose_missing_steps(true_steps, pred_steps)

        # Strict, one-to-one: each expected step can be matched by one prediction.
        tp = sum(
            (
                Counter(map(step_key, pred_steps)) & Counter(map(step_key, true_steps))
            ).values()
        )
        p, r, f1 = prf(tp, len(pred_steps), len(true_steps))
        precisions.append(p)
        recalls.append(r)
        f1s.append(f1)

        pred_total += len(pred_steps)
        true_total += len(true_steps)
        for pred_step, true_step in pair_steps(pred_steps, true_steps):
            paired_total += 1
            for f in PAIRED_FIELDS:
                field_hits[f] += pred_step.get(f) == true_step.get(f)

    n = len(merged)
    print(
        f"  • Step Precision (strict): {Style.BOLD}{sum(precisions) / n:.4f}{Style.RESET}"
    )
    print(
        f"  • Step Recall (strict):    {Style.BOLD}{sum(recalls) / n:.4f}{Style.RESET}"
    )
    print(
        f"  • Step F1 (strict):        {Style.GREEN}{Style.BOLD}{sum(f1s) / n:.4f}{Style.RESET}"
    )
    print(f"  • Steps predicted / expected: {pred_total} / {true_total}")

    print(
        f"\n{Style.BOLD}Field accuracy on steps paired by (phase, resource_id) "
        f"({paired_total} pairs):{Style.RESET}"
    )
    for f in PAIRED_FIELDS:
        acc = field_hits[f] / paired_total if paired_total else 0.0
        print(f"  • {f:<12} {acc * 100:6.2f}%")

    # 3. Sequence & Order Validation (using STEP_AGENT_PHASE_ORDER constant)
    print(
        f"\n{Style.CYAN}{Style.BOLD}🔄 3. Sequence & Ordering Validation{Style.RESET}"
    )
    sequence_exact_matches = 0
    phase_violations = 0

    for _, row in merged.iterrows():
        pred_steps = parse_steps(row["steps_json_pred"])
        true_steps = parse_steps(row["steps_json_true"])

        if pred_steps == true_steps:
            sequence_exact_matches += 1

        last_phase_val = 0
        for step in pred_steps:
            p_val = STEP_AGENT_PHASE_ORDER.get(step.get("phase"), 99)
            if p_val < last_phase_val:
                phase_violations += 1
            last_phase_val = p_val

    seq_rate = sequence_exact_matches / n
    print(f"  • Exact Sequence Match:   {Style.BOLD}{seq_rate * 100:.2f}%{Style.RESET}")
    viol_color = Style.GREEN if phase_violations == 0 else Style.RED
    print(
        f"  • Phase Order Violations: {viol_color}{Style.BOLD}{phase_violations}{Style.RESET}"
    )
    print(
        f"{Style.HEADER}============================================================{Style.RESET}\n"
    )


# --- DIAGNOSTIC SCRIPTS ----


def diagnose_missing_steps(expected_steps, predicted_steps):
    # Normalize keys to verify if formatting is the culprit
    def make_key(step):
        return (
            str(step.get("phase", "")).strip().lower(),
            normalize_resource(step.get("resource_id") or step.get("resource")),
        )

    predicted_keys = {make_key(p) for p in predicted_steps}

    missing_steps = []
    for exp in expected_steps:
        key = make_key(exp)
        if key not in predicted_keys:
            missing_steps.append({"raw_expected": exp, "normalized_key": key})

    print(f"Total unmatched expected steps: {len(missing_steps)}")
    for item in missing_steps[:10]:  # Inspect the first 10
        print(
            f"Missing -> Phase: '{item['raw_expected'].get('phase')}' | Resource: '{item['raw_expected'].get('resource_id')}'"
        )

    return missing_steps


def inspect_resource_id_differences(expected_steps, predicted_steps):
    print("\n" + "=" * 60)
    print("🔍 RESOURCE_ID & PHASE SCHEMA / NAMING INSPECTION")
    print("=" * 60)

    # Extract unique values across expected vs predicted
    exp_phases = {str(s.get("phase")) for s in expected_steps}
    pred_phases = {str(s.get("phase")) for s in predicted_steps}

    exp_resources = {
        str(s.get("resource_id") or s.get("resource")) for s in expected_steps
    }
    pred_resources = {
        str(s.get("resource_id") or s.get("resource")) for s in predicted_steps
    }

    print("\n--- PHASES ---")
    print(f"Expected Phases ({len(exp_phases)}):", sorted(list(exp_phases)))
    print(f"Predicted Phases ({len(pred_phases)}):", sorted(list(pred_phases)))

    diff_phases = exp_phases - pred_phases
    if diff_phases:
        print(f"⚠️  Phases in expected but NEVER predicted: {diff_phases}")

    print("\n--- RESOURCE IDs (Sample Differences) ---")
    print(f"Total Unique Expected Resources: {len(exp_resources)}")
    print(f"Total Unique Predicted Resources: {len(pred_resources)}")

    unmatched_resources = exp_resources - pred_resources
    if unmatched_resources:
        print(
            f"\n⚠️  {len(unmatched_resources)} Expected resource_ids had NO exact string match in predictions:"
        )
        for r in sorted(list(unmatched_resources))[:15]:  # Display top 15
            print(f"  • Expected: '{r}'")
            # Find closest predicted candidate
            matches = [
                p
                for p in pred_resources
                if r.lower().replace("-", "_") in p.lower().replace("-", "_")
            ]
            if matches:
                print(f"\t    Possible predicted matches: {matches}")
            else:
                print("\t    No obvious string similarity found in predictions.")

    print("=" * 60 + "\n")


def run_project_evaluation(tracker: UsageTracker = None, request_count: int = 0):
    """Call AFTER the output file is saved, so it scores this run's output."""
    if not GENERATED_OUTPUT_PATH.exists():
        print(
            f"{Style.YELLOW}⚠️ Generated output missing at '{GENERATED_OUTPUT_PATH}'. Please run code/main.py first.{Style.RESET}"
        )
        return

    pred = pd.read_csv(GENERATED_OUTPUT_PATH)

    if REFERENCE_OUTPUT_PATH is None or not REFERENCE_OUTPUT_PATH.exists():
        print_distribution(pred)
    else:
        evaluate_predictions(pred, pd.read_csv(REFERENCE_OUTPUT_PATH))

    if tracker:
        report_token_usage(tracker)
        write_usage_report(tracker, request_count or len(pred))

    report_run_issues()


if __name__ == "__main__":
    run_project_evaluation()
