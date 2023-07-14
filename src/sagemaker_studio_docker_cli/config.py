import os
import json
import boto3
import logging as log

def get_home():
    """
    Function to determine system home folder
    """
    home = os.getenv("HOME")
    if home=="" or home==None:
        home = "/home/sagemaker-user"
    return home


def ReadFromFile(filename, report_err=True):
    """
    Function to read data from json files
    """
    try:
        with open(filename, "r") as meta_file:
            data = json.load(meta_file)
        return data
    except FileNotFoundError:
        if report_err:
            log.error(f"File {filename} not found")
        else:
            log.info(f"File {filename} not found")
        raise FileNotFoundError(f"File {filename} not found")
    except Exception as error:
        UnhandledError(error)

class ReadConfig():
    def __init__(self):
        """
        Prepare configuration based on Studio, networking and configuration file
        """ 
        log.info("Fetching SageMaker Studio configuration")
        self.config={}
        
        internal_metadata = "/opt/.sagemakerinternal/internal-metadata.json"
        resource_metadata = "/opt/ml/metadata/resource-metadata.json"
        
        internal_meta = ReadFromFile(internal_metadata)
        resource_meta = ReadFromFile(resource_metadata)
        
        self.config["UserProfile"] = resource_meta["UserProfileName"]
        self.config["DomainId"] = resource_meta["DomainId"]
        if internal_meta["AppNetworkAccessType"]=="VpcOnly":
            self.config["VPCOnly"] = True
        else:
            self.config["VPCOnly"] = False
        self.config["Region"] = os.environ.get("REGION_NAME")
        
        if not self.config["VPCOnly"]:
            log.error("SageMaker Studio Domain must be in \"VPCOnly mode\".")
        assert self.config["VPCOnly"], "SageMaker Studio Domain must be in \"VPCOnly mode\"."

        self.ReadReqConfig()
        self.ReadOptionalConfig()
        log.debug(f"Resource: {self.config}")
        

    def ReadReqConfig(self):
        """
        This function reads configuration from sagemaker:DescribeDomain, sagemaker:ListTags and EFS:DescribeMountTargets API calls
        """
        try:
            sm_client = boto3.client("sagemaker", region_name=self.config["Region"])
            domain_reponse = sm_client.describe_domain(DomainId=self.config["DomainId"])
            UserProfile_reponse = sm_client.describe_user_profile(
                DomainId=self.config["DomainId"],
                UserProfileName=self.config["UserProfile"]
            )
            self.config["SubnetIds"] = domain_reponse["SubnetIds"]
            self.config["VpcId"] = domain_reponse["VpcId"]
            self.config["EfsId"] = domain_reponse["HomeEfsFileSystemId"]
            self.config["UserUid"] = UserProfile_reponse["HomeEfsFileSystemUid"]
            if "UserSettings"  in UserProfile_reponse.keys() and "SecurityGroups" in UserProfile_reponse["UserSettings"].keys():
                self.config["SecurityGroups"] = UserProfile_reponse["UserSettings"]["SecurityGroups"] 
            else:
                self.config["SecurityGroups"] = domain_reponse["DefaultUserSettings"]["SecurityGroups"]
            if "UserSettings" in UserProfile_reponse.keys() and "ExecutionRole" in UserProfile_reponse["UserSettings"]:
                self.config["ExecutionRole"] = UserProfile_reponse["UserSettings"]["ExecutionRole"]
            else:
                self.config["ExecutionRole"] = domain_reponse["DefaultUserSettings"]["ExecutionRole"]
            self.config["UserProfileArn"] = UserProfile_reponse["UserProfileArn"]
            # TODO add pagination support
            Tags_reponse = sm_client.list_tags(ResourceArn=self.config["UserProfileArn"])
            self.config["Tags"] = Tags_reponse["Tags"]
            efs_client = boto3.client("efs", region_name=self.config["Region"])
            self.config["EFSClient"] = efs_client
            Efs_response = efs_client.describe_mount_targets(FileSystemId=self.config["EfsId"])
            self.config["EfsIpAddress"] = Efs_response["MountTargets"][0]["IpAddress"]
            self.config["NetworkInterfaceId"] = Efs_response["MountTargets"][0]["NetworkInterfaceId"]
            self.config["MountTargetId"] = Efs_response["MountTargets"][0]["MountTargetId"]
            Mount_target_response = efs_client.describe_mount_target_security_groups(
                MountTargetId=self.config["MountTargetId"]
            )
            self.config["MountTargetSecurityGroups"] = Mount_target_response["SecurityGroups"]
        except Exception as error:
            UnhandledError(error)


    def ReadOptionalConfig(self):
        """
        Read optional configuration from ~//.sagemaker_studio_docker_cli/sdocker.conf
        Properties:
            ImageId: AMI id used for Docker Host EC2 instance.
            Key: SSH key name.
            Port: port number used to connect to docker daemon, default is 1111.
            EBSVolumeSize: EBS volume size used, default is 400 GB.
            InstanceProfileArn: instance profile ARN.
            HostSGs: list of security group ids.
            DockerImageURI: docker image used for CPU instances.
            DockerImageNvidiaURI: docker image used for GPU instances.
        """

        home = get_home()
        config_file = f"{home}/.sagemaker_studio_docker_cli/sdocker.conf"

        try:
            config_data = ReadFromFile(config_file, report_err=False)
        except FileNotFoundError:
            config_data = {}

        try:
            ec2_client = boto3.client("ec2", region_name=self.config["Region"])
            if "ImageId" not in config_data.keys():
                Image_response = ec2_client.describe_images(
                    Owners=["amazon"],
                    Filters=[{
                        "Name": "name",
                        "Values": ["AWS Deep Learning Base AMI (Amazon Linux 2) Version *"]
                    }]
                )
                image_id = Image_response["Images"][0]["ImageId"]
            else:
                image_id = config_data["ImageId"]
            self.config["ImageId"] = image_id
            if "Key" in config_data.keys():
                self.config["Key"] = config_data["Key"]
            else:
                self.config["Key"] = None
            if "Port" in config_data.keys() and type(config_data["Port"]) == int:
                self.config["Port"] = config_data["Port"]
            else:
                self.config["Port"] = 1111
            if "EBSVolumeSize" in config_data.keys() and type(config_data["EBSVolumeSize"]) == int:
                self.config["EBSVolumeSize"] = config_data["EBSVolumeSize"]
            else:
                self.config["EBSVolumeSize"] = 400
            if "InstanceProfileArn" in config_data.keys():
                self.config["InstanceProfileArn"] = config_data["InstanceProfileArn"]
            else:
                self.config["InstanceProfileArn"] = None
            if "HostSGs" in config_data.keys() and (type(config_data["HostSGs"]) == list and len(config_data["HostSGs"]) > 0):
                self.config["HostSGs"] = config_data["HostSGs"]
            else:
                self.config["HostSGs"] = []
            if "DockerImageURI" in config_data.keys():
                self.config["DockerImageURI"] = config_data["DockerImageURI"]
            else:
                self.config["DockerImageURI"] = "docker:dind"
            if "DockerImageNvidiaURI" in config_data.keys():
                self.config["DockerImageNvidiaURI"] = config_data["DockerImageNvidiaURI"]
            else:
                self.config["DockerImageNvidiaURI"] = "brandsight/dind:nvidia-docker"
            if "AdditionalPorts" in config_data.keys():
                self.config["AdditionalPorts"] = config_data["AdditionalPorts"]
                if "8080" not in self.config["AdditionalPorts"]:
                    self.config["AdditionalPorts"].append("8080")
        except Exception as error:
            UnhandledError(error)
    

def UnhandledError(error):
    log.error(f"Unhandled Exception: {error}")
    log.exception()
    raise error
        
