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
ctrl-d to exit the bash shell once created

docker exec -it django_app bash 

docker logs "app name"
I.e. docker logs django_app

# Future notes and practices

CSRF not properly setup, SSL certificate not secured yet

# Reminders for myself

REMEMBER IMPORTANT:
Create a new Elastic IP, otherwise you have to go onto cloudflare, and change the content IP to the new public IP that
EC2 creates if you dont have an elastic IP.

ENSURE THAT IF NO CERTIFICATE IS IN USE, USE HTTP in the URL. 

# For setting up TLS/SSL (CLOUDFLARE FULL SSL)

refer to nginx, ensure SSL certificates are ready

mkdir -p ./nginx  # Ensure directory exists
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout ./nginx/cloudflare.key \
    -out ./nginx/cloudflare.crt \
    -subj "/CN=yourdomain.com"

chmod 644 ./nginx/cloudflare.crt
chmod 600 ./nginx/cloudflare.key

# For setting up TLS/SSL (CLOUDFLARE FULL STRICT SSL)

sudo pip3 install certbot certbot-nginx
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

It will ask a few questions and then populate /etc/letsencrypt/live/... with our certificates
ensure all resources point to there and that docker compose sees the mounted volume - what is a volume?

# nginx config
ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

# docker-compose
volumes:
    - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf
    - /etc/letsencrypt/live/rsalardadevelop.co.uk/fullchain.pem:/etc/letsencrypt/live/rsalardadevelop.co.uk/fullchain.pem:ro
    - /etc/letsencrypt/live/rsalardadevelop.co.uk/privkey.pem:/etc/letsencrypt/live/rsalardadevelop.co.uk/privkey.pem:ro

# Add a cron job for auto renewal
echo "0 0 * * * /usr/local/bin/certbot renew --quiet --post-hook 'systemctl reload nginx'" | sudo tee -a /etc/crontab

# CSRF

In manage.py add this

CSRF_TRUSTED_ORIGINS = [
    'https://yourdomain.com',
    'https://www.yourdomain.com',
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # For Cloudflare/Proxy
SECURE_SSL_REDIRECT = True  # Force HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# TODO:

add IAM to S3 bucket instead of access keys which if leaked is bad.