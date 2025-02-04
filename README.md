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

# ENSURE YOU CHECK AND UPDATE CONFIG WHERE NEEDED!

sudo vim .env
sudo vim docker-compose.yaml

1. update .env file, update with credentials,

ALLOWED_HOSTS = <your_ip>

DEBUG = FALSE # for EC2

DB_HOST to "db" instead of "localhost"

Update AWS credentials - create a new AWS secret in the dashboard if you don't have one.

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

# After all systems are healthy and running

docker exec django_app python manage.py collectstatic --noinput

docker exec django_app python manage.py makemigrations

docker exec django_app python manage.py migrate

docker exec -it django_app bash 

python manage.py createsuperuser

## to run commands within docker

docker exec -to "container name" "cmd to execute"

to enter django shell (used for py manage.py)

docker exec -it django_app bash 

# Future notes and practices

CSRF not properly setup, SSL certificate not secured yet