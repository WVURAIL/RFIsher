"""Independent adversarial contract tests; synthetic declared evidence only."""
from copy import deepcopy
import hashlib
import json
import math
import pytest
from rfisher.response.calendar import evaluate_document, write_report
QUALIFIED = {'evidence_kind': 'physical_same_mask_response', 'physical_response_qualified': True, 'science_selection_eligible': True, 'residual_contains_sensitivity_floor': False}

def document():
    prov = {'evidence_ids': ['fixture'], 'description': 'Synthetic contract fixture, not a calibrated channel'}
    ref = {'parameter_scope': 'per_forecast_bin', 'forecast_bins': ['bin10'], 'parameter_names': ['bin10:aperp', 'bin10:apar'], 'parameter_units': ['dimensionless'] * 2, 'sigma': [0.01, 0.02], 'science_bins': ['766', '768'], 'excluded_pilot_bins': ['767'], 'on_sky_hours': 8760, 'provenance': deepcopy(prov), 'evidence': deepcopy(QUALIFIED)}
    candidate = {'id': 'quiet', 'threshold': {'kind': 'finite', 'eta_q16': '131526'}, 'evidence': deepcopy(QUALIFIED), 'science_bins': ['766', '768'], 'excluded_pilot_bins': ['767'], 'response_provenance': deepcopy(prov), 'evaluations': [point(8760)]}
    return {'schema': 'rfisher_physical_calendar_candidates_v1', 'channel': 19, 'reference': ref, 'context': {'tolerance': 1, 'duty': 0.152, 'hours_per_calendar_year': 8766, 'budgets_calendar_years': [10, 100]}, 'candidates': [candidate], 'fallback_threshold': {'kind': 'finite', 'eta_q16': '999999'}, 'evidence_files': [{'id': 'fixture', 'path': 'evidence.txt', 'sha256': hashlib.sha256(b'synthetic').hexdigest()}]}

def point(hours, bias=None, sigma=None):
    return {'on_sky_hours': hours, 'status': 'available', 'bias': [0.0, 0.0] if bias is None else bias, 'sigma': [0.01, 0.02] if sigma is None else sigma}

def decisions(doc):
    return evaluate_document(doc)['budget_decisions']

def put(doc, path, value):
    parts = path.split('.')
    node = doc
    for key in parts[:-1]:
        node = node[int(key)] if isinstance(node, list) else node[key]
    key = parts[-1]
    node[int(key) if isinstance(node, list) else key] = value

def test_quiet_null_has_finite_clean_target_recovery():
    result = evaluate_document(document())
    for row in result['budget_decisions']:
        assert row['scientific_candidate_id'] == 'quiet'
        assert row['required_on_sky_hours_at_evaluated_point'] == 8760
        assert row['required_calendar_years_at_evaluated_point'] == pytest.approx(8760 / (8766 * 0.152))
        assert row['threshold_assignment']['kind'] == 'finite'
    assert result['evidence_bytes_authenticated'] is False
    assert result['qualification_independently_established'] is False
    assert result['threshold_activated'] is False

@pytest.mark.parametrize('bias', [[0.01, 0.02], [-0.01, -0.02], [0.01, -0.02], [0.0, 0.0]])
def test_signed_bias_and_equality(bias):
    doc = document()
    doc['candidates'][0]['evaluations'][0]['bias'] = bias
    report = evaluate_document(doc)
    assert report['budget_decisions'][0]['scientific_candidate_id'] == 'quiet'
    assert report['candidates'][0]['evaluations'][0]['bias'] == bias

def test_improved_precision_does_not_shrink_fixed_bias_budget():
    doc = document()
    doc['candidates'][0]['evaluations'] = [point(10000, [0.009, -0.019], [0.001, 0.002])]
    assert decisions(doc)[0]['scientific_candidate_id'] == 'quiet'

@pytest.mark.parametrize('field,value,failed', [('bias', [math.nextafter(0.01, math.inf), 0.0], 'failed_bias_parameters'), ('bias', [0.0, -math.nextafter(0.02, math.inf)], 'failed_bias_parameters'), ('sigma', [math.nextafter(0.01, math.inf), 0.02], 'failed_precision_parameters'), ('sigma', [0.01, math.nextafter(0.02, math.inf)], 'failed_precision_parameters')])
def test_each_requirement_is_independently_enforced(field, value, failed):
    doc = document()
    doc['candidates'][0]['evaluations'][0][field] = value
    result = evaluate_document(doc)
    assert result['budget_decisions'][0]['scientific_candidate_id'] is None
    assert result['candidates'][0]['evaluations'][0][failed]

def test_all_forecast_bins_must_pass():
    doc = document()
    ref = doc['reference']
    ref.update(forecast_bins=['bin9', 'bin10'], parameter_names=['bin9:aperp', 'bin9:apar', 'bin10:aperp', 'bin10:apar'], parameter_units=['dimensionless'] * 4, sigma=[0.01, 0.02, 0.01, 0.02])
    doc['candidates'][0]['evaluations'] = [point(8760, [0, 0, 0, 0.0201], [0.01, 0.02, 0.01, 0.02])]
    assert decisions(doc)[0]['scientific_candidate_id'] is None
    doc['candidates'][0]['evaluations'][0]['bias'][-1] = 0.02
    assert decisions(doc)[0]['scientific_candidate_id'] == 'quiet'

def test_all_requirements_must_hold_at_same_time():
    doc = document()
    doc['candidates'][0]['evaluations'] = [point(8000, [0, 0.03], [0.01, 0.02]), point(9000, [0.02, 0], [0.01, 0.02])]
    assert decisions(doc)[0]['scientific_candidate_id'] is None

def test_calendar_budget_exact_boundary_and_no_extra_mask_charge():
    doc = document()
    doc['candidates'][0]['evaluations'] = [point(13324.32)]
    a, b = decisions(doc)
    assert a['scientific_candidate_id'] == 'quiet'
    assert a['required_calendar_years_at_evaluated_point'] == 10
    assert b['available_on_sky_hours'] == pytest.approx(133243.2)
    doc['candidates'][0]['evaluations'][0]['on_sky_hours'] = math.nextafter(13324.32, math.inf)
    a, b = decisions(doc)
    assert a['scientific_candidate_id'] is None
    assert b['scientific_candidate_id'] == 'quiet'

def test_earliest_supplied_feasible_time_not_interpolated():
    doc = document()
    doc['candidates'][0]['evaluations'] = [point(15000), point(8000, sigma=[0.0101, 0.02]), point(16000)]
    a, b = decisions(doc)
    assert a['scientific_candidate_id'] is None
    assert b['required_on_sky_hours_at_evaluated_point'] == 15000
    assert not b['continuous_time_optimum_established']

def test_minimum_across_candidates_is_exact_not_two_percent_plateau():
    doc = document()
    second = deepcopy(doc['candidates'][0])
    second.update(id='other', threshold={'kind': 'finite', 'eta_q16': '131527'})
    second['evaluations'] = [point(8800, bias=[0, 0])]
    doc['candidates'][0]['evaluations'][0]['bias'] = [0.009, 0.019]
    doc['candidates'].append(second)
    assert decisions(doc)[0]['scientific_candidate_id'] == 'quiet'

def test_equal_time_ties_reported_and_deterministic():
    doc = document()
    second = deepcopy(doc['candidates'][0])
    second.update(id='aaa', threshold={'kind': 'finite', 'eta_q16': '131527'})
    doc['candidates'].append(second)
    result = decisions(doc)[0]
    assert result['scientific_candidate_id'] == 'aaa'
    assert result['tied_candidate_ids'] == ['aaa', 'quiet']

@pytest.mark.parametrize('evaluations', [[], [{'status': 'unavailable', 'on_sky_hours': 8760, 'reason': 'matched control unavailable'}]])
def test_missing_response_preserves_provisional_assignment(evaluations):
    doc = document()
    doc['candidates'][0]['evaluations'] = evaluations
    for row in decisions(doc):
        assert row['scientific_candidate_id'] is None
        assert row['threshold_assignment'] == doc['fallback_threshold']
        assert row['unresolved_candidates'] == ['quiet']
        assert not row['all_threshold_infeasibility_established']

@pytest.mark.parametrize('location', ['reference', 'candidates.0'])
@pytest.mark.parametrize('key,value', [('evidence_kind', 'matched_null_detector_contrast'), ('physical_response_qualified', False), ('science_selection_eligible', False), ('residual_contains_sensitivity_floor', True)])
def test_diagnostic_or_floor_evidence_never_selects(location, key, value):
    doc = document()
    put(doc, location + '.evidence.' + key, value)
    assert decisions(doc)[0]['scientific_candidate_id'] is None

def test_unresolved_competitor_retained_beside_evaluated_minimum():
    doc = document()
    second = deepcopy(doc['candidates'][0])
    second.update(id='unknown', threshold={'kind': 'finite', 'eta_q16': '131527'}, evaluations=[])
    doc['candidates'].append(second)
    row = decisions(doc)[0]
    assert row['scientific_candidate_id'] == 'quiet'
    assert row['unresolved_candidates'] == ['unknown']
    assert not row['continuous_time_optimum_established']

def test_reject_all_is_endpoint_not_fabricated_zero_bias_recovery():
    doc = document()
    doc['candidates'][0].update(threshold={'kind': 'reject_all'}, evaluations=[])
    report = evaluate_document(doc)
    assert report['candidates'][0]['status'] == 'permanent_mask_endpoint_no_channel_information'
    assert report['budget_decisions'][0]['scientific_candidate_id'] is None
    assert report['budget_decisions'][0]['threshold_assignment'] == doc['fallback_threshold']

def test_finite_zero_threshold_is_distinct_from_reject_all():
    doc = document()
    doc['candidates'][0]['threshold']['eta_q16'] = '0'
    assert decisions(doc)[0]['threshold_assignment'] == {'kind': 'finite', 'eta_q16': '0'}

def test_maximum_uint64_threshold_preserved_exactly():
    doc = document()
    doc['candidates'][0]['threshold']['eta_q16'] = str(2 ** 64 - 1)
    assert decisions(doc)[0]['threshold_assignment']['eta_q16'] == '18446744073709551615'

@pytest.mark.parametrize('path,value', [('context.tolerance', 0.5), ('context.duty', 0), ('context.duty', 1.01), ('context.duty', True), ('context.hours_per_calendar_year', 0), ('context.budgets_calendar_years', [10, 10]), ('context.budgets_calendar_years', []), ('context.budgets_calendar_years', [0]), ('reference.sigma', [0, 0.02]), ('reference.sigma', [-0.01, 0.02]), ('reference.sigma', [0.01]), ('reference.parameter_names', ['bin10:aperp']), ('reference.parameter_names', ['bin10:aperp', 'bin10:aperp']), ('reference.parameter_units', ['MHz', 'MHz']), ('reference.forecast_bins', ['bin10', 'bin11']), ('reference.science_bins', ['767']), ('reference.science_bins', ['766', '766']), ('reference.excluded_pilot_bins', []), ('reference.on_sky_hours', 0), ('reference.provenance.evidence_ids', ['unknown']), ('reference.provenance.description', ''), ('candidates.0.science_bins', ['766']), ('candidates.0.excluded_pilot_bins', ['other']), ('candidates.0.evaluations.0.sigma', [float('inf'), 0.02]), ('candidates.0.evaluations.0.bias', [float('nan'), 0]), ('candidates.0.evaluations.0.on_sky_hours', 0), ('candidates.0.evaluations.0.on_sky_hours', True), ('candidates.0.evaluations.0.on_sky_hours', 10 ** 1000), ('candidates.0.threshold.eta_q16', str(2 ** 64)), ('candidates.0.threshold.eta_q16', '01'), ('candidates.0.threshold.eta_q16', 131526), ('candidates.0.threshold.eta_q16', '1e5'), ('candidates.0.threshold.eta_q16', '-1'), ('candidates.0.threshold.eta_q16', True), ('channel', True), ('channel', -1), ('evidence_files.0.sha256', 'a' * 63), ('evidence_files.0.sha256', 'z' * 64)])
def test_invalid_contract_data_refused(path, value):
    doc = document()
    put(doc, path, value)
    with pytest.raises(ValueError):
        evaluate_document(doc)

def test_duplicate_times_refused():
    doc = document()
    doc['candidates'][0]['evaluations'] *= 2
    with pytest.raises(ValueError):
        evaluate_document(doc)

@pytest.mark.parametrize('same_id,same_threshold', [(True, False), (False, True), (True, True)])
def test_ambiguous_candidate_identity_refused(same_id, same_threshold):
    doc = document()
    c = deepcopy(doc['candidates'][0])
    if not same_id:
        c['id'] = 'other'
    if not same_threshold:
        c['threshold']['eta_q16'] = '131527'
    doc['candidates'].append(c)
    with pytest.raises(ValueError):
        evaluate_document(doc)

def test_reject_all_may_not_claim_finite_precision():
    doc = document()
    doc['candidates'][0]['threshold'] = {'kind': 'reject_all'}
    with pytest.raises(ValueError):
        evaluate_document(doc)

def test_unqualified_reference_does_not_skip_candidate_schema_validation():
    doc = document()
    doc['reference']['evidence'] = {}
    doc['candidates'][0]['evidence'] = 'not a mapping'
    with pytest.raises(ValueError):
        evaluate_document(doc)

def test_output_qualification_is_not_inferred_from_valid_hashes(tmp_path):
    doc = document()
    (tmp_path / 'evidence.txt').write_bytes(b'synthetic')
    input_path = tmp_path / 'input.json'
    input_path.write_text(json.dumps(doc))
    report = write_report(input_path, tmp_path / 'report.json')
    assert report['evidence_bytes_authenticated'] is True
    assert report['qualification_independently_established'] is False
    assert report['physical_response_derived_by_this_command'] is False
    assert report['input_file']['sha256'] == hashlib.sha256(input_path.read_bytes()).hexdigest()
    assert report['budget_decisions'][0]['scientific_candidate_id'] == 'quiet'

def test_altered_evidence_fails_before_report_written(tmp_path):
    doc = document()
    (tmp_path / 'evidence.txt').write_bytes(b'changed')
    input_path = tmp_path / 'input.json'
    input_path.write_text(json.dumps(doc))
    out = tmp_path / 'report.json'
    with pytest.raises(ValueError, match='hash mismatch'):
        write_report(input_path, out)
    assert not out.exists()

def test_existing_output_is_not_overwritten(tmp_path):
    doc = document()
    (tmp_path / 'evidence.txt').write_bytes(b'synthetic')
    input_path = tmp_path / 'input.json'
    input_path.write_text(json.dumps(doc))
    out = tmp_path / 'report.json'
    out.write_text('accepted')
    with pytest.raises(FileExistsError):
        write_report(input_path, out)
    assert out.read_text() == 'accepted'

def test_duplicate_json_fields_fail(tmp_path):
    doc = document()
    input_path = tmp_path / 'input.json'
    text = json.dumps(doc)
    text = text.replace('"channel": 19', '"channel": 19, "channel": 20')
    input_path.write_text(text)
    with pytest.raises(ValueError, match='duplicate JSON key'):
        write_report(input_path, tmp_path / 'report.json')

def test_cli_calendar_route_writes_authenticated_review(tmp_path):
    import os
    import subprocess
    import sys
    doc = document()
    (tmp_path / 'evidence.txt').write_bytes(b'synthetic')
    input_path = tmp_path / 'input.json'
    input_path.write_text(json.dumps(doc))
    out = tmp_path / 'report.json'
    run = subprocess.run([sys.executable, '-m', 'rfisher.cli', 'response', 'calendar', '--input', str(input_path), '--output', str(out)], capture_output=True, text=True, env=os.environ.copy())
    assert run.returncode == 0, run.stderr
    assert json.loads(out.read_text())['evidence_bytes_authenticated']
    assert json.loads(run.stdout)['channel'] == 19


def test_input_changed_while_evidence_is_verified_is_refused(tmp_path, monkeypatch):
    from rfisher.response import calendar
    doc = document()
    evidence = tmp_path / 'evidence.txt'
    evidence.write_bytes(b'synthetic')
    input_path = tmp_path / 'input.json'
    input_path.write_text(json.dumps(doc))
    output_path = tmp_path / 'report.json'
    original = calendar._sha
    def mutate_after_first_hash(path):
        digest = original(path)
        if path == evidence:
            input_path.write_text(input_path.read_text() + ' ')
        return digest
    monkeypatch.setattr(calendar, '_sha', mutate_after_first_hash)
    with pytest.raises(ValueError, match='input document changed'):
        write_report(input_path, output_path)
    assert not output_path.exists()


@pytest.mark.parametrize('failure', ['existing_output', 'hash_mismatch', 'duplicate_key'])
def test_cli_refuses_invalid_or_nonfresh_artifacts(tmp_path, failure):
    import os
    import subprocess
    import sys
    doc = document()
    evidence = tmp_path / 'evidence.txt'
    evidence.write_bytes(b'changed' if failure == 'hash_mismatch' else b'synthetic')
    input_path = tmp_path / 'input.json'
    text = json.dumps(doc)
    if failure == 'duplicate_key':
        text = text.replace('"channel": 19', '"channel": 19, "channel": 20')
    input_path.write_text(text)
    output_path = tmp_path / 'report.json'
    if failure == 'existing_output':
        output_path.write_text('accepted')
    run = subprocess.run([sys.executable, '-m', 'rfisher.cli', 'response', 'calendar', '--input', str(input_path), '--output', str(output_path)], capture_output=True, text=True, env=os.environ.copy())
    assert run.returncode != 0
    if failure == 'existing_output':
        assert output_path.read_text() == 'accepted'
    else:
        assert not output_path.exists()
