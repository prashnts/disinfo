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

Local git push helper:
https://gist.github.com/noelboss/3fe13927025b89757f8fb12e9066f2fa

```bash
mkdir ~/disinfo  # Where we'd deploy the working copy
git init --bare ~/_disinfo.git
# Add git hook
cat << 'EOF' > ~/_disinfo.git/hooks/post-receive
#!/bin/bash
TARGET="/home/pi/disinfo"
GIT_DIR="/home/pi/_disinfo.git"
BRANCH="master"

while read oldrev newrev ref
do
	# only checking out the master (or whatever branch you would like to deploy)
	if [ "$ref" = "refs/heads/$BRANCH" ];
	then
		echo "Ref $ref received. Deploying ${BRANCH} branch to production..."
		git --work-tree=$TARGET --git-dir=$GIT_DIR checkout -f $BRANCH
	else
		echo "Ref $ref received. Doing nothing: only the ${BRANCH} branch may be deployed on this server."
	fi
done
EOF
chmod +x ~/_disinfo.git/hooks/post-receive

```
