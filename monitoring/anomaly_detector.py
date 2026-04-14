import statistics
from dataclasses import dataclass
from typing import List,Tuple

@dataclass
class AnomalyResult:
    is_anomaly: bool; score: float; method: str; reason: str; details: dict=None

class BaseDetector:
    method_name="base"
    def detect(self, series): raise NotImplementedError

class ZScoreDetector(BaseDetector):
    method_name="zscore"
    def __init__(self,threshold=3.0,window=30):
        self.threshold=threshold; self.window=window
    def detect(self,series):
        if len(series)<self.window: return AnomalyResult(False,0,self.method_name,"insufficient_data")
        hist=series[-(self.window+1):-1]
        mu=statistics.mean(hist); sd=statistics.stdev(hist) if len(hist)>1 else 0
        if sd==0: return AnomalyResult(False,0,self.method_name,"zero_std")
        z=abs((series[-1]-mu)/sd); ok=z>self.threshold; sc=min(1.0,z/(self.threshold*2))
        return AnomalyResult(ok,sc,self.method_name,f"Z={z:.2f}(mu={mu:.2f},sigma={sd:.2f})",
                              {'zscore':round(z,3),'mean':round(mu,3),'std':round(sd,3)})

class IQRDetector(BaseDetector):
    method_name="iqr"
    def __init__(self,k=1.5,window=30):
        self.k=k; self.window=window
    def detect(self,series):
        if len(series)<self.window: return AnomalyResult(False,0,self.method_name,"insufficient_data")
        h=sorted(series[-(self.window+1):-1]); n=len(h)
        q1=h[n//4]; q3=h[3*n//4]; iqr=q3-q1
        if iqr==0: return AnomalyResult(False,0,self.method_name,"zero_iqr")
        lo=q1-self.k*iqr; hi=q3+self.k*iqr; latest=series[-1]
        if latest<lo:
            sc=min(1.0,(lo-latest)/iqr)
            return AnomalyResult(True,sc,self.method_name,f"<IQR下界{lo:.2f}",{'direction':'low'})
        if latest>hi:
            sc=min(1.0,(latest-hi)/iqr)
            return AnomalyResult(True,sc,self.method_name,f">IQR上界{hi:.2f}",{'direction':'high'})
        return AnomalyResult(False,0,self.method_name,"normal")

class MovingAvgDetector(BaseDetector):
    method_name="moving_avg"
    def __init__(self,mw=10,tf=2.0):
        self.mw=mw; self.tf=tf
    def detect(self,series):
        if len(series)<self.mw+1: return AnomalyResult(False,0,self.method_name,"insufficient_data")
        mav=[]
        for i in range(self.mw,len(series)):
            mav.append(statistics.mean(series[i-self.mw:i]))
        actual=series[-1]; ma=mav[-1]
        res=[series[self.mw+i]-mav[i] for i in range(len(mav))]
        rsd=statistics.stdev(res) if len(res)>1 else 0
        dev=abs(actual-ma); th=self.tf*rsd if rsd>0 else ma*0.1
        dir_='high' if actual>ma else 'low'
        return AnomalyResult(dev>th,min(1.0,dev/(th*2))if th>0 else 0,self.method_name,
            f"偏差={dev:.2f}",{'ma':round(ma,3),'dev':round(dev,3),'direction':dir_})

class RateOfChangeDetector(BaseDetector):
    method_name="rate_of_change"
    def __init__(self,max_pct=50.0):
        self.max_pct=max_pct
    def detect(self,series):
        if len(series)<2: return AnomalyResult(False,0,self.method_name,"insufficient_data")
        prev=series[-2]; curr=series[-1]
        if prev==0: return AnomalyResult(False,0,self.method_name,"zero_base")
        pct=abs((curr-prev)/prev*100); ok=pct>self.max_pct
        sc=min(1.0,pct/(self.max_pct*2)); d='spike_up' if curr>prev else 'drop_down'
        return AnomalyResult(ok,sc,self.method_name,f"变化率={pct:.1f}%",{'pct':round(pct,2),'direction':d})

class CompositeAnomalyDetector(BaseDetector):
    method_name="composite"
    def __init__(self,detectors=None,vote_thr=0.5):
        self.detectors=detectors or [
            ZScoreDetector(threshold=2.5), IQRDetector(k=1.5),
            MovingAvgDetector(), RateOfChangeDetector()]
        self.vote_thr=vote_thr
    def detect(self,series):
        results=[]
        for d in self.detectors:
            try: results.append(d.detect(series))
            except: results.append(AnomalyResult(False,0,d.method_name,"error"))
        ac=sum(1 for r in results if r.is_anomaly); tot=len(results)
        vr=ac/tot if tot>0 else 0
        drs=[{"method":r.method,"anomaly":r.is_anomaly,"score":round(r.score,3)} for r in results]
        return AnomalyResult(vr>=self.vote_thr,round(vr,4),self.method_name,
            f"{ac}/{tot}算法判定异常",{'vote_ratio':round(vr,3),'results':drs})

class AnomalyDetector:
    def __init__(self,method='auto'):
        self.method=method; self.method_used=None
    def detect(self,values):
        if len(values)<5: return False,0.0,"数据不足"
        m={'zscore':ZScoreDetector(),'iqr':IQRDetector(),
           'moving_avg':MovingAvgDetector(),'rate_of_change':RateOfChangeDetector(),
           'composite':CompositeAnomalyDetector()}
        det=m.get(self.method)
        if not det:
            if len(values)<20: det=ZScoreDetector(threshold=2.5)
            else: det=CompositeAnomalyDetector(vote_thr=0.6)
        self.method_used=det.method_name
        r=det.detect(values)
        return r.is_anomaly,r.score,r.reason

    @classmethod
    def from_config(cls, method='auto'):
        from .models import DetectorConfig
        det_map = {
            'zscore': ZScoreDetector,
            'iqr': IQRDetector,
            'moving_avg': MovingAvgDetector,
            'rate_of_change': RateOfChangeDetector,
            'composite': CompositeAnomalyDetector,
        }
        if method == 'auto':
            return cls(method='auto')
        DetectorClass = det_map.get(method)
        if not DetectorClass:
            return cls(method='auto')
        try:
            from .utils import get_detector_config
            config = get_detector_config(method)
        except Exception:
            from .models import DetectorConfig
            config = DetectorConfig.objects.filter(detector_name=method, is_enabled=True).first()
        if config and config.params:
            return DetectorClass(**config.params)
        return DetectorClass()
