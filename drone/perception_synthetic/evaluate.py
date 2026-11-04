"""Withheld truth is opened here only, after numerical replay completes."""
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np
from scipy.stats import chi2

from maritime_perception.validation import load_json


def evaluate(session, output):
    truth = load_json(Path(session)/"truth.json")
    reports = [json.loads(raw) for raw in (Path(output)/"reports.jsonl").read_text().splitlines()]
    targets = {target["id"]: np.asarray(target["position_enu_m"][:2]) for target in truth["targets"]}
    associations = truth["detections"]
    track_targets, target_tracks = defaultdict(set), defaultdict(set)
    last_identity, identity_switches = {}, 0
    errors, residuals, containment, shared_eigenvalues, independent_traces = [], [], [], [], []
    rejected, statuses = Counter(), Counter()
    ambiguous, max_age, latencies = 0, 0., []
    for report in reports:
        for decision in report["diagnostics"]:
            if decision["status"] == "rejected":
                rejected[decision["reason"]] += 1
            if decision["status"] == "ambiguous":
                ambiguous += 1
            target_id = associations.get(decision.get("detection_id"))
            if target_id and decision["status"] in ("initiated", "matched"):
                track_id = decision["track_id"]
                track_targets[track_id].add(target_id)
                target_tracks[target_id].add(track_id)
                if target_id in last_identity and last_identity[target_id] != track_id:
                    identity_switches += 1
                last_identity[target_id] = track_id
        for track in report["tracks"]:
            statuses[track["estimate_status"]] += 1
            max_age = max(max_age, track["age_s"])
            ids = track_targets[track["id"]]
            if len(ids) != 1 or track["association_status"] != "confirmed":
                continue
            residual = np.asarray(track["position_enu_m"][:2])-targets[next(iter(ids))]
            cov = np.asarray(track["uncertainty"]["covariance_en_m2"])
            residuals.append(residual)
            errors.append(float(np.linalg.norm(residual)))
            containment.append(float(residual @ np.linalg.solve(cov, residual)) <= chi2.ppf(.95, 2))
        from datetime import datetime
        latencies.append((datetime.fromisoformat(report["published_at"].replace("Z", "+00:00"))-
                          datetime.fromisoformat(report["state_at"].replace("Z", "+00:00"))).total_seconds())
    final = reports[-1] if reports else {"tracks": []}
    for track in final["tracks"]:
        shared_eigenvalues.append(float(np.linalg.eigvalsh(track["uncertainty"]["shared_covariance_en_m2"])[0]))
        independent_traces.append(float(np.trace(track["uncertainty"]["independent_covariance_en_m2"])))
    replay_errors = (Path(output)/"replay_errors.jsonl").read_text().splitlines()
    return {"scenario": truth["scenario"], "report_count": len(reports),
            "true_object_count": len(targets), "final_track_count": len(final["tracks"]),
            "final_confirmed_track_count": sum(t["association_status"] == "confirmed" for t in final["tracks"]),
            "identity_switches": identity_switches,
            "fragmentations": sum(max(0, len(ids)-1) for ids in target_tracks.values()),
            "mixed_identity_tracks": sum(len(ids) > 1 for ids in track_targets.values()),
            "objects_with_identity": len(target_tracks),
            "horizontal_error_m": {"median": float(np.median(errors)) if errors else None,
                                   "p95": float(np.quantile(errors, .95)) if errors else None,
                                   "max": max(errors, default=None)},
            "mean_bias_en_m": np.mean(residuals, axis=0).tolist() if residuals else None,
            "single_run_95_region_containment": float(np.mean(containment)) if containment else None,
            "final_min_shared_eigenvalues_m2": shared_eigenvalues,
            "final_independent_covariance_traces_m2": independent_traces,
            "rejection_counts": dict(rejected), "replay_error_count": len(replay_errors),
            "ambiguous_observations": ambiguous, "track_status_counts": dict(statuses),
            "maximum_observation_age_s": max_age, "maximum_report_latency_s": max(latencies, default=None),
            "assumptions": ["synthetic calibration; point targets on a horizontal water plane",
                            "stationary objects and constant session-wide Gaussian navigation errors",
                            "independent pixel and distinct pose-sample errors; shared sample IDs preserve reuse",
                            "first-order propagation; association-conditional distributions",
                            "single-run containment is not statistical or physical coverage acceptance"],
            "physical_accuracy_validated": False}
