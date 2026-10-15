from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np,pandas as pd
from glucotwin.contracts import baseline_contract
from glucotwin.preprocessing import prepare_observations
ROOT=Path(__file__).resolve().parents[1]
def config():return json.loads((ROOT/'configs/stage2_protocol.json').read_text())
def baseline(value=None):
 raw=pd.DataFrame({'subject':[1],'Age':[50],'BMI':[30.0],'A1c PDL (Lab)':[7.0],'Fasting GLU - PDL (Lab)':[150]})
 if value is not None:raw.loc[0,'BMI']=value
 return baseline_contract(raw,config(),'fixture/bio.csv','fixture-sha')[1]
def raw_fixture(n=180,values=None):
 return pd.DataFrame({'Timestamp':pd.date_range('2020-01-01',periods=n,freq='min'),'Dexcom GL':np.full(n,100.0) if values is None else values})
def observed(n=180,values=None):return prepare_observations(raw_fixture(n,values),1,'fixture/cgm.csv','fixture-sha')
