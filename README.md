# SageMaker Studio Docker CLI extension - Docker integration for SageMaker Studio
Helper application to automate setting up `local mode` and `docker` for SageMaker Studio. You can also install [SageMaker Studio Docker UI extension](https://github.com/aws-samples/sagemaker-studio-docker-ui-extension) to get a UI interface that can interact with this extension seamlessly.

## How SageMaker Studio Docker CLI extension works
It provisions an EC2 instance that is used as a remote docker host to running docker daemon. `sdocker` does the following:
- Setup networking and security groups between the instance and SageMaker Studio Apps and EFS
  - For EFS, a security group called `EFSDockerHost` is created which only allows connections to port 2049 inbound and outbound
  - For EC2 instance, you can either supply your own security groups or it will be created for you with open outbound rules and inbounds allowing all ports from SageMaker Studio. The minimum required rules are:
    - **Inbound**: 
      - port 1111 (or DockerHostPort if not default), port 8080 and destination is SageMaker Studio secutiry group. Other ports might be required depending on container usage.
    - **OutBound**:
      - Port 80 to contact EC2 metadata on `169.254.169.254`
      - Port 443 to pull images from docker registeries.
- Provision EC2 instance
- Mount SageMaker Studio EFS on EC2 instance
- Run a `docker:dind` image as Host docker daemon and map port 1111 (or custom port) to allow access to docker daemon.
- Create docker context on the client to connect to docker host

## Prerequsites
- SageMaker Studio setup in `VPCOnly` mode (`PublicInternetOnly` mode is not supported.
- VPC has `DNS hostnames` and `DNS resolution` options enabled.
- Execution role for Studio with the below permissions:
  ```
  sagemaker:DescribeDomain
  sagemaker:DescribeUserProfile
  sagemaker:ListTags
  elasticfilesystem:DescribeMountTargets
  elasticfilesystem:DescribeMountTargetSecurityGroups
  elasticfilesystem:ModifyMountTargetSecurityGroups
  ec2:RunInstances
  ec2:TerminateInstances
  ec2:DescribeInstances
  ec2:DescribeInstanceTypes
  ec2:DescribeImages
  ec2:DescribeSecurityGroups
  ec2:DescribeNetworkInterfaces
  ec2:DescribeNetworkInterfaceAttribute
  ec2:ModifyNetworkInterfaceAttribute
  ec2:CreateSecurityGroup
  ec2:AuthorizeSecurityGroupIngress
  ec2:RevokeSecurityGroupEgress
  ec2:AuthorizeSecurityGroupEgress
  ec2:CreateTags
  ```
- Docker
- Docker compose (required for `local mode`)
- Python 3
- Boto3

## Setup
### Environment setup
You can use [this](https://github.com/aws-samples/sagemaker-studio-docker-cli-extension/blob/main/CloudFormationTemplate/studio-vpc-only-with-nat.yaml) CloudFormation Template to setup minimal environment.
### Manual Setup
Setup is staightforward, you clone this repo and then run `./setup.sh`:
```
$ git clone https://github.com/aws-samples/sagemaker-studio-docker-cli-extension.git
$ cd sagemaker-studio-docker-cli-extension
$ ./setup.sh
```
When running `setup.sh` from terminal of `KernalGateway`, make sure to activate your conda environment first.
`setup.sh` will do the following:
- Create `~/.sagemaker_studio_docker_cli` directory
- Create sample `~/.sagemaker_studio_docker_cli/pre-bootstrap.sh` and `~/.sagemaker_studio_docker_cli/post-bootstrap.sh` scripts
- Setup softlink for `sdocker` to make it possible to run it from anywhere from command line
- Install `docker` and `docker-compose` (requires `wget` to be installed on system)
- Create `~/temp` directory used in `local mode`
- Create `config.yaml` to change temporay directory to `~/temp`
- Install SageMaker Python SDK v2.80.0 or higher which introduces Remote Docker Host capability (see [PR 2864](https://github.com/aws/sagemaker-python-sdk/pull/2864)).
### Setup via Studio LifeCycle Configuration script
1- Create Studio LifeCycle script
```
#!/bin/bash

set -eux
STATUS=$(python3 -c "import sagemaker_dataprep";echo $?)
if [ "$STATUS" -eq 0 ]; then
  echo 'Instance is of Type Data Wrangler'
else
  echo 'Instance is not of Type Data Wrangler'
  cd ~
  if cd sagemaker-studio-docker-cli-extension 
  then
      git reset --hard
      git pull
  else
      git clone https://github.com/aws-samples/sagemaker-studio-docker-cli-extension.git
      cd sagemaker-studio-docker-cli-extension
  fi
  nohup ./setup.sh > docker_setup.out 2>&1 &
fi
```
2- Encode script content to `base64` encoding using below command:
```
$  LCC_CONTENT=`openssl base64 -A -in <LifeCycle script file>`
```
3- Create Studio LifeCycle config from environment variable `LCC_CONTENT`
```
$ aws sagemaker create-studio-lifecycle-config --studio-lifecycle-config-name sdocker --studio-lifecycle-config-content $LCC_CONTENT --studio-lifecycle-config-app-type KernelGateway
```
4- Update Studio domain to add LCC to default user settings (optional)
```
$ aws sagemaker update-domain --domain-id <domain-id> --default-user-settings '{"KernelGatewayAppSettings": {"DefaultResourceSpec": {"InstanceType": "<default instance type>", "LifecycleConfigArn": "arn:aws:sagemaker:<region>:<AWS account ID>:studio-lifecycle-config/sdocker"}}}'
```
5- Update user profile settings
```
$ aws sagemaker update-user-profile --domain-id <domain-id> --user-profile-name <user profile> --user-settings '{"KernelGatewayAppSettings": {"DefaultResourceSpec": {"InstanceType": "ml.t3.medium", "LifecycleConfigArn": "arn:aws:sagemaker:<region>:<AWS account ID>:studio-lifecycle-config/sdocker"}, "LifecycleConfigArns": ["arn:aws:sagemaker:<region>:<AWS account ID>:studio-lifecycle-config/sdocker"]}}'
```
6- Delete JupyterServer app and create a new one for the above to take effect
## Configuration
`sdocker` can be configured to do the following (all the below properties are optional):
- Choose a different *AMI*. Use `ImageId` property to supply required *AMI*.
- Include EC2 key pair. Use `Key` property to supply public ssh key.
- Use custom port to connect to *Docker Daemon* on host. Use `Port` property to supply custom port. By default, port value is 1111.
- Cuustomize root EBS volume size. Use `EBSVolumeSize` property to supply required EBS volume size.
- Supply instance profile to the *Docker Host* to be able to perform tasks like logging into ECR service. Use `InstanceProfileArn` property to supply instance profile ARN.
- Use custom security groups for *Docker Host*. Use `HostSGs` property to supply a list of security group ids that will be attached to the *Docker Host*. If an empty list is provided, CLI extension will automatically create one for you.
- Use custom docker images for CPU or GPU instances. By default, CLI extension uses `docker:dind` image for CPU and `brandsight/dind:nvidia-docker`. Use `DockerImageURI` and `DockerImageNvidiaURI` properties to supply CPU or GPU images respectively.

Configuration file location is  `~/.sagemaker_studio_docker_cli/sdocker.conf`.
Make sure your *AMI* has docker daemon installed and running by default. It is only tested on `Amazon linux 2` instances. We recommend using *AWS Deep Learning Base AMI (Amazon Linux 2).*. You can use below ASW CLI command to find latest AWS Deep learning AMI ID:

```
$ aws ec2 describe-images --region <region> --owners amazon --filters "Name=name,Values=AWS Deep Learning Base AMI (Amazon Linux 2) Version ????"
```
For more information on how to create an EC2 key pair check this [link](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html#having-ec2-create-your-key-pair)

An example of a valid configuration `~/.sagemaker_studio_docker_cli/sdocker.conf` file is shown below:
```
{
    "ImageId": "ami-052783664d99ae241",
    "Key": "docker-key",
    "Port": 1111,
    "EBSVolumeSize": 500,
    "InstanceProfileArn": "arn:aws:iam::012345678910:instance-profile/some-profile-name",
    "HostSGs": ["sg-00000001", "sg-00000002"],
    "DockerImageURI": "docker:dind",
    "DockerImageNvidiaURI": "brandsight/dind:nvidia-docker"
}
```

The `InstanceProfileArn` will be assigned to the EC2 Docker Host. This is useful in case you need to use [Systems Manager Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started.html). 
The `DockerImageURI` and `DockerImageNvidiaURI` fields is useful if you need to access these docker images from a private registry.

## Usage
```
$ sdocker [COMMANDS][OPTIONS]
```
Where `[COMMANDS]` can be:
* `create-host`: Create security groups `DockerHost` and `EFSDockerHost`, then provision EC2 Docker Host. Takes the below `[OPTIONS]`:
  * `--instance-type` <instance-type> *[REQUIRED]*
  * `--subnet-id` <subnet-id>
    
* `terminate-current-host`: Terminates current host, this will only work if creation was successful. Takes no `[OPTIONS]`

## Examples
Below example creates a docker host using `c5.xlarge` instance type:
```
$ sdocker create-host --instance-type c5.xlarge
```
Once the host is provisioned and `Healthy` it should show below message:
```
Successfully launched DockerHost on instance i-xxxxxxxxxxxxxxxxx with private DNS ip-xxx-xxx-xxx-xxx.ec2.internal
Waiting on docker host to be ready
Docker host is ready!
ip-xxx-xxx-xxx-xxx.ec2.internal
Successfully created context "ip-xxx-xxx-xxx-xxx.ec2.internal"
ip-xxx-xxx-xxx-xxx.ec2.internall
Current context is now "ip-xxx-xxx-xxx-xxx.ec2.internal"
```
Then you can use normal docker commands or use SageMaker Python SDK 'local mode'
Only when the Host was successfully created and turned `Healthy`, you can use below command to terminate the EC2 instance:
```
$ sdocker terminate-current-host
```
Otherwise, you will need to terminate the instance manually.
## Troubleshooting
- Consult `~/.sdocker/sdocker.log` for `sdocker` logs.
- To troubleshoot issues related to host instance (eg. `Unhealthy` host), check logs in `/home/sagemaker-user/.sagemaker_studio_docker_cli/<intance-type_instance-id>/dockerd-logs` folder.

## Notes
- `sdocker` does not terminate or stop EC2 instance after it created, always make sure you have terminated unused instances when you are done. You can use `terminate-current-host` command to terminate the current host.
- Networking is setup between *Docker Host*, *SageMaker Studio* and *EFS* using two *Security Groups* (listed below), it is recommended to deleted these when you create new *SageMaker Studio Domain* so `sdocker` can create new ones that are setup correctly:
  - `DockerHost` (You can optionally supply your own security groups if you supply a list of security group ids using `HostSGs` property)
  - `EFSDockerHost`
If you need to delete `EFSDockerHost` without deleting EFS or Studio domain, you can use the below AWS CLI to update mount target with new list of security groups:
```
$ aws efs modify-mount-target-security-groups --mount-target-id <mount target id> --security-groups <list of security groups>
```
Then you can go ahead and delete `EFSDockerHost`.
- Currenlty, `sdocker` is setup EC2 with `400GB` root EBS volume by default which will be mainly used to store docker images.
- Docker uses TLS to connect to Docker Host

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
