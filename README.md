# Disinfo!

![Simulated Info Demo](assets/disinfo-export.gif)

Note that this repo is actively being developed over various weekends. It may be drastically different tomorrow.

Lots of things are currently undocumented and unstable.

Connections:

- Homeassistant (over MQTT)
- Pirate Weather
- Numbers API
- IDFM (Paris Metro)

Hardware:

- 2x HUB75 RGB LED Matrix 64x64
- Raspberry Pi (3B+ or better)
- Interface to connect the matrix to GPIOs
- Power Supply

Refer to rgb-led-matrix library for details.

Notes:

- Upgrade pillow (apt is too old) via `pip install --upgrade pillow`


Licenses:

- Tamzen
- Scientifica
- Pixel Operator

(todo: Attributions)


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
