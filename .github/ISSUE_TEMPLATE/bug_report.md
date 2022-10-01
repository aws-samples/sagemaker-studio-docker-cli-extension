---
name: Bug report
about: Create a report to help us improve
title: "[BUG]"
labels: ''
assignees: awssamdwar

---

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Screenshots**
If applicable, add screenshots to help explain your problem.

**Logs**
Please provide the following logs:
- `/home/sagemaker-user/.sagemaker_studio_docker_cli/sdocker.log`
- Docker host EC2 system log, you can get this from AWS console or by running below command:
```
aws ec2 get-console-output --instance-id i-07436fc781ad50018 | sed 's/\\n/\
/g' | sed 's/\\r//' | grep "user-data:"
```
***NOTE:*** Make sure to maintain the newline character in the above command

**Additional context**
Add any other context about the problem here.
