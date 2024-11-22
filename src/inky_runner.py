import urllib.request
import os,random,time,signal
from datetime import datetime, timedelta
from flask import Flask, flash, request, redirect, url_for,render_template
from inky.auto import auto
from PIL import ImageDraw,Image
from inky_ai import InkyAI
import shutil
import uuid

import warnings
warnings.filterwarnings("ignore")

print("Starting web server")
app = Flask(__name__)

print("Connecting to inky display")
inky_display = auto()
inky_display.set_border(inky_display.BLACK)
print(f"Resolution {inky_display.resolution}")

inky_ai = InkyAI()

latest_request_time = datetime.now() - timedelta(minutes=1)
current_image_prompt = ""
current_image_file = os.path.join("src","static","current_image.png")

def resize_image(image, desired_size):
    desired_width, desired_height = desired_size
    desired_ratio = desired_width / desired_height
    img_width, img_height = image.size
    img_ratio = img_width / img_height
    x_offset, y_offset = 0,0
    # Step 1: Determine crop dimensions
    if img_ratio > desired_ratio:
        # Image is wider than desired aspect ratio
        new_width = int(img_height * desired_ratio)
        new_height = img_height
        x_offset = (img_width - new_width) // 2
    else:
        # Image is taller than desired aspect ratio
        new_width = img_width
        new_height = int(img_width / desired_ratio)
        y_offset = (img_height - new_height) // 2

    # Step 2: Crop the image
    cropped_image = image.crop((x_offset, y_offset, x_offset + new_width, y_offset + new_height))

    # Step 3: Resize to the exact desired dimensions (if necessary)
    return cropped_image.resize((desired_width, desired_height), Image.LANCZOS)

def display_image(filename):
    print(f"Displaying image {filename}")
    with Image.open(filename) as img:
        # resize image to display resolution
        img = resize_image(img, inky_display.resolution)

        inky_display.set_image(img)
        inky_display.show()

def generate_image(self, prompt, image_dir, test=True):
    urllib.request.urlretrieve(image_url, image_dir)

@app.route('/', methods=['GET', 'POST'])
def root_request():
    global latest_request_time, current_image_prompt, current_image_file
    print('Received new request!')
    if request.method == 'POST':
        print('Got POST request!')
        current_time = datetime.now()
        time_difference = current_time - latest_request_time
        if time_difference >= timedelta(minutes=1):
            image_updated = False
            if "inputText" in request.form:
                # if text provided
                try:
                    prompt = request.form.getlist("inputText")[0]
                    inky_ai.generate_image(prompt,current_image_file, test=False)
                    display_image(current_image_file)
                    image_updated = True
                except Exception as e:
                    print("Failed to process prompt: " + e)
            elif "imageFile" in request.files:
                # if image provided
                image_file = request.files["imageFile"]
                image_file.save(current_image_file)
                display_image(current_image_file)
                image_updated = True
            elif "action" in request.form and request.form.get("action") == "generate_random_image":
                try:
                    prompt = inky_ai.get_image_prompt()
                    inky_ai.generate_image(prompt,current_image_file, test=False)
                    display_image(current_image_file)
                    image_updated = True
                except Exception as e:
                    print("Failed to process prompt: " + e)
            elif "action" in request.form and request.form.get("action") == "save_image":
                image_id = str(uuid.uuid4())
                image_path = os.path.join("src","static", "saved_images", f"{image_id}.png")
                print(f"LIKE BUTTON RECIEVED: SAVING TO {image_path}")
                shutil.copy(current_image_file, image_path)
            else:
                print("Recieved unhandled request: "+ request.form)
            if image_updated:
                latest_request_time = current_time
        else:
            print("Image has been updated within 1 minute, skipping.")

    return render_template('main.html', current_image='current_image.png')
if __name__ == '__main__':
    app.secret_key = str(random.randint(100000,999999))
    app.run(host="0.0.0.0",port=80)
