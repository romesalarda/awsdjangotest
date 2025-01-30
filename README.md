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

ENSURE: before running, you add an .env file and update

docker-compose up -d --build

# to run other commands within docker

docker exec -to "container name" "cmd to execute"

## .env to contain the following

# Django Secret Key
SECRET_KEY=mysecretkey

# Debug Mode (Set to False in production)
DEBUG=True

# Allowed Hosts (Comma-separated)
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Configuration (PostgreSQL)
DB_ENGINE=django.db.backends.postgresql
DB_NAME=
DB_USER=postgres
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=
AWS_S3_REGION_NAME=