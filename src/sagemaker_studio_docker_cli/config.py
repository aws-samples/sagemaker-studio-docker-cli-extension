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
        home = get_home()
        internal_metadata = "/opt/.sagemakerinternal/internal-metadata.json"
        resource_metadata = "/opt/ml/metadata/resource-metadata.json"
        config_file = f"{home}/.sagemaker_studio_docker_cli/sdocker.conf"
        internal_meta = ReadFromFile(internal_metadata)
        resource_meta = ReadFromFile(resource_metadata)
        try:
            config_data = ReadFromFile(config_file, report_err=False)
        except FileNotFoundError:
            config_data = {}
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
        
        sm_client = boto3.client("sagemaker", region_name=self.config["Region"])
        try:
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
            if "EBSVolumeSize" in config_data.keys() and type(config_data["EBSVolumeSize"])==int:
                self.config["EBSVolumeSize"] = config_data["EBSVolumeSize"]
            else:
                self.config["EBSVolumeSize"] = 400
            if "InstanceProfileArn" in config_data.keys():
                self.config["InstanceProfileArn"] = config_data["InstanceProfileArn"]
            else:
                self.config["InstanceProfileArn"] = None
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
            if "DockerImageURI" in config_data.keys():
                self.config["DockerImageURI"] = config_data["DockerImageURI"]
            else:
                self.config["DockerImageURI"] = "docker:dind"
            if "DockerImageNvidiaURI" in config_data.keys():
                self.config["DockerImageNvidiaURI"] = config_data["DockerImageNvidiaURI"]
            else:
                self.config["DockerImageNvidiaURI"] = "brandsight/dind:nvidia-docker"
            log.debug(f"Resource: {self.config}")
        except Exception as error:
            UnhandledError(error)
    

def UnhandledError(error):
    log.error(f"Unhandled Exception: {error}")
    log.exception()
    raise error
        
