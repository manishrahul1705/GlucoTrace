import {describe,it,expect} from 'vitest';
import {validateSnapshot} from './validation';
describe('API response validation',()=>{
 const valid={session_id:'opaque',generation:'g',sequence:1,elapsed_minutes:0,history:[],forecasts:[],summaries:[]};
 it('accepts an empty valid replay without inventing metrics',()=>expect(()=>validateSnapshot(valid)).not.toThrow());
 it('rejects malformed lists and nonfinite clock values',()=>{expect(()=>validateSnapshot({...valid,forecasts:null})).toThrow();expect(()=>validateSnapshot({...valid,elapsed_minutes:NaN})).toThrow()});
 it('rejects nonfinite revealed readings and point forecasts',()=>{expect(()=>validateSnapshot({...valid,history:[{measurement_time:'t',value:Infinity}]})).toThrow();expect(()=>validateSnapshot({...valid,forecasts:[{id:'a',origin_time:'t',target_time:'u',intervals:[],value:NaN}]})).toThrow()});
});
