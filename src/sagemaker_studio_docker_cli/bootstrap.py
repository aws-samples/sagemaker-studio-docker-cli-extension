def generate_bootstrap_script(home, efs_ip_address, port, user_uid, gpu_option, docker_image_name, pre_bootstrap, post_bootstrap, create_certs):
    bootstrap_script = f"""Content-Type: multipart/mixed; boundary="//"
MIME-Version: 1.0

--//
Content-Type: text/cloud-config; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Content-Disposition: attachment; filename="cloud-config.txt"

#cloud-config
cloud_final_modules:
- [scripts-user, always]

--//
Content-Type: text/x-shellscript; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Content-Disposition: attachment; filename="userdata.txt"

#!/bin/bash
set -x
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

    {pre_bootstrap}

    echo "Mounting EFS to /root"
    
    sudo mkdir -p /root
    sudo mount -t nfs \
    -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 \
    {efs_ip_address}:/{user_uid} \
    /root
    
    sudo mkdir -p /home/sagemaker-user
    sudo mount -t nfs \
    -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 \
    {efs_ip_address}:/{user_uid} \
    /home/sagemaker-user
    
    {create_certs}
    
    TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 3600")
    
    instance_type=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-type)
    instance_id=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
        
    if ( ! [[ "{home}" == "/home/sagemaker-user" ]] || [[ "{home}" == "/root" ]] )
    then
        sudo mkdir -p {home}
        sudo mount -t nfs \
        -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 \
        {efs_ip_address}:/{user_uid} \
        {home}

        CERTS={home}/.sagemaker_studio_docker_cli/${{instance_type}}_${{instance_id}}
        
        mkdir -p $CERTS/certs
        
        _tls_generate_certs "$CERTS/certs"

        chown -R {user_uid}:1001 $CERTS
        
        sudo -u ec2-user docker run -d \
        -p {port}:2376 \
        -p 8080:8080 {gpu_option} \
        -v /root:/root \
        -v /home/sagemaker-user:/home/sagemaker-user \
        -v $CERTS/certs:/certs \
        -v {home}:{home} \
        --privileged \
        --name dockerd-server \
        -e DOCKER_TLS_CERTDIR="/certs" {docker_image_name} \
        dockerd --tlsverify --tlscacert=/certs/ca/cert.pem --tlscert=/certs/server/cert.pem --tlskey=/certs/server/key.pem -H=0.0.0.0:2376
    else
        CERTS=/root/.sagemaker_studio_docker_cli/${{instance_type}}_${{instance_id}}
        mkdir -p $CERTS/certs

        _tls_generate_certs "$CERTS/certs"
        
        chown -R {user_uid}:1001 $CERTS
        
        sudo -u ec2-user docker run -d \
        -p {port}:2376 \
        -p 8080:8080 {gpu_option} \
        -v /root:/root \
        -v /home/sagemaker-user:/home/sagemaker-user \
        -v $CERTS/certs:/certs \
        --privileged \
        --name dockerd-server \
        -e DOCKER_TLS_CERTDIR="/certs" {docker_image_name} \
        dockerd --tlsverify --tlscacert=/certs/ca/cert.pem --tlscert=/certs/server/cert.pem --tlskey=/certs/server/key.pem -H=0.0.0.0:2376
    fi
    
    {post_bootstrap}

--//--"""

    return bootstrap_script