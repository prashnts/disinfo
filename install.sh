#!/bin/bash
sudo apt update
sudo apt install git redis -y

# Setting up the repo

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
        echo "=> Restarting services"
        sudo supervisorctl restart all
        echo "=> Deployed!"
	else
		echo "Ref $ref received. Doing nothing: only the ${BRANCH} branch may be deployed on this server."
	fi
done
EOF
chmod +x ~/_disinfo.git/hooks/post-receive

echo "=> Setup of git repo complete. Pulling the default branch."

cd ~/disinfo
git clone https://github.com/prashnts/disinfo.git .

cat << 'EOF' > ~/disinfo/.config.json
{
    "pw_api_key": "x",
    "pw_unit": "ca",
    "ha_base_url": "10.0.1.207:8123",
    "ha_mqtt_host": "10.0.1.207",
    "ha_mqtt_port": 1883,
    "ha_mqtt_username": "x",
    "ha_mqtt_password": "x",
    "idfm_api_key": "x",
    "latitude": 48.2,
    "longitude": 2.1,
    "timezone": "Europe/Paris",
    "width": 64,
    "height": 64,
    "name": "picowpanel"
}

EOF

echo "=> Setting up rpi-rgb-matrix"

cd ~
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd rpi-rgb-led-matrix
sudo apt-get install python3-dev python3-pillow python3-pip cython3 -y
make build-python PYTHON=$(command -v python3)
sudo make install-python PYTHON=$(command -v python3)

echo "=> Disable onboard sound"

cat <<EOF | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf
blacklist snd_bcm2835
EOF

sudo update-initramfs -u

echo "=> Installing python dependencies"

sudo apt install libcairo2-dev pkg-config -y

cd ~/disinfo
sudo pip install -r requirements.txt

# Quirk, this does not upgrade pillow.
sudo pip install --upgrade pillow

echo "=> Installing services"
sudo apt install supervisor -y

sudo ln -s /home/pi/disinfo/config/di_haservice.conf /etc/supervisor/conf.d
sudo ln -s /home/pi/disinfo/config/di_dataservice.conf /etc/supervisor/conf.d
# sudo ln -s /home/pi/disinfo/config/di_renderer.conf /etc/supervisor/conf.d
sudo ln -s /home/pi/disinfo/config/di_server.conf /etc/supervisor/conf.d
sudo ln -s /home/pi/disinfo/config/di_pico_udp_renderer.conf /etc/supervisor/conf.d
sudo ln -s /home/pi/disinfo/config/di_3dp_udp_renderer.conf /etc/supervisor/conf.d
sudo ln -s /home/pi/disinfo/config/di_salon_udp_renderer.conf /etc/supervisor/conf.d

sudo supervisorctl update
sudo supervisorctl start didataservice
sudo supervisorctl start dihaservice
# sudo supervisorctl start direnderer
sudo supervisorctl start diserver
sudo supervisorctl start di3dp
sudo supervisorctl start disalon

echo "=> Installation complete. Adding extras"

echo "deb [signed-by=/usr/share/keyrings/azlux-archive-keyring.gpg] http://packages.azlux.fr/debian/ bullseye main" | sudo tee /etc/apt/sources.list.d/azlux.list
sudo wget -O /usr/share/keyrings/azlux-archive-keyring.gpg  https://azlux.fr/repo.gpg
sudo apt update
sudo apt install log2ram -y

sudo apt install neovim zsh -y

sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
