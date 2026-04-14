import json,hmac,hashlib,base64,time,logging,urllib.parse
from datetime import datetime
from typing import List,Dict
from dataclasses import dataclass,field

logger=logging.getLogger(__name__)

@dataclass
class NotificationMessage:
    title:str; content:str; severity:str="P1"; alert_id:int=0
    server_name:str=""; metric_name:str=""
    current_value:float=0.0; threshold:float=0.0
    timestamp:str=field(default_factory=lambda:datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dingtalk_markdown(self):
        return {"msgtype":"markdown","markdown":{
            "title":self.title,"text":
            f"### {self.severity} {self.title}\n\n"
            f"- **服务器**: {self.server_name}\n- **指标**: {self.metric_name}\n"
            f"- **当前值**: {self.current_value}\n- **阈值**: {self.threshold}\n\n"
            f"{self.content}\n\n> {self.timestamp}"}}

    def to_wechat_text(self):
        return f'<font color="warning">{self.title}</font>\n{self.content}\n时间: {self.timestamp}'

    def to_email_html(self):
        c={'P0':'#ff4d4f','P1':'#fa8c16','P2':'#faad14','P3':'#52c41a'}
        color=c.get(self.severity,'#1890ff')
        return f'''<html><body style="font-family:sans-serif;padding:20px">
<div style="max-width:600px;margin:auto;border:1px solid #e8e8e8;border-radius:8px;overflow:hidden">
<div style="background:{color};color:white;padding:16px 24px"><h2 style="margin:0">{self.title}</h2>
<p style="margin:4px 0 0;opacity:.9">级别: {self.severity}</p></div>
<div style="padding:24px"><table style="width:100%;border-collapse:collapse">
<tr><td style="padding:8px;border-bottom:1px solid #eee"><b>服务器</b></td><td>{self.server_name}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee"><b>指标</b></td><td>{self.metric_name}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee"><b>当前值</b></td>
<td style="color:{color};font-weight:bold">{self.current_value}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee"><b>阈值</b></td><td>{self.threshold}</td></tr>
<tr><td style="padding:8px"><b>触发时间</b></td><td>{self.timestamp}</td></tr></table>
<hr style="border:none;border-top:1px solid #eee;margin:16px 0">
<p style="color:#666;line-height:1.6">{self.content}</p></div>
<div style="background:#fafafa;padding:12px 24px;font-size:12px;color:#999;text-align:center">
AiOps 自动发送</div></div></body></html>'''

    def to_slack_attachment(self):
        e={'P0':'danger','P1':'warning','P2':'warning','P3':'good'}
        em={'P0':':rotating_light:','P1':':warning:','P2':':information_source:','P3':':bell:'}
        return {"attachments":[{"color":e.get(self.severity,'#439FE5'),
            "title":f"{em.get(self.severity,'')} {self.title}",
            "fields":[{"title":"服务器","value":self.server_name,"short":True},
                      {"title":"指标","value":self.metric_name,"short":True},
                      {"title":"当前值","value":str(self.current_value),"short":True},
                      {"title":"阈值","value":str(self.threshold),"short":True}],
            "text":self.content,"footer":"AiOps","ts":int(time.time())}]}


class DingTalkChannel:
    name="dingtalk"
    def __init__(self,cfg):
        self.url=cfg.get('webhook_url',''); self.secret=cfg.get('secret','')
        self.msg_type=cfg.get('msg_type','markdown')
    def send(self,msg):
        import requests
        try:
            payload=msg.to_dingtalk_markdown() if self.msg_type=='markdown' else {"msgtype":"text",
                "text":{"content":f"**{msg.title}**\n{msg.content}\n> {msg.timestamp}"}}
            url=self.url
            if self.secret:
                ts=str(round(time.time()*1000)); sig_str=f'{ts}\n{self.secret}'
                hc=hmac.new(self.secret.encode(),sig_str.encode(),digestmod=hashlib.sha256).digest()
                sign=urllib.parse.quote_plus(base64.b64encode(hc))
                url=f"{url}&timestamp={ts}&sign={sign}"
            r=requests.post(url,json=payload,timeout=10)
            ok=r.status_code==200 and r.json().get('errcode')==0
            return {'success':ok,'channel':self.name,'response':r.json() if ok else r.text}
        except Exception as e:
            logger.error(f"[DingTalk] {e}"); return {'success':False,'channel':self.name,'error':str(e)}

class WeChatChannel:
    name="wechat"
    def __init__(self,cfg): self.url=cfg.get('webhook_url','')
    def send(self,msg):
        import requests
        try:
            r=requests.post(self.url,json={"msgtype":"markdown",
                "markdown":{"content":msg.to_wechat_text()}},timeout=10)
            return {'success':r.status_code==200 and r.json().get('errcode')==0,'channel':self.name}
        except Exception as e:
            logger.error(f"[WeChat] {e}"); return {'success':False,'channel':self.name,'error':str(e)}

class EmailChannel:
    name="email"
    def __init__(self,cfg):
        self.host=cfg.get('smtp_host',''); self.port=cfg.get('smtp_port',587)
        self.user=cfg.get('smtp_user',''); self.pwd=cfg.get('smtp_pass','')
        self.frm=cfg.get('from_addr',''); self.tls=cfg.get('use_tls',True)
        self.to_addr=cfg.get('to_addrs','')
    def send(self,msg):
        import smtplib
        from email.mime.text import MIMEText; from email.mime.multipart import MIMEMultipart
        try:
            msg=MIMEMultipart('alternative')
            msg['Subject']=f"[{msg.severity}] {msg.title}"
            msg['From']=self.frm; msg['To']=self.to_addr
            msg.attach(MIMEText(msg.to_email_html(),'html','utf-8'))
            srv=smtplib.SMTP(self.host,self.port)
            if self.tls: srv.starttls()
            srv.login(self.user,self.pwd)
            srv.sendmail(self.frm,self.to_addr.split(','),msg.as_string()); srv.quit()
            return {'success':True,'channel':self.name}
        except Exception as e:
            logger.error(f"[Email] {e}"); return {'success':False,'channel':self.name,'error':str(e)}

class WebhookChannel:
    name="webhook"
    def __init__(self,cfg):
        self.url=cfg.get('url',''); self.method=cfg.get('method','POST')
        self.headers=cfg.get('headers',{})
    def send(self,msg):
        import requests
        try:
            r=requests.request(self.method,self.url,json={
                "alert_id":msg.alert_id,"title":msg.title,"content":msg.content,
                "severity":msg.severity,"server":msg.server_name,"metric":msg.metric_name,
                "current_value":msg.current_value,"threshold":msg.threshold,"timestamp":msg.timestamp},
                headers=self.headers,timeout=10)
            return {'success':r.status_code<400,'channel':self.name,'status_code':r.status_code}
        except Exception as e:
            return {'success':False,'channel':self.name,'error':str(e)}

CHANNEL_CLS={'dingtalk':DingTalkChannel,'wechat':WeChatChannel,
             'email':EmailChannel,'slack':None,'webhook':WebhookChannel}


class NotificationRouter:
    def __init__(self):
        self.channels={}
        self._load()

    def _load(self):
        from system.models import SystemConfig
        for name,cls in CHANNEL_CLS.items():
            if not cls: continue
            raw=SystemConfig.objects.filter(key=f'notify_{name}_config').first()
            if raw and raw.value:
                try:
                    cfg=json.loads(raw.value); self.channels[name]=cls(cfg)
                except Exception as e:
                    logger.error(f"[Notify] 加载{name}失败: {e}")

    def route_and_send(self,msg,target_channels):
        results=[]
        for ch in target_channels:
            c=self.channels.get(ch)
            if not c:
                results.append({'success':False,'channel':ch,'error':'not_configured'}); continue
            r=c.send(msg); results.append(r)
            st="OK" if r['success'] else f"FAIL({r.get('error','?')})"
            logger.info(f"[Notify] {ch}: {st}")
        return results


from celery import shared_task

@shared_task(bind=True,max_retries=3,default_retry_delay=60)
def send_alert_notifications(self,event_id):
    from monitoring.models import AlertEvent,NotificationLog
    try:
        event=AlertEvent.objects.select_related('rule','server').get(id=event_id)
        msg=NotificationMessage(
            title=f"【{event.rule.name}】{event.message}",content=event.detail or "",
            severity=event.severity,alert_id=event.id,
            server_name=event.server.hostname if event.server else "",
            metric_name=event.metric_name,current_value=event.current_value,
            threshold=event.threshold_value or 0)
        channels=event.rule.notify_channels or ['dingtalk']
        router=NotificationRouter(); results=router.route_and_send(msg,channels)
        event.notification_log=results; event.save(update_fields=['notification_log'])
        for r in results:
            NotificationLog.objects.create(alert_event=event,channel=r['channel'],
                status='sent' if r['success'] else 'failed',
                error_message=r.get('error',''),content_summary=msg.title[:200])
        af=all(not rr['success'] for rr in results)
        if af and self.request.retries<self.max_retries:
            raise self.retry(countdown=60*(self.request.retries+1))
        return results
    except AlertEvent.DoesNotExist:
        return {'error':'not_found'}
    except Exception as e:
        logger.error(f"[AlertNotify] {event_id}: {e}")
        raise self.retry(exc=e)
