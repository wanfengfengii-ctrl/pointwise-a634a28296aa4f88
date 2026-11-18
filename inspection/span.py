from inspection.standards import CheckFinding, locate_evidence, unavailable_evidence, within_closed_interval


def check_span(snapshot, standard):
    if standard.kind != 'span':
        raise ValueError('span check requires a span standard')
    row = locate_evidence(snapshot, standard)
    unavailable = unavailable_evidence(row, standard)
    if unavailable is not None:
        return unavailable
    error = row.value - standard.reference
    lower_error = standard.lower - standard.reference
    upper_error = standard.upper - standard.reference
    if within_closed_interval(error, lower_error, upper_error):
        return CheckFinding(row.position, row.value, True, 'within_span')
    reason = 'below_span' if error < lower_error else 'above_span'
    return CheckFinding(row.position, row.value, False, reason)
