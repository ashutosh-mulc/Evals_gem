import requests
import time
import base64
from tkinter import Tk, Label
from PIL import Image, ImageTk
from io import BytesIO
import sys
import json
import subprocess


class ImageDisplayClient:
    """
    A client to fetch and display images from a server using a GUI.

    Attributes:
        server_url (str): URL of the server providing commands.
        root (Tk): Tkinter root window.
        label (Label): Tkinter label to display the image.
        image_displayed (bool): Flag indicating if an image is currently displayed.
    """

    def __init__(self, server_url):
        """
        Initializes the client and GUI.

        Args:
            server_url (str): URL to fetch commands from.
        """
        self.server_url = server_url
        self.root = Tk()
        self.root.attributes("-fullscreen", True)
        self.label = Label(self.root)
        self.label.pack()
        self.image_displayed = False

    def fetch_command(self):
        """
        Fetches a command from the server.

        Returns:
            dict: Command data if successful, None otherwise.
        """
        try:
            print(f"{self.server_url}/get_image")
            response = requests.get(f"{self.server_url}/get_image")
            return response.json()
        except Exception as e:
            print(f"Error fetching command: {e}")
            return None

    def display_image(self, image_data):
        """
        Displays a base64-encoded image in the GUI.

        Args:
            image_data (str): Base64-encoded image data.
        """

        screen_width = self.root.winfo_screenwidth() #1900
        screen_height = self.root.winfo_screenheight() #1000

        print("screen_width:", screen_width)
        print("screen_height:", screen_height)
        # Decode the image data
        image_bytes = base64.b64decode(image_data)
        #screen_width, screen_height = 1920, 1080
        base_image = Image.open(BytesIO(image_bytes))
        image = Image.new("RGB", (screen_width, screen_height), (0, 0, 0))

        image_width = 1440;
        image_height = screen_height - 40
        #base_image = base_image.resize((image_width, image_height), Image.LANCZOS)
        # Step 3: Paste the 1080x1080 image in the center
        x_offset = (screen_width - image_width) // 2
        y_offset = (screen_height - image_height) // 2
        base_image = base_image.resize((image_height, image_width), Image.LANCZOS)


        base_image = base_image.rotate(90, expand=True)
        image.paste(base_image, (x_offset, y_offset))

        photo = ImageTk.PhotoImage(image)

        self.label.config(image=photo)
        self.label.image = photo
        self.label.pack()

        self.root.geometry(f"{screen_width}x{screen_height}+0+0")
        self.image_displayed = True
        # Keep the image displayed for 30 seconds
        self.root.after(3000000000000, self.hide_image)


    def hide_image(self):
        """
        Clears the displayed image and resets the GUI.
        """
        self.label.config(image="")
        self.label.image = None
        self.image_displayed = False

    def run(self):
        """
        Main loop to fetch commands and update the GUI.
        """
        while True:
            try:
                command = self.fetch_command()
                if command:
                    if command["action"] == "show" and not self.image_displayed:
                        self.display_image(command["image_data"])
                    elif command["action"] == "stop" and self.image_displayed:
                        self.hide_image()
                self.root.update()
                self.root.bind_all("<Escape>", lambda e: self.root.destroy())
                time.sleep(1)
            except KeyboardInterrupt:
                exit(1)
            except:
                print("[Cool]")
                continue

display_client_ip = sys.argv[1]
if __name__ == "__main__":
    #send_image()
    client = ImageDisplayClient(display_client_ip)
    client.run()
