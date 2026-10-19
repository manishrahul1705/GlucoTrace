const messages:Record<string,string>={
 OK:'Available',STALE_INPUT:'The latest input is too old for a fresh forecast.',
 INCOMPLETE_HISTORY:'incomplete history: all 61 valid minute cells are required.',
 INSUFFICIENT_HISTORY:'insufficient history: 61 valid minute cells spanning 60 minutes are required.',
 MISSING_CURRENT:'The current reading is missing.',
 SYNTHETIC_INTERVALS_UNCALIBRATED:'No interval calibration exists in demo mode; the point forecast can still be available.',
 INSUFFICIENT_CALIBRATION:'Too few eligible calibration pairs for an interval.',
 INSUFFICIENT_OFFSET_DATA:'Too few eligible pairs to fit the fixed offset.',
 TARGET_MISSING:'The exact target reading is unavailable; this prediction cannot be scored.',
 INVALID_MODEL_OUTPUT:'The predictor returned an invalid value; no forecast is issued.',
 MODEL_UNAVAILABLE:'The matching model is missing. Restore the local artifacts or select demo mode.',
 INCOMPATIBLE_ARTIFACTS:'Local artifacts do not match the frozen protocol. Restore the matching bundle.',
 CONFLICTING_DUPLICATE:'Conflicting input readings invalidate the affected history.',
 LOCAL_MODE_DISABLED:'Private replay is disabled. Start with --local only when matching private artifacts are available.'
};
Object.assign(messages,{
 SESSION_ENDED:'Session ended; no future issue is scheduled.',
 SESSION_NOT_STARTED:'Replay has not processed its first minute.',
 NO_FORECAST_ISSUED:'No scheduled forecast has been issued yet.',
 AWAITING_NEXT_ISSUE:'Not yet assessed; evaluated when the next scheduled issue is processed.',
 INVALID_INTERVAL_ORDER:'Calibration cannot produce valid ordered interval bounds.',
 MISSING_CURRENT_READING:'missing current reading: the current exact-minute reading is missing; no fresh point is issued.',
 SIMULATED_INPUT_DROPOUT:'Simulated input dropout active: current reading is missing.',
 STALE_READING:'The last accepted reading is over 10 minutes old. Wait for new input and history rebuilding.',
 INVALID_UNIT:'Input units must be mg/dL. The affected history is rejected.',
 NON_FINITE_READING:'A reading is not finite; the affected history is unavailable.',
 SOURCE_INVALID_READING:'The current reading fails the inherited source-validity contract.',
 INVALID_INTERVAL:'Interval bounds are invalid; point availability is assessed separately.',
 INVALID_CALIBRATION_SCORES:'Calibration contains invalid scores; the interval is unavailable.',
 MISSING_MODEL:'The matching model is missing. Restore local artifacts; there is no automatic fallback.',
 LOCAL_ARTIFACTS_UNAVAILABLE:'Required local research artifacts are missing. Restore the matching bundle or select demo mode.',
 SOURCE_UNAVAILABLE:'The requested source stream is unavailable.',
 PRIVATE_CONFIGURATION_FIXED:'Private replay configuration is fixed to default seed (1705) and 720m duration.'
});
export function reasonText(code:string){return code.split(';').map(c=>messages[c]??c.toLowerCase().replaceAll('_',' ')).join(' · ')}
export function reasonDetail(code:string){return `${reasonText(code)} [${code}]`}
