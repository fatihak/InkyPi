
# Mounting a shared folder 

This are instructions on how to mount a shared folder on Pi OS. This allows the image_folder plugin to pull images from an local directory thats mounted to a network folder.

1. Install the required linux package
    ``` sudo apt install cifs-utils ```
2. Find your uid
    ``` id 
    uid=1000(pi-ink)
    ```
3. Example usage for temporary a mount
    ```
    sudo mount -t cifs -o username=MY_USER,password=MY_PASSWORD,uid=MY_UID //SERVER_IP/SHARED_FOLDER  LOCAL_PATH
    sudo mount -t cifs -o username=pi-ink,password=pass123,uid=1000 //192.168.50.123/Media/Pictures/ ~/Pictures
    ```
4. Create a credentials file with your actual credentials (Optional)
    ``` sudo nano /root/.CRED_FILENAME
    username=MY_USER
    password=MY_PASSWORD
    ```

5. Open the fstab
    ``` sudo nano /etc/fstab ```

5. Permanent automatic mounting on boot (with a credentials file)
    ```
    Add the following line at the end of the file
    //SERVER_IP/SHARED_FOLDER        LOCAL_PATH            cifs credentials=/root/.CRED_FILENAME,uid=MY_UID 0 0
    Example line to add
    //192.168.50.123/Media/Pictures/ /home/pi-ink/Pictures cifs credentials=/root/.smb_nas,uid=1000 0 0
    ```
5. Permanent automatic mounting on boot (without a credentials file)
    ```
    Add the following line at the end of the file
    //SERVER_IP/SHARED_FOLDER        LOCAL_PATH            cifs username=MY_USER,password=MY_PASSWORD,uid=MY_UID 0 0
    Example line to add
    //192.168.50.123/Media/Pictures/ /home/pi-ink/Pictures cifs username=pi-ink,password=pass123,uid=1000 0 0
    ```
