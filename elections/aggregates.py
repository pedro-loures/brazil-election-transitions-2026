"""Geographic sums of municipal transition estimates, with explicit coverage.

These are sums of fitted matrices, not new state/region/national regressions.
Municipal bootstrap quantiles are deliberately not added into aggregate intervals.
"""
import numpy as np

from .model import ORIGINS, DESTINATIONS

STATES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
    "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}
REGIONS = {
    "north": ("North · Norte", ["AC", "AP", "AM", "PA", "RO", "RR", "TO"]),
    "northeast": ("Northeast · Nordeste", ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"]),
    "central-west": ("Central-West · Centro-Oeste", ["DF", "GO", "MT", "MS"]),
    "southeast": ("Southeast · Sudeste", ["ES", "MG", "RJ", "SP"]),
    "south": ("South · Sul", ["PR", "RS", "SC"]),
}
COUNT_FIELDS = [f"{key}_{turn}" for key in ["a", "b", "other", "invalid", "eligible", "turnout", "abstention", "valid"] for turn in [1, 2]]
ANALYZED_FIELDS = ["analyzed_"+field for field in COUNT_FIELDS]


def aggregate_records(cities, flow_rows):
    cities = cities[cities.uf.ne("ZZ")].copy()
    if cities.empty or not set(cities.uf).issubset(STATES):
        raise ValueError("Expected domestic TSE municipalities with known UFs")
    state_sets = [set(states) for _, states in REGIONS.values()]
    assert set.union(*state_sets) == set(STATES)
    assert sum(map(len, state_sets)) == len(STATES)
    groups = [("state", uf, STATES[uf], cities[cities.uf.eq(uf)]) for uf in sorted(cities.uf.unique())]
    groups += [("region", key, name, cities[cities.uf.isin(ufs)]) for key, (name, ufs) in REGIONS.items()
               if cities.uf.isin(ufs).any()]
    groups += [("country", "BR", "Brazil · domestic electorate", cities)]
    models = {}
    for model, rows in flow_rows.groupby("model"):
        covered = rows[["uf", "municipality_code"]].drop_duplicates()
        models[model] = (rows, covered)
    records = {}
    for level, key, label, members in groups:
        full = {field: float(members[field].sum()) for field in COUNT_FIELDS}
        full.update({"municipality": label, "municipality_code": None, "uf": key if level == "state" else None,
                     "sections_union": int(members.sections_union.sum()), "municipalities_total": len(members)})
        fitted = {}
        for model, (rows, covered_keys) in models.items():
            covered = members.merge(covered_keys, on=["uf", "municipality_code"], how="inner", validate="one_to_one")
            if covered.empty:
                continue
            selected = rows.merge(members[["uf", "municipality_code"]], on=["uf", "municipality_code"], how="inner", validate="many_to_one")
            table = selected.groupby(["origin", "destination"]).estimated_voters.sum().unstack("destination").reindex(index=ORIGINS, columns=DESTINATIONS)
            matrix = np.maximum(table.to_numpy(), 0)
            analyzed = {field: float(covered[field].sum()) for field in ANALYZED_FIELDS}
            source = np.array([analyzed[f"analyzed_{origin}_1"] for origin in ORIGINS])
            target = np.array([analyzed[f"analyzed_{destination}_2"] for destination in DESTINATIONS])
            if not (np.allclose(matrix.sum(axis=1), source, atol=.001)
                    and np.allclose(matrix.sum(axis=0), target, atol=.001)):
                raise ValueError(f"Aggregate margins do not reconcile: {level} {key} {model}")
            coverage = {**analyzed, "sections_analyzed": int(covered.sections_analyzed.sum()),
                        "municipalities_modeled": len(covered), "sections_union": full["sections_union"],
                        "electorate_coverage": analyzed["analyzed_eligible_1"] / full["eligible_1"] if full["eligible_1"] else None}
            fitted[model] = {"matrix": matrix.round(6).tolist(), "coverage": coverage,
                             "uncertainty": "Not calculated: municipal bootstrap quantiles cannot be summed into an aggregate interval"}
        records[f"{level}-{key}"] = {"city": full, "models": fitted,
            "aggregate": {"level": level, "key": key, "label": label,
                          "method": "Sum of municipal model estimates; no aggregate refit",
                          "municipalities_total": len(members), "overseas_excluded": True}}
    return records
