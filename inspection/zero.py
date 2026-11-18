from inspection.standards import CheckFinding, locate_evidence, unavailable_evidence, within_closed_interval


def check_zero(snapshot, standard):
    if standard.kind != 'zero':
        raise ValueError('zero check requires a zero standard')
    row = locate_evidence(snapshot, standard)
    unavailable = unavailable_evidence(row, standard)
    if unavailable is not None:
        return unavailable
    passed = within_closed_interval(row.value, standard.lower, standard.upper)
    return CheckFinding(row.position, row.value, passed, 'within_zero' if passed else 'zero_offset')
