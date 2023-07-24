#!/bin/bash
sudo apt update
sudo apt install git -y

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
	else
		echo "Ref $ref received. Doing nothing: only the ${BRANCH} branch may be deployed on this server."
	fi
done
EOF
chmod +x ~/_disinfo.git/hooks/post-receive

echo "=> Setup of git repo complete. Pulling the default branch."

cd ~/disinfo
git clone https://github.com/prashnts/disinfo.git .

cat << 'EOF' > ~/disinfo/disinfo/config.py
# Pirate Weather
pw_api_key = 'x'
pw_unit = 'ca'  # ca: SI units with kmph for wind.
# Latitude and Longitude of the location
pw_latitude = 48.8
pw_longitude = 2.3

# Homeassistant MQTT
ha_base_url = '10.0.1.207:8123'
ha_mqtt_host = '10.0.1.207'
ha_mqtt_port = 1883
ha_mqtt_username = 'x'
ha_mqtt_password = 'x'

# Quirks
mqtt_btn_latch_t = 300

# idf mobilité
idfm_api_key = 'x'

# Matrix config
# Represents combined panels
matrix_w = 128
matrix_h = 64

timezone = 'Europe/Paris'
EOF

echo "=> Setting up rpi-rgb-matrix"

cd ~
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd rpi-rgb-led-matrix
sudo apt-get install python3-dev python3-pillow -y
make build-python PYTHON=$(command -v python3)
sudo make install-python PYTHON=$(command -v python3)

echo "=> Installing python dependencies"

cd ~/disinfo
sudo pip install -r requirements.txt

echo "=> Installing services"
sudo apt install supervisor -y

sudo ln -s /home/pi/disinfo/config/*.conf /etc/supervisor/conf.d

sudo supervisorctl update
sudo supervisorctl start didataservice
sudo supervisorctl start dihaservice
sudo supervisorctl start direnderer
sudo supervisorctl start diserver
