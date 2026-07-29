import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from flask import Flask

from src.blueprints.widget import widget_bp
from src.config import Config


@pytest.fixture
def app():
    """Create a Flask app for testing."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(widget_bp)
    
    # Mock device config
    mock_config = Mock(spec=Config)
    mock_config.get_widgets.return_value = [
        {'id': 'date_widget', 'name': 'Date Widget'},
        {'id': 'static_message', 'name': 'Static Message'}
    ]
    mock_config.get_widget.side_effect = lambda widget_id: next(
        (w for w in mock_config.get_widgets() if w['id'] == widget_id), None
    )
    mock_config.get_config.return_value = {
        'enabled_widgets': ['date_widget'],
        'corner': 'top-left',
        'orientation': 'horizontal',
        'spacing': 10,
        'margin': 10,
        'widgets': {}
    }
    
    app.config['DEVICE_CONFIG'] = mock_config
    
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


class TestWidgetAPI:
    """Test widget API endpoints."""
    
    def test_reorder_widgets_success(self, client, app):
        """Test successful widget reordering."""
        with app.app_context():
            mock_config = app.config['DEVICE_CONFIG']
            mock_config.update_value = Mock()
            
            response = client.post(
                '/api/widgets/reorder',
                data=json.dumps({'order': ['static_message', 'date_widget']}),
                content_type='application/json'
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'Widget order updated' in data['message']
            mock_config.update_value.assert_called_once()
    
    def test_reorder_widgets_invalid_json(self, client):
        """Test reordering with invalid JSON."""
        response = client.post(
            '/api/widgets/reorder',
            data='invalid json',
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Invalid JSON' in data['error']
    
    def test_reorder_widgets_invalid_widget_id(self, client, app):
        """Test reordering with invalid widget ID."""
        with app.app_context():
            response = client.post(
                '/api/widgets/reorder',
                data=json.dumps({'order': ['invalid_widget', 'date_widget']}),
                content_type='application/json'
            )
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'Invalid widget IDs' in data['error']
    
    def test_toggle_widget_enable(self, client, app):
        """Test enabling a widget."""
        with app.app_context():
            mock_config = app.config['DEVICE_CONFIG']
            mock_config.update_value = Mock()
            
            response = client.post(
                '/api/widgets/toggle',
                data=json.dumps({'widget_id': 'static_message', 'enable': True}),
                content_type='application/json'
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'enabled' in data['message']
    
    def test_toggle_widget_disable(self, client, app):
        """Test disabling a widget."""
        with app.app_context():
            mock_config = app.config['DEVICE_CONFIG']
            mock_config.update_value = Mock()
            
            response = client.post(
                '/api/widgets/toggle',
                data=json.dumps({'widget_id': 'date_widget', 'enable': False}),
                content_type='application/json'
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'disabled' in data['message']
    
    def test_toggle_widget_not_found(self, client, app):
        """Test toggling a non-existent widget."""
        with app.app_context():
            response = client.post(
                '/api/widgets/toggle',
                data=json.dumps({'widget_id': 'nonexistent', 'enable': True}),
                content_type='application/json'
            )
            
            assert response.status_code == 404
            data = json.loads(response.data)
            assert 'not found' in data['error']
    
    def test_save_widget_settings_success(self, client, app):
        """Test saving widget global settings."""
        with app.app_context():
            mock_config = app.config['DEVICE_CONFIG']
            mock_config.update_value = Mock()
            
            response = client.post(
                '/api/widgets/settings',
                data=json.dumps({
                    'corner': 'bottom-right',
                    'orientation': 'vertical',
                    'spacing': 15,
                    'margin': 20
                }),
                content_type='application/json'
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'saved' in data['message']
    
    def test_save_widget_settings_invalid_json(self, client):
        """Test saving settings with invalid JSON."""
        response = client.post(
            '/api/widgets/settings',
            data='not json',
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Invalid JSON' in data['error']
    
    def test_save_widget_settings_invalid_numeric(self, client, app):
        """Test saving settings with invalid numeric values."""
        with app.app_context():
            response = client.post(
                '/api/widgets/settings',
                data=json.dumps({
                    'corner': 'top-left',
                    'orientation': 'horizontal',
                    'spacing': 'not_a_number',
                    'margin': 10
                }),
                content_type='application/json'
            )
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'Invalid numeric value' in data['error']


class TestWidgetUtils:
    """Test widget utility functions."""
    
    @patch('src.utils.widget_utils.get_widget_instance')
    @patch('src.utils.widget_utils.calculate_contrast_color')
    def test_contrast_only_computed_when_enabled(self, mock_contrast, mock_get_widget):
        """Test that contrast is only computed when use_contrast_color is True."""
        from src.utils.widget_utils import generate_and_apply_widgets
        from PIL import Image
        
        # Create a mock image
        main_image = Image.new('RGB', (800, 600), color='white')
        
        # Mock device config
        mock_config = Mock()
        mock_config.get_config.return_value = {
            'enabled_widgets': ['test_widget'],
            'corner': 'top-left',
            'orientation': 'horizontal',
            'spacing': 10,
            'margin': 10,
            'widgets': {
                'test_widget': {
                    'use_contrast_color': False  # Contrast disabled
                }
            }
        }
        mock_config.get_widget.return_value = {'id': 'test_widget', 'name': 'Test'}
        
        # Mock widget instance
        mock_widget = Mock()
        mock_widget.generate_image.return_value = Image.new('RGBA', (100, 50), color=(0, 0, 0, 0))
        mock_get_widget.return_value = mock_widget
        
        # Call the function
        result = generate_and_apply_widgets(main_image, mock_config)
        
        # Verify contrast was NOT calculated
        mock_contrast.assert_not_called()
        
        # Verify widget was generated without contrast_color
        call_args = mock_widget.generate_image.call_args[0][0]
        assert 'contrast_color' not in call_args
    
    @patch('src.utils.widget_utils.get_widget_instance')
    @patch('src.utils.widget_utils.calculate_contrast_color')
    def test_contrast_computed_when_enabled(self, mock_contrast, mock_get_widget):
        """Test that contrast is computed when use_contrast_color is True."""
        from src.utils.widget_utils import generate_and_apply_widgets
        from PIL import Image
        
        # Create a mock image
        main_image = Image.new('RGB', (800, 600), color='white')
        
        # Mock device config
        mock_config = Mock()
        mock_config.get_config.return_value = {
            'enabled_widgets': ['test_widget'],
            'corner': 'top-left',
            'orientation': 'horizontal',
            'spacing': 10,
            'margin': 10,
            'widgets': {
                'test_widget': {
                    'use_contrast_color': True  # Contrast enabled
                }
            }
        }
        mock_config.get_widget.return_value = {'id': 'test_widget', 'name': 'Test'}
        
        # Mock widget instance
        mock_widget = Mock()
        mock_widget.generate_image.return_value = Image.new('RGBA', (100, 50), color=(0, 0, 0, 0))
        mock_get_widget.return_value = mock_widget
        
        # Mock contrast calculation
        mock_contrast.return_value = '#FFFFFF'
        
        # Call the function
        result = generate_and_apply_widgets(main_image, mock_config)
        
        # Verify contrast WAS calculated
        mock_contrast.assert_called_once()
        
        # Verify widget was generated WITH contrast_color
        call_args = mock_widget.generate_image.call_args[0][0]
        assert 'contrast_color' in call_args
        assert call_args['contrast_color'] == '#FFFFFF'
    
    def test_calculate_contrast_color_returns_hex(self):
        """Test that calculate_contrast_color returns consistent hex format."""
        from src.utils.image_utils import calculate_contrast_color
        from PIL import Image
        
        # Test with light background
        light_image = Image.new('RGB', (100, 100), color=(200, 200, 200))
        result = calculate_contrast_color(light_image, (0, 0, 100, 100))
        assert result == '#000000'  # Should return black for light background
        
        # Test with dark background
        dark_image = Image.new('RGB', (100, 100), color=(50, 50, 50))
        result = calculate_contrast_color(dark_image, (0, 0, 100, 100))
        assert result == '#FFFFFF'  # Should return white for dark background
        
        # Verify format is always hex
        assert result.startswith('#')
        assert len(result) == 7
