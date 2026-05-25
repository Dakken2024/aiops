import logging
from datetime import timedelta, datetime

import numpy as np
import pandas as pd
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False
    logger.warning("statsmodels not installed, ARIMA/SARIMA forecasting disabled")

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    logger.warning("scikit-learn not installed, IsolationForest disabled")


@shared_task
def arima_forecast(server_id=None, metric_type='cpu', forecast_days=7):
    """
    使用 ARIMA 模型进行容量预测
    """
    from cmdb.models import Server, ServerMetric
    from prediction.models import CapacityForecast
    
    if not HAS_STATSMODELS:
        logger.error("statsmodels not installed, skipping ARIMA forecast")
        return {'status': 'error', 'msg': 'statsmodels not installed'}
    
    servers = Server.objects.filter(status='Running')
    if server_id:
        servers = servers.filter(id=server_id)
    
    metric_map = {
        'cpu': 'cpu_usage',
        'memory': 'mem_usage',
        'disk': 'disk_usage',
    }
    db_field = metric_map.get(metric_type)
    if not db_field:
        return {'status': 'error', 'msg': 'invalid metric_type'}
    
    results = []
    for server in servers:
        try:
            thirty_days_ago = timezone.now() - timedelta(days=30)
            metrics = list(ServerMetric.objects.filter(
                server=server,
                created_at__gte=thirty_days_ago,
            ).order_by('created_at').values_list('created_at', db_field))
            
            if len(metrics) < 50:
                logger.debug(f"[ARIMA] {server.hostname} 数据不足，跳过")
                continue
            
            timestamps = [m[0] for m in metrics]
            values = [float(m[1]) for m in metrics if m[1] is not None]
            
            if len(values) < 30:
                continue
            
            try:
                model = ARIMA(values, order=(5, 1, 0))
                model_fit = model.fit()
                forecast = model_fit.forecast(steps=forecast_days * 24)
                confidence = float(model_fit.aic)
                
                forecast_dates = [
                    timezone.now().date() + timedelta(days=i // 24)
                    for i in range(len(forecast))
                ]
                
                daily_forecasts = {}
                for i, date in enumerate(forecast_dates):
                    if date not in daily_forecasts:
                        daily_forecasts[date] = []
                    daily_forecasts[date].append(float(forecast[i]))
                
                for date, hourly_values in daily_forecasts.items():
                    avg_value = sum(hourly_values) / len(hourly_values)
                    CapacityForecast.objects.update_or_create(
                        server=server,
                        metric_type=metric_type,
                        forecast_date=date,
                        defaults={
                            'forecast_data': hourly_values,
                            'confidence': min(1.0, max(0.0, 1 - confidence / 1000)),
                        }
                    )
                
                results.append({
                    'server': server.hostname,
                    'metric': metric_type,
                    'forecast_points': len(forecast),
                    'status': 'success',
                })
            except Exception as e:
                logger.error(f"[ARIMA] {server.hostname} 模型训练失败: {e}")
                continue
                
        except Exception as e:
            logger.error(f"[ARIMA] {server.hostname} 处理失败: {e}")
            continue
    
    logger.info(f"[ARIMA] 完成 {len(results)} 台服务器的 {metric_type} 预测")
    return {'processed': len(results), 'details': results}


@shared_task
def prophet_forecast(server_id=None, metric_type='cpu', forecast_days=7):
    """
    使用 Prophet 模型进行容量预测（如果可用）
    """
    from cmdb.models import Server, ServerMetric
    from prediction.models import CapacityForecast
    
    try:
        from prophet import Prophet
        HAS_PROPHET = True
    except ImportError:
        HAS_PROPHET = False
        logger.warning("prophet not installed, falling back to ARIMA")
        return arima_forecast(server_id, metric_type, forecast_days)
    
    servers = Server.objects.filter(status='Running')
    if server_id:
        servers = servers.filter(id=server_id)
    
    metric_map = {
        'cpu': 'cpu_usage',
        'memory': 'mem_usage',
        'disk': 'disk_usage',
    }
    db_field = metric_map.get(metric_type)
    if not db_field:
        return {'status': 'error', 'msg': 'invalid metric_type'}
    
    results = []
    for server in servers:
        try:
            thirty_days_ago = timezone.now() - timedelta(days=30)
            metrics = list(ServerMetric.objects.filter(
                server=server,
                created_at__gte=thirty_days_ago,
            ).order_by('created_at').values_list('created_at', db_field))
            
            if len(metrics) < 50:
                logger.debug(f"[Prophet] {server.hostname} 数据不足，跳过")
                continue
            
            df = pd.DataFrame({
                'ds': [m[0] for m in metrics],
                'y': [float(m[1]) if m[1] is not None else 0 for m in metrics],
            })
            
            model = Prophet(daily_seasonality=True, weekly_seasonality=True)
            model.fit(df)
            
            future = model.make_future_dataframe(periods=forecast_days * 24, freq='H')
            forecast = model.predict(future)
            
            forecast_dates = forecast['ds'].dt.date.tolist()
            forecast_values = forecast['yhat'].tolist()
            
            daily_forecasts = {}
            for date, value in zip(forecast_dates[-forecast_days * 24:], forecast_values[-forecast_days * 24:]):
                if date not in daily_forecasts:
                    daily_forecasts[date] = []
                daily_forecasts[date].append(float(value))
            
            for date, hourly_values in daily_forecasts.items():
                CapacityForecast.objects.update_or_create(
                    server=server,
                    metric_type=metric_type,
                    forecast_date=date,
                    defaults={
                        'forecast_data': hourly_values,
                        'confidence': 0.95,
                    }
                )
            
            results.append({
                'server': server.hostname,
                'metric': metric_type,
                'forecast_points': len(forecast_values),
                'status': 'success',
            })
            
        except Exception as e:
            logger.error(f"[Prophet] {server.hostname} 处理失败: {e}")
            continue
    
    logger.info(f"[Prophet] 完成 {len(results)} 台服务器的 {metric_type} 预测")
    return {'processed': len(results), 'details': results}


@shared_task
def isolation_forest_detection():
    """
    使用 Isolation Forest 进行异常检测
    """
    from cmdb.models import Server, ServerMetric
    from prediction.models import AnomalyDetection
    
    if not HAS_SKLEARN:
        logger.error("scikit-learn not installed, skipping isolation forest detection")
        return {'status': 'error', 'msg': 'scikit-learn not installed'}
    
    servers = Server.objects.filter(status='Running')
    results = []
    
    for server in servers:
        try:
            one_hour_ago = timezone.now() - timedelta(hours=1)
            metrics = list(ServerMetric.objects.filter(
                server=server,
                created_at__gte=one_hour_ago,
            ).order_by('created_at').values(
                'created_at', 'cpu_usage', 'mem_usage', 'disk_usage', 
                'load_1min', 'net_in', 'net_out'
            ))
            
            if len(metrics) < 10:
                continue
            
            feature_names = ['cpu_usage', 'mem_usage', 'disk_usage', 'load_1min']
            data = []
            timestamps = []
            
            for m in metrics:
                row = []
                valid = True
                for fn in feature_names:
                    val = m.get(fn)
                    if val is None:
                        valid = False
                        break
                    row.append(float(val))
                if valid:
                    data.append(row)
                    timestamps.append(m['created_at'])
            
            if len(data) < 10:
                continue
            
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(data)
            
            clf = IsolationForest(
                contamination=0.1,
                random_state=42,
                n_estimators=100,
            )
            predictions = clf.fit_predict(scaled_data)
            scores = clf.decision_function(scaled_data)
            
            anomalies_found = 0
            for i, (pred, score, ts) in enumerate(zip(predictions, scores, timestamps)):
                if pred == -1:
                    anomaly_score = 1 - score
                    severity = 'high' if anomaly_score > 0.8 else 'medium' if anomaly_score > 0.5 else 'low'
                    
                    features = {fn: float(data[i][j]) for j, fn in enumerate(feature_names)}
                    
                    AnomalyDetection.objects.create(
                        server=server,
                        detected_at=ts,
                        score=anomaly_score,
                        features=features,
                        metric_name=feature_names[0],
                        severity=severity,
                        method_used='isolation_forest',
                    )
                    anomalies_found += 1
            
            results.append({
                'server': server.hostname,
                'anomalies_found': anomalies_found,
                'total_samples': len(data),
            })
            
        except Exception as e:
            logger.error(f"[IsolationForest] {server.hostname} 处理失败: {e}")
            continue
    
    logger.info(f"[IsolationForest] 完成 {len(results)} 台服务器的异常检测")
    return {'processed': len(results), 'details': results, 'total_anomalies': sum(r['anomalies_found'] for r in results)}


@shared_task
def baseline_learning():
    """
    智能基线学习 - 检测日/周/月周期模式
    """
    from cmdb.models import Server, ServerMetric
    from prediction.models import BaselineModel
    
    servers = Server.objects.filter(status='Running')
    metric_types = ['cpu_usage', 'mem_usage', 'disk_usage']
    
    results = []
    
    for server in servers:
        for metric_type in metric_types:
            try:
                seven_days_ago = timezone.now() - timedelta(days=7)
                metrics = list(ServerMetric.objects.filter(
                    server=server,
                    created_at__gte=seven_days_ago,
                ).order_by('created_at').values_list('created_at', metric_type))
                
                if len(metrics) < 100:
                    continue
                
                timestamps = [m[0] for m in metrics]
                values = [float(m[1]) if m[1] is not None else 0 for m in metrics]
                
                df = pd.DataFrame({'timestamp': timestamps, 'value': values})
                df['hour'] = df['timestamp'].apply(lambda x: x.hour)
                df['day_of_week'] = df['timestamp'].apply(lambda x: x.weekday())
                df['day_of_month'] = df['timestamp'].apply(lambda x: x.day)
                
                hourly_pattern = df.groupby('hour')['value'].agg(['mean', 'std', 'max', 'min']).to_dict('index')
                weekday_pattern = df.groupby('day_of_week')['value'].agg(['mean', 'std']).to_dict('index')
                
                baseline_data = {
                    'hourly': hourly_pattern,
                    'upper_bound': {},
                    'lower_bound': {},
                }
                
                for hour in range(24):
                    if hour in hourly_pattern:
                        mean_val = hourly_pattern[hour]['mean']
                        std_val = hourly_pattern[hour]['std']
                        baseline_data['upper_bound'][hour] = float(mean_val + 2 * std_val)
                        baseline_data['lower_bound'][hour] = float(max(0, mean_val - 2 * std_val))
                
                learned_periods = {
                    'daily': bool(len(hourly_pattern) >= 20),
                    'weekly': bool(len(weekday_pattern) >= 5),
                    'monthly': False,
                }
                
                BaselineModel.objects.update_or_create(
                    server=server,
                    metric_type=metric_type,
                    defaults={
                        'baseline_data': baseline_data,
                        'learned_periods': learned_periods,
                        'last_learned_at': timezone.now(),
                    }
                )
                
                results.append({
                    'server': server.hostname,
                    'metric': metric_type,
                    'periods': [k for k, v in learned_periods.items() if v],
                    'status': 'success',
                })
                
            except Exception as e:
                logger.error(f"[BaselineLearning] {server.hostname} {metric_type} 失败: {e}")
                continue
    
    logger.info(f"[BaselineLearning] 完成 {len(results)} 条基线学习")
    return {'processed': len(results), 'details': results}