"""Read-only M14A post-hoc validation of immutable DGA M1-R1 bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import tldextract
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)

from evidencegate.plugins.providers.dga_m1 import (
    ARTIFACT_SHA256,
    R1_NEGATIVE_CLASS,
    R1_POSITIVE_CLASS,
    r1_class_semantic_failure,
)

INPUTS = {
    "train": (
        "openset_train.parquet",
        "32e469d50bdc367eed324b796d9bf2b43200b735d504319e91ea7564aa503c0c",
        319999,
    ),
    "validation": (
        "openset_val.parquet",
        "69100d0372926e178d8dc47f6a342df957d8e3ca8191db9b9d0be067fd1528de",
        40000,
    ),
    "test": (
        "openset_test.parquet",
        "2b3d376929e5ffc26837f4a220bc9d421039ad7aa9cad105ccff8ffb3374ada0",
        290000,
    ),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(value: object) -> str:
    return str(value).strip().lower().rstrip(".")


def semantic_score(model: dict, values: pd.Series) -> np.ndarray:
    classes = list(model["classifier"].classes_)
    index = classes.index(R1_POSITIVE_CLASS)
    matrix = model["vectorizer"].transform(values.map(normalize))
    return model["classifier"].predict_proba(matrix)[:, index]


def metric_record(model: dict, table: pd.DataFrame) -> dict[str, object]:
    labels = table["label"]
    scores = semantic_score(model, table["domain"])
    prediction = model["classifier"].predict(
        model["vectorizer"].transform(table["domain"].map(normalize))
    )
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels,
        prediction,
        average="binary",
        pos_label=R1_POSITIVE_CLASS,
        zero_division=0,
    )
    is_positive = labels.eq(R1_POSITIVE_CLASS)
    return {
        "rows": len(table),
        "positive_rows": int(is_positive.sum()),
        "label_counts": {str(k): int(v) for k, v in labels.value_counts().items()},
        "accuracy": float(accuracy_score(labels, prediction)),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "auroc": float(roc_auc_score(is_positive, scores)),
        "pr_auc": float(average_precision_score(is_positive, scores)),
    }


def candidate(value: object, extractor: tldextract.TLDExtract) -> tuple[str | None, str]:
    historical = normalize(value)
    if not historical:
        return None, "empty"
    if any(ord(char) > 127 for char in historical):
        return None, "unicode"
    result = extractor(historical)
    if not result.suffix or not result.domain:
        return None, "unknown_or_internal_suffix"
    return f"{result.domain}.{result.suffix}", "available"


def representation_audit(tables: dict[str, pd.DataFrame]) -> dict[str, object]:
    private = tldextract.TLDExtract(suffix_list_urls=(), include_psl_private_domains=True)
    public = tldextract.TLDExtract(suffix_list_urls=(), include_psl_private_domains=False)
    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    total = exact = unavailable = private_changes = 0
    for name, table in tables.items():
        for value in table["domain"]:
            total += 1
            historical = normalize(value)
            live, status = candidate(value, private)
            public_live, _ = candidate(value, public)
            category = (
                "exact" if live == historical else (status if live is None else "changed_by_psl")
            )
            counts[category] = counts.get(category, 0) + 1
            if category != "exact":
                examples.setdefault(category, []).append(historical)
            exact += category == "exact"
            unavailable += live is None
            private_changes += live != public_live
    return {
        "scope_rows": total,
        "exact_parity_count": exact,
        "exact_parity_rate": exact / total,
        "changed_by_psl_count": counts.get("changed_by_psl", 0),
        "unavailable_count": unavailable,
        "unavailable_rate": unavailable / total,
        "categories": counts,
        "representative_examples": {k: v[:10] for k, v in examples.items()},
        "private_psl_changed_count": private_changes,
        "private_psl_changed_rate": private_changes / total,
        "unknown_suffix_count": counts.get("unknown_or_internal_suffix", 0),
        "unicode_count": counts.get("unicode", 0),
        "policy": "tldextract 5.1.3 bundled snapshot; suffix_list_urls=(); private domains enabled",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    input_records, tables = {}, {}
    for name, (filename, expected_hash, rows) in INPUTS.items():
        path = args.data_dir / filename
        actual = digest(path)
        if actual != expected_hash:
            raise SystemExit(f"{name} hash mismatch; refusing evaluation")
        table = pd.read_parquet(path)
        if len(table) != rows:
            raise SystemExit(f"{name} row count mismatch; refusing evaluation")
        tables[name] = table
        input_records[name] = {
            "sha256": actual,
            "rows": len(table),
            "label_dtype": str(table.label.dtype),
            "label_counts": {str(k): int(v) for k, v in table.label.value_counts().items()},
        }

    if digest(args.artifact) != ARTIFACT_SHA256:
        raise SystemExit("artifact hash mismatch; refusing evaluation")
    model = joblib.load(args.artifact)
    classes = list(model["classifier"].classes_)
    failure = r1_class_semantic_failure(classes, R1_POSITIVE_CLASS, R1_NEGATIVE_CLASS)
    if failure:
        raise SystemExit(f"R1 semantic class contract failed: {failure}")
    known = tables["test"].loc[tables["test"]["split"].eq("test_known")].copy()
    validation = metric_record(model, tables["validation"])
    known_metrics = metric_record(model, known)
    historical = joblib.load(args.historical)
    fixture = known.iloc[np.linspace(0, len(known) - 1, 12, dtype=int)]
    r1_scores = semantic_score(model, fixture["domain"])
    historical_comparison: dict[str, object]
    try:
        historical_scores = historical["classifier"].predict_proba(
            historical["vectorizer"].transform(fixture["domain"].map(normalize))
        )[:, list(historical["classifier"].classes_).index(1)]
        historical_comparison = {
            "status": "AVAILABLE",
            "scores": [float(value) for value in historical_scores],
        }
    except Exception as exc:
        historical_comparison = {
            "status": "UNAVAILABLE_IN_R1_ENVIRONMENT",
            "exception_type": type(exc).__name__,
            "detail": str(exc),
            "artifact_sklearn_version": getattr(
                historical["classifier"], "_sklearn_version", "1.8.0"
            ),
        }
    posthoc = {
        "kind": "POST_HOC_R1_ARTIFACT_VALIDATION",
        "artifact_sha256": ARTIFACT_SHA256,
        "input_verification": input_records,
        "classes": classes,
        "positive_class": R1_POSITIVE_CLASS,
        "positive_class_index": classes.index(R1_POSITIVE_CLASS),
        "validation": validation,
        "known_test": known_metrics,
        "historical_reference": {
            "validation_auroc": 0.9934168536674146,
            "known_test_auroc": 0.9936188955033447,
        },
        "auroc_delta": {
            "validation": validation["auroc"] - 0.9934168536674146,
            "known_test": known_metrics["auroc"] - 0.9936188955033447,
        },
        "deterministic_fixture": [
            {"row_index": int(index), "domain": str(domain), "r1_score": float(r1)}
            for index, domain, r1 in zip(fixture.index, fixture.domain, r1_scores)
        ],
        "historical_comparison": historical_comparison,
        "original_run_outputs": "MISSING; this is post-hoc validation, not original output recreation",
    }
    audit = representation_audit(
        {"train": tables["train"], "validation": tables["validation"], "known_test": known}
    )
    (args.output_dir / "dga_m1_r1_posthoc_validation.json").write_text(
        json.dumps(posthoc, indent=2), encoding="utf-8"
    )
    (args.output_dir / "dga_m1_r1_representation_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
