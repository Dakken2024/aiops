import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class MonitoringConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = 'monitoring'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'message': 'WebSocket connected',
        }))
        logger.info(f"[WS] Client connected: {self.channel_name}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"[WS] Client disconnected: {self.channel_name}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            if action == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
            elif action == 'subscribe':
                await self.send(text_data=json.dumps({'type': 'subscribed', 'channels': ['monitoring']}))
        except Exception as e:
            logger.error(f"[WS] Receive error: {e}")

    async def monitoring_event(self, event):
        await self.send(text_data=json.dumps(event['data']))