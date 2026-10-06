"""Threshold-specific conditional regions from exact empirical score summaries.

Unknown constant and score-coupled physical transfer coefficients remain free.
This module never assigns a physical coefficient or a scientific threshold.
"""
from __future__ import annotations
import importlib.util,json,sys,datetime,time,hashlib,math
from fractions import Fraction
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
SCORES=HERE.parent/'scores'
PRIOR=Path('/home/djg/rail/output/native-threshold-expansion-2026-10-04/model-review')
spec=importlib.util.spec_from_file_location('validated_paired_modes',PRIOR/'paired_mode_forecast.py')
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
MODELS=('independent_averaging_covariance','persistent_gaussian_covariance','persistent_coherent_mean')
SHAPES=('noise_shaped','low_kparallel')
YEARS=(10,100)


def fraction_key(value):
 return value['numerator']+'/'+value['denominator']


def projected_coefficients(d,w,q,indices):
 """Exact target projection retaining all nuisance coordinates.

 For x=R/Nref or x=M/Nref, bias=x*b. Covariance-only variance is
 v0+x*v1+x²*v2; deterministic-mean-only variance is v0+x*v1.
 These are a diagonal projection of F^-1 G F^-1, not a new Fisher fit.
 """
 d=np.asarray(d,float);w=np.asarray(w,float);q=np.asarray(q,float)
 if d.ndim!=2 or w.shape!=(d.shape[1],) or q.shape!=w.shape:raise ValueError('inconsistent mode shapes')
 if not all(np.isfinite(v).all() for v in [d,w,q]) or np.any(w<0) or np.any(q<0):raise ValueError('invalid mode inputs')
 f=(d*w)@d.T
 if not np.isfinite(f).all():raise ValueError('nonfinite Fisher system')
 scales=np.sqrt(np.diag(f))
 if np.any(scales<=0):raise ValueError('unconstrained parameter')
 scaled=f/np.outer(scales,scales);eigen=np.linalg.eigvalsh(scaled)
 if eigen[0]<=eigen[-1]/1e12:raise ValueError('singular or ill-conditioned Fisher system')
 inv=np.linalg.inv(scaled)/np.outer(scales,scales)
 projection=inv@d
 full_bias=(projection*w)@q
 full_v1=2*(projection*(w*q))@projection.T
 full_v2=(projection*(w*q*q))@projection.T
 full_v0=(projection*w)@projection.T
 if not np.allclose(full_v0/np.outer(np.sqrt(np.diag(inv)),np.sqrt(np.diag(inv))),inv/np.outer(np.sqrt(np.diag(inv)),np.sqrt(np.diag(inv))),rtol=1e-9,atol=1e-10):raise ValueError('clean sandwich identity failed')
 v0=np.diag(full_v0)[indices];bias=full_bias[indices]
 v1=np.diag(full_v1)[indices];v2=np.diag(full_v2)[indices]
 if not all(np.isfinite(v).all() for v in [bias,v0,v1,v2]):raise ValueError('nonfinite projected moments')
 return {'bias':bias,'v0':v0,'v1':v1,'v2':v2,'fisher':f,'full_fit_covariance':inv,'full_unit_power_bias':full_bias,'full_variance_linear':full_v1,'full_variance_quadratic':full_v2,'condition_number':float(eigen[-1]/eigen[0])}


def power_cap(bias,v0,v1,v2,target):
 """Maximum nonnegative model power coefficient; no feasible point vs infinity distinct."""
 values=np.asarray([bias,v0,v1,v2,target],float)
 if not np.isfinite(values).all() or min(v0,v1,v2)<0 or target<=0:raise ValueError('invalid cap inputs')
 room=target*target-v0
 if not math.isfinite(room):raise ValueError('nonfinite variance allowance')
 if room<0:return {'status':'insufficient_clean_precision','cap':None}
 bc=target/abs(bias) if bias else math.inf
 if v2>0:
  radicand=v1*v1+4*v2*room
  if not math.isfinite(radicand):raise ValueError('nonfinite cap discriminant')
  vc=2*room/(v1+math.sqrt(radicand)) if room else 0.
 elif v1>0:vc=room/v1
 else:vc=math.inf
 cap=min(bc,vc)
 return {'status':'unbounded' if math.isinf(cap) else 'finite','cap':None if math.isinf(cap) else cap,'bias_cap':None if math.isinf(bc) else bc,'variance_cap':None if math.isinf(vc) else vc}


def coefficient_region(cap,g,model):
 """Positive quadrant below constant+g*score<=cap, without dropping its constant."""
 if cap['status']!='finite':return {'status':cap['status'],'constant_axis_intercept':None,'score_only_axis_intercept':None,'g':g}
 limit=cap['cap'];amplitude=math.sqrt(limit) if model=='persistent_coherent_mean' else limit
 if g is None:
  return {'status':'constant_slice_only_score_transfer_unavailable','constant_axis_intercept':amplitude,'score_only_axis_intercept':None,'g':None}
 if not np.isfinite(g) or g<0:raise ValueError('invalid score transfer')
 return {'status':'finite_region' if g>0 else 'score_coefficient_unconstrained_by_zero_transfer_hypothesis','constant_axis_intercept':amplitude,'score_only_axis_intercept':amplitude/g if g>0 else None,'g':g}


def load_scores():
 index=json.loads((SCORES/'INDEX.json').read_text())
 channels={ch:json.loads((SCORES/f'ch{ch}.json').read_text()) for ch in range(14,38)}
 for ch,record in channels.items():
  assert record['channel']==ch
  for candidate in record['candidates']:
   for key in ['retained_probability','masked_probability','unsupported_probability','g']:
    value=candidate[key]
    if value is None:continue
    exact=Fraction(int(value['numerator']),int(value['denominator']))
    assert exact>=0 and float(exact)==value['float'],(ch,candidate['id'],key)
   assert Fraction(candidate['retained_probability']['numerator']+'/'+candidate['retained_probability']['denominator'])+Fraction(candidate['masked_probability']['numerator']+'/'+candidate['masked_probability']['denominator'])==1
 return index,channels


def main():
 started=time.monotonic();out=HERE/'results';out.mkdir(exist_ok=False)
 prior_complete=json.loads((PRIOR/'COMPLETE.json').read_text())
 for f,h in prior_complete['files'].items():assert native.sha(PRIOR/f)==h,f
 assert prior_complete['status']=='PASS_CONDITIONAL_MODEL_ONLY'
 prior_plan=json.loads((PRIOR/'results/PLAN.json').read_text())
 target_path=Path(prior_plan['fixed_reference_file']);assert native.sha(target_path)==prior_plan['fixed_reference_sha256']
 target=json.loads(target_path.read_text());index,channels=load_scores()
 # Scores are authenticated by their final manifest before any candidate is evaluated.
 manifest=json.loads((SCORES/'MANIFEST.json').read_text())
 for f,h in manifest['files'].items():assert native.sha(SCORES/f)==h,f
 contract_path=HERE/'CONTRACT.json';contract=json.loads(contract_path.read_text())
 plan={'schema':'threshold_conditional_bridge_plan_v1','declared_before_evaluation':True,'source_sha256':native.sha(__file__),'contract_sha256':native.sha(contract_path),'scores_index_sha256':native.sha(SCORES/'INDEX.json'),'scores_manifest_sha256':native.sha(SCORES/'MANIFEST.json'),'prior_validated_model_complete_sha256':native.sha(PRIOR/'COMPLETE.json'),'target_sha256':native.sha(target_path),'calendar_years':list(YEARS),'shapes':list(SHAPES),'models':list(MODELS),'physical_response_qualified':False,'science_selection_eligible':False,'threshold_assignments_changed':False}
 native.dump(out/'PLAN.json',plan)
 bank=native.banks.FisherBank(target['bank_path'],expected_artifact_kind='forecast');cache=native.resources.filesystem_data_file(bank.meta['provenance']['pk_cache']['filename'])
 assert native.sha(cache)==bank.meta['provenance']['pk_cache']['sha256']
 rf,_,_=native.banks._init_context('/home/djg/rail/RadioFisher',cache,'chime2022',0.,.14,cosmology=bank.meta['cosmology'])
 current_native=native.banks._git_state(Path('/home/djg/rail/RadioFisher'),**native.banks.RADIOFISHER_SOURCE_MANIFEST)
 assert current_native['working_tree_sha256']==prior_plan['native_backend_identity']['working_tree_sha256']
 target_by_ch={c['channel']:c for c in target['channels']};coeffs={};coefficient_rows=[]
 for b in target['bins']:
  ib=b['index'];c=native.capture_native_bin(ib,8760.,rf)
  keep=[i for i,n in enumerate(c['names']) if n not in native.EXCLUDE_PERBIN];names=[c['names'][i] for i in keep];indices=[names.index(p) for p in ['aperp','apar']]
  assert set(names)=={'A','sigma_NL','aperp','apar','fs8','bs8'}
  volume=sum(hi-lo for lo,hi in b['science_support_intervals_mhz'])/(b['frequency_bounds_mhz'][1]-b['frequency_bounds_mhz'][0])
  w=(c['quadrature']*c['volume_prefactor']*volume).ravel();base=c['derivatives'][keep].reshape(len(keep),-1);ctref=c['signal']+c['noise']
  refs=[b['sigma_pilot_excluded_reference'][p] for p in ['aperp','apar']]
  fractions={}
  for ch,record in channels.items():
   if b['label'] not in target_by_ch[ch]['forecast_bins']:continue
   for candidate in record['candidates']:
    value=candidate['retained_probability']
    if value['float']>0:fractions[fraction_key(value)]=value['float']
  K,U=np.meshgrid(c['k'],c['u']);shape_arrays={s:native.templates.make_template(s).shape(K,U) for s in SHAPES}
  print(f'bin{ib}: {len(fractions)} unique exact retained fractions',flush=True)
  for key,frac in fractions.items():
   for years in YEARS:
    hours=years*8766*.152;scale=8760/(hours*frac);ct=c['signal']+c['noise']*scale;d=base*(ctref/ct).ravel()
    for shape in SHAPES:
     q=(c['noise']*shape_arrays[shape]/ct).ravel()
     try:
      p=projected_coefficients(d,w,q,indices)
      record={'bin':ib,'retained_fraction_exact':key,'retained_fraction':frac,'calendar_years':years,'on_sky_hours':hours,'effective_on_sky_hours':hours*frac,'shape':shape,'parameter_names':['aperp','apar'],'fixed_reference_sigma':refs,'unit_power_bias':p['bias'].tolist(),'clean_variance':p['v0'].tolist(),'linear_variance_increment':p['v1'].tolist(),'quadratic_variance_increment':p['v2'].tolist(),'full_fisher':p['fisher'].tolist(),'full_fit_covariance':p['full_fit_covariance'].tolist(),'full_unit_power_bias':p['full_unit_power_bias'].tolist(),'full_variance_linear':p['full_variance_linear'].tolist(),'full_variance_quadratic':p['full_variance_quadratic'].tolist(),'all_fit_parameter_names':names,'condition_number_scaled':p['condition_number'],'status':'available'}
     except ValueError as exc:
      record={'bin':ib,'retained_fraction_exact':key,'calendar_years':years,'shape':shape,'status':'unavailable','reason':str(exc)}
     coeffs[(ib,key,years,shape)]=record;coefficient_rows.append(record)
  print(f'bin{ib}: complete',flush=True)
  del c
 rows=[]
 for ch,source in channels.items():
  domain=target_by_ch[ch];bins=[int(b.removeprefix('bin')) for b in domain['forecast_bins']]
  assert len(source['candidates'])<=26
  for candidate in source['candidates']:
   retained=candidate['retained_probability'];f=retained['float'];g=candidate['g']['float'] if candidate['g'] is not None else None
   for years in YEARS:
    for shape in SHAPES:
     for model in MODELS:
      common={'channel':ch,'candidate_id':candidate['id'],'threshold':candidate['threshold'],'roles':candidate['roles'],'calendar_years':years,'on_sky_hours':years*8766*.152,'shape':shape,'model':model,'retained_probability':retained,'g':candidate['g'],'forecast_bins':domain['forecast_bins'],'physical_response_qualified':False,'science_selection_eligible':False,'actual_threshold_selected':False}
      if f<=0:
       rows.append({**common,'status':'no_retained_exposure','limiting_parameter':None,'region':None,'parameters':[]});continue
      components=[];refusal=None
      for ib in bins:
       p=coeffs[(ib,fraction_key(retained),years,shape)]
       if p['status']!='available':refusal=p['reason'];continue
       scale=8760/(years*8766*.152*f) if model=='independent_averaging_covariance' else 1.
       for k,param in enumerate(['aperp','apar']):
        cap=power_cap(p['unit_power_bias'][k]*scale,p['clean_variance'][k],p['linear_variance_increment'][k]*scale,0. if model=='persistent_coherent_mean' else p['quadratic_variance_increment'][k]*scale*scale,p['fixed_reference_sigma'][k])
        components.append({'parameter':f'bin{ib}:{param}','sigma_clean':math.sqrt(p['clean_variance'][k]),'reference_sigma':p['fixed_reference_sigma'][k],'signed_bias_per_unit_power':p['unit_power_bias'][k]*scale,'variance_polynomial':[p['clean_variance'][k],p['linear_variance_increment'][k]*scale,0. if model=='persistent_coherent_mean' else p['quadratic_variance_increment'][k]*scale*scale],'cap':cap})
      if refusal:
       rows.append({**common,'status':'unavailable_numerical_response','limiting_parameter':None,'reason':refusal,'region':None,'parameters':components});continue
      if any(p['cap']['status']=='insufficient_clean_precision' for p in components):joint={'status':'insufficient_clean_precision','cap':None}
      else:
       values=[p['cap']['cap'] for p in components if p['cap']['status']=='finite']
       joint={'status':'finite','cap':min(values)} if values else {'status':'unbounded','cap':None}
      if joint['status']=='finite':limiting=min((p for p in components if p['cap']['status']=='finite'),key=lambda p:p['cap']['cap'])['parameter']
      elif joint['status']=='insufficient_clean_precision':limiting=max(components,key=lambda p:p['sigma_clean']/p['reference_sigma'])['parameter']
      else:limiting=None
      region=coefficient_region(joint,g,model)
      region['inequality']='A_const + g*A_score <= constant_axis_intercept' if model=='persistent_coherent_mean' else 'a_const + g*a_score <= constant_axis_intercept'
      region['coefficient_domain']='nonnegative; coherent mean components additionally share a fixed phase' if model=='persistent_coherent_mean' else 'nonnegative covariance contributions'
      rows.append({**common,'status':joint['status'],'limiting_parameter':limiting,'region':region,'parameters':components})
 native.dump(out/'COEFFICIENTS.json',{'schema':'native_mode_projected_coefficients_v1','rows':coefficient_rows,'source_sha256':native.sha(__file__),'physical_response_qualified':False})
 result={'schema':'conditional_threshold_calibration_regions_v1','status':'COMPLETE_CONDITIONAL_ONLY','source_sha256':native.sha(__file__),'plan_sha256':native.sha(out/'PLAN.json'),'coefficients_sha256':native.sha(out/'COEFFICIENTS.json'),'contract':contract,'channels':list(range(14,38)),'rows':rows,'runtime_seconds':time.monotonic()-started,'actual_threshold_assignments_changed':False,'physical_response_qualified':False,'science_selection_eligible':False}
 native.dump(out/'REGIONS.json',result)
 print(json.dumps({'status':result['status'],'rows':len(rows),'native_coefficient_records':len(coefficient_rows),'runtime_seconds':result['runtime_seconds']}),flush=True)
if __name__=='__main__':main()
