import {useEffect,useRef,useState} from 'react';

const steps=[
 ['Choose a source','Scenario Lab offers steady, scripted rise/recovery, activity, noise and four input-loss scenarios. Choose a seed and bounded duration; inspect the generator version/configuration. These are independent engineering scenarios, not validated physiology. Private replay needs explicit opt-in and matching artifacts.'],
 ['Prepare a session','Warm start processes earlier events chronologically; full chronology starts at zero. The session library can rename and recreate a synthetic configuration as a NEW session/generation. Retained summaries are read-only. Server restart expires runtimes; recreation is not resume.'],
 ['Control the clock','Start or resume playback, pause, step exactly five minutes while paused, or change speed. Reset creates a new generation. The clock is simulated, not a live sensor.'],
 ['Read the endpoint','Each dot is a forecast at origin plus exactly 30 minutes. Click a dot or ledger origin, or press Enter on a focused dot, to open the inspector. Escape closes and restores focus. Choose a history range/cutoff to inspect revealed history; Follow replay returns to the clock. Dots never form a future trajectory.'],
 ['Wait for scoring','Targets remain hidden until maturity. Summary counts distinguish issued, pending, scored and missing targets, separately per variant. Synthetic exports contain configuration, revealed readings, issued forecasts, matured scores or summary at a fixed cutoff. Patient exports are blocked. A point may be available without an interval.'],
 ['Try input loss','Create a 15, 30, 60 or 120 minute dropout session. At minute 180 inputs stop, forecasts are suppressed, then all 61 valid minute cells must rebuild before recovery. Reference targets are retained by the evaluator.'],
 ['Understand the limits','Synthetic persistence is not evidence of diabetes accuracy. Local replay uses processed values with assumed arrivals and upstream interpolation. No clinical decisions or guaranteed interval coverage.']
];

export function Help(){
 const [open,setOpen]=useState(false),[step,setStep]=useState(0);
 const panel=useRef<HTMLElement>(null),trigger=useRef<HTMLButtonElement>(null);
 const close=()=>{setOpen(false);trigger.current?.focus()};
 useEffect(()=>{if(open)panel.current?.focus()},[open]);
 return <><button ref={trigger} className="help-trigger" aria-expanded={open} onClick={()=>{setStep(0);setOpen(!open)}}>Help · How to use</button>
 {open&&<section className="help-panel" ref={panel} tabIndex={-1} aria-label="How to use GlucoTwin" onKeyDown={e=>{if(e.key==='Escape')close();if(e.key==='ArrowRight')setStep(s=>Math.min(6,s+1));if(e.key==='ArrowLeft')setStep(s=>Math.max(0,s-1))}}>
  <div className="help-heading"><span>QUICK GUIDE · {step+1} / 7</span><button onClick={close} aria-label="Close help">Close ×</button></div>
  <h2>{steps[step][0]}</h2><p aria-live="polite">{steps[step][1]}</p>
  <div className="help-navigation"><button disabled={step===0} onClick={()=>setStep(step-1)}>Previous</button><span>← → navigate · Esc closes</span><button onClick={()=>step===6?close():setStep(step+1)}>{step===6?'Finish':'Next'}</button></div>
 </section>}</>;
}
