# Disinfo!

![Simulated Info Demo](assets/disinfo-export.gif)

Note that this repo is actively being developed over various weekends. It may be drastically different tomorrow.

Lots of things are currently undocumented and unstable.

Connections:

- Homeassistant (over Websocket (ongoing))
- Numbers API
- IDFM (Paris Metro)
- Kagi News

Hardware:

- 6x HUB75 RGB LED Matrix 64x64
- Raspberry Pi 4B
- Adafruit Matrix Bonnet
- Interface to connect the matrix to GPIOs
- Power Supply

Refer to rgb-led-matrix library for details.

Notes:

- We use `uv` as the package manager. Additional dependencies for cairo and others would require system packages.
- A demo/dev script is available to start the whole stack:
    `uv run maindev.py`
- The following command also sets up an auto-reload dev env:
    `uv run watchmedo auto-restart -d disinfo -d clients -d assets --patterns="*.py"  --recursive -- uv run maindev.py`
- The websocket client in clients/ dir is what runs on the Raspberry Pi. A supervisor config handles runtime.
- We use [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) to communicate with the panels, and there is a vast documentation available there.
- Fonts are collected from various sources and accompany the licenses.


HUB75 Connections to Pi

```
MATRIX  PIN       GPIO
strobe  7         4
clock   11        17

G1      13        27
G2      21        9
R1      23        11
R2      24        8
B1      26        7
B2      19        10

A       15        22
B       16        23
C       18        24
D       22        25
E       10        15

OE      12        18
```


Log2RAM
https://github.com/azlux/log2ram
```
echo "deb [signed-by=/usr/share/keyrings/azlux-archive-keyring.gpg] http://packages.azlux.fr/debian/ bullseye main" | sudo tee /etc/apt/sources.list.d/azlux.list
sudo wget -O /usr/share/keyrings/azlux-archive-keyring.gpg  https://azlux.fr/repo.gpg
sudo apt update
sudo apt install log2ram
```


[notes] Setup RPI from scratch

- Assuming a fresh minimal install.
- Set `isolcpus=3` in cmdline.txt at the end.
- Set `dtparam=audio=off` in config.txt


- check disk speed with `sudo hdparm -Tt /dev/sda` (install hdparm first)
- with dd `dd if=/dev/zero of=/tmp/output bs=8k count=10k; rm -f /tmp/output`


### macOS Setup

- Install pyenv, redis, libsixel, cairo from brew.
- Ensure libsixel can be found -- `sudo ln -s /opt/homebrew/lib /usr/local/lib` -- on macos with apple silicon

- `watchmedo auto-restart -d disinfo -d assets --patterns="*.py;*.png;*.bdf;*.ttf" --recursive -- python -m disinfo.renderers.sixel --fps 42`

- `uvicorn disinfo.web.server:app --host 0.0.0.0 --port 4200 --reload` -- run a local server showing the screen.
- `watchmedo auto-restart -d disinfo -d assets --patterns="*.py;*.png;*.bdf;*.ttf" --recursive -- python -m disinfo.renderers.background --fps 25` -- to feed the webpage.