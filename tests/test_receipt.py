from copy import deepcopy
from dataclasses import replace

from candidate.replace import replace_candidate
from demo import STATION
from publication.admission import admit_replacement
from receipt.lookup import read_report
from receipt.manifest import package_digest
from receipt.package import export_report
from receipt.verify import verify_package, verify_provenance
from tests.fixtures import StationCase


class ReceiptTests(StationCase):
    def test_export_after_source_closes(self):
        prior = self.sign(self.prepare('R0').candidate_id)
        original = export_report(self.publication, 'issue:R0')
        self.prepare('R1', calibration='C3', corrects='day-R0')
        self.select('R1')
        new = self.sign('R1')
        self.close_station()
        self.assertEqual(self.current(), new)
        self.assertEqual(self.history('R0'), prior)
        exported = export_report(self.publication, 'issue:R0')
        self.assertEqual(exported, original)
        self.assertTrue(verify_package(exported))
        self.assertEqual(exported['manifest']['receipt']['zero_receipt_id'], 'R0-zero')
        self.assertIsNone(read_report(self.publication, issue_id='issue:unknown'))
        with self.assertRaises(KeyError):
            export_report(self.publication, 'issue:unknown')

    def test_fixed_provenance(self):
        report = self.sign(self.prepare('R0').candidate_id).report
        self.close_station()
        package = export_report(self.publication, 'issue:R0')
        rows = package['manifest']['report']['rows']
        self.assertEqual([row['sample_id'] for row in rows], ['reading', 'zero-trial', 'gap', 'mid', 'span-trial', 'repeat'])
        first = rows[0]
        self.assertEqual((first['calibration_id'], first['scale'], first['offset']), ('C1', '1/2', '1/4'))
        self.assertEqual((first['raw'], first['input_unit'], first['value'], first['report_unit']), ('3', 'mV', '7/4', 'mm'))
        self.assertIsNone(rows[2]['raw'])
        self.assertTrue(verify_provenance(report))
        self.assertTrue(verify_package(package))
        self.assertFalse(verify_provenance(replace(report, rows=tuple(reversed(report.rows)))))
        missing_scale = deepcopy(package)
        del missing_scale['manifest']['report']['rows'][0]['scale']
        missing_scale['digest'] = package_digest(missing_scale['manifest'])
        self.assertFalse(verify_package(missing_scale))
        wrong_receipt = deepcopy(package)
        wrong_receipt['manifest']['receipt']['candidate_id'] = 'R1'
        wrong_receipt['digest'] = package_digest(wrong_receipt['manifest'])
        self.assertFalse(verify_package(wrong_receipt))

    def test_scope_errors_leave_existing_work_intact(self):
        prior = self.sign(self.prepare('R0').candidate_id)
        with self.assertRaises(ValueError):
            replace_candidate(self.station, STATION, '2026-10-15', 'R0', 'wrong-day',
                              lambda request, snapshot: admit_replacement(self.publication, request, snapshot))
        with self.assertRaises(ValueError):
            read_report(self.publication, station=STATION, issue_id='issue:R0')
        self.assertEqual(self.current(), prior)
