from candidate.store import load_candidate
from inspection.receipts import confirm_receipt_delivery, list_pending_receipts, load_check_receipt


def _send(db, receipt, port):
    snapshot = load_candidate(db, receipt.candidate_id)
    result = port(receipt, snapshot)
    if getattr(result, 'receipt_id', None) != receipt.receipt_id:
        raise ValueError('delivery result does not identify the original receipt')
    confirm_receipt_delivery(db, receipt.receipt_id)
    return result


def send_pending_receipts(db, port):
    return tuple(_send(db, receipt, port) for receipt in list_pending_receipts(db))


def redeliver_receipt(db, receipt_id, port):
    return _send(db, load_check_receipt(db, receipt_id), port)
