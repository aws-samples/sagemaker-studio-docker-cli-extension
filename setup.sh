#!/bin/bash

set -ex

mkdir -p ~/.sagemaker_studio_docker_cli

PRE_BOOTSTRAP_SCRIPT="$HOME/.sagemaker_studio_docker_cli/pre-bootstrap.sh"
if [[ ! -f "$PRE_BOOTSTRAP_SCRIPT" ]]; then
    echo "$PRE_BOOTSTRAP_SCRIPT does not exists."
    touch $PRE_BOOTSTRAP_SCRIPT

    cat <<EOT >> $PRE_BOOTSTRAP_SCRIPT
#!/bin/bash
# This script will execute before the rest of the bootstrap script.
# ie. private docker registry login
EOT

fi

POST_BOOTSTRAP_SCRIPT="$HOME/.sagemaker_studio_docker_cli/post-bootstrap.sh"
if [[ ! -f "$POST_BOOTSTRAP_SCRIPT" ]]; then
    echo "$POST_BOOTSTRAP_SCRIPT does not exists."
    touch $POST_BOOTSTRAP_SCRIPT

    cat <<EOT >> $POST_BOOTSTRAP_SCRIPT
#!/bin/bash
# This script will execute after the rest of the bootstrap script.
# ie. clean up temporary files
EOT

fi

if [[ `command -v /usr/bin/sdocker` == "" ]]
then
    if [[ $EUID != 0 ]]
    then
        sudo ln -s $PWD/src/sagemaker_studio_docker_cli/sdocker /usr/bin/sdocker
        if [[ ! -x  "$PWD/src/sagemaker_studio_docker_cli/sdocker" ]]
        then
            sudo chmod +x $PWD/src/sagemaker_studio_docker_cli/sdocker
        fi
    else
        ln -s $PWD/src/sagemaker_studio_docker_cli/sdocker /usr/bin/sdocker
        if [[ ! -x  "$PWD/src/sagemaker_studio_docker_cli/sdocker" ]]
        then
            chmod +x $PWD/src/sagemaker_studio_docker_cli/sdocker
        fi
    fi
fi

if [[ `command -v docker` == "" ]]
then
    if [[ "$(. /etc/os-release && echo "$ID")" == "amzn" ]]
    then
        sudo yum update -y && sudo yum upgrade -y
        if [[ "$(. /etc/os-release && echo "$VERSION")" == "2" ]]
        then
            sudo -u root bash -l -c 'sudo amazon-linux-extras install docker'            
        else
            sudo yum install -y docker
        fi
    else
        wget https://get.docker.com/ -O installer.sh
        chmod +x installer.sh
        ./installer.sh
    fi
    if [[ `command -v docker` == "" ]]
    then
        echo "docker not installed, please refer on how to install docker CLI (https://docs.docker.com/get-docker/)."
        exit 1
    fi
fi

if [[ `command -v docker-compose` == "" ]]
then
    echo "Installing docker-compose ..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi

mkdir -p ~/.sagemaker
echo -e "local:\n    container_root: $HOME/temp" > ~/.sagemaker/config.yaml
mkdir -p ~/temp

/opt/conda/bin/python3 -m pip install "sagemaker>=2.80.0"
