from flask import Blueprint
from flask_socketio import emit
import logging
import time

logger = logging.getLogger(__name__)
dev_bp = Blueprint("dev", __name__)


def register_socketio_events(socketio):
    """Register Socket.IO events for live reload."""
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection."""
        logger.info("Client connected to live reload")
        emit('connected', {'message': 'Live reload connected'})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        logger.info("Client disconnected from live reload")
    
    @socketio.on('ping')
    def handle_ping():
        """Handle ping for connection testing."""
        emit('pong', {'timestamp': time.time()})
    
    @socketio.on('reload_request')
    def handle_reload_request():
        """Handle manual reload request from client."""
        logger.info("Manual reload requested by client")
        emit('reload', {'source': 'client', 'timestamp': time.time()}, broadcast=True)