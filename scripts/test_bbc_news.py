import os
import sys
from unittest.mock import MagicMock
from PIL import Image

# --- Path Setup ---
# Add the project root to the Python path to allow for correct module imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# --- Imports from Plugin ---
from plugins.bbc_news.bbc_news import BbcNews, BBC_FEEDS
from utils.image_utils import resize_image

# --- Configuration for the Test ---
RESOLUTIONS = [
    [400, 300], [640, 400], [600, 448], [800, 480], [1280, 960]
]
ORIENTATIONS = ["horizontal", "vertical"]


# --- Test Script Main Logic ---
def run_all_tests():
    """
    Iterates through all configured BBC feeds, creating a separate composite
    image for each one that shows all resolution and orientation combinations.
    """
    print("Starting BBC News plugin test script...")

    # FIX: Create a mock plugin config to pass to the plugin's constructor
    plugin_config = {
        "id": "bbc_news",
        "display_name": "BBC News"
    }
    # Instantiate the plugin once, passing the required config
    plugin_instance = BbcNews(plugin_config)
    mock_device_config = MagicMock()

    # Create an output directory for the test images
    output_dir = "test_outputs"
    os.makedirs(output_dir, exist_ok=True)
    print(f"Saving composite images to '{output_dir}/' directory...")

    # --- Loop through each feed ---
    for feed_name, feed_url in BBC_FEEDS.items():
        safe_feed_name = feed_name.replace(' & ', '_and_').replace(' ', '_')
        print(f"\n--- Generating composite for: '{feed_name}' ---")

        # --- Create a new blank composite image for this feed ---
        # Calculate the size needed for the composite image
        max_width = max(res[0] for res in RESOLUTIONS)
        total_height = sum(max(res) for res in RESOLUTIONS)
        composite = Image.new('RGB', (max_width * 2, total_height), color='gray')

        y_offset = 0
        for resolution in RESOLUTIONS:
            x_offset = 0
            max_height_for_row = 0

            for orientation in ORIENTATIONS:
                print(f" - Testing {resolution[0]}x{resolution[1]} ({orientation}) for '{feed_name}'")

                try:
                    # Set up the mock device config for this iteration
                    mock_device_config.get_resolution.return_value = resolution
                    mock_device_config.get_config.return_value = orientation

                    # Set the specific feed URL for this iteration
                    plugin_settings = {"bbc_feed_url": feed_url}

                    # Generate the image using the plugin
                    img = plugin_instance.generate_image(plugin_settings, mock_device_config)

                    if img:
                        # The plugin's generate_image function should return the final image
                        # with the correct orientation. We just need to resize it back to
                        # the target resolution for the composite if it's not exact.
                        if orientation == "vertical":
                           img = resize_image(img, (resolution[1], resolution[0]), [])                           
                        else:
                           img = resize_image(img, resolution, [])

                        composite.paste(img, (x_offset, y_offset))
                        x_offset += max(resolution)
                        if img.height > max_height_for_row:
                            max_height_for_row = img.height

                except Exception as e:
                    print(f"   - ERROR generating {resolution} ({orientation}) for '{feed_name}': {e}")

            y_offset += max_height_for_row

        # --- Save the composite image for the current feed ---
        output_filename = f"composite_{safe_feed_name}.png"
        output_path = os.path.join(output_dir, output_filename)
        print(f" -> Saving composite image to {output_path}...")
        composite.save(output_path)

    print("\nAll tests complete.")


if __name__ == "__main__":
    run_all_tests()
