# awsdjangotest
simple testing repository that is dockerised to be used in an EC2 instance using amazon linux distro

## install docker compose and git

sudo yum install -y docker git

sudo systemctl start docker

sudo systemctl enable docker

sudo usermod -aG docker ec2-user

newgrp docker

## install docker compose

sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

docker-compose --version

git clone "my repo"

## run compose

# What to run before building

1. update .env file, update with credentials, allowed domains/IPs, SET DEBUG TO FALSE for EC2 

2. update docker-compose.yaml with updates to health check

for database test

test: ["CMD-SHELL", "pg_isready -U <my_postgres_user> -d <my_database_name>"] 

for web - endpoint to test

test: ["CMD", "curl", "http://web:8000"]

3. settings.py changes

if needed, update default security key, but .env should defined one anyway

4. update nginx.conf with s3 bucket

return 301 https://<your_s3_bucket>/static/;

## run to build 

docker-compose up -d --build

docker-compose down 

## to run other commands within docker

docker exec -to "container name" "cmd to execute"

to enter django shell (used for py manage.py)

docker exec -it django_app bash 

# Future notes and practices

CSRF not properly setup, SSL certificate not secured yet