# Django Channels WebSocket Setup for Live Event Dashboard

This document describes the WebSocket implementation for real-time event monitoring and participant check-in tracking.

## Overview

The system provides real-time updates for:
- Participant check-ins and check-outs
- New participant registrations  
- Event dashboard updates for supervisors

## Components

### 1. WebSocket Consumers (`apps/events/consumers.py`)

#### `EventCheckInConsumer`
- **URL Pattern**: `ws/events/checkin/<event_id>/`
- **Purpose**: Real-time monitoring of specific event check-ins
- **Permissions**: Event creators, superusers, and service team members only
- **Features**:
  - Sends initial event and participant data on connection
  - Broadcasts live check-in/check-out updates
  - Handles ping/pong for connection health

#### `EventDashboardConsumer` 
- **URL Pattern**: `ws/events/dashboard/`
- **Purpose**: General dashboard updates for multiple events
- **Permissions**: Authenticated users (shows only their accessible events)
- **Features**:
  - Provides overview of user's events
  - Receives updates about participant count changes

### 2. WebSocket Utilities (`apps/events/websocket_utils.py`)

#### `WebSocketNotifier`
Central utility class for broadcasting messages:
- `notify_checkin_update()` - Broadcasts check-in/out events
- `notify_participant_registered()` - Broadcasts new registrations
- `notify_event_update()` - Sends general event updates to dashboards

#### Helper Functions
- `serialize_participant_for_websocket()` - Formats participant data for WebSocket
- `get_event_supervisors()` - Gets user IDs who should receive event updates

### 3. API Integration

The following REST endpoints now broadcast WebSocket updates:

#### Check-in Endpoint
```
POST /api/events/participants/{event_pax_id}/check-in/
```
- Broadcasts `checkin_update` message to event group
- Notifies dashboards of participant count change

#### Check-out Endpoint  
```
POST /api/events/participants/{event_pax_id}/check-out/
```
- Broadcasts `checkout_update` message to event group
- Notifies dashboards of participant count change

#### Registration Endpoint
```
POST /api/events/{event_id}/register/
```
- Broadcasts `participant_registered` message to event group
- Notifies dashboards of new participant

## WebSocket Message Types

### Event Check-in Consumer Messages

#### Incoming (Client → Server)
```json
{
  "type": "get_participants"
}
```

```json
{
  "type": "ping",
  "timestamp": "2025-01-01T12:00:00Z"
}
```

#### Outgoing (Server → Client)

**Initial Data**
```json
{
  "type": "initial_data",
  "event": {
    "id": "uuid",
    "name": "Event Name",
    "start_date": "2025-01-01T10:00:00Z",
    "participant_count": 50
  },
  "participants": [...]
}
```

**Check-in Update**
```json
{
  "type": "checkin_update",
  "participant": {
    "id": "uuid",
    "event_pax_id": "ABC123",
    "user": {
      "first_name": "John",
      "last_name": "Doe",
      "email": "john@example.com"
    },
    "checked_in": true,
    "check_in_time": "2025-01-01T10:30:00Z"
  },
  "action": "checkin",
  "timestamp": "2025-01-01T10:30:00Z"
}
```

**New Registration**
```json
{
  "type": "participant_registered",
  "participant": {...},
  "timestamp": "2025-01-01T10:15:00Z"
}
```

### Dashboard Consumer Messages

**Event Update**
```json
{
  "type": "event_update", 
  "event_id": "uuid",
  "update_type": "participant_checked_in",
  "data": {"participant_id": "uuid"},
  "timestamp": "2025-01-01T10:30:00Z"
}
```

## Channel Layer Configuration

### Development (In-Memory)
```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}
```

### Production (Redis)
```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("redis-server", 6379)],
        },
    },
}
```

## Frontend Integration Examples

### JavaScript WebSocket Client
```javascript
// Connect to event check-in monitoring
const eventSocket = new WebSocket(
    'ws://localhost:8000/ws/events/checkin/' + eventId + '/'
);

eventSocket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    
    switch(data.type) {
        case 'initial_data':
            displayEventInfo(data.event);
            displayParticipants(data.participants);
            break;
            
        case 'checkin_update':
            updateParticipantStatus(data.participant);
            showNotification(`${data.participant.user.first_name} ${data.action}`);
            break;
            
        case 'participant_registered':
            addNewParticipant(data.participant);
            break;
    }
};

// Send ping to keep connection alive
setInterval(() => {
    eventSocket.send(JSON.stringify({
        type: 'ping',
        timestamp: new Date().toISOString()
    }));
}, 30000);
```

### Dashboard WebSocket
```javascript
// Connect to general dashboard
const dashboardSocket = new WebSocket(
    'ws://localhost:8000/ws/events/dashboard/'
);

dashboardSocket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    
    if(data.type === 'event_update') {
        updateEventBadge(data.event_id, data.update_type);
    }
};
```

## Security

- All WebSocket connections require authentication
- Event monitoring is restricted to authorized users (creators, service team)
- CORS and allowed hosts are enforced via `AllowedHostsOriginValidator`
- JWT authentication is supported through `AuthMiddlewareStack`

## Deployment Notes

### Redis Setup (Production)
1. Install Redis server
2. Update `CHANNEL_LAYERS` settings with Redis configuration
3. Ensure Redis is accessible from Django application
4. Consider Redis clustering for high availability

### WebSocket Server
- Use Daphne or uvicorn for ASGI serving
- Configure nginx/proxy for WebSocket support
- Set up SSL/TLS for secure WebSocket connections (wss://)

### Docker Configuration
Add to docker-compose.yml:
```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
      
  web:
    # ... existing config
    depends_on:
      - redis
    environment:
      - REDIS_HOST=redis
```

## Error Handling

The WebSocket implementation includes graceful error handling:
- API operations continue even if WebSocket broadcast fails
- Connection drops are handled with automatic reconnection
- Invalid messages are caught and error responses sent
- Permissions are checked on every connection

## Testing

### Manual Testing
1. Start Django development server with channels
2. Connect to WebSocket endpoint using browser dev tools or WebSocket client
3. Trigger check-in/registration via API
4. Verify real-time updates are received

### Automated Testing
Consider using channels testing utilities:
```python
from channels.testing import WebsocketCommunicator
from django.test import TestCase

class WebSocketTests(TestCase):
    async def test_checkin_consumer(self):
        communicator = WebsocketCommunicator(
            EventCheckInConsumer.as_asgi(), 
            "/ws/events/checkin/test-event-id/"
        )
        connected, subprotocol = await communicator.connect()
        assert connected
        # ... test message handling
        await communicator.disconnect()
```