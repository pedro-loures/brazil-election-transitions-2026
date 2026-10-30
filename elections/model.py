"""Explicit ecological regression, distinct from the thread's unspecified model."""
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, minimize

ORIGINS = ["a", "b", "other", "invalid", "abstention"]
DESTINATIONS = ["a", "b", "invalid", "abstention"]


def fit_transition(x, y, no_cross=False):
    """Fit common row-stochastic P, with exact municipality destination margins.

    Minimize sum_s ||x_s P - y_s||^2 / N_s. Rates are constant across
    sections within a municipality. Section margins are approximated, not exact.
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    if x.shape[1] != 5 or y.shape != (len(x), 4):
        raise ValueError("Expected n x 5 origins and n x 4 destinations")
    if not np.allclose(x.sum(axis=1), y.sum(axis=1)):
        raise ValueError("Transition analysis requires equal section electorates")
    n = x.sum(axis=1)
    if (n <= 0).any() or (x < 0).any() or (y < 0).any():
        raise ValueError("Invalid origin/destination counts")
    gram = x.T @ (x / n[:, None]) / len(x)
    cross = x.T @ (y / n[:, None]) / len(x)
    eq = np.zeros((8, 20))
    for i in range(5):
        eq[i, i*4:(i+1)*4] = 1
    origin_share = x.sum(axis=0) / n.sum()
    destination_share = y.sum(axis=0) / n.sum()
    for j in range(3):
        eq[5+j, j::4] = origin_share
    rhs = np.r_[np.ones(5), destination_share[:3]]
    lower, upper = np.zeros(20), np.ones(20)
    start = np.tile(destination_share, (5, 1)).ravel()
    if no_cross:
        upper[1] = 0  # A -> B
        upper[4] = 0  # B -> A
        feasible = linprog(np.zeros(20), A_eq=eq, b_eq=rhs,
                           bounds=list(zip(lower, upper)), method="highs")
        if not feasible.success:
            return {"status": "infeasible", "message": feasible.message}
        start = feasible.x

    def objective(flat):
        p = flat.reshape(5, 4)
        return float(np.sum(p * (gram @ p)) - 2 * np.sum(p * cross))

    def gradient(flat):
        return (2 * (gram @ flat.reshape(5, 4) - cross)).ravel()

    result = minimize(objective, start, jac=gradient, method="SLSQP",
                      bounds=Bounds(lower, upper), constraints=LinearConstraint(eq, rhs, rhs),
                      options={"maxiter": 250, "ftol": 1e-9})
    if (not result.success or np.max(np.abs(eq @ result.x - rhs)) > 1e-6
            or np.min(result.x) < -1e-7 or np.max(result.x - upper) > 1e-7):
        return {"status": "optimizer_failed", "message": result.message}
    p = result.x.reshape(5, 4)
    residual = x @ p - y
    return {"status": "ok", "p": p, "flows": x.sum(axis=0)[:, None] * p,
            "rmse_votes": float(np.sqrt(np.mean(residual ** 2))),
            "max_section_error_votes": float(np.abs(residual).max()),
            "margin_error_votes": float(np.abs(residual.sum(axis=0)).max())}


def model_city(task):
    uf, code, x, y, draws, seed, min_sections = task
    diagnostic = {"uf": uf, "municipality_code": code, "model_sections": len(x),
                  "bootstrap_requested": draws}
    if len(x) < min_sections:
        diagnostic["model_status"] = "too_few_sections"
        return diagnostic, []
    proportions = x / x.sum(axis=1, keepdims=True)
    rank = np.linalg.matrix_rank(proportions)
    diagnostic.update(design_rank=int(rank), design_condition=float(np.linalg.cond(proportions)))
    if rank < 5:
        diagnostic["model_status"] = "rank_deficient"
        return diagnostic, []
    full = fit_transition(x, y)
    diagnostic["model_status"] = full["status"]
    if full["status"] != "ok":
        return diagnostic, []
    restricted = fit_transition(x, y, no_cross=True)
    diagnostic["no_cross_status"] = restricted["status"]
    for name, fit in [("full", full), ("no_cross", restricted)]:
        if fit["status"] == "ok":
            for stat in ["rmse_votes", "max_section_error_votes", "margin_error_votes"]:
                diagnostic[f"{name}_{stat}"] = fit[stat]
    rng = np.random.default_rng(np.random.SeedSequence([seed, int(code)]))
    samples = []
    for _ in range(draws):
        ix = rng.integers(0, len(x), len(x))
        if np.linalg.matrix_rank(proportions[ix]) < 5:
            continue
        fit = fit_transition(x[ix], y[ix])
        if fit["status"] == "ok":
            # Apply resampled rate estimates to the original municipality electorate.
            samples.append(x.sum(axis=0)[:, None] * fit["p"])
    diagnostic["bootstrap_successful"] = len(samples)
    diagnostic["bootstrap_status"] = ("not_requested" if not draws else
                                       "ok" if len(samples) >= .8 * draws else "insufficient_success")
    quantiles = np.quantile(samples, [.025, .5, .975], axis=0) if samples else None
    rows = []
    for name, fit in [("full", full), ("no_cross", restricted)]:
        if fit["status"] != "ok":
            continue
        for i, origin in enumerate(ORIGINS):
            for j, destination in enumerate(DESTINATIONS):
                row = {"uf": uf, "municipality_code": code, "model": name,
                       "origin": origin, "destination": destination,
                       "rate": float(fit["p"][i, j]), "estimated_voters": float(fit["flows"][i, j])}
                if name == "full" and quantiles is not None:
                    row.update(bootstrap_p025=float(quantiles[0, i, j]),
                               bootstrap_median=float(quantiles[1, i, j]),
                               bootstrap_p975=float(quantiles[2, i, j]))
                rows.append(row)
    return diagnostic, rows
