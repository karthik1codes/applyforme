# EC2 backend (Amazon Linux · `ec2-user`)

| File | Purpose |
|------|---------|
| `PUSH.md` | **Commands** — SSH as `ec2-user`, install, update, trigger |
| `setup.sh` | Detects Amazon Linux / `ec2-user`, installs + enables systemd |
| `launch-ec2.sh` | Launch AL2023 AMI via AWS CLI |
| `user-data.sh` | First-boot as `ec2-user` |
| `applyforme-*.service` | `User=ec2-user` |

Start: **[PUSH.md](./PUSH.md)**.
