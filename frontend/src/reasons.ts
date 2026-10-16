const messages:Record<string,string>={
 OK:'Available',STALE_INPUT:'The latest input is too old for a fresh forecast.',
 INCOMPLETE_HISTORY:'Rebuilding history: all 61 valid minute cells are required.',
 INSUFFICIENT_HISTORY:'Not enough history yet: 61 valid minute cells spanning 60 minutes are required.',
 MISSING_CURRENT:'The current reading is missing.',
 SYNTHETIC_INTERVALS_UNCALIBRATED:'No synthetic interval calibration exists; the point forecast can still be available.',
 INSUFFICIENT_CALIBRATION:'Too few eligible calibration pairs for an interval.',
 INSUFFICIENT_OFFSET_DATA:'Too few eligible pairs to fit the fixed offset.',
 TARGET_MISSING:'The exact target reading is unavailable; this prediction cannot be scored.',
 INVALID_MODEL_OUTPUT:'The predictor returned an invalid value; no forecast is issued.',
 MODEL_UNAVAILABLE:'The matching model is missing. Restore the local artifacts or select synthetic mode.',
 INCOMPATIBLE_ARTIFACTS:'Local artifacts do not match the frozen protocol. Restore the matching bundle.',
 CONFLICTING_DUPLICATE:'Conflicting input readings invalidate the affected history.',
 LOCAL_MODE_DISABLED:'Private replay is disabled. Start with --local only when matching private artifacts are available.'
};
Object.assign(messages,{
 MISSING_CURRENT_READING:'The current exact-minute reading is missing; no fresh point is issued.',
 STALE_READING:'The last accepted reading is over 10 minutes old. Wait for new input and history rebuilding.',
 INVALID_UNIT:'Input units must be mg/dL. The affected history is rejected.',
 NON_FINITE_READING:'A reading is not finite; the affected history is unavailable.',
 SOURCE_INVALID_READING:'The current reading fails the inherited source-validity contract.',
 INVALID_INTERVAL:'Interval bounds are invalid; point availability is assessed separately.',
 INVALID_CALIBRATION_SCORES:'Calibration contains invalid scores; the interval is unavailable.',
 MISSING_MODEL:'The matching model is missing. Restore local artifacts; there is no automatic fallback.'
});
export function reasonText(code:string){return code.split(';').map(c=>messages[c]??c.toLowerCase().replaceAll('_',' ')).join(' · ')}
export function reasonDetail(code:string){return `${reasonText(code)} [${code}]`}
