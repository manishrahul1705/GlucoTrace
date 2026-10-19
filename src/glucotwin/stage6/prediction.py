"""Prediction message boundary: only arrived history, current origin, fixed artifacts.

No Source, reference targets, future schedules or evaluation results are accepted.
This is an in-process capability boundary, not an OS sandbox.
"""
from dataclasses import dataclass
import math
import pandas as pd
import numpy as np
from glucotwin.stage5.core import Calibration, forecast_stream, interval_bounds, StreamError
from .sources import Reading

EPOCH=pd.Timestamp('2026-01-01T08:00:00Z')
INTERNAL=pd.Timestamp('2000-01-01')


def timestamp(minute):
    return (EPOCH+pd.Timedelta(minutes=minute)).isoformat()


@dataclass(frozen=True)
class PredictRequest:
    origin: int
    history: tuple[Reading,...]
    variant: str
    offset: float | None
    quantiles: tuple[tuple[str,Calibration],...]


@dataclass(frozen=True)
class Prediction:
    value: float | None
    reason: str
    intervals: tuple[tuple[str,float|None,float|None,str],...]


class Predictor:
    def __init__(self,base):self._base=base

    def predict(self,request: PredictRequest):
        if any(r.minute>request.origin for r in request.history):
            raise ValueError('Future reading in prediction request')
        if not request.history:return Prediction(None,'INSUFFICIENT_HISTORY',())
        if any(r.unit!='mg/dL' for r in request.history):return Prediction(None,'INVALID_UNIT',())
        frame=pd.DataFrame(dict(glucose_mg_dl=[r.value for r in request.history],
                                valid=[r.valid for r in request.history],
                                row_present=[r.row_present for r in request.history],sensor='Dexcom GL'),
                           index=pd.DatetimeIndex([INTERNAL+pd.Timedelta(minutes=r.minute) for r in request.history]))
        try:
            row=forecast_stream(frame,[INTERNAL+pd.Timedelta(minutes=request.origin)],self._base).iloc[0]
            value=float(row.prediction) if np.isfinite(row.prediction) else None
            reason=row.point_reason
        except StreamError as exc:return Prediction(None,str(exc),())
        if request.variant.endswith('_offset24h'):
            if request.offset is None:value,reason=None,'INSUFFICIENT_OFFSET_DATA'
            elif value is not None:value+=request.offset
        if value is not None and not math.isfinite(value):value,reason=None,'INVALID_MODEL_OUTPUT'
        intervals=[]
        for alpha,cal in request.quantiles:
            if value is None:lower,upper,ir=None,None,reason
            else:
                l,u,ir=interval_bounds(value,cal)
                lower,upper=(float(l),float(u)) if ir=='OK' else (None,None)
            intervals.append((alpha,lower,upper,ir))
        return Prediction(value,reason,tuple(intervals))
