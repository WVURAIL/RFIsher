"""Protocol separation and data-preserving resume guards for residual study v2."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

from rfisher_results.validation.coverage import binomial_lower

SPEC = importlib.util.spec_from_file_location("residual_v2_test", Path(__file__).parents[1]/"scripts/calibrate_synthetic_residual_v2.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def mini_plan(tmp_path):
    geometry = {"num_streams": 2048, "reduced_geometry": False, "physical_channel": 14,
                "offset_fine_bins": 0., "anchor_bin": 255, "bulk_size": 2, "fine_bins": 4,
                "input_scale": 3.3, "designated_half_width": 2, "guard_fine_bins": 1,
                "spectral_sense": "normal"}
    runtime = {"executable": "/virtual/venv/bin/python", "python": "3.12.3 test", "numpy": np.__version__, "cupy": "test", "cuda_runtime": 1}
    inputs = {"input_iq": str(tmp_path/"waveform"), "input_iq_sha256": "abc", "waveform_audit_sha256": "def",
              "weights_path": str(tmp_path/"weights"), "weights_sha256": "ghi", "iq_sample_rate_hz": 10.}
    template = {"schema_version": "synthetic-test", "geometry": geometry,
                "calibration": {"pilot_below_data_db": 11.3, "bin_enbw_hz": 3., "dtv_bandwidth_hz": 6., "pilot_capture_efficiency": 1.},
                "campaign": {"seed": 1, "frames_on": 1, "frames_off": 3, "frames_floor": 1,
                             "shelf_snr_db": [-10., -44., -50., -55.], "duty_cycle": [.25], "rho": [62]},
                "policy": {}, "inputs": inputs, "software": {"numpy": np.__version__, "python": "3.12.3"}}
    return {"frozen_utc": "2020-01-01T00:00:00+00:00", "calibration_content": .99, "calibration_confidence": .95,
            "evaluation_target": .95, "evaluation_confidence": .95, "minimum_retained": 30,
            "calibration_seeds": [1], "evaluation_seeds": [2], "blocks_per_seed": 1,
            "off_frames_per_block": 3, "on_frames_per_block": 1, "unused_floor_frames_per_seed": 1,
            "shelves_db": [-10., -44., -50., -55.], "development_shards": [],
            "geometry": geometry, "generator_configuration_template": template, "generator_runtime": runtime,
            "generator_python": runtime["executable"], "proxy_directory": str(tmp_path),
            "input_iq": inputs["input_iq"], "waveform_audit": str(tmp_path/"audit.json")}


def make_config(directory, plan, seed):
    directory.mkdir(parents=True, exist_ok=True)
    config = runner.expected_config(plan, seed)
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    config["config_sha256"] = runner.hashlib.sha256(encoded).hexdigest()
    path = directory/"study_config.json"
    if not path.exists():
        path.write_text(json.dumps(config))
    return config


def make_shard(directory, plan, seed, label):
    config = make_config(directory, plan, seed)
    size = runner.population_counts(plan)[label]
    path = directory/"frames"/(label+".npz")
    path.parent.mkdir(exist_ok=True)
    meta = {"seed": seed, "population": label, "frames": size,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "config_sha256": config["config_sha256"], "always_masked_sentinel": 0,
            "injected_linear": 0. if label in ("off", "floor") else 10**(-float(label[4:].replace("p", "."))/10),
            **{k: plan["geometry"][k] for k in ("num_streams", "reduced_geometry", "physical_channel", "offset_fine_bins", "anchor_bin", "bulk_size")}}
    np.savez_compressed(path, required_multiplier_q16=np.ones((size,2),dtype=np.uint64),
        fine_power_u64=np.ones((size,3,4),dtype=np.uint64), coarse_marginals_u64=np.ones((size,3),dtype=np.uint64),
        frame_seed=np.array([runner.frame_seed(seed,label,i,plan["geometry"]) for i in range(size)],dtype=np.uint64),
        normalized_excess=np.ones(size), shelf_estimate_db=np.full(size,np.nan), clip_fraction=np.zeros(size),
        meta_json=np.asarray(json.dumps(meta)))
    return path


def mutate_array(path, key, mutate):
    with np.load(path, allow_pickle=False) as data:
        arrays = {k:data[k] for k in data.files}
    mutate(arrays[key])
    np.savez_compressed(path, **arrays)


def install_plan(output, plan):
    output.mkdir()
    runner.write_pinned(output/"plan.json", plan)


def test_primary_95_endpoint_does_not_relabel_inherited_99_endpoint(tmp_path):
    plan = mini_plan(tmp_path)
    evaluation = {"content": .99, "confidence": .95, "joint_success_probability_lower": binomial_lower(196,200,alpha=.05), "requested_content_demonstrated": False}
    result = runner.separate_evaluation_endpoint(evaluation, plan)
    assert result["evaluation_target_demonstrated"] is True
    assert result["calibration_content_demonstrated_in_evaluation"] is False
    assert evaluation["requested_content_demonstrated"] is False
    assert result["evaluation_target"] == .95 and result["calibration_content"] == .99
    evaluation["joint_success_probability_lower"] = binomial_lower(195,200,alpha=.05)
    assert not runner.separate_evaluation_endpoint(evaluation, plan)["evaluation_target_demonstrated"]


def test_evaluator_confidence_drift_is_refused(tmp_path):
    with pytest.raises(ValueError, match="contract"):
        runner.separate_evaluation_endpoint({"content":.99,"confidence":.9},mini_plan(tmp_path))


def test_effective_seed_collision_is_refused_even_when_raw_seeds_differ(tmp_path,monkeypatch):
    plan = mini_plan(tmp_path)
    old = tmp_path/"development.npz"
    np.savez(old,frame_seed=np.array([7],dtype=np.uint64))
    plan["development_shards"] = [str(old)]
    monkeypatch.setattr(runner,"frame_seed",lambda *args:7+(1<<63))
    with pytest.raises(ValueError,match="effective63-bit"):
        runner.validate_seed_partition(plan)


def test_new_calibration_and_evaluation_seed_sets_must_be_disjoint(tmp_path):
    plan=mini_plan(tmp_path)
    plan["evaluation_seeds"] = plan["calibration_seeds"]
    with pytest.raises(ValueError,match="overlaps"):
        runner.validate_seed_partition(plan)


def test_prescribed_seed_algorithm_and_partition_are_deterministic(tmp_path):
    plan=mini_plan(tmp_path)
    result=runner.validate_seed_partition(plan)
    assert result["planned_frames_including_unused_floor"] == {"calibration":8,"evaluation":8}
    assert result["planned_raw_and_effective_disjoint"]
    assert runner.frame_seed(20260920,"off",0,plan["geometry"]) == 16604925960634532114


def test_array_shape_seed_and_config_guards(tmp_path):
    plan=mini_plan(tmp_path)
    directory=tmp_path/"seed-1"
    path=make_shard(directory,plan,1,"off")
    boundary=datetime.fromisoformat(plan["frozen_utc"])
    assert len(runner.audit_seed(directory,plan,1,boundary,complete=False)) == 2
    with pytest.raises(ValueError,match="missing"):
        runner.audit_seed(directory,plan,1,boundary,complete=True)
    mutate_array(path,"frame_seed",lambda a:a.__setitem__(0,a[0]+np.uint64(1)))
    with pytest.raises(ValueError,match="exact prescribed"):
        runner.audit_seed(directory,plan,1,boundary,complete=False)


def test_config_and_whole_array_read_guard(tmp_path):
    plan=mini_plan(tmp_path)
    directory=tmp_path/"seed-1"
    path=make_shard(directory,plan,1,"off")
    config_path=directory/"study_config.json"
    config=json.loads(config_path.read_text());config["campaign"]["seed"]=99
    config_path.write_text(json.dumps(config))
    with pytest.raises(ValueError,match="configuration digest"):
        runner.audit_seed(directory,plan,1,datetime.fromisoformat(plan["frozen_utc"]),complete=False)
    config_path.unlink();make_config(directory,plan,1)
    path.write_bytes(b"incomplete compressed output")
    with pytest.raises(ValueError):
        runner.audit_seed(directory,plan,1,datetime.fromisoformat(plan["frozen_utc"]),complete=False)


def test_old_generation_dates_are_refused(tmp_path):
    plan=mini_plan(tmp_path)
    directory=tmp_path/"seed-1"
    make_shard(directory,plan,1,"off")
    with pytest.raises(ValueError,match="before"):
        runner.audit_seed(directory,plan,1,datetime(2099,1,1,tzinfo=timezone.utc),complete=False)


def test_receipt_protects_numeric_contents_on_resume(tmp_path):
    plan=mini_plan(tmp_path);output=tmp_path/"study";install_plan(output,plan)
    stage=output/"calibration";stage.mkdir()
    path=make_shard(stage/"seed-1",plan,1,"off")
    identities=runner.audit_stage(output,plan,"calibration",complete=False)
    runner.record_attempt(stage,runner.sha(output/"plan.json"),"calibration","interrupted",identities)
    mutate_array(path,"normalized_excess",lambda a:a.__setitem__(0,2.))
    with pytest.raises(ValueError,match="recorded generation artifact changed"):
        runner.audit_stage(output,plan,"calibration",complete=False)


def test_evaluation_requires_bound_before_any_generator_runtime_or_subprocess(tmp_path,monkeypatch):
    plan=mini_plan(tmp_path)
    monkeypatch.setattr(runner,"load_plan",lambda output:plan)
    monkeypatch.setattr(runner,"generator_runtime",lambda executable:pytest.fail("runtime must not run"))
    with pytest.raises(FileNotFoundError):
        runner.generate(tmp_path,"evaluation")


def test_refuse_calibration_generation_after_fit(tmp_path,monkeypatch):
    plan=mini_plan(tmp_path);(tmp_path/"calibration.json").write_text("{}");monkeypatch.setattr(runner,"load_plan",lambda output:plan)
    with pytest.raises(ValueError,match="already frozen"):
        runner.generate(tmp_path,"calibration")


def test_interruption_resumes_only_missing_prescribed_shards_and_preserves_completed_bytes(tmp_path,monkeypatch):
    plan=mini_plan(tmp_path);output=tmp_path/"study";install_plan(output,plan)
    monkeypatch.setattr(runner,"load_plan",lambda output:plan)
    monkeypatch.setattr(runner,"generator_runtime",lambda executable:plan["generator_runtime"])
    calls=[]
    def fake_run(command,**kwargs):
        calls.append(command)
        directory=Path(command[command.index("--output-dir")+1])
        for label in ("off","floor"):
            if not (directory/"frames"/(label+".npz")).exists():
                make_shard(directory,plan,1,label)
        if len(calls)==1:
            raise subprocess.CalledProcessError(1,command)
        for label in runner.population_counts(plan):
            if not (directory/"frames"/(label+".npz")).exists():
                make_shard(directory,plan,1,label)
    monkeypatch.setattr(runner.subprocess,"run",fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        runner.generate(output,"calibration")
    preserved=runner.sha(output/"calibration/seed-1/frames/off.npz")
    with pytest.raises(FileExistsError,match="--resume"):
        runner.generate(output,"calibration")
    runner.generate(output,"calibration",resume=True)
    assert len(calls)==2
    assert all("--resume" in command for command in calls)
    assert all(command[0]==plan["generator_python"] for command in calls)
    assert runner.sha(output/"calibration/seed-1/frames/off.npz")==preserved
    assert len(runner.completed_inputs(output,plan,"calibration"))==9
    runner.generate(output,"calibration",resume=True)
    assert len(calls)==2


def test_resume_refuses_tampered_generation_receipt(tmp_path,monkeypatch):
    plan=mini_plan(tmp_path);output=tmp_path/"study";install_plan(output,plan)
    stage=output/"calibration";stage.mkdir()
    runner.write_pinned(stage/"generation-start.json",{"started_utc":runner.now(),"plan_sha256":runner.sha(output/"plan.json"),"calibration_sha256":None})
    runner.record_attempt(stage,runner.sha(output/"plan.json"),"calibration","start",{})
    receipt=next((stage/"attempts").glob("*.json"));receipt.write_text(receipt.read_text()+" ")
    monkeypatch.setattr(runner,"load_plan",lambda output:plan)
    monkeypatch.setattr(runner,"generator_runtime",lambda executable:plan["generator_runtime"])
    monkeypatch.setattr(runner.subprocess,"run",lambda *args,**kwargs:pytest.fail("must refuse before launch"))
    with pytest.raises(ValueError,match="digest changed"):
        runner.generate(output,"calibration",resume=True)


def test_early_evaluation_prevents_refit(tmp_path,monkeypatch):
    (tmp_path/"evaluation").mkdir()
    monkeypatch.setattr(runner,"load_plan",lambda output:pytest.fail("must refuse before reading data"))
    with pytest.raises(ValueError,match="before calibration"):
        runner.fit(tmp_path)


def test_changed_prescribed_protocol_refuses(tmp_path):
    plan=mini_plan(tmp_path)
    with pytest.raises(ValueError,match="protocol differs"):
        runner.validate_protocol(plan)


def test_write_new_does_not_leave_nonfinite_or_overwrite_existing_data(tmp_path):
    path=tmp_path/"report.json"
    with pytest.raises(ValueError):runner.write_new(path,{"x":float("nan")})
    assert not path.exists()
    runner.write_new(path,{"x":1})
    with pytest.raises(FileExistsError):runner.write_new(path,{"x":2})
    assert json.loads(path.read_text())=={"x":1}


def previous_study_fixture(tmp_path):
    plan=mini_plan(tmp_path)
    for name,content in [("waveform",b"synthetic waveform"),("weights",b"synthetic weights"),("audit.json",b"{}")]:
        (tmp_path/name).write_bytes(content)
    template=plan["generator_configuration_template"]
    template["inputs"].update(input_iq_sha256=runner.sha(tmp_path/"waveform"),
                               waveform_audit_sha256=runner.sha(tmp_path/"audit.json"),
                               weights_sha256=runner.sha(tmp_path/"weights"))
    previous=tmp_path/"old-release/residual";previous.mkdir(parents=True)
    development=tmp_path/"original-frontier.npz";np.savez(development,frame_seed=np.array([10],dtype=np.uint64))
    old={**plan,"calibration_seeds":[100],"evaluation_seeds":[200],"development_shards":[str(development)],
         "inputs":{str(development):runner.sha(development)},"scope":"synthetic fixture", "reference_directory":str(tmp_path),
         "floor_linear":.01,"policies":[{"name":"a"},{"name":"b"},{"name":"c"}],
         "independence_unit":"synthetic fixture blocks","null_scenario":"same fixture null frames"}
    identities={}
    counter=11
    for stage,seed in [("calibration",100),("evaluation",200)]:
        identities[stage]={}
        directory=previous/stage/f"seed-{seed}"
        make_config(directory,old,seed)
        (directory/"frames").mkdir()
        for label in runner.population_counts(old):
            path=directory/"frames"/(label+".npz")
            np.savez(path,frame_seed=np.array([counter],dtype=np.uint64));counter+=1
            identities[stage][str(path)]=runner.sha(path)
    runner.write_pinned(previous/"plan.json",old)
    runner.write_pinned(previous/"calibration.json",{"plan_sha256":runner.sha(previous/"plan.json"),"inputs":identities["calibration"]})
    runner.write_new(previous/"evaluation.json",{"calibration_sha256":runner.sha(previous/"calibration.json"),"inputs":identities["evaluation"]})
    return previous.parent,plan["generator_runtime"]


def test_freeze_binds_all_old_stages_new_seed_partition_and_virtual_environment_path(tmp_path,monkeypatch):
    prior,runtime=previous_study_fixture(tmp_path)
    monkeypatch.setattr(runner,"generator_runtime",lambda executable:{**runtime,"executable":executable})
    output=tmp_path/"v2-study"
    runner.freeze(output,prior,Path("/virtual/venv/bin/python"))
    plan=runner.load_plan(output)
    assert plan["calibration_seeds"]==list(range(20261001,20261016))
    assert plan["evaluation_seeds"]==list(range(20261016,20261026))
    assert plan["generator_python"]=="/virtual/venv/bin/python"
    assert len(plan["development_shards"])==13
    assert plan["seed_partition"]["development_raw_seeds"]==13
    assert plan["seed_partition"]["planned_frames_including_unused_floor"]=={"calibration":52950,"evaluation":35300}
    assert plan["calibration_content"]==.99 and plan["evaluation_target"]==.95
    Path(plan["development_shards"][0]).write_bytes(b"changed")
    with pytest.raises(ValueError,match="frozen input changed"):
        runner.load_plan(output)


def test_freeze_refuses_changed_previous_shards_before_runtime_or_new_output(tmp_path,monkeypatch):
    prior,_=previous_study_fixture(tmp_path)
    old=json.loads((prior/"residual/plan.json").read_text())
    Path(old["development_shards"][0]).write_bytes(b"changed")
    monkeypatch.setattr(runner,"generator_runtime",lambda executable:pytest.fail("must refuse before runtime"))
    output=tmp_path/"v2-study"
    with pytest.raises(ValueError,match="previous development shard changed"):
        runner.freeze(output,prior,Path("/virtual/venv/bin/python"))
    assert not output.exists()
