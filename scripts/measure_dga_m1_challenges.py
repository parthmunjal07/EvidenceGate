"""Read-only, no-tuning challenge measurements for frozen M1-R1 inputs."""
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


FILES = {
    "crux_broad": ("CRUX_202608_SOURCE_SHIFT_1M.csv", "host", "bdc202c2e8f926376ffba83a5477c0b3166b1d37e82914d55c0b4d926111a223"),
    "crux_machine_looking": ("CRUX_202608_MACHINE_LOOKING_CANDIDATES_250K.csv", "host", "1eecd1bbacbbde4e76eac4ff40151854a81b5168701118367186c2242af1b0c8"),
}


def main() -> None:
    root = Path("artifacts/dga/local/m14a")
    model = joblib.load("artifacts/dga/local/DGA_M1_R1_SERIALIZED_MODEL.joblib")
    index = list(model["classifier"].classes_).index("dga")
    def score(values):
        strings = values.map(lambda value: str(value).strip().lower().rstrip("."))
        return model["classifier"].predict_proba(model["vectorizer"].transform(strings))[:, index]
    def summary(values):
        return {"rows": len(values), "quantiles": {str(q): float(np.quantile(values, q)) for q in (.01, .05, .5, .95, .99)},
                "score_at_or_above_historical_0_5_rate": float(np.mean(values >= .5)),
                "note": "0.5 is a historical comparison point, not a production threshold."}
    test = pd.read_parquet(root / "openset_test.parquet")
    result = {"kind": "POST_HOC_CHALLENGE_MEASUREMENT_NO_TUNING", "evaluations": {}}
    for name, split in (("unknown_family", "test_unknown_family"), ("ood", "test_unknown_ood")):
        result["evaluations"][name] = summary(score(test.loc[test.split.eq(split), "domain"]))
    for name, (filename, column, expected) in FILES.items():
        path = root / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit(f"{name} hash mismatch; refusing challenge measurement")
        parts = [score(chunk[column]) for chunk in pd.read_csv(path, usecols=[column], chunksize=10000)]
        result["evaluations"][name] = summary(np.concatenate(parts))
    Path("benchmark_results/dga_m1_r1_challenge_measurement.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
