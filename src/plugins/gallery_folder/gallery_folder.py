from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from io import BytesIO
import requests
import logging
import os
from flask import Blueprint, jsonify, current_app, request

from utils.app_utils import resolve_path
import random

logger = logging.getLogger(__name__)
GALLERY_FOLDER = resolve_path(os.path.join("static", "images", "gallery"))
THUMBNAIL_FOLDER = resolve_path(os.path.join(GALLERY_FOLDER, "thumbnails"))

class Gallery(BasePlugin):

    def __init__(self, device_config):
        super().__init__(device_config)
        # Initialize the folders
        if not os.path.exists(GALLERY_FOLDER):
            os.makedirs(GALLERY_FOLDER)
        if not os.path.exists(THUMBNAIL_FOLDER):
            os.makedirs(THUMBNAIL_FOLDER)
        # create gitignore file if it doesn't exist
        gitignore_path = os.path.join(GALLERY_FOLDER, ".gitignore")
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, 'w') as f:
                f.write("*\n!.gitignore\n")

    def generate_image(self, settings, device_config):
        img_index = settings.get("image_index", 0)

        folder = resolve_path(os.path.join("static", "images", "gallery"))
        if not folder or not os.path.isdir(folder):
            logger.error("Configured gallery folder not found")
            return None

        supported_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}
        image_locations = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in supported_exts
        ]

        if not image_locations:
            logger.error("No images found in gallery folder")
            return None

        img_index = self.select_new_index(img_index, len(image_locations))
        image_path = image_locations[img_index]

        try:
            image = Image.open(image_path)
        except Exception as e:
            logger.error(f"Error opening image: {str(e)}")
            return None

        settings['image_index'] = img_index
        return image
    
    def select_new_index(self, current_index, total_images):
        if total_images <= 1:
            return 0
        new_index = current_index
        while new_index == current_index:
            new_index = random.randint(0, total_images - 1)
        return new_index

def generate_thumbnail(image_path, size=(300, 300)):
    # Generate a thumbnail for the given image path and store it in the thumbnail folder
    thumbnail_path = os.path.join(THUMBNAIL_FOLDER, os.path.basename(image_path))
    if not os.path.isfile(thumbnail_path):
        try:
            with Image.open(image_path) as img:
                img.thumbnail(size)
                img.save(thumbnail_path, "JPEG")
        except Exception as e:
            logger.error(f"Error creating thumbnail: {str(e)}")
            return None
    return thumbnail_path

gallery_bp = Blueprint('gallery_folder', __name__)

@gallery_bp.route('/gallery/image', methods=['GET'])
def list_images():

    supported_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}
    images = [
        f for f in os.listdir(GALLERY_FOLDER)
        if os.path.splitext(f)[1].lower() in supported_exts
    ]
    return jsonify({"images": images})

@gallery_bp.route('/gallery/image/<filename>', methods=['GET'])
def get_image(filename):
    file_path = os.path.join(GALLERY_FOLDER, filename)
    if not os.path.isfile(file_path):
        return jsonify({"error": "Image not found"}), 404

    try:
        with open(file_path, 'rb') as f:
            image_data = f.read()
        return image_data, 200, {'Content-Type': 'image/jpeg'}  
    except Exception as e:
        logger.error(f"Error reading image file: {str(e)}")
        return jsonify({"error": "Failed to read image file"}), 500
    
@gallery_bp.route('/gallery/image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    file_path = os.path.join(GALLERY_FOLDER, image_file.filename)
    try:
        image_file.save(file_path)
        return jsonify({"message": "Image uploaded successfully", "filename": image_file.filename}), 201
    except Exception as e:
        logger.error(f"Error saving image file: {str(e)}")
        return jsonify({"error": "Failed to save image file"}), 500
    
@gallery_bp.route('/gallery/image/<filename>', methods=['DELETE'])
def delete_image(filename):
    file_path = os.path.join(GALLERY_FOLDER, filename)
    if not os.path.isfile(file_path):
        return jsonify({"error": "Image not found"}), 404

    try:
        os.remove(file_path)
        # Delete the thumbnail if it exists
        thumbnail_path = os.path.join(THUMBNAIL_FOLDER, filename)
        if os.path.isfile(thumbnail_path):
            os.remove(thumbnail_path)
        return jsonify({"message": "Image deleted successfully"}), 200
    except Exception as e:
        logger.error(f"Error deleting image file: {str(e)}")
        return jsonify({"error": "Failed to delete image file"}), 500
    
@gallery_bp.route('/gallery/thumbnail/<filename>', methods=['GET'])
def get_thumbnail(filename):
    image_path = os.path.join(GALLERY_FOLDER, filename)
    if not os.path.isfile(image_path):
        return jsonify({"error": "Image not found"}), 404
    thumbnail_path = generate_thumbnail(image_path)
    if not thumbnail_path:
        return jsonify({"error": "Failed to create thumbnail"}), 500 
    try:
        with open(thumbnail_path, 'rb') as f:
            thumbnail_data = f.read()
        return thumbnail_data, 200, {'Content-Type': 'image/jpeg'}
    except Exception as e:
        logger.error(f"Error reading thumbnail file: {str(e)}")
        return jsonify({"error": "Failed to read thumbnail file"}), 500
