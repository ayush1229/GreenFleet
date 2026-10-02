"""Pathway eligibility and factor provenance; never substitute missing factors."""


def pathway_issues(vessel, fuel, engine, scenario):
    issues=[]
    if engine is None or not engine.auxiliary_compatible or fuel.id not in vessel.tanks:
        issues.append("incompatible_engine")
    if fuel.price_per_kg is None:
        issues.append("missing_price")
    if fuel.wtw_g_mj is None and (fuel.wtt_g_mj is None or fuel.ttw_g_mj is None):
        issues.append("missing_lifecycle_factor")
    if not fuel.source or not fuel.version:
        issues.append("missing_factor_provenance")
    if fuel.lhv_mj_kg<=0:
        issues.append("missing_lhv")
    if fuel.currency!=scenario.currency or fuel.price_date!=scenario.price_date:
        issues.append("currency_or_price_date_mismatch")
    for record in (fuel,engine):
        if record is not None:
            if record.valid_from and record.valid_from>scenario.start or record.valid_to and record.valid_to<scenario.end:
                issues.append("factor_outside_validity")
    if engine and (not engine.source or not 0<engine.efficiency<=1 or not 0<engine.auxiliary_efficiency<=1):
        issues.append("missing_efficiency")
    return tuple(issues)


def wtw_factor(fuel):
    if fuel.wtw_g_mj is not None:
        return fuel.wtw_g_mj
    if fuel.wtt_g_mj is None or fuel.ttw_g_mj is None:
        raise ValueError("missing lifecycle factor")
    return fuel.wtt_g_mj+fuel.ttw_g_mj
