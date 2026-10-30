"""Read only the national presidential members, never BR + BRASIL together."""
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

KEY = ["uf", "municipality_code", "zone", "section"]
ROUND_KEY = KEY + ["round"]
RENAME = {
    "SG_UF": "uf", "CD_MUNICIPIO": "municipality_code", "NM_MUNICIPIO": "municipality",
    "NR_ZONA": "zone", "NR_SECAO": "section", "NR_TURNO": "round",
    "NR_LOCAL_VOTACAO": "polling_place", "QT_APTOS": "eligible",
    "QT_COMPARECIMENTO": "turnout", "QT_ABSTENCOES": "abstention",
    "QT_VOTOS_BRANCOS": "blank", "QT_VOTOS_NULOS": "null",
    "QT_VOTOS_NOMINAIS": "nominal", "ST_SECAO_INSTALADA": "installed",
    "ST_SECAO_ANULADA": "annulled", "NR_VOTAVEL": "candidate_number",
    "NM_VOTAVEL": "candidate_name", "QT_VOTOS": "votes",
}


def chunks(path, year, stem, columns):
    with zipfile.ZipFile(path) as archive:
        member = f"{stem}_{year}_BR.csv"
        if member not in archive.namelist():
            raise ValueError(f"Missing presidential file {member}")
        with archive.open(member) as stream:
            for chunk in pd.read_csv(stream, sep=";", encoding="latin1", usecols=columns,
                                     chunksize=250_000, low_memory=False):
                yield chunk


def prepare(raw, output, year):
    raw, output = Path(raw), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    common = ["ANO_ELEICAO", "CD_TIPO_ELEICAO", "CD_CARGO", "CD_ELEICAO"]
    detail_cols = ["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
                   "NR_TURNO", "NR_LOCAL_VOTACAO", "QT_APTOS", "QT_COMPARECIMENTO",
                   "QT_ABSTENCOES", "QT_VOTOS_BRANCOS", "QT_VOTOS_NULOS", "QT_VOTOS_NOMINAIS",
                   "ST_SECAO_INSTALADA", "ST_SECAO_ANULADA"]
    detail = []
    election_ids = {}
    for d in chunks(raw / f"detalhe_votacao_secao_{year}.zip", year,
                    "detalhe_votacao_secao", common + detail_cols):
        d = d[d.ANO_ELEICAO.eq(year) & d.CD_TIPO_ELEICAO.eq(2) & d.CD_CARGO.eq(1)]
        for turn, g in d.groupby("NR_TURNO"):
            election_ids.setdefault(int(turn), set()).update(g.CD_ELEICAO.unique().tolist())
        detail.append(d[detail_cols].rename(columns=RENAME))
    detail = pd.concat(detail, ignore_index=True)
    if set(election_ids) != {1, 2} or any(len(v) != 1 for v in election_ids.values()):
        raise ValueError(f"Need exactly one ordinary presidential election per round: {election_ids}")
    if detail.duplicated(ROUND_KEY).any():
        raise ValueError("Duplicate presidential detail records; resolve election/section versions first")
    print(f"Loaded {len(detail):,} section-round detail records", flush=True)

    registry_cols = ["NR_TURNO", "NR_CANDIDATO", "NM_CANDIDATO", "NM_TIPO_DESTINACAO_VOTOS",
                     "QT_VOTOS_NOMINAIS", "QT_VOTOS_NOMINAIS_VALIDOS"]
    registry_parts = []
    for c in chunks(raw / f"votacao_candidato_munzona_{year}.zip", year,
                    "votacao_candidato_munzona", common + registry_cols):
        c = c[c.ANO_ELEICAO.eq(year) & c.CD_TIPO_ELEICAO.eq(2) & c.CD_CARGO.eq(1)]
        registry_parts.append(c[registry_cols])
    registry = pd.concat(registry_parts)
    registry = registry.groupby(registry_cols[:4], as_index=False)[registry_cols[4:]].sum()
    registry.to_csv(output / "candidate_registry.csv", index=False)
    if not registry.NM_TIPO_DESTINACAO_VOTOS.eq("Válido").all():
        raise ValueError("Candidate file includes non-valid vote destinations; extend classification explicitly before analysis")
    valid_pairs = set(zip(registry.NR_TURNO, registry.NR_CANDIDATO))

    vote_cols = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_TURNO",
                 "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS"]
    grouped, candidate_totals = [], []
    for v in chunks(raw / f"votacao_secao_{year}_BR.zip", year, "votacao_secao", common + vote_cols):
        v = v[v.ANO_ELEICAO.eq(year) & v.CD_TIPO_ELEICAO.eq(2) & v.CD_CARGO.eq(1)]
        if not all(set(g.CD_ELEICAO.unique()) == election_ids[int(t)] for t, g in v.groupby("NR_TURNO")):
            raise ValueError("Election ID mismatch between datasets")
        v = v[vote_cols].rename(columns=RENAME)
        candidate_totals.append(v.groupby(["round", "candidate_number", "candidate_name"],
                                         as_index=False).votes.sum())
        grouped.append(v.groupby(ROUND_KEY + ["candidate_number"], as_index=False).votes.sum())
    totals = pd.concat(candidate_totals).groupby(
        ["round", "candidate_number", "candidate_name"], as_index=False).votes.sum()
    totals["registered_valid_candidate"] = pd.MultiIndex.from_frame(
        totals[["round", "candidate_number"]]).isin(valid_pairs)
    totals.to_csv(output / "candidates.csv", index=False)
    final = totals[totals["round"].eq(2) & ~totals.candidate_number.isin([95, 96]) & totals.votes.gt(0)]
    if len(final) != 2:
        raise ValueError(f"Expected two runoff candidates, found {len(final)}")
    # Stable ordering independent of the result: smaller ballot number is A.
    final = final.sort_values("candidate_number")
    finalists = {label: {"number": int(row.candidate_number), "name": row.candidate_name}
                  for label, row in zip(["a", "b"], final.itertuples())}
    votes = pd.concat(grouped).groupby(ROUND_KEY + ["candidate_number"], as_index=False).votes.sum()
    votes["category"] = "other"
    recognized = pd.MultiIndex.from_frame(votes[["round", "candidate_number"]]).isin(valid_pairs)
    votes.loc[~recognized, "category"] = "technical_null"
    for label, c in finalists.items():
        votes.loc[votes.candidate_number.eq(c["number"]), "category"] = label
    votes.loc[votes.candidate_number.eq(95), "category"] = "blank_from_votes"
    votes.loc[votes.candidate_number.eq(96), "category"] = "null_from_votes"
    votes.groupby(["uf", "municipality_code", "round", "candidate_number", "category"], as_index=False).votes.sum().to_csv(
        output / "municipality_candidate_votes.csv.gz", index=False)
    wide = votes.groupby(ROUND_KEY + ["category"]).votes.sum().unstack("category", fill_value=0)
    wide = wide.reindex(columns=["a", "b", "other", "technical_null", "blank_from_votes", "null_from_votes"], fill_value=0)
    d = detail.merge(wide.reset_index(), on=ROUND_KEY, how="outer", validate="one_to_one", indicator=True)
    d[wide.columns] = d[wide.columns].fillna(0)
    d["has_detail"] = d._merge.ne("right_only")
    d["has_vote_record"] = d._merge.ne("left_only")
    d = d.drop(columns="_merge")
    d["raw_null"] = d["null"]
    d["null"] = d["raw_null"] + d.technical_null
    d["invalid"] = d["blank"] + d["null"]
    d["valid"] = d.a + d.b + d.other
    d["vote_total_ok"] = d.valid.add(d.invalid).eq(d.turnout)
    d["nominal_ok"] = d.valid.add(d.technical_null).eq(d.nominal)
    d["special_votes_ok"] = d.blank.eq(d.blank_from_votes) & d.raw_null.eq(d.null_from_votes)
    d["electorate_ok"] = d.turnout.add(d.abstention).eq(d.eligible)
    d["counts_nonnegative"] = d[["a", "b", "other", "blank", "null", "turnout", "abstention", "eligible"]].ge(0).all(axis=1)
    d["section_usable"] = (d.has_detail & d.vote_total_ok & d.nominal_ok & d.special_votes_ok
                           & d.electorate_ok & d.counts_nonnegative
                           & d.installed.eq("Sim") & d.annulled.eq("Não"))
    d.to_csv(output / "section_rounds.csv.gz", index=False)
    print(f"Prepared section votes; finalists: {finalists}", flush=True)

    summary_columns = ["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_TURNO", "QT_APTOS",
                       "QT_COMPARECIMENTO", "QT_ABSTENCOES", "QT_VOTOS_BRANCOS",
                       "QT_TOTAL_VOTOS_NULOS", "QT_TOTAL_VOTOS_VALIDOS", "QT_SECOES_PRINCIPAIS", "QT_VOTOS_NULOS_TECNICOS"]
    reference = []
    for s in chunks(raw / f"detalhe_votacao_munzona_{year}.zip", year,
                    "detalhe_votacao_munzona", common + summary_columns):
        s = s[s.ANO_ELEICAO.eq(year) & s.CD_TIPO_ELEICAO.eq(2) & s.CD_CARGO.eq(1)]
        reference.append(s[summary_columns].rename(columns={**RENAME,
            "QT_TOTAL_VOTOS_NULOS": "null", "QT_TOTAL_VOTOS_VALIDOS": "valid",
            "QT_SECOES_PRINCIPAIS": "principal_sections", "QT_VOTOS_NULOS_TECNICOS": "technical_null"}))
    reference = pd.concat(reference)
    reference = reference.groupby(["uf", "municipality_code", "municipality", "round"], as_index=False).sum(numeric_only=True)
    technical = d.groupby(["uf", "municipality_code", "round"], as_index=False).technical_null.sum()
    technical = technical.merge(reference, on=["uf", "municipality_code", "round"], how="outer", suffixes=("_sections", "_reference"))
    if not technical.technical_null_sections.eq(technical.technical_null_reference).all():
        raise ValueError("Unrecognized ballot codes do not exactly match official technical-null totals; investigate instead of reclassifying")
    reference.to_csv(output / "municipal_reference.csv", index=False)
    meta = {"year": year, "finalists": finalists,
            "election_ids": {str(k): list(v) for k, v in election_ids.items()},
            "scope": "Domestic municipalities; ZZ retained in source data and excluded from municipal analysis",
            "section_rounds": len(d), "usable_section_rounds": int(d.section_usable.sum())}
    (output / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return meta
