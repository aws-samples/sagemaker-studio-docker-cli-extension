import botocore
import logging as log
import boto3
import requests
import json
import time
import os
from config import get_home, ReadFromFile, UnhandledError
from bootstrap import generate_bootstrap_script

log_cmd = f" &>> {get_home()}/.sagemaker_studio_docker_cli/sdocker.log"
retry_wait = 5
timeout = 720
max_retries = 720 // retry_wait

def ping_host(home, instance_type, instance_id, dns, port, retry=True):
    """
    Check Docker host health by requesting /version from docker daemon on host
    """
    try:
        log.info(f"Pinging {dns}")
        path_to_cert = f"{home}/.sagemaker_studio_docker_cli/{instance_type}_{instance_id}/certs/"
        cert=(path_to_cert + "client/cert.pem", path_to_cert + "client/key.pem")
        response = json.loads(requests.get(f"https://{dns}:{port}/version", cert=cert, verify=path_to_cert + "ca/cert.pem").content.decode("utf-8"))
        log.info(f"DockerHost {dns} is healthy!")
        return (True, None)
    except Exception as error:
        if retry:
            log.error(f"Failed to reach {dns}:{port}, retrying in {retry_wait}s")
        else:
            log.error(f"Failed to reach {dns}:{port}, with error message {error.message}")
        return (False, error)


class Commands():
    """
    Class for sagemaker_studio_docker_cli commands
    """
    def __init__(self, args, config):
        """
        Create ec2 client and passes args and config
        """
        commands = {
            "create-host": self.create_host,
            "terminate-current-host": self.terminate_current_host,
            "terminate-host": self.terminate_host
        }
        self.ec2_client = boto3.client("ec2", region_name=config["Region"])
        self.args = args
        self.config = config
        commands[self.args.func]()


    def create_sg(self, name, desc, source_sg, from_port, to_port, revoke_egress=False):
        """
        Creates security group if not found in VPC
        """
        sg_exist = False
        log.info(f"Checking {name} security group exists")
        try:
            check_response= self.ec2_client.describe_security_groups(
                Filters=[
                    {
                        "Name": "group-name",
                        "Values": [name]
                    },
                    {
                        "Name": "vpc-id",
                        "Values": [self.config["VpcId"]]
                    }
                ]
            )
            if len(check_response['SecurityGroups']) > 0:
                sg_exist = True
                log.info(f"Found {name} security group {check_response['SecurityGroups'][0]['GroupId']}")
            else:
                log.info(f"Security group {name} not found")
        except botocore.exceptions.ClientError as error:
            if error.response["Error"]["Code"] == "InvalidGroup.NotFound":
                log.info(f"Security group {name} not found, 'ClientError' was raised")
                sg_exist = False
            else:
                UnhandledError(error)
        except Exception as error:
            UnhandledError(error)
                
        if not sg_exist:
            log.info(f"Creating {name} security group")
            try:
                response = self.ec2_client.create_security_group(
                    Description=desc,
                    GroupName=name,
                    VpcId=self.config["VpcId"]
                )
                if revoke_egress:
                    revoke_response = self.ec2_client.revoke_security_group_egress(
                        GroupId=response["GroupId"],
                        IpPermissions=[
                            {
                                "IpProtocol": "-1",
                                "IpRanges": [
                                    {
                                        "CidrIp": "0.0.0.0/0"
                                    }
                                ]
                            }
                        ]
                    )
                    rule_response = self.ec2_client.authorize_security_group_egress(
                    GroupId=response["GroupId"],
                        IpPermissions=[
                            {
                                "FromPort": from_port,
                                "IpProtocol": 'tcp',
                                "ToPort": to_port,
                                "UserIdGroupPairs": [
                                    {
                                        "Description": desc,
                                        "GroupId": response["GroupId"] if source_sg=="self" else source_sg,
                                    },
                                ],
                            },
                        ]
                    )
                rule_response = self.ec2_client.authorize_security_group_ingress(
                    GroupId=response["GroupId"],
                    IpPermissions=[
                        {
                            "FromPort": from_port,
                            "IpProtocol": 'tcp',
                            "ToPort": to_port,
                            "UserIdGroupPairs": [
                                {
                                    "Description": desc,
                                    "GroupId": response["GroupId"] if source_sg=="self" else source_sg,
                                },
                            ],
                        },
                    ]
                )                
                log.info(f"Security Group id: {response['GroupId']}")
            except botocore.exceptions.ClientError as error:
                if error.response["Error"]["Code"] != "InvalidGroup.Duplicate":
                    UnhandledError(error)
            except Exception as error:
                UnhandledError(error)
            sg = response["GroupId"]
        else:
            sg = check_response['SecurityGroups'][0]["GroupId"]
        return sg


    def prepare_efs(self, sg):
        """
        Adds mount target to EFS
        """
        if sg not in self.config["MountTargetSecurityGroups"]:
            try:
                response = self.config["EFSClient"].modify_mount_target_security_groups(
                    MountTargetId=self.config["MountTargetId"],
                    SecurityGroups=[*self.config["MountTargetSecurityGroups"], sg]
                )
            except Exception as error:
                UnhandledError(error)
    
    def terminate_host(self):
        instance_id = self.args.instance_id
        try:
            response = self.ec2_client.terminate_instances(
                InstanceIds=[instance_id]
            )
        except Exception as error:
            UnhandledError(error)
        finally:
            log.info("Running OS level command:")            
            os.system(f"docker context use default" + log_cmd)
            os.system(f'docker context rm `docker context list -q | grep "{instance_id}"`' + log_cmd)


    def terminate_current_host(self, instance_id=None):
        """
        Terminate Docker Host command
        """
        home = get_home()
        sdocker_host_filename = f"{home}/.sagemaker_studio_docker_cli/sdocker-hosts.conf"
        try:
            if not instance_id:
                sdocker_host_config = ReadFromFile(sdocker_host_filename)
                instance_id = sdocker_host_config["ActiveHosts"][0]["InstanceId"]
            response = self.ec2_client.terminate_instances(
                InstanceIds=[instance_id]
            )
        except Exception as error:
            UnhandledError(error)
        finally:
            log.info("Running OS level command:")             
            os.system(f"docker context use default" + log_cmd)
            os.system(f'docker context rm `docker context list -q | grep "{instance_id}"`' + log_cmd)
        instance_id = sdocker_host_config["ActiveHosts"][0]["InstanceId"]
        instance_dns = sdocker_host_config["ActiveHosts"][0]["InstanceDns"]
        print(f"Successfully terminated instance {instance_id} with private DNS {instance_dns}")
        log.info(f"Successfully terminated instance {instance_id} with private DNS {instance_dns}")

    def read_custom_script(self, script_path):
        with open(script_path, "rb") as script:
            readlines = script.readlines()
            if readlines[0].decode().startswith("#!"):
                readlines = readlines[1:]

            return b"".join(readlines).decode().replace("\n", "\n    ")

    def create_host(self):
        """
        Create Docker Host command
        """
        home = get_home()
        port = self.config["Port"]
        if self.args.subnet_id:
            if self.args.subnet_id in self.config["SubnetIds"]:
                self.config["SubnetId"] = self.args.subnet_id
            else:
                message = f"InvalidSubnetId: {self.args.subnet_id} is either invalid subnet id or not part of {self.config['VpcId']}"
                log.error(message)
                raise ValueError(message)
        else:
            self.config["SubnetId"] = self.config["SubnetIds"][0]
        
        docker_sg = self.config["HostSGs"]
        if len(docker_sg) == 0:
            docker_sg = [self.create_sg(
                "DockerHost",
                "Docker host security group",
                self.config["SecurityGroups"][0],
                0,
                65535
            )]
        efs_sg = self.create_sg(
            "EFSDockerHost",
            "EFS security group used with Docker host",
            "self",
            2049,
            2049,
            revoke_egress=True
        )
        self.prepare_efs(efs_sg)
        docker_image_name = self.config["DockerImageURI"]
        gpu_option = ""
        if "GpuInfo" in self.ec2_client.describe_instance_types(InstanceTypes=[self.args.instance_type])['InstanceTypes'][0].keys():
            # https://stackoverflow.com/a/71866959/18516713
            docker_image_name = self.config["DockerImageNvidiaURI"]
            gpu_option = "--gpus all"

        pre_bootstrap_script = self.read_custom_script(f"{home}/.sagemaker_studio_docker_cli/pre-bootstrap.sh")
        create_certs = self.read_custom_script(
            f"{home}/sagemaker-studio-docker-cli-extension/src/sagemaker_studio_docker_cli/create_certs.sh"
        )
        post_bootstrap_script = self.read_custom_script(f"{home}/.sagemaker_studio_docker_cli/post-bootstrap.sh")
        additional_ports = self.config["AdditionalPorts"]

        bootstrap_script = generate_bootstrap_script(
            home,
            self.config['EfsIpAddress'], 
            port, 
            self.config['UserUid'], 
            gpu_option, 
            docker_image_name, 
            pre_bootstrap_script, 
            post_bootstrap_script, 
            create_certs,
            additional_ports
        )

        args = {}
        args["ImageId"] = self.config["ImageId"]
        args["InstanceType"] = self.args.instance_type
        if self.config["Key"]:
            args["KeyName"] = self.config["Key"]
        args["SecurityGroupIds"] = docker_sg + [efs_sg]
        args["SubnetId"] = self.config["SubnetId"]
        args["MinCount"] = 1
        args["MaxCount"] = 1
        args["UserData"] = bootstrap_script
        args["BlockDeviceMappings"] = [
                {
                    "DeviceName": "/dev/xvda",
                    "Ebs": {
                        "VolumeSize": self.config["EBSVolumeSize"]
                    }
                }
            ]
        if self.config["InstanceProfileArn"]:
            args["IamInstanceProfile"] = {
                "Arn": self.config["InstanceProfileArn"]
            }
        self.config["Tags"].append({"Key": "Name", "Value": "DockerHost"})
        args["TagSpecifications"] = [{"Tags": self.config["Tags"], "ResourceType": "instance"}]
        try:
            response = self.ec2_client.run_instances(**args)
        except Exception as error:
            UnhandledError(error)
        instance_id = response['Instances'][0]['InstanceId']
        instance_dns = response['Instances'][0]['PrivateDnsName']
        log.info(f"Successfully launched instance {instance_id} with private DNS {instance_dns}")
        print(f"Successfully launched DockerHost on instance {instance_id} with private DNS {instance_dns}")
        print("Waiting on docker host to be ready")
        IsHealthy = (False, "")
        retries = 0
        while not IsHealthy[0] and retries < max_retries:
            time.sleep(retry_wait)
            IsHealthy = ping_host(home, self.args.instance_type, instance_id, instance_dns, port)
            retries += 1

        if not IsHealthy[0]:
            print("Failed to establish connection with docker daemon on DockerHost instance. Terminating instance")
            log.error("Failed to establish connection with docker daemon on DockerHost instance. Terminating instance")
            log.error(f"Not able to reach docker daemon on host: {IsHealthy[1]}")
            self.terminate_current_host(instance_id)

        assert IsHealthy[0], "Aborting."

        print("Docker host is ready!")
        active_host = {
            "ActiveHosts": [
                {
                    "InstanceId": instance_id,
                    "InstanceDns": instance_dns,
                    "Port": port,
                    "InstanceType": self.args.instance_type
                }
            ]
        }
        home = get_home()
        try:
            with open(f"{home}/.sagemaker_studio_docker_cli/sdocker-hosts.conf", "w") as file:
                json.dump(active_host, file)
            create_context_command = f"docker context create {self.args.instance_type}_{instance_id}" \
                + f" --docker host=tcp://{instance_dns}:{port}" \
                + f",ca={home}/.sagemaker_studio_docker_cli/{self.args.instance_type}_{instance_id}/certs/ca/cert.pem" \
                + f",cert={home}/.sagemaker_studio_docker_cli/{self.args.instance_type}_{instance_id}/certs/client/cert.pem" \
                + f",key={home}/.sagemaker_studio_docker_cli/{self.args.instance_type}_{instance_id}/certs/client/key.pem"
            log.info(f"Running OS level command: {create_context_command}{log_cmd}") 
            os.system(create_context_command + log_cmd)
            exit_code = -1
            retry_count = 0
            max_retry = 5
            time.sleep(2)
            while exit_code != 0 and retry_count < max_retry:
                log.info(f"Running OS level command: docker context use {self.args.instance_type}_{instance_id}{log_cmd}") 
                exit_code = os.system(f"docker context use {self.args.instance_type}_{instance_id}" + log_cmd)
                log.info(f"Exit code for above command: {exit_code}")
                if exit_code != 0:
                    log.error("Unable to switch context, retrying....")
                    time.sleep(1)
                retry_count += 1
        except Exception as error:
            UnhandledError(error)
        return instance_id, instance_dns, port
