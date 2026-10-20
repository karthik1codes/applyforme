#!/usr/bin/env bash
# Launch Amazon Linux 2023 EC2 (login: ec2-user) for applyforme.
#
#   export AWS_REGION=ap-south-1
#   export KEY_NAME=my-keypair
#   export APPLYFORME_REPO_URL=https://github.com/YOU/applyforme.git
#   export ALLOCATE_EIP=1        # optional: stable public IP across stop/start
#   bash deploy/ec2/launch-ec2.sh
#
set -euo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
KEY_NAME="${KEY_NAME:?Set KEY_NAME to your EC2 key pair name}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"
VOLUME_GB="${VOLUME_GB:-30}"
REPO_URL="${APPLYFORME_REPO_URL:-https://github.com/YOUR_USER/applyforme.git}"
REPO_BRANCH="${APPLYFORME_REPO_BRANCH:-main}"
NAME_TAG="${NAME_TAG:-applyforme}"

# Amazon Linux 2023 (ec2-user)
AMI=$(aws ssm get-parameters \
  --region "$REGION" \
  --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameters[0].Value' --output text 2>/dev/null || true)
if [[ -z "$AMI" || "$AMI" == "None" ]]; then
  AMI=$(aws ec2 describe-images \
    --region "$REGION" \
    --owners amazon \
    --filters "Name=name,Values=al2023-ami-2023*-x86_64" "Name=state,Values=available" \
    --query 'sort_by(Images,&CreationDate)[-1].ImageId' \
    --output text)
fi
echo "AMI=$AMI  region=$REGION  type=$INSTANCE_TYPE  user=ec2-user"

MY_IP=$(curl -fsS https://checkip.amazonaws.com | tr -d '\n')/32 || MY_IP=0.0.0.0/0
SG_NAME="applyforme-sg"
SG_ID=$(aws ec2 describe-security-groups --region "$REGION" --filters "Name=group-name,Values=$SG_NAME" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)
if [[ -z "$SG_ID" || "$SG_ID" == "None" ]]; then
  VPC=$(aws ec2 describe-vpcs --region "$REGION" --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
  SG_ID=$(aws ec2 create-security-group --region "$REGION" --group-name "$SG_NAME" \
    --description "applyforme web (80/443) + SSH" --vpc-id "$VPC" --query GroupId --output text)
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" \
    --ip-permissions \
    "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$MY_IP,Description=SSH}]" \
    "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0,Description=HTTP}]" \
    "IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0,Description=HTTPS}]"
fi
echo "SecurityGroup=$SG_ID"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_DATA=$(mktemp)
{
  echo '#!/bin/bash'
  echo "export APPLYFORME_REPO_URL='$REPO_URL'"
  echo "export APPLYFORME_REPO_BRANCH='$REPO_BRANCH'"
  echo "export APPLYFORME_USER=ec2-user"
  tail -n +2 "$SCRIPT_DIR/user-data.sh"
} > "$USER_DATA"

IID=$(aws ec2 run-instances \
  --region "$REGION" \
  --image-id "$AMI" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"VolumeSize\":$VOLUME_GB,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
  --user-data "file://$USER_DATA" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME_TAG},{Key=app,Value=applyforme}]" \
  --query 'Instances[0].InstanceId' \
  --output text)
rm -f "$USER_DATA"

echo "Waiting for instance $IID …"
aws ec2 wait instance-running --region "$REGION" --instance-ids "$IID"
PUB=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$IID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

if [[ "${ALLOCATE_EIP:-0}" == "1" ]]; then
  ALLOC=$(aws ec2 allocate-address --region "$REGION" --domain vpc --query AllocationId --output text)
  aws ec2 associate-address --region "$REGION" --instance-id "$IID" --allocation-id "$ALLOC" >/dev/null
  PUB=$(aws ec2 describe-addresses --region "$REGION" --allocation-ids "$ALLOC" \
    --query 'Addresses[0].PublicIp' --output text)
  echo "Elastic IP: $PUB  (allocation $ALLOC)"
fi

cat <<EOF

=== EC2 launched (Amazon Linux · ec2-user) ===
Instance:  $IID
Public IP: $PUB
SSH:       ssh -i ~/.ssh/${KEY_NAME}.pem ec2-user@$PUB

Bootstrap ~5–10 min (sudo tail -f /var/log/applyforme-userdata.log).
Then:

  ssh -i ~/.ssh/${KEY_NAME}.pem ec2-user@$PUB
  sudo nano /opt/applyforme/.env
  sudo systemctl restart applyforme-worker applyforme-web
  curl -s http://127.0.0.1:8787/health

Do NOT open port 8787 in the security group.
EOF
