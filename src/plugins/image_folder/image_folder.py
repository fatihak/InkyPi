from plugins.base_plugin.base_plugin import BasePlugin
from os import listdir
from os.path import isfile, join
import random
from PIL import Image, ImageOps
import logging

log = logging.getLogger(__name__)

class ImageFolder(BasePlugin):
    def generate_image(self, settings, device_config):
        folder_path = settings.get('path')
        orientation = device_config.get_config("orientation")
        folder_path = folder_path + "/" + orientation
        
        if not folder_path:
            raise RuntimeError("Folder path is required.")

        dimensions = device_config.get_resolution()
        chosen_pics = set(settings.get("chosen_pics", []))
        
        files = {f"{folder_path}/{f}" for f in listdir(folder_path) if isfile(join(folder_path, f))}
        files = files - chosen_pics
        
        if not files:
            files = chosen_pics
            chosen_pics.clear()
            
        file = random.choice(list(files))
        chosen_pics.add(file)
        settings["chosen_pics"] = list(chosen_pics)
        
        img = ImageFolder.resize_with_padding(file, dimensions)
        
        if not img:
            raise RuntimeError("Failed to load image, please check logs.")
            
        return img

    @staticmethod
    def resize_with_padding(path:str, size: tuple) -> Image:
        log.info(f"Loading picture: {path}")
        
        with Image.open(path) as img:
            n_dom_colors = 1
            colors = img.quantize(colors=4, kmeans=4).convert('RGB')
            dom_colors = sorted(colors.getcolors(2 ** 24), reverse=True)[:n_dom_colors]
            img = ImageOps.pad(img, size, Image.Resampling.BICUBIC, dom_colors[0][1])
            
            log.info("Picture loaded and padded")
            return img