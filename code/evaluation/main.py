# /code/evaluation/main.py

"""
+-----------------------------------------------------------------------------+
|                         EVALUTATION PIPELINE                                |
+-----------------------------------------------------------------------------+

Evaluation Scorer and Usage Analysis for Ghost Data Still Exists
Computes accuracy metrics and extracts real token/prompt cost metrics
from UsageTracker to update evaluation_report.md and usage_report.md.
"""

import json
import os

import pandas as pd
from sklearn.metrics import classification_report
from src.constants import (
    DATASET_PATH,
    OUTPUT_COLUMNS,
    OUTPUT_FILE,
    STEP_AGENT_PHASE_ORDER,
)
from src.constants import (
    USE_SAMPLE as ENV_USE_SAMPLE,
)
from src.usage_tracker import UsageTracker


# --- ANSI Styling Helpers ---
class Style:
    HEADER = "\033[95m\033[1m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


# Environment and output path detection using constants
USE_SAMPLE = os.getenv("USE_SAMPLE", ENV_USE_SAMPLE).lower() in ("true", "1", "t")
GENERATED_OUTPUT_PATH = str(OUTPUT_FILE)
REFERENCE_OUTPUT_PATH = str(
    DATASET_PATH / ("sample_output.csv" if USE_SAMPLE else "output.csv")
)


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

        if least.get("resource_id") or least.get("tokens", 100000) < 100000:
            print(f"\n    {Style.GREEN}🔹 Least Expensive Prompt:{Style.RESET}")
            print(f"       • Response ID: {least.get('resource_id') or 'N/A'}")
            print(f"       • Tokens Used: {least.get('tokens')}")
            snippet = repr(least.get("prompt", ""))[:80]
            print(f"       • Prompt:      {Style.DIM}{snippet}...{Style.RESET}")

        if most.get("resource_id") or most.get("tokens", 0) > 0:
            print(f"\n    {Style.RED}🔺 Most Expensive Prompt:{Style.RESET}")
            print(f"       • Response ID: {most.get('resource_id') or 'N/A'}")
            print(f"       • Tokens Used: {most.get('tokens')}")
            snippet = repr(most.get("prompt", ""))[:80]
            print(f"       • Prompt:      {Style.DIM}{snippet}...{Style.RESET}")


def evaluate_predictions(pred_df: pd.DataFrame, true_df: pd.DataFrame):
    """Evaluates case, step, and sequence accuracy against ground truth."""
    mode_label = "SAMPLE" if USE_SAMPLE else "PRODUCTION"
    print(
        f"\n{Style.HEADER}============================================================"
    )
    print(f" 👻 GHOST DATA AUDIT SCORER ({mode_label} MODE)")
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
    accuracy = correct_cases / total_cases if total_cases > 0 else 0.0

    acc_color = (
        Style.GREEN
        if accuracy >= 0.9
        else (Style.YELLOW if accuracy >= 0.7 else Style.RED)
    )
    print(
        f"  • Overall Accuracy: {acc_color}{Style.BOLD}{accuracy * 100:.2f}%{Style.RESET} ({correct_cases}/{total_cases} cases)"
    )

    labels = ["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]
    print(f"\n{Style.BOLD}Classification Report:{Style.RESET}")
    print(classification_report(y_true, y_pred, labels=labels, zero_division=0))

    # 2. Step-Level & Field-Level Accuracy
    print(
        f"{Style.CYAN}{Style.BOLD}📋 2. Step-Level & Field-Level Accuracy{Style.RESET}"
    )
    step_precisions, step_recalls, step_f1s = [], [], []

    for _, row in merged.iterrows():
        try:
            pred_steps = json.loads(row["steps_json_pred"])
        except Exception:
            pred_steps = []

        try:
            true_steps = json.loads(row["steps_json_true"])
        except Exception:
            true_steps = []

        matched_count = 0
        for p_step in pred_steps:
            for t_step in true_steps:
                if p_step.get("resource_id") == t_step.get(
                    "resource_id"
                ) and p_step.get("phase") == t_step.get("phase"):
                    matched_count += 1
                    break

        tp = matched_count
        fp = max(0, len(pred_steps) - tp)
        fn = max(0, len(true_steps) - tp)

        p = (
            tp / (tp + fp)
            if (tp + fp) > 0
            else (1.0 if len(pred_steps) == 0 and len(true_steps) == 0 else 0.0)
        )
        r = (
            tp / (tp + fn)
            if (tp + fn) > 0
            else (1.0 if len(pred_steps) == 0 and len(true_steps) == 0 else 0.0)
        )
        f1 = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0

        step_precisions.append(p)
        step_recalls.append(r)
        step_f1s.append(f1)

    avg_p = sum(step_precisions) / len(step_precisions) if step_precisions else 0.0
    avg_r = sum(step_recalls) / len(step_recalls) if step_recalls else 0.0
    avg_f1 = sum(step_f1s) / len(step_f1s) if step_f1s else 0.0

    print(f"  • Step Precision: {Style.BOLD}{avg_p:.4f}{Style.RESET}")
    print(f"  • Step Recall:    {Style.BOLD}{avg_r:.4f}{Style.RESET}")
    print(f"  • Step F1 Score:  {Style.GREEN}{Style.BOLD}{avg_f1:.4f}{Style.RESET}")

    # 3. Sequence & Order Validation (using STEP_AGENT_PHASE_ORDER constant)
    print(
        f"\n{Style.CYAN}{Style.BOLD}🔄 3. Sequence & Ordering Validation{Style.RESET}"
    )
    sequence_exact_matches = 0
    phase_violations = 0

    for _, row in merged.iterrows():
        try:
            pred_steps = json.loads(row["steps_json_pred"])
            true_steps = json.loads(row["steps_json_true"])
        except Exception:
            continue

        if pred_steps == true_steps:
            sequence_exact_matches += 1

        last_phase_val = 0
        for step in pred_steps:
            p_val = STEP_AGENT_PHASE_ORDER.get(step.get("phase"), 99)
            if p_val < last_phase_val:
                phase_violations += 1
            last_phase_val = p_val

    seq_rate = sequence_exact_matches / len(merged) if merged.shape[0] > 0 else 0.0
    print(f"  • Exact Sequence Match:   {Style.BOLD}{seq_rate * 100:.2f}%{Style.RESET}")
    viol_color = Style.GREEN if phase_violations == 0 else Style.RED
    print(
        f"  • Phase Order Violations: {viol_color}{Style.BOLD}{phase_violations}{Style.RESET}"
    )
    print(
        f"{Style.HEADER}============================================================{Style.RESET}\n"
    )


def run_evaluation(tracker: UsageTracker = None):
    if not os.path.exists(GENERATED_OUTPUT_PATH):
        print(
            f"{Style.YELLOW}⚠️ Generated output missing at '{GENERATED_OUTPUT_PATH}'. Please run code/main.py first.{Style.RESET}"
        )
        return

    if not os.path.exists(REFERENCE_OUTPUT_PATH):
        print(
            f"{Style.DIM}ℹ️ Reference ground truth missing at '{REFERENCE_OUTPUT_PATH}'. Skipping comparison (Distribution-only mode).{Style.RESET}"
        )
        if tracker:
            report_token_usage(tracker)
        return

    pred = pd.read_csv(GENERATED_OUTPUT_PATH)
    true = pd.read_csv(REFERENCE_OUTPUT_PATH)
    evaluate_predictions(pred, true)

    if tracker:
        report_token_usage(tracker)


if __name__ == "__main__":
    run_evaluation()
