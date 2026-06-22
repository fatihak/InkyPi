import logging
from widgets.widget_registry import get_widget_instance
from utils.image_utils import calculate_contrast_color

logger = logging.getLogger(__name__)

def generate_and_apply_widgets(main_image, device_config):
    """
    Generates enabled widgets and applies them to the main image, 
    calculating contrast against the background.
    """
    widget_settings = device_config.get_config('widget_settings', {})
    enabled_widgets = widget_settings.get('enabled_widgets', [])
    
    corner = widget_settings.get('corner', 'top-left')
    orientation = widget_settings.get('orientation', 'horizontal')
    spacing = widget_settings.get('spacing', 10)
    margin = widget_settings.get('margin', 10)
    
    width, height = main_image.size
    
    # Calculate start position
    x_start, y_start = {
        'top-left': (0+margin, 0+margin),
        'top-right': (width-margin, 0+margin),
        'bottom-left': (0+margin, height-margin),
        'bottom-right': (width-margin, height-margin)
    }[corner]
    
    current_x, current_y = x_start, y_start
    
    for widget_id in enabled_widgets:
        widget_config = device_config.get_widget(widget_id)
        if not widget_config:
            logger.warning(f"Widget config not found for enabled widget {widget_id}")
            continue
            
        # Get stored settings for this widget
        specific_widget_settings = widget_settings.get('widgets', {}).get(widget_id, {})
        
        # Determine check box for contrast
        check_size = 100
        box = (0, 0, check_size, check_size) # Default
        
        if corner == 'top-left':
            box = (current_x, current_y, current_x + check_size, current_y + check_size)
        elif corner == 'top-right':
             box = (current_x - check_size, current_y, current_x, current_y + check_size)
        elif corner == 'bottom-left':
             box = (current_x, current_y - check_size, current_x + check_size, current_y)
        elif corner == 'bottom-right':
            box = (current_x - check_size, current_y - check_size, current_x, current_y)
            
        # Clamp to image bounds
        box = (
            max(0, int(box[0])), max(0, int(box[1])),
            min(width, int(box[2])), min(height, int(box[3]))
        )
        
        # Calculate contrast
        contrast_color = calculate_contrast_color(main_image, box)
        specific_widget_settings['contrast_color'] = contrast_color
        
        # Generate widget
        try:
            widget_instance = get_widget_instance(widget_config)
            widget_img = widget_instance.generate_image(specific_widget_settings, device_config)
            
            ov_w, ov_h = widget_img.size
            paste_x, paste_y = current_x, current_y
            
            if orientation == 'horizontal':
                if corner in ['top-right', 'bottom-right']:
                    paste_x = current_x - ov_w
                
                if corner in ['bottom-left', 'bottom-right']:
                    paste_y = current_y - ov_h
                
                main_image.paste(widget_img, (int(paste_x), int(paste_y)), widget_img)
                
                if corner in ['top-left', 'bottom-left']:
                    current_x += ov_w + spacing
                else:
                    current_x -= (ov_w + spacing)
                    
            else: # Vertical
                if corner in ['bottom-left', 'bottom-right']:
                    paste_y = current_y - ov_h
                
                if corner in ['top-right', 'bottom-right']:
                    paste_x = current_x - ov_w
                    
                main_image.paste(widget_img, (int(paste_x), int(paste_y)), widget_img)
                
                if corner in ['top-left', 'top-right']:
                    current_y += ov_h + spacing
                else:
                    current_y -= (ov_h + spacing)
                    
        except Exception as e:
            logger.error(f"Error generating/applying widget {widget_id}: {e}")
            
    return main_image
